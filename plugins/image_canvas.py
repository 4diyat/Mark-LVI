"""Open a prompt-based image canvas; image generation starts only on user click."""
PLUGIN = {
    "name": "image_canvas",
    "description": ("Open the AI image canvas, optionally prefilling a prompt. The person "
                    "clicks Generate to send that prompt to Gemini and can save the image."),
    "parameters": {"type": "OBJECT", "properties": {
        "prompt": {"type": "STRING", "description": "Optional image description to prefill."},
    }, "required": []},
    "behavior": "NON_BLOCKING", "scheduling": "WHEN_IDLE", "tier": "core",
}


def run(parameters: dict, player=None, session_memory=None) -> str:
    if player is None or not callable(getattr(player, "show_code_job", None)):
        return "The image canvas needs the desktop interface."
    prompt = str((parameters or {}).get("prompt") or "")
    if len(prompt) > 5000:
        return "The image prompt is too long."
    try:
        player.show_code_job({"kind": "creative_workspace", "tab": "canvas", "prompt": prompt})
        return "Opening the AI image canvas. Press Generate to create the image."
    except Exception as exc:
        return f"Could not open the image canvas: {exc}"
