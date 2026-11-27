"""Permission switches gate only classified actions, including pending calls."""
import threading

import pytest

from core import action_gate, audit_log, confirm, tool_permissions


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv('JARVIS_STATE_DIR', str(tmp_path))
    tool_permissions.reset(); audit_log.reset_shared(); confirm._pending = None
    shown = []; finished = threading.Event(); logs = []
    def log(line):
        logs.append(line)
        if 'Blocked' in line:
            finished.set()
    confirm.bind(lambda token, title, detail: shown.append(token), lambda token: None, log)
    yield shown, finished, logs
    confirm._pending = None; confirm.bind(None, None); tool_permissions.reset(); audit_log.reset_shared()


def test_disabled_safe_tool_is_blocked_and_audited():
    tool_permissions.set_allowed('safe', False)
    calls = []
    result = action_gate.check('web_search', lambda: calls.append(1))
    assert not result.ran and not result.needs_human and not calls
    assert 'disabled' in result.message
    assert [e['outcome'] for e in audit_log.shared().entries()] == ['requested', 'held']


def test_revoking_medium_after_banner_prevents_execution(isolated):
    shown, finished, logs = isolated
    calls = []
    result = action_gate.check('file_controller', lambda: calls.append(1), {'action': 'delete'})
    assert result.needs_human and shown
    tool_permissions.set_allowed('medium', False)
    confirm.resolve(shown[0], True)
    assert finished.wait(2) and not calls
    assert any('Blocked' in line for line in logs)


def test_revoking_internal_gate_after_banner_prevents_execution(isolated):
    shown, finished, _ = isolated
    calls = []
    def internally_gated():
        return confirm.request('code', 'Run?', 'Execute?', lambda: calls.append(1))
    result = action_gate.check('code_helper', internally_gated, {'action': 'run'}, self_gated=True)
    assert result.needs_human and shown
    tool_permissions.set_allowed('risky', False)
    confirm.resolve(shown[0], True)
    assert finished.wait(2) and not calls


def test_bad_level_cannot_be_enabled():
    with pytest.raises(ValueError):
        tool_permissions.set_allowed('unknown', True)
    assert not tool_permissions.is_allowed('unknown')
