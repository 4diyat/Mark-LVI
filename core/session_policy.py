"""What the session loop does when a connection dies — as data, not as `if`s.

WHY THIS EXISTS
    `main.py::JarvisLive.run` is 299 lines, and the last ~140 of them are one
    `except` block holding six decisions stacked in `if`s. That shape has two
    costs, and both have already been paid in this repository:

      1. NOBODY CAN TEST IT. Every branch needs a live Gemini session to reach,
         so the reconnect policy — the code that decides whether the assistant
         comes back at all — has zero tests.
      2. ORDER IS INVISIBLE. The guards are not independent: an out-of-quota
         error says "quota", a network error says "timeout", and a server that
         is simply unreachable answers with a message that looks like both. The
         current order puts quota first, which means a transient network failure
         during a quota-checked model can be read as "out of quota", burn the
         model ladder, and land on the last rung for the rest of the day.

    So the decisions move here, as a LIST of rules with predicates, and this
    module has no imports from the app at all: it takes a failure description
    and returns a verdict. `main.py` keeps the part that talks to the world.

WHAT THIS MODULE DOES NOT DO
    It does not sleep, log, reconnect, prompt for an API key or touch the UI. It
    returns a `Verdict`: what to call it, how long to wait, whether to step down
    the model ladder, and what to tell the user. The caller does those things,
    and a test can read the decision without any of them happening.
"""
from __future__ import annotations

from dataclasses import dataclass

# ── verdict kinds ─────────────────────────────────────────────────────────
#
# Kinds rather than free strings: the caller switches on these, and a typo in a
# string would mean a reconnect that silently does nothing.
RECONNECT = "reconnect"          # voluntary (a voice change); no backoff, no alarm
LADDER_STEP = "ladder_step"      # this model is out of quota; try the next one
DROP_TUNING = "drop_tuning"      # the server rejected our turn-taking knobs
DROP_PROACTIVE = "drop_proactive"  # the server rejected proactive audio
NEEDS_KEY = "needs_key"          # the key is invalid; ask for a new one
BACKOFF = "backoff"              # transient; wait, then try again

KINDS = (RECONNECT, LADDER_STEP, DROP_TUNING, DROP_PROACTIVE, NEEDS_KEY, BACKOFF)

# ── the backoff ladder ────────────────────────────────────────────────────
FIRST_BACKOFF = 3
MAX_BACKOFF = 60


@dataclass(frozen=True)
class Failure:
    """Everything the policy is allowed to look at. Nothing here sleeps.

    `quota_laddered_by` is what the session loop's `note_live_failure()` said:
    whether it treated this message as a quota event, AND whether stepping down
    actually changed the model. Two flags rather than one because the caller
    already knows both and the difference decides whether the user is told
    "switching to X" or "every model is rate-limited".
    """

    message: str = ""                 # `_exception_details(...)`, already joined
    is_reconnect: bool = False        # a _ReconnectSignal was raised
    keep_context: bool = True         # ...and it asked to keep the conversation
    tuned: bool = False               # live tuning is currently ON
    proactive: bool = False           # proactive audio is currently ON
    live_model: str = ""              # the model this attempt used
    previous_backoff: int = 0
    quota_laddered_by: str = ""       # the model now in force, when it CHANGED
                                      # ("" = unchanged, or not a quota event)


@dataclass(frozen=True)
class Verdict:
    """What to do about one failure."""

    kind: str
    delay: int = 0                    # seconds to wait before the next attempt
    keep_context: bool = True         # False = start the next session clean
    step_model: bool = False          # ask the ladder for the next model
    note: str = ""                    # the SYS: line, or "" when the user need
                                      # not be told anything

    @property
    def must_sleep(self) -> bool:
        return self.delay > 0


def _has(message: str, *needles: str) -> bool:
    text = (message or "").lower()
    return any(n.lower() in text for n in needles)


# ── the predicates, named so the order below can be argued about ──────────

def looks_like_quota(message: str) -> bool:
    """Out of quota, or this model is not available to this key.

    Deliberately NOT including bare "timeout"/"oserror": the quota branch steps
    the model ladder down PERMANENTLY, so treating a transient network error as
    a quota event costs the user the best model for the rest of the day.
    """
    return _has(message,
                "429", "resource_exhausted", "resource exhausted", "quota",
                "rate limit", "rate-limit", "exceeded your current quota")


def looks_like_network(message: str) -> bool:
    return _has(message,
                "timeouterror", "timed out", "getaddrinfo", "cancellederror",
                "connectionrefusederror", "connectionreseterror", "connectionabortederror",
                "oserror", "cannot connect",
                "connection reset", "connection aborted", "network is unreachable",
                "temporary failure in name resolution", "ssl", "handshake")


def looks_like_rejected_tuning(message: str) -> bool:
    return _has(message,
                "invalid_argument", "unknown name", "unexpected keyword",
                "realtime_input", "media_resolution", "thinking")


