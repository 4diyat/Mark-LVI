"""Board 12's window-layout adapter: policy to store, with the store mocked.

These test `actions.window_layout` with `memory.config_manager` stubbed, so
no config file is touched. The claims are: the adapter reads the real mode,
an unknown request is refused and writes nothing, a change persists, and a
no-op or a failed write never claims the choice moved.
"""
from __future__ import annotations

from actions.window_layout import apply, choose, read_state


class _FakeConfig:
    def __init__(self, value):
        self.value = value
        self.saved = None

    def get(self):
        return self.value

    def save(self, value):
        self.saved = value
        return True


def _patch(monkeypatch, config, save_ok=True):
    monkeypatch.setattr("memory.config_manager.get_window_layout", config.get)
    monkeypatch.setattr("memory.config_manager.save_window_layout",
                        lambda m: config.save(m) if save_ok else False)


def test_read_state_reads_the_config(monkeypatch):
    config = _FakeConfig("columns3")
    _patch(monkeypatch, config)
    assert read_state() == "columns3"


def test_an_unknown_mode_is_refused_and_writes_nothing(monkeypatch):
    config = _FakeConfig("columns2")
    _patch(monkeypatch, config)
    decision = choose("tiled")
    assert decision.allowed is False
    assert apply(decision) is False
    assert config.saved is None, "a refused request must not reach the store"


def test_a_real_change_persists(monkeypatch):
    config = _FakeConfig("columns2")
    _patch(monkeypatch, config)
    decision = choose("focus")
    assert decision.allowed is True
    assert apply(decision) is True
    assert config.saved == "focus"


def test_a_re_pick_does_not_write(monkeypatch):
    config = _FakeConfig("focus")
    _patch(monkeypatch, config)
    decision = choose("focus")
    assert decision.allowed is True
    assert decision.changed is False
    assert apply(decision) is True
    assert config.saved is None, "a no-op must not reach the store"


def test_a_failed_write_is_reported_not_claimed(monkeypatch):
    config = _FakeConfig("columns2")
    _patch(monkeypatch, config, save_ok=False)
    decision = choose("columns3")
    assert decision.allowed is True
    assert apply(decision) is False
    assert "tidak bisa disimpan" in decision.reason


def test_a_read_fallback_when_config_raises(monkeypatch):
    def _boom():
        raise RuntimeError("locked")

    monkeypatch.setattr("memory.config_manager.get_window_layout", _boom)
    assert read_state() == "columns2", "an unreadable choice defaults to the artboard"
