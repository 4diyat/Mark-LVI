"""Open a local code editor; execution is only started by the person at the UI."""
PLUGIN = {
    "name": "code_editor",
    "description": ("Open an interactive code editor for writing, opening, saving, and running "
                    "Python or JavaScript. The person must choose files and approve every run. "
                    "The code is NOT sandboxed. Optional code is shown for editing, not run."),
    "parameters": {"type": "OBJECT", "properties": {
        "code": {"type": "STRING", "description": "Optional initial code to put in a new editor."},
    }, "required": []},
    "behavior": "NON_BLOCKING", "scheduling": "WHEN_IDLE", "tier": "core",
}


def run(parameters: dict, player=None, session_memory=None) -> str:
    if player is None or not callable(getattr(player, "show_code_job", None)):
        return "The code editor needs the desktop interface."
    code = str((parameters or {}).get("code") or "")
    if len(code) > 100_000:
        return "The initial code is too large for the editor."
    try:
        player.show_code_job({"kind": "creative_workspace", "tab": "editor", "code": code})
        return "Opening the code editor. Saving and running require your action in the editor."
    except Exception as exc:
        return f"Could not open the code editor: {exc}"
