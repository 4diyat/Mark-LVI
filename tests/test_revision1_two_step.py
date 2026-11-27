"""Both confirmations are required and cancellation is fail-closed."""
from ui import desktop_confirm


def test_two_steps_accept(monkeypatch):
    answers = iter([True, True])
    calls = []
    def ask(*args):
        calls.append(args)
        return next(answers)
    monkeypatch.setattr(desktop_confirm, '_ask_once', ask)
    assert desktop_confirm.confirm_twice(None, 'first', 'details', 'final', 'details', 'yes', 'no')
    assert len(calls) == 2 and calls[0][1] == 'first' and calls[1][1] == 'final'


def test_first_cancel_skips_final(monkeypatch):
    calls = []
    monkeypatch.setattr(desktop_confirm, '_ask_once', lambda *a: calls.append(a) or False)
    assert not desktop_confirm.confirm_twice(None, 'a', 'b', 'c', 'd', 'yes', 'no')
    assert len(calls) == 1


def test_final_cancel_prevents_action(monkeypatch):
    answers = iter([True, False])
    monkeypatch.setattr(desktop_confirm, '_ask_once', lambda *a: next(answers))
    assert not desktop_confirm.confirm_twice(None, 'a', 'b', 'c', 'd', 'yes', 'no')
