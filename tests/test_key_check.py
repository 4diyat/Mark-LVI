"""What the setup screen decides, and what it must never decide.

WHY THIS IS TESTED WITHOUT QT
    The screen is 460×660 of widgets; the decisions are four sentences and one
    boolean. Testing the widget would need a display, and the display is the
    part that is least likely to be wrong.

THE FOUR CLAIMS
    1. A key is only saved when it was ACCEPTED or could not be TESTED — never
       when the service said no. A rejected key must not overwrite a good one.
    2. Untested is a saved key with a sentence, not a blocked setup: the owner's
       decision was that an offline machine still has to finish setting up.
    3. The setup screen is the only way in, so `mark_ready()` must be called on
       every path that closes it — and on none that leaves it open.
    4. A key is never written to a log, a file name or a sentence.
"""
from __future__ import annotations

import pytest

from core import key_check


class Probe:
    """A stand-in for the SDK's `models.get`."""

    def __init__(self, raises=None):
        self.raises = raises
        self.calls = []

    def get(self, model=None, config=None):
        self.calls.append((model, config))
        if self.raises is not None:
            raise self.raises
        return object()


def _builder(exc=None):
    probe = Probe(exc)

    def build(key):
        probe.key = key
        return type("Client", (), {"models": probe})()

    build.probe = probe
    return build


GOOD = "AIzaSyB" + "x" * 30


# ── the shape check, before any network ─────────────────────────────────────

def test_a_healthy_key_passes_the_shape_check():
    assert key_check.looks_like_a_key(GOOD) is True


@pytest.mark.parametrize("value", [
    "", "   ", None, "GEMINI_API_KEY", "short",
    '"AIzaSyBxxxxxxxxxxxxxxxxxxxxxxxxxxxx"',       # quotes from a JSON paste
    "AIzaSyBxxxxxxxxxxxxxxxxxxxxxxxxxxxx,",        # trailing comma from JSON
    "AIzaSyB xxxxxxxxxxxxxxxxxxxxxxxxxxxx",        # a space in the middle
    "AIzaSyBxxxxxxxxxxxxxxxxxxxxxxxxxxxx\n",       # handled by strip — still fine
])
def test_the_three_ways_a_paste_goes_wrong_are_caught(value):
    """Label, quotes, and a stray comma are what a password field actually
    receives. Saying which one is wrong is the difference between "fix it" and
    "paste it again and hope"."""
    expected = value is not None and value.strip().isprintable() and value.strip() == (
        "AIzaSyBxxxxxxxxxxxxxxxxxxxxxxxxxxxx") and value.endswith("\n")
    assert key_check.looks_like_a_key(value) is expected, value


def test_a_shape_failure_never_touches_the_network():
    built = []
    verdict = key_check.check("short", client=lambda key: built.append(key))
    assert verdict.rejected
    assert built == [], "a key that cannot be right was sent anyway"


# ── the three verdicts ──────────────────────────────────────────────────────

def test_an_accepted_key_says_ok_and_may_proceed():
    verdict = key_check.check(GOOD, client=_builder())
    assert verdict.ok and verdict.may_proceed
    assert verdict.detail == ""


def test_a_rejected_key_names_the_fix_and_may_NOT_proceed():
    build = _builder(Exception("400 API key not valid. Please pass a valid API key."))
    verdict = key_check.check(GOOD, client=build)
    assert verdict.rejected
    assert verdict.may_proceed is False, "a rejected key must not close setup"
    assert "rejected" in verdict.detail.lower()


def test_an_offline_machine_may_proceed_and_says_it_was_not_tested():
    """The owner's decision: a laptop without internet finishes setup."""
    build = _builder(OSError("Temporary failure in name resolution"))
    verdict = key_check.check(GOOD, client=build)
    assert verdict.untested
    assert verdict.may_proceed is True
    assert "not\ntested" in verdict.detail or "not" in verdict.detail.lower()


def test_a_timeout_is_untested_and_never_reported_as_a_bad_key():
    """The failure that would make an offline user retype a good key."""
    verdict = key_check.check(GOOD, client=_builder(TimeoutError("timed out")))
    assert verdict.untested, verdict
    assert not verdict.rejected


def test_a_retired_probe_model_does_not_block_setup():
    """The app's own stale constant is not the user's problem."""
    build = _builder(Exception("404 model not found"))
    build.probe.raises.code = 404 if hasattr(build.probe.raises, "code") else None
    verdict = key_check.check(GOOD, client=_builder(
        type("NotFound", (Exception,), {"code": 404})("model not found")))
    assert verdict.untested
    assert verdict.may_proceed is True


def test_a_missing_sdk_is_untested_not_rejected():
    verdict = key_check.check(GOOD, client=lambda key: (_ for _ in ()).throw(
        ImportError("google-genai is not installed")))
    assert verdict.untested and not verdict.rejected
    assert "ImportError" in verdict.detail


def test_no_sdk_failure_can_make_the_check_raise():
    """The caller is a screen on the Qt thread.

    `SystemExit` and `KeyboardInterrupt` are deliberately NOT in this list: they
    derive from `BaseException`, and swallowing them would mean a setup screen
    that refuses to die on Ctrl-C. The contract is "no ordinary failure
    escapes", not "the process cannot be stopped".
    """
    for exc in (ValueError(), RuntimeError(), OSError(), LookupError("x"),
                ArithmeticError(), EOFError()):
        verdict = key_check.check(GOOD, client=_builder(exc))
        assert verdict.kind in key_check.VERDICTS


def test_ctrl_c_is_not_swallowed():
    """A setup screen that catches Ctrl-C cannot be quit while it is stuck."""
    import pytest as _pytest

    with _pytest.raises(KeyboardInterrupt):
        key_check.check(GOOD, client=_builder(KeyboardInterrupt()))


# ── what the screen does with the verdict ───────────────────────────────────

def test_only_ok_and_untested_are_allowed_to_close_setup():
    """One place decides this, so the widget cannot disagree with the policy."""
    assert key_check.Verdict(key_check.OK).may_proceed is True
    assert key_check.Verdict(key_check.UNTESTED).may_proceed is True
    assert key_check.Verdict(key_check.REJECTED).may_proceed is False


def test_the_verdicts_are_exactly_three_and_named():
    assert key_check.VERDICTS == ("ok", "rejected", "untested")


def test_no_verdict_sentence_contains_the_key():
    """A sentence showing a typo'd key on screen is a key on a screenshot."""
    for exc in (Exception("400 API key not valid: " + GOOD), OSError(GOOD)):
        verdict = key_check.check(GOOD, client=_builder(exc))
        assert GOOD not in verdict.detail, verdict.detail


def test_an_unrecognised_failure_still_allows_setup():
    """The fallback matters more than the list: an error nobody anticipated
    must not be reported as "your key is wrong", because the user would retype
    a good key and the next attempt would fail the same way."""
    verdict = key_check.check(GOOD, client=_builder(ValueError("something new")))
    assert verdict.untested, verdict
    assert verdict.may_proceed is True
    assert "ValueError" in verdict.detail


def test_a_connection_error_with_no_recognisable_words_is_still_untested():
    """`OSError("")` — a type check would catch this and the word list would
    not, which is why the fallback is asserted rather than the list."""
    verdict = key_check.check(GOOD, client=_builder(OSError("")))
    assert verdict.untested and verdict.may_proceed is True
