"""Board 15's gesture binding adapter, driven with a mocked config layer."""
import pytest

from actions.gesture_binding import apply, cycle, read_state, rebind
from core.gesture_binding import (CLICK, INTERFACE_CALL, MEDIA_PAUSE,
                                  BindingDecision)


@pytest.fixture
def config_state(monkeypatch):
    """A fake config store, with the read/write entry points the adapter uses."""
    store = {"gesture_bindings": dict()}

    def get_gesture_bindings():
        return store.get("gesture_bindings", {})

    def save_gesture_binding(gesture, action):
        store.setdefault("gesture_bindings", {})[gesture] = action
        return True

    monkeypatch.setattr("memory.config_manager.get_gesture_bindings",
                        get_gesture_bindings)
    monkeypatch.setattr("memory.config_manager.save_gesture_binding",
                        save_gesture_binding)
    return store


def test_read_state_returns_the_defaults_when_nothing_is_stored(config_state):
    out = read_state()
    assert out["open_palm"] == INTERFACE_CALL
    assert out["pinch"] == CLICK
    assert out["fist"] == MEDIA_PAUSE


def test_a_real_rebind_persists_and_is_read_back(config_state):
    decision = rebind("fist", CLICK)
    assert decision.allowed and decision.changed
    assert apply(decision)
    assert read_state()["fist"] == CLICK


def test_a_re_pick_writes_nothing(config_state):
    decision = rebind("fist", MEDIA_PAUSE)  # already the default
    assert decision.allowed and not decision.changed
    assert apply(decision)
    assert read_state()["fist"] == MEDIA_PAUSE


def test_an_unknown_action_writes_nothing(config_state):
    decision = rebind("fist", "bogus")
    assert not decision.allowed
    assert not apply(decision)
    assert read_state()["fist"] == MEDIA_PAUSE


def test_cycle_walks_to_the_next_action(config_state):
    decision = cycle("open_palm")
    assert decision.allowed and decision.changed
    assert decision.desired == CLICK
    assert apply(decision)
    assert read_state()["open_palm"] == CLICK


def test_a_failed_write_is_reported(config_state, monkeypatch):
    monkeypatch.setattr("memory.config_manager.save_gesture_binding",
                        lambda g, a: False)
    decision = cycle("open_palm")
    assert not apply(decision)
    assert "tidak bisa disimpan" in decision.reason


def test_read_falls_back_when_the_store_is_unreadable(monkeypatch):
    def boom():
        raise RuntimeError("no config")
    monkeypatch.setattr("memory.config_manager.get_gesture_bindings", boom)
    out = read_state()
    assert out["pinch"] == CLICK


def test_the_decision_type_is_the_policy_one():
    assert isinstance(rebind("fist", CLICK), BindingDecision)
