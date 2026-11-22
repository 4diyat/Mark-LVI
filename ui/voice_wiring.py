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


def stop_voice_overlay(shell: "AmbientShell") -> None:
    """Take the camera and the window down at quit. Never raises."""
    feed = getattr(shell, "_hand_feed", None)
    if feed is not None:
        feed.stop()
        shell._hand_feed = None
    overlay = getattr(shell, "_voice_overlay", None)
    if overlay is not None:
        overlay.stop()
        shell._voice_overlay = None


__all__ = [
    "HandFeed", "SHOWN_STATES", "camera_state", "overlay_state", "poll_hand",
    "set_answer", "set_camera_available", "set_hand", "set_transcript",
    "should_show", "show_exchange", "start_voice_overlay",
    "stop_voice_overlay", "sync",
]


# ── the camera, when there is one ───────────────────────────────────────────

def camera_state(controller) -> bool:
    """Whether the tile's hand is backed by a camera that is actually feeding it.

    `WorkspaceHandController.status` is one of `off` / `starting` / `active` /
    `windows_only` / `error`. Only `active` means frames are arriving. The tile
    says "KAMERA" for that one and "KAMERA NONAKTIF" for the rest — a tile that
    looked the same in every case would be a picture of a feature rather than an
    indicator of one.
    """
    try:
        return str(getattr(controller, "status", "off")).strip().lower() == "active"
    except Exception:                               # noqa: BLE001
        return False


def poll_hand(shell: "AmbientShell", controller) -> None:
    """One tick: read the newest sample and put it on the tile.

    WHY THE FIRST HAND AND NOT THE BEST ONE
        `WorkspaceHandController.sample()` returns the hands it can see, newest
        frame only, and it returns `()` for "nothing usable" — a lost hand, a
        stale frame, or a closed hand that has not been deliberately re-opened.
        The tile shows the first; the empty tuple means the hand is gone, and an
        empty tile is the honest picture of that. It is also what makes the
        pause visible: `core.gesture_os` releases a held button on the same
        signal.

    WHY IT IS A POLL AND NOT A CALLBACK
        The camera worker publishes; this reads. A callback from that thread
        would put a Qt widget's state change on a thread that does not own it.
        The overlay's timer calls this, which is the Qt thread by construction.

    NEVER RAISES. `status` is read every tick, so a controller that died mid-run
    is reported as an unlit tile rather than as an exception inside a paint.
    """
    overlay = getattr(shell, "_voice_overlay", None)
    if overlay is None:
        return
    try:
        available = camera_state(controller)
        overlay.set_camera_available(available)
        if not available or overlay.gestures_paused:
            overlay.set_hand(None)
            return
        hands = controller.sample()
        first = hands[0] if hands else None
        if first is None:
            overlay.set_hand(None)
            return
        # `sample()` hands back `(x, y, pinch, scroll, …)` per hand; the tile
        # needs the first three and `hand_from_sample` absorbs the rest.
        overlay.set_hand(tuple(first[:3]))
    except Exception as exc:                        # noqa: BLE001
        _note(shell, f"hand not shown — {type(exc).__name__}: {exc}")


# ── the controller's owner ──────────────────────────────────────────────────

class HandFeed:
    """Owns the camera worker and the one timer that puts it on the tile.

    WHY THIS IS AN OBJECT AND NOT THREE FUNCTIONS
        The worker has a lifetime: it is started when the overlay is built,
        stopped when the program quits, and polled while it runs. Three separate
        functions would need the controller passed between them and would make
        "who stops the camera" a question with three answers.

    WHAT IT REFUSES TO DO
        It does not start a camera off Windows. `WorkspaceHandController.start()`
        already refuses (`status = "windows_only"`) and mediapipe is a
        Windows-only dependency in `requirements.txt`; asking anyway would open
        a device on a platform where the detector cannot run. `start()` reports
        that state rather than pretending, so the tile can say KAMERA NONAKTIF
        for the right reason.

    WHY THE TIMER IS CREATED LAZILY
        `QTimer` needs a Qt application. Creating it in `__init__` would make
        `HandFeed()` raise on a machine with no display, and this class is
        constructed by `start_voice_overlay`, whose whole contract is that a
        decoration cannot take the program down.
    """

    # 12 fps, the overlay's own rate: the tile cannot show more than the frame
    # it is drawn on, and a faster poll would only burn wake-ups.
    POLL_MS = 83

    def __init__(self, shell, controller=None):
        self._shell = shell
        self._controller = controller
        self._timer = None
        self._started = False
        self._error = ""

    @property
    def status(self) -> str:
        """The controller's own word, or `off` when there is no controller."""
        try:
            return str(getattr(self._controller, "status", "off"))
        except Exception:                           # noqa: BLE001
            return "off"

    @property
    def error(self) -> str:
        return self._error

    def start(self) -> bool:
        """Build the controller, start the camera, start the poll. Never raises.

        Returns whether frames are expected. `False` is the normal answer on
        Linux and macOS, and it is not a failure.
        """
        try:
            if self._controller is None:
                from core.workspace_gesture import WorkspaceHandController

                self._controller = WorkspaceHandController()
            self._started = bool(self._controller.start())
            if not self._started:
                return False
            self._start_timer()
            return True
        except Exception as exc:                    # noqa: BLE001
            self._error = f"{type(exc).__name__}: {exc}"
            print(f"[JARVIS] hand feed not started: {self._error}")
            return False

    def poll(self) -> None:
        """One tick. Public so a test can run it without a timer."""
        poll_hand(self._shell, self._controller)

    def stop(self) -> None:
        """Stop the timer, then the camera. Order matters: stopping the camera
        first would leave one tick reading from a controller that is closing."""
        self._stop_timer()
        controller = self._controller
        if controller is None or not self._started:
            return
        try:
            controller.stop()
        except Exception as exc:                    # noqa: BLE001
            print(f"[JARVIS] hand feed would not stop — "
                  f"{type(exc).__name__}: {exc}")
        finally:
            self._started = False

    def _start_timer(self) -> None:
        if self._timer is not None:
            return
        try:
            from PyQt6.QtCore import QTimer

            timer = QTimer()
            timer.setInterval(self.POLL_MS)
            timer.timeout.connect(self.poll)
            timer.start()
            self._timer = timer
        except Exception as exc:                    # noqa: BLE001
            # The camera still runs and the OS pointer still follows the hand;
            # only the tile stops moving, which is a smaller loss than a crash.
            print(f"[JARVIS] hand feed has no timer — {type(exc).__name__}: {exc}")

    def _stop_timer(self) -> None:
        timer, self._timer = self._timer, None
        if timer is None:
            return
        try:
            timer.stop()
        except Exception as exc:                    # noqa: BLE001
            print(f"[JARVIS] hand feed timer would not stop — "
                  f"{type(exc).__name__}: {exc}")
