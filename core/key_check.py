"""Whether an API key works, and what to tell the user when it does not.

WHY THIS IS A MODULE OF ITS OWN
    Three different failures look identical to somebody who just pasted a key:
    the key is wrong, the network is down, and the key format is obviously not a
    key. Each one has a different sentence and a different next step — *fix the
    key*, *try again when you are online*, *paste the whole thing* — and a
    string-matching branch inside a Qt dialog is the kind of code nobody can
    test. This module decides; the screen only draws.

THE THREE VERDICTS
    OK        the key reached the service and the service answered
    REJECTED  the service answered, and the answer was "that key is not valid"
    UNTESTED  the check could not be completed: no network, no SDK, a timeout

    UNTESTED is not a failure. The owner's decision on 2026-11-22 was that an
    offline machine must still be able to finish setup: the key is saved with a
    sentence saying it was not tested, and `core/session_policy` already owns
    what happens when a bad key reaches a real session (`NEEDS_KEY`).

THE CHECK ITSELF
    `models.get` on a known model, not a generation: it costs no tokens, it
    answers in one round trip, and an invalid key fails it with the same
    `API key not valid` the session would fail with. A generation would work
    too and is deliberately not used — the user is at a setup screen, and
    charging them a request to prove their key is a strange way to say hello.

NEVER RAISES
    The caller is a screen, possibly on the Qt thread. Every path returns a
    `Verdict`, and the SDK is imported inside the function so this module costs
    nothing on an install that never runs setup.
"""
from __future__ import annotations

from dataclasses import dataclass

OK = "ok"
REJECTED = "rejected"
UNTESTED = "untested"
VERDICTS = (OK, REJECTED, UNTESTED)

# One model, named: `models.get` needs something to look up, and the setup screen
# has no session to borrow a choice from. If Google retires this name the check
# degrades to UNTESTED (a 404 is not an invalid key) rather than blocking setup.
PROBE_MODEL = "gemini-2.0-flash"

# Long enough for a slow connection to answer, short enough that a machine with
# no route at all does not leave the user looking at a spinner.
TIMEOUT_S = 8.0


@dataclass(frozen=True)
class Verdict:
    """What the check decided, and the sentence the screen should show."""

    kind: str
    detail: str = ""

    @property
    def ok(self) -> bool:
        return self.kind == OK

    @property
    def rejected(self) -> bool:
        return self.kind == REJECTED

    @property
    def untested(self) -> bool:
        return self.kind == UNTESTED

    @property
    def may_proceed(self) -> bool:
        """Whether setup may continue with this key.

        A key that was never tested may NOT be treated as fine on the spot —
        but it may be saved, which is the owner's decision: a laptop without
        internet still has to be able to finish setting itself up. So "may
        proceed" is true for OK and UNTESTED, and the screen shows the sentence
        for each.
        """
        return self.kind in (OK, UNTESTED)


def looks_like_a_key(key: str) -> bool:
    """A cheap shape check, run BEFORE any network call.

    Not a security measure — it is an ergonomics one. Pasting an API key into a
    password field very often goes wrong in three ways: the field keeps the
    label ("GEMINI_API_KEY"), the paste includes quotes and a trailing comma
    from a JSON file, or the line picked up a newline. All three are caught
    here, with a sentence that says which.
    """
    text = (key or "").strip()
    if not text:
        return False
    if len(text) < 20:
        return False
    if any(ch.isspace() for ch in text):
        return False
    if text.startswith(("\"", "'")) or text.endswith(("\"", "'", ",", ";")):
        return False
    return True


