"""Let JARVIS navigate its own desktop workspace, without OS-wide automation."""
import json

from core.workspace_control import validate
from core import outcome

PLUGIN = {
    "name": "workspace_control",
    "description": (
        "Control JARVIS's own desktop workspace in response to a user request, including Indonesian: "
        "list windows, open/focus, minimize, maximize, restore, move to left/right or close a core panel. "
        "Navigate Files to an explicit folder path or filter its current files. To manage an open editor "
        "or trading document, first list windows and use its exact doc-N id. Use active for the currently "
        "focused workspace window. Open model_viewer for the user to select an OBJ wireframe locally. "
        "Never close document windows "
        "or save/discard edits. Camera open/close requests start/stop camera asynchronously. "
        "Do not use this for controlling other OS applications, deleting files or placing trades."
    ),
    "parameters": {"type": "OBJECT", "properties": {
        "action": {"type": "STRING", "description": "list, open, focus, minimize, maximize, restore, move_left, move_right, close, navigate, search"},
        "target": {"type": "STRING", "description": "assistant, files, navigation, video, camera, model_viewer, active, code_editor, image_editor, trading, or exact doc-N id from list"},
        "text": {"type": "STRING", "description": "Folder path for navigate or filter text for search"},
    }, "required": ["action"]},
    "behavior": "NON_BLOCKING", "scheduling": "WHEN_IDLE", "tier": "core",
}


def run(parameters, player=None, session_memory=None):
    try:
        command = validate(parameters)
        callback = getattr(player, "control_workspace", None) if player is not None else None
        if not callable(callback):
            return "Workspace control requires the JARVIS desktop interface."
        result = callback(command)
        if not isinstance(result, dict):
            return "Workspace did not return a confirmed result."
        if command["action"] == "list" and result.get("ok"):
            return outcome.untrusted("workspace", json.dumps(result.get("windows", []), ensure_ascii=False))
        return str(result.get("message") or "Workspace returned no status.")
    except Exception as exc:
        return f"Workspace command failed: {exc}"
