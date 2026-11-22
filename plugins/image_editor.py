"""Open a local image editor with an optional user-applied suggestion."""
PLUGIN = {
    "name": "image_editor",
    "description": ("Open the local image editor. Optionally suggest rotate, flip, grayscale, crop, or add_text; "
                    "the person chooses a file and explicitly applies or saves edits. "
                    "Opening the editor does not modify any file."),
    "parameters": {"type": "OBJECT", "properties": {
        "suggestion": {"type": "STRING", "description": "Optional: rotate, flip, grayscale, crop, or add_text"},
        "text": {"type": "STRING", "description": "Optional proposed text for add_text; the person must confirm it"},
    }, "required": []},
    "behavior": "NON_BLOCKING", "scheduling": "WHEN_IDLE", "tier": "extra",
}


def run(parameters: dict, player=None, session_memory=None) -> str:
    if player is None or not callable(getattr(player, "show_code_job", None)):
        # The editor was a pane inside the window, and the window is gone
        # (docs/mockups/NOT-IN-MOCKUP.md). `show_code_job` is the method that
        # asked for it, so its absence is the absence of the editor.
        return ("The image editor has no interface in this build — its window "
                "was removed. No image was changed.")
    suggestion = str((parameters or {}).get("suggestion") or "").lower()
    if suggestion not in ("", "rotate", "flip", "grayscale", "crop", "add_text"):
        return "Supported suggestions are rotate, flip, grayscale, crop and add_text; no image was changed."
    try:
        job = {"kind": "image_editor", "suggestion": suggestion}
        if suggestion == "add_text":
            text = str((parameters or {}).get("text") or "")
            if len(text) > 500 or any(ord(c) < 32 for c in text):
                return "Suggested text must be a single line of at most 500 characters; no image was changed."
            job["text"] = text
        player.show_code_job(job)
        return "Opening the image editor. Choose an image and apply or save edits yourself; no file was changed."
    except Exception as exc:
        return f"Could not open the image editor: {exc}"
