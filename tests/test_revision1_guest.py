"""Guest mode protects built-in history/memory, not arbitrary tools or logs."""
import threading

import pytest

from actions import background_monitor
from core import guest_mode, history
from memory import memory_manager


@pytest.fixture(autouse=True)
def reset_guest():
    guest_mode._reset_for_tests()
    yield
    guest_mode._reset_for_tests()


def test_no_new_history_memory_or_monitor_writes(tmp_path, monkeypatch):
    monkeypatch.setattr(history, '_base_dir', lambda: tmp_path)
    path = tmp_path / 'long_term.json'
    monkeypatch.setattr(memory_manager, 'MEMORY_PATH', path)
    assert history.record('user', 'before guest')
    memory_manager.update_memory({'notes': {'a': 'before'}})
    before_history = list((tmp_path / 'logs/history').glob('*.jsonl'))[0].read_bytes()
    before_memory = path.read_bytes()
    guest_mode.enable()
    assert not history.record('user', 'after guest')
    with pytest.raises(guest_mode.GuestModeError):
        memory_manager.update_memory({'notes': {'a': 'after'}})
    with pytest.raises(guest_mode.GuestModeError):
        memory_manager.save_session_summary('after guest')
    with pytest.raises(guest_mode.GuestModeError):
        background_monitor._save({'example': {'topic': 'after'}})
    assert list((tmp_path / 'logs/history').glob('*.jsonl'))[0].read_bytes() == before_history
    assert path.read_bytes() == before_memory


def test_enable_waits_for_guarded_write_then_denies_new_writes():
    entered, release, enabled = threading.Event(), threading.Event(), threading.Event()
    def write():
        with guest_mode.storage_guard() as allowed:
            assert allowed
            entered.set()
            assert release.wait(2)
    writer = threading.Thread(target=write); writer.start()
    assert entered.wait(1)
    switch = threading.Thread(target=lambda: (guest_mode.enable(), enabled.set()))
    switch.start()
    assert not enabled.wait(.05)
    release.set(); writer.join(2); switch.join(2)
    assert enabled.is_set()
    with guest_mode.storage_guard() as allowed:
        assert not allowed
