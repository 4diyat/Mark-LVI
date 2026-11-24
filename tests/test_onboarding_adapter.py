"""Tests for the board 7 onboarding adapter: `actions/onboarding.py`.

The adapter is the only place the pure policy touches a store. The stores are
mocked: `pages_people.record_consent` and `presence_mode.set_mode` are patched
at their real module so the adapter's import path is exercised, while no real
config file or mode state is written.
"""
from core.onboarding import MIC, PRESENCE, WELCOME, Onboarding

from actions.onboarding import answer_step, run_onboarding


def test_welcome_advances_without_touching_a_store(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("a navigation step must not touch a store")
    monkeypatch.setattr("ui.pages_people.record_consent", boom)
    monkeypatch.setattr("core.presence_mode.set_mode", boom)
    flow, ok = answer_step(Onboarding.start(), "next")
    assert ok
    assert flow.current == MIC


def test_mic_allow_writes_consent_true(monkeypatch):
    calls = []
    monkeypatch.setattr("ui.pages_people.record_consent",
                        lambda allowed: calls.append(allowed) or True)
    flow = Onboarding.start().answer("next")
    new_flow, ok = answer_step(flow, True)
    assert ok
    assert calls == [True]
    assert new_flow.is_done(MIC)
    assert new_flow.current == PRESENCE


def test_mic_deny_writes_consent_false(monkeypatch):
    calls = []
    monkeypatch.setattr("ui.pages_people.record_consent",
                        lambda allowed: calls.append(allowed) or True)
    flow = Onboarding.start().answer("next")
    new_flow, ok = answer_step(flow, False)
    assert ok
    assert calls == [False]
    assert new_flow.is_skipped(MIC)


def test_mic_failed_write_keeps_the_step_open(monkeypatch):
    monkeypatch.setattr("ui.pages_people.record_consent", lambda allowed: False)
    flow = Onboarding.start().answer("next")
    new_flow, ok = answer_step(flow, True)
    assert not ok
    # The returned flow is the pre-answer one: the step is still open.
    assert new_flow.current == MIC
    assert not new_flow.is_done(MIC)


def test_presence_writes_the_mode(monkeypatch):
    calls = []
    monkeypatch.setattr("core.presence_mode.set_mode",
                        lambda mode: calls.append(mode) or True)
    flow = Onboarding.start().answer("next").answer(True)
    new_flow, ok = answer_step(flow, "focus")
    assert ok
    assert calls == ["focus"]
    assert new_flow.presence_mode == "focus"
    assert new_flow.current == "done"


def test_presence_unknown_mode_keeps_the_step_open(monkeypatch):
    monkeypatch.setattr("core.presence_mode.set_mode", lambda mode: False)
    flow = Onboarding.start().answer("next").answer(True)
    new_flow, ok = answer_step(flow, "nonsense")
    assert not ok
    assert new_flow.current == PRESENCE


def test_run_onboarding_walks_every_step(monkeypatch):
    monkeypatch.setattr("ui.pages_people.record_consent", lambda allowed: True)
    monkeypatch.setattr("core.presence_mode.set_mode", lambda mode: True)
    flow = run_onboarding(
        Onboarding.start(),
        ["next", True, "active", "finish"],
    )
    assert flow.is_complete
    assert flow.presence_mode == "active"


def test_run_onboarding_stops_at_a_failed_write(monkeypatch):
    monkeypatch.setattr("ui.pages_people.record_consent", lambda allowed: True)
    monkeypatch.setattr("core.presence_mode.set_mode", lambda mode: False)
    flow = run_onboarding(
        Onboarding.start(),
        ["next", True, "active", "finish"],
    )
    # Stopped at presence: welcome + mic are done, presence is still open.
    assert flow.is_done(WELCOME)
    assert flow.is_done(MIC)
    assert flow.current == PRESENCE
    assert not flow.is_complete
