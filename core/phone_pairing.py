"""Board 16 — phone pairing, as a pure policy.

The artboard draws a phone card, a pairing code, and a "Putuskan" pill, and
for a long time the page said there was no pairing backend. There IS one — the
dashboard server issues one-time keys and consumes them at `/login` — but its
logic lives inside `DashboardServer`, mixed with transport, throttling and
AES. That makes the pairing decision hard to test in isolation and easy to
regress: the rules that matter (one-time use, expiry, scope, handoff) deserve
to be a pure function of time and state.

WHAT THIS MODULE IS. A policy module in the same shape as `core/routines.py`
and `core/form_fill.py`: it generates pairing codes, validates and consumes
them, records paired devices with a scope, and decides whether a handoff
(continue the conversation on another device) is allowed. It takes an injectable
clock and does no I/O — no socket, no file, no thread — so every rule is
testable with a fake clock and plain assertions.

WHAT IT IS NOT. It is not the transport. `DashboardServer.new_key` mints the
raw key string and `/login` consumes it over HTTP; this module owns the
*decision* of what a valid pairing looks like, and a thin adapter
(`actions/phone_pair.py`) bridges the two. The character set and length here
MUST match the server's `_KEY_CHARS` / `_KEY_LENGTH` (both are pinned by
`tests/test_dashboard.py`), so a code this policy mints is one the server will
accept.
"""
from __future__ import annotations

import secrets
import time
from dataclasses import dataclass, field

# The pairing code alphabet: uppercase letters and digits, minus the four
# characters a person can confuse when reading a code off a screen (O/I/L/0/1).
# This MUST equal `dashboard.server._KEY_CHARS` — the login page and the server
# both hard-code the length, and a mismatch makes manual entry impossible.
PAIRING_CHARS = [c for c in "ABCDEFGHJKMNPQRSTUVWXYZ23456789"]

# Eight characters from a 31-symbol alphabet is ~40 bits: enough against
# online guessing at a rate-limited login endpoint, which is the threat model
# here. The server pins the same length.
PAIRING_CODE_LENGTH = 8

# How long a freshly minted code stays valid. Five minutes, matching the
# server's default `new_key(expiry_secs=600)`.
PAIRING_CODE_TTL = 600

# The two scopes a paired device can hold. "command" lets it send commands;
# "read" lets it watch the feed only. Enforced here so a policy-level decision
# never grants more than the caller asked for.
SCOPE_COMMAND = "command"
SCOPE_READ = "read"
_SCOPES = (SCOPE_COMMAND, SCOPE_READ)


@dataclass(frozen=True)
class PairingCode:
    """A one-time pairing code, with the instant it expires."""

    code: str
    expires_at: float

    def is_valid(self, now: float) -> bool:
        """A code is valid only while the clock is before its expiry."""
        return now < self.expires_at


@dataclass
class PairedDevice:
    """A device that has consumed a code and holds a scope."""

    name: str
    scope: str
    paired_at: float

    def allows(self, needed: str) -> bool:
        """Does this device's scope cover what `needed` asks for?

        "command" implies "read" (a device that can send commands can also see
        the feed); "read" does not imply "command". An unknown scope is refused.
        """
        if needed not in _SCOPES:
            return False
        if self.scope == SCOPE_COMMAND:
            return True
        return needed == SCOPE_READ and self.scope == SCOPE_READ


@dataclass
class PairingSession:
    """The mutable state of phone pairing, driven by an injectable clock.

    Holds the pending code (one at a time — a new mint replaces the old), the
    list of paired devices, and the handoff target. All decisions flow through
    the methods below; nothing here touches the network or the filesystem.
    """

    _now: object = field(default_factory=time.time)
    _code: PairingCode | None = None
    devices: list[PairedDevice] = field(default_factory=list)
    handoff_target: str | None = None

    def _clock(self) -> float:
        """The current time: a callable clock, or a fixed number for tests."""
        return self._now() if callable(self._now) else float(self._now)

    # -- minting ----------------------------------------------------------
    def mint_code(self, ttl: float = PAIRING_CODE_TTL) -> PairingCode:
        """Mint a fresh one-time code, replacing any pending one.

        The code is random from the pairing alphabet and expires `ttl` seconds
        from the clock. A second mint supersedes the first: only one code is
        ever live at a time, so an old code that lingers on a screen cannot be
        used after a new one has been shown.
        """
        code = "".join(secrets.choice(PAIRING_CHARS) for _ in range(PAIRING_CODE_LENGTH))
        self._code = PairingCode(code=code, expires_at=self._clock() + ttl)
        return self._code

    # -- consuming --------------------------------------------------------
    def consume_code(self, code: str, name: str, scope: str = SCOPE_COMMAND) -> PairedDevice:
        """Consume a code and pair `name` with `scope`.

        Raises :class:`PairingError` when the code is missing, expired, or
        already consumed (one-time use). A valid code is consumed exactly once:
        the second attempt, even with the same string, is refused. On success
        the device is recorded and becomes the handoff target.
        """
        if scope not in _SCOPES:
            raise PairingError(f"Unknown scope: {scope!r}")
        if self._code is None:
            raise PairingError("No pairing code is pending.")
        entered = (code or "").strip().upper()
        if entered != self._code.code:
            raise PairingError("Pairing code does not match.")
        if not self._code.is_valid(self._clock()):
            # Consume it anyway: an expired code must not be retried later.
            self._code = None
            raise PairingError("Pairing code has expired.")
        # One-time use: the code is gone whether or not the device is recorded.
        self._code = None
        device = PairedDevice(name=name, scope=scope, paired_at=self._clock())
        self.devices.append(device)
        self.handoff_target = name
        return device

    # -- inspection -------------------------------------------------------
    @property
    def pending_code(self) -> PairingCode | None:
        """The live code, or None when none is pending or it has expired."""
        if self._code is not None and self._code.is_valid(self._clock()):
            return self._code
        return None

    def paired_names(self) -> list[str]:
        """Names of all paired devices, oldest first."""
        return [d.name for d in self.devices]

    def find(self, name: str) -> PairedDevice | None:
        """The device with `name`, or None."""
        for device in self.devices:
            if device.name == name:
                return device
        return None

    # -- handoff ----------------------------------------------------------
    def handoff(self, target: str, needed: str = SCOPE_COMMAND) -> PairedDevice:
        """Decide whether `target` may take over the conversation.

        A handoff needs a paired device whose scope covers `needed`. The
        decision is a pure read of state: the actual transfer of memory and
        history is transport, done by the adapter, not here.
        """
        device = self.find(target)
        if device is None:
            raise PairingError(f"Device is not paired: {target!r}")
        if not device.allows(needed):
            raise PairingError(
                f"Device {target!r} lacks the {needed!r} scope for handoff.")
        self.handoff_target = target
        return device


class PairingError(ValueError):
    """Raised when a pairing or handoff operation is not allowed."""


__all__ = [
    "PAIRING_CHARS",
    "PAIRING_CODE_LENGTH",
    "PAIRING_CODE_TTL",
    "SCOPE_COMMAND",
    "SCOPE_READ",
    "PairedDevice",
    "PairingCode",
    "PairingError",
    "PairingSession",
]
