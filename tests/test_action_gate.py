"""The gate: classify, record, run-or-hold, record again.

The test that matters most here is the forgery one. `core.confirm.request`
returns a token-bearing sentence, and the model is the one that reads it. If a
tool could be made to run by passing a flag, or if the gate ran a risky action
because the model said "confirmed", the whole trusted-UI design would be
decoration.
"""
from __future__ import annotations


import pytest

from core import action_gate, audit_log, confirm, risk_policy


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_STATE_DIR", str(tmp_path))
    audit_log.reset_shared()
    # A headless sandbox has no HUD bound, and an unbound `core.confirm`
    # refuses every risky action — which is correct, and would make these
    # tests assert nothing about the gate. Bind a recorder instead.
    shown = []
    # `core.confirm` deliberately keeps at most one pending request, so a test
    # that ends with a banner still up would leak it into the next test. Reset
    # it by letting the clock run past the timeout is not possible here, so the
    # pending slot is cleared directly — this is a test fixture, not the app.
    confirm._pending = None
    confirm.bind(lambda token, title, detail: shown.append((token, title, detail)),
                 lambda token: None)
    yield shown
    confirm._pending = None
    confirm.bind(None, None)
    audit_log.reset_shared()


def _entries():
    return audit_log.shared().entries()


def test_a_safe_action_runs_and_is_recorded():
    result = action_gate.check("web_search", lambda: "found 3 pages")
    assert result.ran is True
    assert result.message == "found 3 pages"
    outcomes = [e["outcome"] for e in _entries()]
    assert outcomes == ["requested", "done"]
    assert {e["level"] for e in _entries()} == {"safe"}


def test_a_medium_action_without_a_known_undo_is_held_for_a_human():
    """The escalation must reach the gate, not just the classification function.

    A tool-level `medium` with no per-action entry has no demonstrated undo, so
    it is escalated. That is the rule that keeps `medium` from being an
    unverifiable promise.
    """
    ran = []
    result = action_gate.check("browser_control", lambda: ran.append(1) or "done")
    assert result.ran is False
    assert ran == []
    assert result.level == risk_policy.RISKY


def test_a_call_whose_undo_is_real_runs_without_asking():
    """`file_controller.delete` pushes `_restore_from_trash`; asking first would
    be asking about something the user can already walk back."""
    result = action_gate.check("file_controller", lambda: "Moved to Trash",
                               {"action": "delete"})
    assert result.ran is True
    assert result.level == risk_policy.MEDIUM
    assert result.risk.reversible is True


def test_the_level_follows_the_arguments_not_just_the_tool():
    """One tool, two answers: reading a folder versus shutting the machine down."""
    assert action_gate.check("computer_settings", lambda: "ok",
                             {"action": "volume_up"}).ran is True
    shutdown = action_gate.check("computer_settings", lambda: "bye",
                                 {"action": "shutdown"})
    assert shutdown.ran is False
    assert shutdown.needs_human is True


def test_a_risky_action_never_runs_before_a_human_answers(isolated):
    ran = []
    result = action_gate.check("send_message", lambda: ran.append(1) or "sent",
                               confirm_title="Kirim laporan")
    assert result.ran is False
    assert ran == []
    assert "CONFIRMATION_PENDING" in result.message
    assert [title for _token, title, _detail in isolated] == ["Kirim laporan"]


def test_an_unbound_interface_refuses_instead_of_running():
    """No HUD bound (headless, or a very early call): refuse, never proceed."""
    confirm._pending = None
    confirm.bind(None, None)
    ran = []
    result = action_gate.check("send_message", lambda: ran.append(1) or "sent")
    assert result.ran is False
    assert ran == []
    assert "not available" in result.message


def test_the_model_cannot_run_a_risky_action_by_claiming_confirmation():
    """No parameter of `check` accepts a 'confirmed' flag, by design."""
    import inspect
    params = set(inspect.signature(action_gate.check).parameters)
    assert not params & {"confirmed", "confirm", "yes", "force", "override", "approve"}


