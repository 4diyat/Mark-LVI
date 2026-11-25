"""Board 14's OS-control adapter: policy to transport, with the store mocked.

These test `actions.os_control` with `memory.config_manager` and
`ui.hand_feed` stubbed, so no config file and no pointer pipeline are touched.
The claims are: the adapter reads the real state, the gate is the policy's, a
no-op never touches the transport, and a failed apply reports the failure
instead of claiming the change took.
"""
from __future__ import annotations

from actions.os_control import apply, disable, enable, read_state, toggle


class _FakeConfig:
    def __init__(self, value):
        self.value = value
        self.saved = None

    def get(self):
        return self.value

    def save(self, value):
        self.saved = value


def _patch(monkeypatch, config, transport_ok=True):
    """Wire the adapter's two externals to the fakes; return the transport log."""
    calls = []

    def _set(enabled):
        calls.append(enabled)
        config.save(enabled)
        return transport_ok

    monkeypatch.setattr("memory.config_manager.get_gesture_os_enabled",
                        config.get)
    monkeypatch.setattr("ui.hand_feed.set_gesture_os", _set)
    return calls


def test_read_state_reads_the_config(monkeypatch):
    config = _FakeConfig(False)
    _patch(monkeypatch, config)
    assert read_state() is False


def test_a_bare_enable_is_refused_and_touches_no_transport(monkeypatch):
    config = _FakeConfig(False)
    calls = _patch(monkeypatch, config)
    decision = toggle(True, confirmed=False)
    assert decision.allowed is False
    assert calls == [], "a refused change must not reach the transport"


def test_the_confirm_path_applies_and_persists(monkeypatch):
    config = _FakeConfig(False)
    calls = _patch(monkeypatch, config)
    decision = enable(confirmed=True)
    assert decision.allowed is True
    assert calls == [True]
    assert config.saved is True


def test_a_disable_applies_without_confirmation(monkeypatch):
    config = _FakeConfig(True)
    calls = _patch(monkeypatch, config)
    decision = disable()
    assert decision.allowed is True
    assert calls == [False]
    assert config.saved is False


def test_a_no_op_does_not_touch_the_transport(monkeypatch):
    config = _FakeConfig(False)
    calls = _patch(monkeypatch, config)
    decision = toggle(False, confirmed=False)
    assert decision.allowed is True
    assert decision.changed is False
    assert calls == [], "a no-op must not reach the transport"


def test_a_failed_apply_reports_the_failure_not_a_success(monkeypatch):
    """The transport refusing must not be reported as the switch moving."""
    config = _FakeConfig(False)
    _patch(monkeypatch, config, transport_ok=False)
    decision = enable(confirmed=True)
    assert decision.allowed is True
    assert apply(decision) is False
    assert "gagal" in decision.reason or "tidak bisa" in decision.reason


def test_a_successful_apply_returns_true(monkeypatch):
    config = _FakeConfig(False)
    _patch(monkeypatch, config, transport_ok=True)
    decision = enable(confirmed=True)
    assert apply(decision) is True


def test_a_read_that_raises_defaults_to_off(monkeypatch):
    def _boom():
        raise RuntimeError("locked")

    monkeypatch.setattr("memory.config_manager.get_gesture_os_enabled", _boom)
    monkeypatch.setattr("ui.hand_feed.set_gesture_os", lambda e: True)
    assert read_state() is False
