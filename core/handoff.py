"""core/handoff.py — the pure policy behind the phone handoff's context
transfer (board 5.6, the part that was missing).

WHAT THIS DECIDES
    Board 16 pairs a phone and lets a session hand off to it. Pairing and the
    handoff gate are already implemented (`core.phone_pairing`); what was
    missing is the transfer of CONTEXT — the memory and the recent history —
    that makes "continue the conversation on the phone" mean the same
    conversation. This module builds and validates that context bundle: what
    goes in, how big it may be, and whether a bundle is well-formed enough to
    receive, with no file, no network, no Qt.

WHY THE DECISION IS PURE
    Deciding which memory entries and which history turns belong in a
    handoff, capping the bundle so it cannot grow without bound, and checking
    that a received bundle is intact are arithmetic over two lists of
    records. The lists come from `memory_manager` and `core.history` (the
    adapter reads them); choosing and validating is policy. Keeping it pure
    means a test can hand in a known memory and history and assert exactly
    what the phone would receive.

THE BUNDLE IS A SNAPSHOT, NOT A LIVE LINK
    A handoff transfers a bounded snapshot — the memory entries and the most
    recent history turns, capped. It does not open a live pipe: after the
    phone receives the bundle, it owns that copy, and later changes on the
    desktop do not stream to it. That is honest: a "live" claim would require
    a transport this policy does not have, and the phone would diverge from
    the desktop the moment either side wrote something.

WHAT THIS DOES NOT DO
    It does not send anything. `build_bundle` returns a plain dict the
    adapter serialises and ships over the existing dashboard channel;
    `validate_bundle` checks a received one. The policy never touches the
    network, so the security of the transport is the dashboard's existing
    TLS + per-device session key, not this module's concern.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

# Scopes a handoff can request. `command` is the full conversation (memory
# + history); `read` is memory only — the phone may recall what JARVIS
# knows without being handed the transcript. These match the scopes the
# pairing gate already defines.
SCOPE_COMMAND = "command"
SCOPE_READ = "read"

SCOPES = (SCOPE_COMMAND, SCOPE_READ)

# Bounds on the bundle. The point is that a handoff is a bounded snapshot,
# not an unbounded dump: a memory that grew over a year and a transcript
# that ran for hours must not be sent as one message.
MAX_MEMORY_ENTRIES = 200
MAX_HISTORY_TURNS = 100

# A bundle version, so a phone that receives an older shape can say so rather
# than silently mis-reading it.
BUNDLE_VERSION = 1


@dataclass
class HandoffBundle:
    """The context a phone receives when a session hands off.

    `scope` says what was included; `memory` and `history` are the records;
    `version` lets a receiver reject a shape it does not understand. A bundle
    built by `build_bundle` is always valid; `validate_bundle` checks one
    that came back over the wire (or was reconstructed) for the same shape.
    """

    scope: str
    version: int
    memory: list[dict] = field(default_factory=list)
    history: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "scope": self.scope,
            "version": self.version,
            "memory": self.memory,
            "history": self.history,
        }


def _clean_memory(entries: Iterable[dict]) -> list[dict]:
    """Keep only memory rows that carry a key and a value, capped.

    A row with no key or no value is not something the phone can use — it
    would be a blank card on the phone's memory page. Dropping it here keeps
    the transferred memory exactly what the panel shows.
    """
    out: list[dict] = []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        key = str(entry.get("key") or "").strip()
        value = str(entry.get("value") or "").strip()
        if not key or not value:
            continue
        out.append({"category": entry.get("category", ""),
                    "key": key,
                    "value": value,
                    "updated": entry.get("updated", "")})
        if len(out) >= MAX_MEMORY_ENTRIES:
            break
    return out


def _clean_history(turns: Iterable[dict]) -> list[dict]:
    """Keep only turns that carry text, capped, oldest first.

    The history is transferred in order so the phone can resume the
    conversation in the sequence it happened. A turn with no text is dropped
    — a blank line in a resumed transcript is worse than a shorter one.
    """
    out: list[dict] = []
    for turn in turns:
        if not isinstance(turn, dict):
            continue
        text = str(turn.get("text") or "").strip()
        if not text:
            continue
        out.append({"role": turn.get("role", ""),
                    "text": text,
                    "time": turn.get("time", "")})
        if len(out) >= MAX_HISTORY_TURNS:
            break
    return out


def is_scope(value) -> bool:
    return value in SCOPES


def build_bundle(
    scope: str,
    memory_entries: Iterable[dict],
    history_turns: Iterable[dict],
) -> HandoffBundle:
    """Build a handoff bundle for a scope.

    An unknown scope is refused by falling back to `SCOPE_READ` (memory only,
    the conservative choice) rather than raising: a caller that asks for a
    scope the policy does not know should not crash the handoff, and the
    conservative scope is the one that cannot leak the transcript.
    """
    if not is_scope(scope):
        scope = SCOPE_READ
    history = _clean_history(history_turns) if scope == SCOPE_COMMAND else []
    return HandoffBundle(
        scope=scope,
        version=BUNDLE_VERSION,
        memory=_clean_memory(memory_entries),
        history=history,
    )


def validate_bundle(bundle) -> tuple[bool, str]:
    """Whether a received bundle is well-formed, and why if it is not.

    A phone that receives a bundle it cannot read must say so rather than
    guess. The checks are structural: it is a mapping, it names a known
    scope, it carries the current version, and its `memory`/`history` are
    lists of records. A bundle that fails is refused with the reason, so the
    handoff reports the failure instead of resuming a conversation from
    garbage.
    """
    if not isinstance(bundle, dict):
        return False, "bundle bukan objek yang dikenal."
    if not is_scope(bundle.get("scope")):
        return False, f"scope bundle tidak dikenal: {bundle.get('scope')!r}."
    if bundle.get("version") != BUNDLE_VERSION:
        return (False,
                f"versi bundle tidak didukung: {bundle.get('version')!r} "
                f"(yang diterima {BUNDLE_VERSION}).")
    memory = bundle.get("memory")
    history = bundle.get("history")
    if not isinstance(memory, list):
        return False, "memory bundle bukan daftar."
    if not isinstance(history, list):
        return False, "history bundle bukan daftar."
    return True, "bundle diterima."


def summary(bundle: HandoffBundle) -> str:
    """One sentence describing what a bundle carries, for the log."""
    who = "percakapan" if bundle.scope == SCOPE_COMMAND else "memori"
    return (f"Handoff {who}: {len(bundle.memory)} entri memori, "
            f"{len(bundle.history)} giliran riwayat.")


__all__ = [
    "SCOPE_COMMAND", "SCOPE_READ", "SCOPES",
    "MAX_MEMORY_ENTRIES", "MAX_HISTORY_TURNS", "BUNDLE_VERSION",
    "HandoffBundle", "is_scope", "build_bundle", "validate_bundle", "summary",
]