def test_a_failing_action_is_recorded_as_failed_and_returns_a_sentence():
    def explode():
        raise ValueError("bad argument")

    result = action_gate.check("web_search", explode)
    assert result.ran is True
    assert "ValueError" in result.message
    assert [e["outcome"] for e in _entries()] == ["requested", "failed"]


def test_an_unverified_result_is_recorded_as_unverified_not_done():
    result = action_gate.check("web_search", lambda: "[UNVERIFIED] could not check")
    assert result.ran is True
    assert [e["outcome"] for e in _entries()] == ["requested", "unverified"]


def test_a_failed_prefix_is_recorded_as_failed():
    action_gate.check("web_search", lambda: "Failed: no network")
    assert [e["outcome"] for e in _entries()] == ["requested", "failed"]


def test_a_tool_that_gates_itself_is_not_asked_about_twice():
    """Four actions already call `core.confirm` with a sentence written for the
    specific operation. A second banner for one shutdown teaches the user to
    dismiss both."""
    r = action_gate.check("code_helper", lambda: "started", {"action": "run"},
                          self_gated=True)
    assert r.ran is True
    assert r.level == risk_policy.RISKY
    assert [e["outcome"] for e in _entries()] == ["requested", "done"]


def test_without_the_declaration_the_same_call_is_parked():
    r = action_gate.check("code_helper", lambda: "started", {"action": "run"})
    assert r.ran is False
    assert r.needs_human is True


def test_the_audit_line_names_the_sub_action():
    """`computer_settings` alone says nothing about what was asked for."""
    action_gate.check("computer_settings", lambda: "ok", {"action": "volume_up"})
    assert _entries()[0]["tool"] == "computer_settings:volume_up"


def test_an_audit_failure_does_not_stop_the_action(monkeypatch):
    def boom(*_a, **_k):
        raise RuntimeError("disk gone")

    monkeypatch.setattr(audit_log, "record", boom)
    result = action_gate.check("web_search", lambda: "still ran")
    assert result.ran is True
    assert result.message == "still ran"


def test_describe_reports_a_level_without_running_anything():
    line = action_gate.describe("send_message")
    assert line.startswith("send_message: risky")
    assert "—" in line


def test_the_audit_line_for_a_held_action_says_so():
    """The question 'did I allow that?' must be answerable from the log."""
    action_gate.check("send_message", lambda: "sent", confirm_title="Kirim laporan")
    held = [e for e in _entries() if e["outcome"] == "awaiting"]
    assert held and held[0]["detail"] == "Kirim laporan"


def test_a_pending_confirmation_blocks_a_second_risky_action(isolated):
    """Two banners cannot stack; the second is refused, not queued."""
    first = action_gate.check("send_message", lambda: "sent", confirm_title="A")
    second = action_gate.check("shutdown", lambda: "bye", confirm_title="B")
    assert "CONFIRMATION_PENDING" in first.message
    assert second.ran is False
    assert "already awaiting" in second.message.lower()
    assert len(isolated) == 1, "only one banner may be on screen at a time"


def test_the_result_reports_whether_a_human_is_needed():
    result = action_gate.check("send_message", lambda: "sent")
    assert result.needs_human is True
    done = action_gate.check("web_search", lambda: "ok")
    assert done.needs_human is False


def test_confirmation_shows_full_parameters_and_refuses_large_details(isolated):
    ran = []
    result = action_gate.check('send_message', lambda: ran.append(1),
                               {'recipient': 'Ada', 'message': '<report>'})
    assert not result.ran and ran == []
    assert 'Ada' in isolated[0][2] and '<report>' in isolated[0][2]
    confirm.resolve(isolated[0][0], False)
    result = action_gate.check('send_message', lambda: ran.append(1),
                               {'message': 'X' * 500})
    assert not result.ran and 'complete action details' in result.message
    assert ran == [] and len(isolated) == 1


def test_confirmation_refuses_unrepresentable_parameters(isolated):
    result = action_gate.check('send_message', lambda: 'sent', {'body': object()})
    assert not result.ran and 'parameters' in result.message
    assert not isolated
