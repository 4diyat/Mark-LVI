"""Revision 1: medium confirmation and honest activity counts."""
import threading

import pytest

from core import action_gate, audit_log, confirm
from core.audit_activity import request_counts


@pytest.fixture(autouse=True)
def gate(tmp_path, monkeypatch):
    monkeypatch.setenv('JARVIS_STATE_DIR', str(tmp_path))
    audit_log.reset_shared()
    confirm._pending = None
    shown = []
    confirm.bind(lambda token, title, detail: shown.append((token, title, detail)), lambda token: None)
    yield shown
    confirm._pending = None
    confirm.bind(None, None)
    audit_log.reset_shared()


def test_medium_approval_runs_once_and_records_outcome(gate):
    ran = threading.Event()
    calls = []
    def run():
        calls.append(1)
        ran.set()
        return 'ok'
    result = action_gate.check('file_controller', run, {'action': 'delete'})
    assert not result.ran and result.needs_human and not ran.is_set()
    confirm.resolve(gate[0][0], True)
    assert ran.wait(2)
    confirm.resolve(gate[0][0], True)
    assert calls == [1] and len(gate) == 1


def test_refused_confirmation_is_not_a_pending_request():
    confirm.bind(None, None)
    result = action_gate.check('file_controller', lambda: pytest.fail('ran'), {'action': 'delete'})
    assert not result.ran and not result.needs_human
    assert 'not available' in result.message


def test_medium_plugin_also_waits(gate):
    ran = []
    result = action_gate.check('example', lambda: ran.append(1), {'input': 'x'}, plugin_level='medium')
    assert result.level == 'medium' and not result.ran and result.needs_human
    assert not ran and 'x' in gate[0][2]


def test_count_only_requests_not_confirmations_or_outcomes():
    records = [{'level': 'medium', 'outcome': 'requested'},
               {'level': 'medium', 'outcome': 'awaiting'},
               {'level': 'risky', 'outcome': 'requested'},
               {'level': 'risky', 'outcome': 'done'},
               {'level': 'unknown', 'outcome': 'requested'}]
    assert request_counts(records) == {'safe': 0, 'medium': 1, 'risky': 1}


def test_self_gated_pending_is_not_reported_done(gate):
    def inner():
        return confirm.request('run', 'Run?', 'Run the requested action?', lambda: 'ok')
    verdict = action_gate.check('code_helper', inner, {'action': 'run'}, self_gated=True)
    assert not verdict.ran and verdict.needs_human
    entries = audit_log.shared().entries()
    assert entries[-1]['outcome'] == 'awaiting'
    assert not any(e['tool'] == 'code_helper:run' and e['outcome'] == 'done' for e in entries)


def test_inline_memory_save_is_medium_and_waits(gate):
    calls = []
    verdict = action_gate.check('save_memory', lambda: calls.append(1),
                                {'category': 'notes', 'key': 'food', 'value': 'tea'})
    assert verdict.level == 'medium' and not verdict.ran and verdict.needs_human
    assert not calls and 'tea' in gate[0][2]


def test_self_gated_refusal_is_held_not_done():
    confirm.bind(None, None)
    def inner():
        return confirm.request('run', 'Run?', 'Execute this file?', lambda: 'ok')
    result = action_gate.check('code_helper', inner, {'action': 'run'}, self_gated=True)
    assert not result.ran and not result.needs_human
    assert 'not available' in result.message
    assert audit_log.shared().entries()[-1]['outcome'] == 'held'
