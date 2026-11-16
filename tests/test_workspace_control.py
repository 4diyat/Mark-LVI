"""Workspace tool validates requests and never fabricates a GUI result."""
import pytest

from core.workspace_control import WorkspaceRequest, validate
from plugins import workspace_control


@pytest.mark.parametrize("command", [
    {}, {"action": "run_shell", "target": "files"},
    {"action": "close", "target": "other-os-app"},
    {"action": "focus", "target": "doc-0"},
    {"action": "open", "target": "doc-12"},
    {"action": "navigate", "text": ""},
    {"action": "navigate", "target": "files", "text": "a\x00b"},
    {"action": "search", "target": "assistant", "text": "foo"},
    {"action": "move_left", "target": "doc-9999999999"},
])
def test_rejects_unknown_or_malformed_commands(command):
    with pytest.raises(ValueError):
        validate(command)


def test_accepts_document_ids_and_explicit_file_path():
    assert validate({"action": "focus", "target": "DOC-12"})["target"] == "doc-12"
    assert validate({"action": "minimize", "target": "active"})["target"] == "active"
    assert validate({"action": "navigate", "text": "C:/Users/me/Documents"}) == {
        "action": "navigate", "target": "files", "text": "C:/Users/me/Documents"}


def test_timed_out_queued_request_is_never_executed():
    request = WorkspaceRequest({"action": "list"})
    assert "cancelled" in request.wait(0)["message"]
    assert not request.claim()


def test_started_request_timeout_is_not_reported_as_cancelled():
    request = WorkspaceRequest({"action": "list"})
    assert request.claim()
    assert "not confirmed" in request.wait(0)["message"]
    request.finish({"ok": True})
    assert request.wait(0) == {"ok": True}


def test_plugin_requires_a_desktop_and_uses_confirmed_result():
    assert "desktop interface" in workspace_control.run({"action": "list"})
    class Player:
        def __init__(self):
            self.calls = []
        def control_workspace(self, command):
            self.calls.append(command)
            return {"ok": False, "message": "Window not open."}
    player = Player()
    assert workspace_control.run({"action": "focus", "target": "doc-1"}, player) == "Window not open."
    assert player.calls == [{"action": "focus", "target": "doc-1", "text": ""}]
    assert "failed" in workspace_control.run({"action": "delete", "target": "files"}, player)
    assert len(player.calls) == 1


def test_native_hand_board_commands_require_valid_note_content():
    assert validate({"action": "open", "target": "handboard"})["target"] == "handboard"
    command = validate({"action": "board_add", "title": "  Plan  ", "text": "Steps"})
    assert command == {"action": "board_add", "target": "handboard", "text": "Steps", "title": "Plan"}
    assert validate({"action": "board_list"})["target"] == "handboard"
    with pytest.raises(ValueError):
        validate({"action": "board_add", "title": ""})
    with pytest.raises(ValueError):
        validate({"action": "board_add", "title": "x" * 121})
    with pytest.raises(ValueError):
        validate({"action": "board_list", "target": "camera"})
