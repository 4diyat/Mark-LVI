"""How the voice overlay (board 6) is turned on, fed, and closed.

WHY A WIRING MODULE AND NOT THREE LINES IN `AmbientShell`
    The rule for WHEN the overlay exists is a product decision with a cost: it
    covers the whole screen, so it may only be up while the assistant is
    actually using the microphone or the voice. Deciding that inside
    `AmbientShell.set_state` — which is called from the audio thread, the model
    thread and the hotkey thread — would put a full-screen window's visibility
    behind whichever thread happened to set a word first.

    So the rule lives in one function, `should_show()`, which is pure and takes
    a state word. `sync()` applies it. `AmbientShell` calls `sync()` from
    `set_state`, after the orb has been told, and nothing else touches the
    window.

WHY IT IS NOT PART OF `ui/voice_overlay.py`
    That module may only fail on its own behalf: it is the surface, and it is
    tested with no Qt at all. This one knows about the shell, the assembler of
    transcript text, and the camera thread — three things the surface must not
    depend on. Same split as `tray_panel` / `tray_panel_wiring`.

WHAT THE OVERLAY SHOWS, AND WHERE IT COMES FROM
    * state        — the shell's own word (LISTENING / SPEAKING / …)
    * transcript   — the last thing the user said, from the session
    * answer       — the last sentence the assistant produced
    * hand         — `core.workspace_gesture`, if this machine has a camera
      and a Windows mediapipe; otherwise the tile reads "KAMERA NONAKTIF".

WHAT IT DOES NOT DO
    It does not listen, and it does not send anything. Esc closes the overlay
    and, through `on_close`, asks the session to stop listening — which is what
    the footnote promises. It never raises: every path prints and carries on,
    because a decoration must not take down a call.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

# THE HAND MOVED TO `ui/hand_feed.py` when this file reached 600 lines. Re-exported
# here because `lifecycle`, `tests/test_voice_wiring.py` and the overlay's own
# starter all say `voice_wiring.HandFeed`, and a move is not a rename.
from ui.hand_feed import (                      # noqa: F401 — re-exported
    HandFeed, camera_state, gesture_bridge_enabled, gesture_context, poll_hand,
    set_gesture_os,
)

if TYPE_CHECKING:                                    # pragma: no cover
    from ui.shell import AmbientShell

# The states the overlay covers the screen for. Deliberately NOT "thinking":
# the user's words are already in, the answer is not out yet, and a full-screen
# frame that appears after the question and before the answer reads as a hang.
SHOWN_STATES = frozenset({"listening", "speaking"})


def should_show(state: str) -> bool:
    """Whether a state word is one the overlay is FOR.

    "no mic" is not listening. A machine whose microphone is missing would
    otherwise throw a 1280×720 frame over the desktop to say "MENDENGARKAN"
    while holding nothing — the worst possible moment for it.
    """
    return str(state or "").strip().lower() in SHOWN_STATES


def overlay_state(state: str) -> str:
    """The shell's word → the overlay's three states."""
    word = str(state or "").strip().lower()
    if word in SHOWN_STATES:
        return word
    return "idle"


def start_voice_overlay(shell: "AmbientShell") -> bool:
    """Build the overlay, unshown. False when this desktop cannot draw it.

    Built now and shown later, for the same reason the command bar is: a window
    constructed on the first LISTENING would put Qt's construction cost on the
    exact moment the feature is being judged.
    """
    from ui.voice_overlay import VoiceOverlay

    overlay = VoiceOverlay(on_close=lambda: _on_close(shell))
    if not overlay.start(active=False):
        _note(shell, f"Voice overlay unavailable ({overlay.error}).")
        return False
    shell._voice_overlay = overlay

    # THE CAMERA IS STARTED WITH THE SURFACE THAT SHOWS IT, and for the same
    # reason: the tile exists to show what the camera sees, and a camera started
    # only when a window appears would have to warm up on the user's first
    # pinch. On this platform it refuses (mediapipe is Windows-only here) and
    # the tile says so — the feed's failure is not the overlay's failure.
    feed = HandFeed(shell)
    feed.start()
    shell._hand_feed = feed

    # The chord from the footnote, bound with the surface it acts on.
    start_pause_hotkey(shell)
    return True


def _on_close(shell: "AmbientShell") -> None:
    """Esc was pressed. The overlay is already hidden; stop listening.

    THE FOOTNOTE SAYS "Esc keluar", and "keluar" from a listening overlay has to
    mean the assistant stops listening — otherwise the frame disappears while
    the microphone stays open, which is the one outcome a user pressing Esc is
    trying to prevent.

    `request_sleep` rather than a lower-level call: it is the same path the
    tray's Sleep control uses, so there is one definition of "stop listening".
    """
    try:
        shell.request_sleep()
    except Exception as exc:                        # noqa: BLE001
        _note(shell, f"could not stop listening after Esc — "
                     f"{type(exc).__name__}: {exc}")


def sync(shell: "AmbientShell") -> None:
    """Apply `should_show` to the window. Called from `set_state`, every time.

    Cheap and idempotent: hiding an already-hidden window is a no-op in Qt, and
    this runs on whichever thread set the state. Nothing here blocks — no
    camera, no file, no scheduler.
    """
    overlay = getattr(shell, "_voice_overlay", None)
    if overlay is None:
        return
    try:
        # `shell._state`, not a new public property: `shell.state` is a free
        # slot that `tests/test_face_bubble.py` assigns a scratch dict to, and a
        # property there would have been a setter-less name where a test puts
        # bookkeeping. The word `set_state` wrote is the one this needs.
        state = getattr(shell, "_state", "") or ""
        overlay.set_state(overlay_state(state))
        if should_show(state):
            if not overlay.active:
                overlay.show()
        elif overlay.active:
            overlay.hide()
    except Exception as exc:                        # noqa: BLE001
        _note(shell, f"voice overlay did not follow the state — "
                     f"{type(exc).__name__}: {exc}")


def set_transcript(shell: "AmbientShell", text: str) -> None:
    """What the user just said. No-op without an overlay, never raises."""
    overlay = getattr(shell, "_voice_overlay", None)
    if overlay is None:
        return
    try:
        overlay.set_transcript(text)
    except Exception as exc:                        # noqa: BLE001
        _note(shell, f"transcript not shown — {type(exc).__name__}: {exc}")


def set_answer(shell: "AmbientShell", text: str) -> None:
    """What the assistant just answered. Truncated by the painter, not here."""
    overlay = getattr(shell, "_voice_overlay", None)
    if overlay is None:
        return
    try:
        overlay.set_answer(text)
    except Exception as exc:                        # noqa: BLE001
        _note(shell, f"answer not shown — {type(exc).__name__}: {exc}")


def set_hand(shell: "AmbientShell", sample) -> None:
    """One camera sample. Called from the gesture thread, if there is one."""
    overlay = getattr(shell, "_voice_overlay", None)
    if overlay is None:
        return
    try:
        overlay.set_hand(sample)
    except Exception as exc:                        # noqa: BLE001
        _note(shell, f"hand not shown — {type(exc).__name__}: {exc}")


def set_camera_available(shell: "AmbientShell", available: bool) -> None:
    overlay = getattr(shell, "_voice_overlay", None)
    if overlay is None:
        return
    try:
        overlay.set_camera_available(available)
    except Exception as exc:                        # noqa: BLE001
        _note(shell, f"camera tile not updated — {type(exc).__name__}: {exc}")


def show_exchange(shell: "AmbientShell", line: str) -> None:
    """Split one log line into the transcript or the answer, and show it.

    WHY THE PREFIXES AND NOT A NEW CALLBACK
        `main.py` writes `You: <what the user said>` and
        `<assistant name>: <what it answered>` to `write_log`, and has done
        since the chat log was removed. Parsing those two prefixes is the
        cheapest honest way to feed the overlay: no second parameter to thread
        through 48 call sites, and no way for the session to forget to tell the
        overlay something it told the log.

    WHAT IT DELIBERATELY DROPS
        `SYS:`, `ERR:`, `USR:` and `TOOL:` lines are the program talking about
        itself. Putting them on the transcript line would make the overlay claim
        the user said "Push-to-talk unavailable".

    A NAME WITH OR WITHOUT A COLON
        The assistant's name is a setting (`JARVIS`, `J.A.R.V.I.S`, anything the
        user typed). Rather than guess, anything that is not `You: ` and not one
        of the four machine prefixes is treated as the assistant's own speech —
        which is exactly how `write_log` already decides what to notify about.
    """
    overlay = getattr(shell, "_voice_overlay", None)
    if overlay is None or not line:
        return
    text = str(line)
    if text.startswith("You: "):
        set_transcript(shell, text[len("You: "):])
        return
    if text.startswith(("SYS:", "ERR:", "USR:", "TOOL:")):
        return
    # `<name>: answer` — split once, because an answer may contain colons.
    _, sep, answer = text.partition(": ")
    if sep and len(text.split(": ", 1)[0]) < 40:
        set_answer(shell, answer)
    else:
        set_answer(shell, text)


def _note(shell, text: str) -> None:
    """`lifecycle.note`, imported at call time to keep the arrow one-way."""
    try:
        from ui.lifecycle import note

        note(shell, text)
    except Exception:                               # noqa: BLE001
        print(f"[JARVIS] {text}")


# The chord printed in board 6's own footnote. Ctrl+Alt+G, not Ctrl+G: the
# second is a common browser and editor shortcut, and a pause key that also
# does something in the window behind the overlay is worse than no key.
PAUSE_CHORD = ("ctrl", "alt", "g")


def start_pause_hotkey(shell: "AmbientShell") -> str:
    """Bind Ctrl+Alt+G to the gesture pause. Returns the scope achieved.

    WHY THIS IS A SECOND KEY FOR ONE FEATURE
        `core.hand_gesture.HandController` polls the same chord as its own
        emergency stop — that is a hardware-level kill switch and it must not
        depend on this program's event loop. This binding is the other half: it
        tells the OVERLAY to show the pause, because the controller stopping is
        not something a tile can see.

    A FAILED BINDING IS NOT A FAILURE. The chord still stops the pointer
    through the controller's own polling — the user loses the word on the tile,
    not the ability to stop. So this reports the scope and never raises.
    """
    from core.hotkey import HotkeyTap

    tap = HotkeyTap(lambda: toggle_gestures(shell), chord=PAUSE_CHORD)
    try:
        scope = tap.start()
    except Exception as exc:                        # noqa: BLE001
        _note(shell, f"gesture pause shortcut unavailable — "
                     f"{type(exc).__name__}: {exc}")
        return "window"
    shell._pause_hotkey = tap
    return scope


def stop_pause_hotkey(shell: "AmbientShell") -> None:
    tap = getattr(shell, "_pause_hotkey", None)
    if tap is None:
        return
    try:
        tap.stop()
    finally:
        shell._pause_hotkey = None


def toggle_gestures(shell: "AmbientShell") -> bool:
    """Ctrl+Alt+G: pause or resume, and say which on the tile.

    Returns the new paused flag, or False when there is no overlay to say it
    on. The pointer itself is stopped by the gesture controller's own poll of
    the same chord; this decides what the user is TOLD.
    """
    overlay = getattr(shell, "_voice_overlay", None)
    if overlay is None:
        return False
    try:
        return bool(overlay.handle_toggle_gestures())
    except Exception as exc:                        # noqa: BLE001
        _note(shell, f"gesture pause did not apply — "
                     f"{type(exc).__name__}: {exc}")
        return False


def stop_voice_overlay(shell: "AmbientShell") -> None:
    """Take the chord, the camera and the window down at quit. Never raises."""
    stop_pause_hotkey(shell)
    feed = getattr(shell, "_hand_feed", None)
    if feed is not None:
        feed.stop()
        shell._hand_feed = None
    overlay = getattr(shell, "_voice_overlay", None)
    if overlay is not None:
        overlay.stop()
        shell._voice_overlay = None


__all__ = [
    "HandFeed", "PAUSE_CHORD", "SHOWN_STATES", "camera_state",
    "gesture_bridge_enabled", "gesture_context", "overlay_state", "poll_hand",
    "set_answer", "set_camera_available", "set_gesture_os", "set_hand",
    "set_transcript", "should_show", "show_exchange", "start_pause_hotkey",
    "start_voice_overlay", "stop_pause_hotkey", "stop_voice_overlay", "sync",
    "toggle_gestures",
]
