"""The session loop's failure policy, out of the loop and under test.

This module exists because the reconnect policy had ZERO tests: every branch of
it needed a live Gemini session, so nothing could reach it from CI. Moving the
decisions into `core/session_policy.py` makes them data, and data can be argued
with — which is what most of this file does.

The bug this work was started for is in here as a test rather than a comment:
`test_a_transient_timeout_is_not_read_as_quota` fails against the ordering that
`main.py` used to have.
"""
from __future__ import annotations

import ast
from pathlib import Path

from core import session_policy as sp

ROOT = Path(__file__).resolve().parent.parent


def failure(**kwargs):
    return sp.Failure(**kwargs)


# ── the bug this module was written for ───────────────────────────────────

def test_a_transient_timeout_is_not_read_as_quota():
    """THE BUG.

    `main.py` checked quota before network, and its quota test was a substring
    match on the joined error text. A transient timeout during a model that is
    near its daily limit therefore read as "out of quota", stepped the model
    ladder down, and left the user on the last rung for the rest of the day —
    a network blip cost them their best model.

    `looks_like_quota` now refuses to match a bare timeout, and the verdict for
    one is a backoff, not a ladder step.
    """
    verdict = sp.decide(failure(message="TimeoutError: timed out", previous_backoff=3))

    assert verdict.kind == sp.BACKOFF
    assert verdict.step_model is False, "a timeout must not cost the user a model"


def test_a_real_quota_error_still_steps_the_ladder():
    verdict = sp.decide(failure(message="429 RESOURCE_EXHAUSTED: quota exceeded",
                                live_model="gemini-2.5-pro"))
    assert verdict.kind == sp.LADDER_STEP
    assert verdict.step_model is True


def test_the_callers_quota_answer_is_trusted_when_this_module_disagrees():
    """This module knows the COMMON shapes of a quota error, not the server's
    whole vocabulary. When `note_live_failure()` says "quota" about a message
    this module did not recognise, the caller's answer wins — ignoring a real
    quota error costs the user the session, not just one model."""
    verdict = sp.decide(failure(message="something novel from the API",
                                quota_laddered_by="models/gemini-2.5-flash"))
    assert verdict.kind == sp.LADDER_STEP
    assert "gemini-2.5-flash" in verdict.note


def test_when_every_model_is_rate_limited_it_waits_before_retrying():
    """The caller signals this with `quota_laddered_by` left empty: it asked for
    the next model and got the same one back."""
    verdict = sp.decide(failure(message="429 RESOURCE_EXHAUSTED"))
    assert verdict.kind == sp.LADDER_STEP
    assert verdict.delay == 15, "retrying instantly against a rate limit"
    assert "rate-limited" in verdict.note


def test_quota_and_network_do_not_claim_the_same_message():
    """Two predicates that both match is how the ordering became load-bearing.

    Every string in this list is a real failure text from this project; no
    message may be read as both an exhausted quota and a dead network, because
    the two need opposite responses (step down permanently / wait and retry).
    """
    samples = [
        "TimeoutError: timed out",
        "429 RESOURCE_EXHAUSTED",
        "quota exceeded",
        "getaddrinfo failed",
        "ConnectionRefusedError: [Errno 111]",
        "Cannot connect to host",
        "503 Service Unavailable",
        "API key not valid. Please pass a valid API key.",
    ]
    for message in samples:
        both = sp.looks_like_quota(message) and sp.looks_like_network(message)
        assert not both, f"{message!r} reads as quota AND network"


# ── each branch, and what it costs the user ───────────────────────────────

def test_a_voluntary_reconnect_does_not_back_off_or_alarm():
    """The user asked for it. Waiting three seconds to do what was asked, and
    printing a scary line about it, is the behaviour this replaces."""
    verdict = sp.decide(failure(is_reconnect=True))
    assert verdict.kind == sp.RECONNECT
    assert verdict.delay == 0
    assert verdict.note == ""


def test_a_voice_change_drops_the_conversation_on_purpose():
    """`keep_context=False` is how the voice change starts clean. It must
    survive the move: the flag is read off the signal, not guessed."""
    verdict = sp.decide(failure(is_reconnect=True, keep_context=False))
    assert verdict.keep_context is False


def test_an_invalid_key_asks_the_user_instead_of_retrying():
    verdict = sp.decide(failure(message="API key not valid. Please pass a valid API key."))
    assert verdict.kind == sp.NEEDS_KEY
    assert "re-enter" in verdict.note


def test_a_rejected_knob_drops_the_knob_not_the_connection_forever():
    verdict = sp.decide(failure(message="INVALID_ARGUMENT: Unknown name 'realtime_input'",
                                tuned=True))
    assert verdict.kind == sp.DROP_TUNING
    assert verdict.delay == 0, "the server is up and answering — reconnect now"


def test_proactive_audio_is_dropped_on_its_own_flag():
    verdict = sp.decide(failure(message="Unknown name 'proactivity'", proactive=True))
    assert verdict.kind == sp.DROP_PROACTIVE


def test_tuning_is_not_dropped_when_it_was_never_on():
    """Otherwise one unrelated INVALID_ARGUMENT turns live tuning off for a user
    who never had it on, and the setting flips under them."""
    verdict = sp.decide(failure(message="INVALID_ARGUMENT: Unknown name 'thinking'",
                                tuned=False, proactive=False))
    assert verdict.kind != sp.DROP_TUNING
    assert verdict.kind != sp.DROP_PROACTIVE


