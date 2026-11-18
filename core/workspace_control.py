"""Thread-safe request envelope and validation for desktop workspace control."""
import re
import threading

ACTIONS = {"list", "open", "focus", "minimize", "maximize", "restore",
           "move_left", "move_right", "close", "navigate", "search"}
CORE_TARGETS = {"assistant", "chat", "files", "navigation", "video", "camera", "model_viewer"}
OPEN_TARGETS = CORE_TARGETS | {"code_editor", "image_editor", "trading"}


def validate(parameters):
    if not isinstance(parameters, dict):
        raise ValueError("Expected a workspace command.")
    action = parameters.get("action")
    if not isinstance(action, str) or action not in ACTIONS:
        raise ValueError("Unsupported workspace action.")
    target = parameters.get("target", "")
    if not isinstance(target, str) or len(target) > 80:
        raise ValueError("Invalid workspace target.")
    target = target.strip().lower()
    if action in {"navigate", "search"}:
        if target not in ("", "files"):
            raise ValueError("Navigation and search only apply to Files.")
        target = "files"
    elif action == "list":
        target = ""
    elif action == "open":
        if target not in OPEN_TARGETS:
            raise ValueError("Unknown workspace to open.")
    elif target not in CORE_TARGETS and target != "active" and not re.fullmatch(r"doc-[1-9][0-9]{0,8}", target):
        raise ValueError("Choose a listed workspace or document id.")
    text = parameters.get("text", "")
    if not isinstance(text, str) or len(text) > 2000 or "\x00" in text:
        raise ValueError("Invalid path or search text.")
    if action == "navigate" and not text.strip():
        raise ValueError("Provide the folder path to navigate to.")
    result = {"action": action, "target": target, "text": text}
    return result


class WorkspaceRequest:
    """One request; a timeout cancels it if the GUI has not started it yet."""
    def __init__(self, command):
        self.command = command
        self.done = threading.Event()
        self.lock = threading.Lock()
        self.started = False
        self.cancelled = False
        self.result = None

    def claim(self):
        with self.lock:
            if self.cancelled:
                return False
            self.started = True
            return True

    def finish(self, result):
        with self.lock:
            self.result = result
            self.done.set()

    def wait(self, timeout):
        if self.done.wait(timeout):
            return self.result
        with self.lock:
            if self.done.is_set():
                return self.result
            if not self.started:
                self.cancelled = True
                return {"ok": False, "message": "Desktop did not respond; command was cancelled before execution."}
            return {"ok": False, "message": "Desktop command started, but its result is not confirmed yet."}
