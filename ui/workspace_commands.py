"""Execute validated workspace commands on the Qt thread only."""
from core.workspace_control import CORE_TARGETS, validate

_OPEN_JOBS = {
    "code_editor": {"kind": "creative_workspace", "tab": "editor"},
    "ai_image": {"kind": "creative_workspace", "tab": "canvas"},
    "image_editor": {"kind": "image_editor"},
    "trading": {"kind": "trading_terminal"},
}


def _state(sub):
    if sub.isHidden():
        return "hidden"
    if sub.isMinimized():
        return "minimized"
    if sub.isMaximized():
        return "maximized"
    return "visible"


def _show(window, sub):
    if sub.isHidden() or sub.isMinimized():
        sub.showNormal()
    window._desktop_mdi.setActiveSubWindow(sub)
    sub.raise_()
    window._desktop_mdi.position_dock()


def execute(window, command):
    command = validate(command)  # do not trust callers that bypass the plugin
    action, target, text = command["action"], command["target"], command["text"]
    if action == "list":
        windows = []
        active = window._desktop_mdi.activeSubWindow()
        for name in ("assistant", "files", "navigation", "video", "camera"):
            sub = window._desktop_windows[name]
            windows.append({"id": name, "kind": name, "state": _state(sub), "active": sub is active})
        if "handboard" in window._desktop_windows:
            sub = window._desktop_windows["handboard"]
            windows.append({"id": "handboard", "kind": "handboard", "state": _state(sub), "active": sub is active})
        for doc_id, (kind, sub) in window._workspace_documents.items():
            windows.append({"id": doc_id, "kind": kind, "state": _state(sub),
                            "title": str(sub.windowTitle())[:120], "active": sub is active})
        return {"ok": True, "windows": windows}

    if action in ("board_add", "board_list"):
        if action == "board_list":
            board = getattr(window, "_hand_board", None)
            if board is None:
                return {"ok": False, "message": "The hand board has not been opened yet."}
            return {"ok": True, "items": board.items_snapshot()}
        window._open_handboard()
        if not window._hand_board.add_note(command["title"], text):
            return {"ok": False, "message": "Could not add the note; the board may be full."}
        return {"ok": True, "message": "Added the note to the hand board. It stays in this session only."}

    if action == "open" and target == "handboard":
        window._open_handboard()
        return {"ok": True, "message": "Opened the hand board. Camera control remains off until the user enables it."}

    if action == "open" and target in _OPEN_JOBS:
        from ui.workspace_router import open_workspace
        previous = set(window._workspace_documents)
        open_workspace(window, dict(_OPEN_JOBS[target]))
        created = set(window._workspace_documents) - previous
        if not created:
            return {"ok": False, "message": f"Could not open {target}; its plugin may be disabled or unavailable."}
        doc_id = next(iter(created))
        return {"ok": True, "message": f"Opened {target} as {doc_id}."}

    if action == "open" and target == "camera":
        if window._camera_active:
            _show(window, window._desktop_windows["camera"])
            return {"ok": True, "message": "Camera preview is already active."}
        window.start_camera_stream()
        return {"ok": True, "message": "Camera start requested; the preview appears only if the camera opens successfully."}

    if target == "active":
        active = window._desktop_mdi.activeSubWindow()
        found = next((name for name in ("assistant", "files", "navigation", "video", "camera", "handboard")
                      if window._desktop_windows.get(name) is active and active is not None), None)
        if found is None:
            found = next((doc_id for doc_id, (_, sub) in window._workspace_documents.items()
                          if sub is active), None)
        if found is None:
            return {"ok": False, "message": "There is no active managed workspace window."}
        target = found
    sub = window._desktop_windows.get(target) if target in CORE_TARGETS else None
    if sub is None:
        entry = window._workspace_documents.get(target)
        sub = entry[1] if entry else None
    if sub is None:
        return {"ok": False, "message": "That workspace window is not open; list windows to see available ids."}

    if action in ("navigate", "search"):
        browser = window._workspace_file_browser
        if action == "navigate":
            if not browser.navigate(text):
                return {"ok": False, "message": "That folder does not exist or cannot be opened."}
            _show(window, sub)
            return {"ok": True, "message": "Files navigated to the requested folder."}
        browser.search.setText(text)
        _show(window, sub)
        return {"ok": True, "message": "Files filter updated."}

    if action in ("open", "focus", "restore"):
        if action == "restore":
            sub.showNormal()
        _show(window, sub)
        if target == "chat":
            window._input.setFocus()
        return {"ok": True, "message": f"Showing {target}."}
    if action == "close":
        if target not in CORE_TARGETS:
            return {"ok": False, "message": "Document windows must be closed by the user so unsaved changes can be reviewed."}
        if target == "handboard":
            sub.close()
            return {"ok": True, "message": "Hand board hidden; workspace hand control remains unchanged."}
        if target == "camera":
            window.stop_camera_stream()
            sub.hide()
            return {"ok": True, "message": "Camera stop requested and its preview hidden."}
        if target == "video":
            window._on_video_close()
            return {"ok": True, "message": "Video stopped and its panel hidden."}
        sub.hide()
        return {"ok": True, "message": f"{target} panel hidden; its dock button can restore it."}
    if sub.isHidden():
        return {"ok": False, "message": "That window is hidden; open or focus it first."}
    if action == "minimize":
        sub.showMinimized()
        suffix = " Camera capture may continue." if target == "camera" else ""
        if target == "video":
            suffix = " Video playback may continue."
        return {"ok": True, "message": f"Minimized {target}.{suffix}"}
    if action == "maximize":
        sub.showMaximized()
        window._desktop_mdi.position_dock()
        return {"ok": True, "message": f"Maximized {target}."}
    if action in ("move_left", "move_right"):
        viewport = window._desktop_mdi.viewport()
        width, height = viewport.width(), viewport.height()
        sub.showNormal()
        sub.setGeometry(0 if action == "move_left" else width // 2, 0,
                        max(1, width // 2), max(1, height - 90))
        window._desktop_mdi.setActiveSubWindow(sub)
        window._desktop_mdi.position_dock()
        return {"ok": True, "message": f"Moved {target} to the {action[5:]} side."}
    return {"ok": False, "message": "Unsupported workspace action."}