def check(key: str, timeout_s: float = TIMEOUT_S, client=None) -> Verdict:
    """Test one key against the service. Returns, never raises.

    `client` is injected for tests: a callable taking a key and returning a
    client-like object with `.models.get(model=...)`. The real one builds a
    `genai.Client`, which — verified here — does not touch the network on
    construction, so an offline machine fails at the CALL and is reported as
    UNTESTED rather than at the import.
    """
    text = (key or "").strip()
    if not looks_like_a_key(text):
        return Verdict(REJECTED, "That does not look like a complete key — "
                                 "paste the whole value, with no quotes.")
    builder = client or _real_client
    try:
        probe = builder(text)
    except Exception as exc:                        # noqa: BLE001
        # No SDK installed, or it refused to build. Not the user's key.
        return Verdict(UNTESTED, f"Could not check the key here — "
                                 f"{type(exc).__name__}: {exc}")
    try:
        probe.models.get(model=PROBE_MODEL, config={"timeout": timeout_s})
    except Exception as exc:                        # noqa: BLE001
        return _classify(exc)
    return Verdict(OK, "")


def _classify(exc: Exception) -> Verdict:
    """One exception → one verdict, using the text the SDK actually emits.

    THE ORDER MATTERS. An invalid key arrives as a 400 whose message contains
    both "invalid" and the key text; a network failure arrives as an OSError
    subclass with no HTTP status at all. Asking "is it an auth error" first
    keeps a timeout from being reported as a bad key — the failure mode that
    would make an offline user retype a perfectly good key.
    """
    text = f"{type(exc).__name__}: {exc}".lower()
    status = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    if status in (401, 403) or "api key not valid" in text or "api_key_invalid" in text:
        return Verdict(REJECTED, "The service rejected that key. Check it was "
                                 "copied in full and not already revoked.")
    if status == 404:
        # The probe model was retired, not the key. Do not block setup on the
        # app's own stale constant.
        return Verdict(UNTESTED, "The test model is no longer available, so the "
                                 "key could not be checked. It has been saved.")
    # NO `isinstance(exc, OSError)` HERE, and that is deliberate. It was tried:
    # every branch it could catch has a message this list already matches, so
    # the type check was unreachable code that no test could distinguish from
    # the list — which is the same thing as not having it. If a future SDK
    # raises a bare `OSError("")`, the fallback below says UNTESTED anyway,
    # which is the right answer for a failure nobody recognised.
    if any(word in text for word in (
            "timeout", "timed out", "connection", "network", "unreachable",
            "getaddrinfo", "ssl", "handshake", "temporary failure",
            "no route", "offline", "dns")):
        return Verdict(UNTESTED, "No network right now, so the key was not "
                                 "tested. It has been saved; if it is wrong, "
                                 "you will be asked again on the first session.")
    return Verdict(UNTESTED, f"Could not check the key — {_redact(exc)}")


def _redact(exc: Exception, limit: int = 120) -> str:
    """The exception's type, and its message with anything key-shaped removed.

    WHY THIS IS NOT PARANOIA
        The Google SDK puts the key in its own error text — a rejected key
        arrives as `400 API key not valid: <the key>`. That sentence was being
        copied into the verdict, the verdict goes on screen, and a screen is a
        screenshot. `tests/test_key_check.py` caught it: it asserts that no
        verdict sentence contains the key it was given.

    A KEY IS `AIza` FOLLOWED BY 30-PLUS BASE64-ISH CHARACTERS, which is the shape
    every Gemini key has had since the first one. Anything else is left alone:
    over-redacting a message the user needs to read is its own failure.
    """
    import re

    text = str(exc) or ""
    text = re.sub(r"AIza[0-9A-Za-z_\-]{30,}", "[key]", text)
    text = " ".join(text.split())
    if len(text) > limit:
        text = text[:limit].rstrip() + "…"
    return f"{type(exc).__name__}: {text}" if text else type(exc).__name__


def _real_client(key: str):
    from google import genai

    return genai.Client(api_key=key, http_options={"api_version": "v1beta"})


__all__ = ["OK", "PROBE_MODEL", "REJECTED", "TIMEOUT_S", "UNTESTED", "VERDICTS",
           "Verdict", "check", "looks_like_a_key"]