def looks_like_rejected_proactive(message: str) -> bool:
    return _has(message,
                "invalid_argument", "proactiv", "unknown name",
                "unexpected keyword")


def looks_like_invalid_key(message: str) -> bool:
    text = (message or "").lower()
    return "api key not valid" in text or "api_key_invalid" in text


# ── the decision ──────────────────────────────────────────────────────────

def decide(failure: Failure) -> Verdict:
    """One failure in, one verdict out.

    THE ORDER IS THE DESIGN, and each step is here because moving it breaks
    something specific:

      1. A voluntary reconnect is not a failure. It must not back off (the user
         asked for it), must not alarm anybody, and must not touch the ladder.
      2. A rejected API key is checked BEFORE quota and before the knobs: an
         invalid key produces messages that also mention the model, and the
         only useful response is to ask the user. Retrying it hammers the API.
      3. Quota steps the ladder. It is checked before network because a real
         quota error sometimes arrives wrapped in a retryable-looking message —
         but `looks_like_quota` refuses to match bare timeouts, so this can no
         longer swallow a transient network failure.
      4. Rejected knobs, then rejected proactive audio: cheapest things first,
         and both reconnect IMMEDIATELY because the server is up and answering.
      5. Network last, because it is the one branch that waits.
    """
    message = failure.message or ""

    if failure.is_reconnect:
        return Verdict(kind=RECONNECT, delay=0, keep_context=failure.keep_context)

    if looks_like_invalid_key(message):
        return Verdict(
            kind=NEEDS_KEY, delay=FIRST_BACKOFF,
            note="ERR: API key invalid — please re-enter your key.")

    if looks_like_quota(message) or failure.quota_laddered_by:
        # The caller's own `note_live_failure()` agreed this was a quota event.
        # Its answer is trusted when this module's narrower predicate did not
        # match — the module knows the common shapes, not the server's whole
        # vocabulary, and ignoring a real quota error costs the user the
        # session rather than one model.
        if failure.quota_laddered_by:
            return Verdict(
                kind=LADDER_STEP, delay=0, step_model=True,
                note=f"SYS: switching to {failure.quota_laddered_by.split('/')[-1]}"
                     " — the previous model is out of quota.")
        # Every live model is rate-limited: wait, then retry the same one.
        return Verdict(kind=LADDER_STEP, delay=15, step_model=True,
                       note="SYS: every live model is rate-limited — retrying.")

    if failure.tuned and looks_like_rejected_tuning(message):
        return Verdict(kind=DROP_TUNING, delay=0,
                       note="SYS: live tuning was rejected — reconnecting without it.")

    if failure.proactive and looks_like_rejected_proactive(message):
        return Verdict(kind=DROP_PROACTIVE, delay=0,
                       note="SYS: proactive audio unavailable — reconnecting "
                            "without it.")

    if looks_like_network(message):
        return Verdict(kind=BACKOFF, delay=backoff_after(failure.previous_backoff),
                       note="NET: connection failed — see the delay below.")

    # Anything unrecognised keeps the old behaviour: a short, fixed wait. It is
    # not treated as a quota event, because one unknown error should never cost
    # the user their model for the day.
    return Verdict(kind=BACKOFF, delay=FIRST_BACKOFF)


def backoff_after(previous: int) -> int:
    """Double, capped. `previous <= 0` restarts at the first rung.

    Capped because a session that waits ten minutes looks like an application
    that has quit, and the user cannot tell the difference from the outside.
    """
    previous = max(0, int(previous or 0))
    if previous <= 0:
        return FIRST_BACKOFF
    return min(previous * 2, MAX_BACKOFF)


def describe(verdict: Verdict) -> str:
    """One line for the log — the verdict in words a user could act on."""
    if verdict.kind == RECONNECT:
        return ("reconnecting now (you asked for it)"
                if verdict.keep_context else
                "starting a fresh session (you asked for it)")
    if verdict.kind == LADDER_STEP:
        return "stepping down the model ladder"
    if verdict.kind == DROP_TUNING:
        return "dropping live tuning and reconnecting"
    if verdict.kind == DROP_PROACTIVE:
        return "dropping proactive audio and reconnecting"
    if verdict.kind == NEEDS_KEY:
        return "waiting for a new API key"
    return f"retrying in {verdict.delay}s"


__all__ = ["BACKOFF", "DROP_PROACTIVE", "DROP_TUNING", "Failure", "FIRST_BACKOFF",
           "KINDS", "LADDER_STEP", "MAX_BACKOFF", "NEEDS_KEY", "RECONNECT",
           "Verdict", "backoff_after", "decide", "describe", "looks_like_invalid_key",
           "looks_like_network", "looks_like_quota", "looks_like_rejected_proactive",
           "looks_like_rejected_tuning"]
