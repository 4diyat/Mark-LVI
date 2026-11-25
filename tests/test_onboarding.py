"""Tests for the board 7 onboarding policy: `core/onboarding.py`.

The policy is pure — no Qt, no config file, no store — so every path of the
four-step flow is driven here: the ladder, each step's decision, skip vs. done,
restoration, progress, and the summary that must read the record honestly.
"""
import pytest

from core.onboarding import (DONE, MIC, PRESENCE, STEPS, WELCOME,
                             Onboarding, OnboardingError)


def test_the_ladder_is_four_steps_in_order():
    assert STEPS == (WELCOME, MIC, PRESENCE, DONE)
    assert len(STEPS) == 4


def test_start_begins_at_the_welcome_step():
    flow = Onboarding.start()
    assert flow.current == WELCOME
    assert flow.current_index == 0
    assert flow.total == 4
    assert not flow.is_complete
    assert flow.decided_count() == 0
    assert flow.progress() == (0, 4)


def test_welcome_is_navigation_and_completes_without_a_decision():
    flow = Onboarding.start().answer("anything")
    assert flow.is_done(WELCOME)
    assert flow.current == MIC
    assert flow.decided_count() == 1


def test_welcome_accepts_any_value():
    assert Onboarding.start().answer(None).is_done(WELCOME)
    assert Onboarding.start().answer(0).is_done(WELCOME)


def test_mic_allow_records_consent():
    # The welcome step is navigation, so answer it first; then allow the mic.
    flow = Onboarding.start()
    flow = flow.answer("next")        # welcome
    flow = flow.answer(True)          # allow the microphone
    assert flow.is_done(MIC)
    assert not flow.is_skipped(MIC)
    assert flow.current == PRESENCE


def test_mic_deny_skips_without_recording_consent():
    flow = Onboarding.start().answer("next")
    flow = flow.answer(False)         # deny / skip the microphone
    assert flow.is_skipped(MIC)
    assert not flow.is_done(MIC)
    assert flow.current == PRESENCE


def test_mic_rejects_a_non_bool_decision():
    flow = Onboarding.start().answer("next")
    with pytest.raises(OnboardingError):
        flow.answer("yes")
    with pytest.raises(OnboardingError):
        flow.answer(None)


def test_presence_records_the_mode_and_advances():
    flow = Onboarding.start().answer("next").answer(True)  # welcome + mic allow
    flow = flow.answer("focus")
    assert flow.is_done(PRESENCE)
    assert flow.presence_mode == "focus"
    assert flow.current == DONE


def test_presence_rejects_a_non_string_decision():
    flow = Onboarding.start().answer("next").answer(True)
    with pytest.raises(OnboardingError):
        flow.answer(123)


def test_done_completes_the_flow():
    flow = (Onboarding.start()
            .answer("next")
            .answer(True)
            .answer("active"))
    assert flow.current == DONE
    assert not flow.is_complete
    flow = flow.answer("finish")
    assert flow.is_complete
    assert flow.decided_count() == 4
    assert flow.progress() == (4, 4)


def test_every_decision_yields_a_new_object():
    base = Onboarding.start()
    after = base.answer("next")
    assert after is not base
    assert base.current == WELCOME          # the original is untouched
    assert after.current == MIC


def test_restore_recomputes_the_position_from_decisions():
    # Persisted as: welcome + mic done, presence skipped — the flow should
    # resume at the step that is still open, not trust a stored index.
    flow = Onboarding.restore(
        done={WELCOME, MIC},
        skipped={PRESENCE},
        presence=None,
    )
    assert flow.current == DONE
    assert flow.is_done(WELCOME)
    assert flow.is_done(MIC)
    assert flow.is_skipped(PRESENCE)


def test_restore_with_everything_decided_shows_the_summary():
    flow = Onboarding.restore(
        done={WELCOME, MIC, PRESENCE, DONE},
        skipped=set(),
        presence="quiet",
    )
    assert flow.is_complete
    assert flow.current == DONE


def test_restore_clamps_a_stale_index():
    # A stored index beyond the ladder cannot point outside it.
    flow = Onboarding.restore(done=set(), skipped=set(), current=99)
    assert flow.current == WELCOME


def test_summary_states_consent_and_mode_honestly():
    flow = (Onboarding.start()
            .answer("next")
            .answer(True)
            .answer("focus")
            .answer("finish"))
    lines = flow.summary_lines()
    assert any("Microphone: consented" in line for line in lines)
    assert any("Presence mode: focus" in line for line in lines)
    assert any("4 of 4 steps done" in line for line in lines)


def test_summary_names_a_skipped_step_as_skipped():
    flow = (Onboarding.start()
            .answer("next")
            .answer(False)      # skip the microphone
            .answer("active")
            .answer("finish"))
    lines = flow.summary_lines()
    assert any("Microphone: skipped" in line for line in lines)


def test_summary_reports_a_mode_never_chosen():
    # A flow where presence was skipped has no recorded mode.
    flow = Onboarding.restore(done={WELCOME, MIC, DONE}, skipped={PRESENCE})
    lines = flow.summary_lines()
    assert any("Presence mode: not chosen" in line for line in lines)


def test_summary_counts_a_not_asked_step():
    # A fresh flow restored with nothing decided still reports the microphone
    # as not asked, because the summary reads the record rather than the screen.
    flow = Onboarding.restore()
    lines = flow.summary_lines()
    assert any("Microphone: not asked" in line for line in lines)


def test_progress_counts_done_and_skipped():
    flow = (Onboarding.start()
            .answer("next")
            .answer(False))     # welcome done, mic skipped
    assert flow.progress() == (2, 4)
