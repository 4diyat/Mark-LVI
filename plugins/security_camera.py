"""security_camera — what the watcher noticed, without taking a new picture.

WHY THIS PLUGIN HAS NO "look" ACTION
    The obvious action would be "take a frame and describe it". A plugin cannot
    deliver an image: the frame only reaches the model through `main.py`'s
    `_pending_vision`, which is set by `screen_process`. A plugin that returned
    "[image attached]" would be lying to the model, and a model that believes
    an attachment exists answers from imagination — the exact failure the
    `[VISION_ACTIVE]` wording in `main.py` was written to avoid.

    So a live look stays where it already works: `screen_process` with
    `angle: camera`. This plugin answers the OTHER question — "did anything
    happen while I was out" — from the record the background watcher keeps in
    memory.

WHAT IT WILL NOT DO
    * It cannot switch the watcher on or off. A camera is not something the
      assistant may enable for itself; that is a person pressing a row in the
      CONTROLS drawer, for the same reason `core/file_access.py` lets no tool
      widen file access.
    * It takes no picture. `status` reads memory, so asking about the camera
      cannot itself activate it.
    * It never returns an image or a file path. The record is timestamps and a
      percentage, and it does not survive a restart.

PERMISSIONS
    `files`: it reads `config/api_keys.json` for the watcher's setting.
"""
from __future__ import annotations

from core import security_camera

PLUGIN = {
    "name": "security_camera",
    "description": (
        "Report what the security-camera watcher has noticed recently — the "
        "times its view changed and by how much — and say whether it is on. "
        "Use for 'apa yang berubah', 'ada gerakan', 'kamera sekuriti', 'apa "
        "yang terjadi saat aku pergi'. For an actual look at the room right "
        "now, use screen_process with angle=camera instead; this tool never "
        "takes a picture. It cannot switch the watcher on or off — tell the "
        "user to use the FULL CAMERA row in the CONTROLS drawer."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": (
                    "status — the recent changes and whether the watcher is on. "
                    "This is the only action."
                ),
            },
        },
        "required": ["action"],
    },
    "behavior": "BLOCKING",
    "scheduling": "WHEN_ASKED",
    "tier": "core",
}


def run(parameters: dict, player=None, session_memory=None) -> str:
    parameters = parameters or {}
    action = str(parameters.get("action") or "status").strip().lower()

    if action in ("status", "report", "recent", "changes", "lista"):
        return security_camera.report()

    if action in ("on", "off", "enable", "disable", "start", "stop"):
        # Said plainly rather than silently ignored: the model should be able
        # to tell the user why it cannot do this, in the user's own words.
        return ("Sir, I cannot switch the camera on or off myself — that is a "
                "switch only you can press, in the CONTROLS drawer "
                "(SECURITY CAMERA). Tell me what you want watched and I will "
                "say what the camera has seen.")

    if action in ("look", "see", "snapshot", "photo"):
        return ("For that I need to see the room: ask me again and I will use "
                "screen_process with the camera. This tool only reports what "
                "the watcher already noticed.")

    return (f"Sir, I know 'status' for the camera — not {action!r}. "
            "Which did you mean?")
