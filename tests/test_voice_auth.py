"""The voice-verification policy, and the defaults that must never soften.

These tests pin the decision logic in `core/voice_auth.py` — the part that
decides pass / fail / lockout — without any audio, Qt, microphone or network.
They follow the same shape as `tests/test_risk_policy.py`: the policy is pure,
so it is tested directly.
"""
from __future__ import annotations

from core.voice_auth import (
    LOCKOUT_SECONDS,
    MAX_ATTEMPTS,
    decide,
    is_locked,
    next_attempt,
    should_verify,
    timeout_state,
)


def test_score_at_threshold_passes():
    d = decide(0.6, 0.55, attempts=0, locked_until=0.0, now=10.0)
    assert d.passed is True
    assert d.locked is False
    assert d.reason


def test_score_below_threshold_fails_with_a_reason():
    d = decide(0.3, 0.55, attempts=0, locked_until=0.0, now=10.0)
    assert d.passed is False
    assert d.locked is False
    assert "does not match" in d.reason


def test_lockout_is_checked_before_the_score():
    """A locked gate rejects even a perfect score: a recording replayed during
    the lockout window must not shorten the window."""
    d = decide(1.0, 0.55, attempts=MAX_ATTEMPTS,
               locked_until=10.0 + LOCKOUT_SECONDS, now=10.0)
    assert d.passed is False
    assert d.locked is True
    assert "locked" in d.reason


def test_failed_attempts_increment_and_clamp():
    assert next_attempt(0) == 1
    assert next_attempt(1) == 2
    assert next_attempt(2) == 3
    assert next_attempt(99) == MAX_ATTEMPTS      # clamped, not overflowed


def test_lockout_expires():
    assert is_locked(10.0 + LOCKOUT_SECONDS, 10.0) is True
    assert is_locked(10.0 + LOCKOUT_SECONDS, 10.0 + LOCKOUT_SECONDS + 0.1) is False


def test_should_verify_states():
    assert should_verify("locked") is True
    assert should_verify("verifying") is True
    assert should_verify("verified") is False


def test_timeout_returns_to_locked_when_stale():
    # A verification fresh at t=100 is still valid a second later.
    assert timeout_state(101.0, 100.0, 600.0) == "verified"
    # Past the window, it is stale: the next voice re-verifies.
    assert timeout_state(100.0 + 600.0 + 1, 100.0, 600.0) == "locked"


def test_timeout_without_a_verification_is_locked():
    assert timeout_state(50.0, None, 600.0) == "locked"