# ── backoff ───────────────────────────────────────────────────────────────

def test_backoff_doubles_from_the_first_rung():
    assert sp.backoff_after(0) == sp.FIRST_BACKOFF
    assert sp.backoff_after(3) == 6
    assert sp.backoff_after(6) == 12


def test_backoff_is_capped_because_a_long_wait_looks_like_a_quit():
    assert sp.backoff_after(sp.MAX_BACKOFF) == sp.MAX_BACKOFF
    assert sp.backoff_after(10_000) == sp.MAX_BACKOFF


def test_backoff_restarts_after_a_success():
    """A successful connection resets the counter; otherwise the next unrelated
    blip waits a minute because of one that happened an hour ago."""
    assert sp.backoff_after(-5) == sp.FIRST_BACKOFF


def test_a_network_failure_uses_the_backoff_it_was_given():
    verdict = sp.decide(failure(message="getaddrinfo failed", previous_backoff=6))
    assert verdict.kind == sp.BACKOFF
    assert verdict.delay == 12


def test_an_unrecognised_error_waits_briefly_and_keeps_the_model():
    """The old fallback was a fixed 3 seconds, and it must stay that way: an
    unknown error is not evidence of an exhausted quota."""
    verdict = sp.decide(failure(message="something nobody has seen before"))
    assert verdict.kind == sp.BACKOFF
    assert verdict.delay == sp.FIRST_BACKOFF
    assert verdict.step_model is False


# ── the caller's contract ─────────────────────────────────────────────────

def test_every_kind_is_one_the_loop_can_act_on():
    """A `Verdict` whose kind the caller does not know would be a reconnect
    that silently does nothing — so the set is closed and checked."""
    assert set(sp.KINDS) == {sp.RECONNECT, sp.LADDER_STEP, sp.DROP_TUNING,
                             sp.DROP_PROACTIVE, sp.NEEDS_KEY, sp.BACKOFF}
    for message, kwargs in (("429 quota", {}), ("timed out", {}),
                            ("API key not valid", {}), ("unknown", {})):
        assert sp.decide(failure(message=message, **kwargs)).kind in sp.KINDS


def test_every_verdict_can_explain_itself():
    for kind_message in ("429 quota", "timed out", "unknown thing", "API key not valid"):
        text = sp.describe(sp.decide(failure(message=kind_message)))
        assert text and text.strip()


def test_the_policy_has_no_friends_in_the_app():
    """It must stay pure: no UI, no network, no sleeping. A single import of
    `main`, `ui` or an audio library would make it untestable again and put it
    back where it came from."""
    tree = ast.parse((ROOT / "core" / "session_policy.py").read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            imported.add((node.module or "").split(".")[0])
    assert imported <= {"__future__", "dataclasses"}, imported


def test_the_policy_never_sleeps():
    """A delay is a NUMBER in the verdict. If this module ever learns to sleep,
    the decision and the waiting become one thing and nothing can test either."""
    tree = ast.parse((ROOT / "core" / "session_policy.py").read_text(encoding="utf-8"))
    banned = {n.attr for n in ast.walk(tree)
              if isinstance(n, ast.Attribute) and n.attr in ("sleep", "run", "wait")}
    assert banned == set(), banned


# ── the loop actually uses it ─────────────────────────────────────────────

def _run_body():
    """The `run()` method of `JarvisLive`, as an AST, without importing main.

    `import main` pulls in Google's Live SDK, sounddevice, numpy and Qt — none
    of which exist in CI, and none of which this test is about. Reading the
    function out of the source is the same trick `tests/test_ui_setup_wiring.py`
    uses on the overlay methods, for the same reason.
    """
    tree = ast.parse((ROOT / "main.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and node.name == "run":
            return node
    raise AssertionError("JarvisLive.run is not in main.py")


def test_the_reconnect_policy_is_decided_by_the_module_not_by_the_loop():
    """`main.py` must ASK, not decide.

    A copy of the policy inside the loop is the state this work started from:
    branches nothing could test, whose order was load-bearing and invisible.
    """
    body = ast.dump(_run_body())
    assert "_session_policy" in body, "run() no longer consults the policy module"
    assert "decide" in body, "run() does not call decide()"

    # The ladder's own answer is passed IN. Without it the module has to guess
    # with its narrower predicate, and a real quota error it does not recognise
    # would be treated as a transient network failure — the user waits forever
    # instead of stepping down.
    assert "note_live_failure" in body, (
        "the quota answer from the ladder is no longer passed in")
    assert "quota_laddered_by" in body, (
        "Failure() is built without the ladder's answer")


def test_the_loop_no_longer_carries_its_own_quota_message():
    """The two sentences the ladder used to print now come from the verdict,
    so there is one spelling of what happened to the model."""
    source = (ROOT / "main.py").read_text(encoding="utf-8")
    assert "Every live model is rate-limited" not in source
    assert "the previous model is out of quota" not in source


def test_connection_backoff_is_initialized_before_first_failure():
    """The first failed connection must not crash while deciding to retry."""
    import ast
    from pathlib import Path
    tree = ast.parse((Path(__file__).resolve().parent.parent / "main.py").read_text())
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "JarvisLive")
    init = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == "__init__")
    assert any(isinstance(n, ast.Assign) and isinstance(n.value, ast.Constant)
               and n.value.value == 0 and any(isinstance(t, ast.Attribute)
               and t.attr == "_conn_backoff" for t in n.targets) for n in ast.walk(init))
