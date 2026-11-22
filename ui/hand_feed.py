"""The camera, the hand on it, and the pointer it drives.

WHY THIS IS ITS OWN MODULE
    `ui/voice_wiring.py` answers one question: when does the voice overlay cover
    the screen. This answers a different one: what is the hand doing, and may it
    touch the desktop. They were one file until it crossed 600 lines, and the
    line they split on is a real boundary — nothing here draws anything, and
    nothing there moves anything.

    The dependency runs one way: this module may be imported by the wiring, and
    the wiring's `HandFeed` name is re-exported from here for every caller that
    already says `voice_wiring.HandFeed`.

WHAT IT OWNS
    * `HandFeed`             the camera worker's lifetime and its 12 fps poll
    * `camera_state`         whether the tile's hand is backed by frames
    * `poll_hand`            the newest sample onto the overlay's tile
    * `gesture_context`      the three facts `HandPointer` must not guess
    * `gesture_bridge_enabled` the saved switch, read fresh
    * `set_gesture_os`       the switch, applied to the running bridge

EVERY PATH HERE IS ON A TIMER. Nothing in this module may raise into the Qt
thread, block on a config read that hangs, or hold a mouse button down when it
returns.
"""
from __future__ import annotations

import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:                                    # pragma: no cover
    from ui.shell import AmbientShell


def _note(shell, text: str) -> None:
    """`lifecycle.note`, imported at call time to keep the arrow one-way."""
    try:
        from ui.lifecycle import note

        note(shell, text)
    except Exception:                               # noqa: BLE001
        print(f"[JARVIS] {text}")


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


def gesture_context(shell: "AmbientShell", now: float | None = None):
    """The facts `HandPointer` must not guess, read from where they live.

    WHY EACH ONE IS READ RATHER THAN PASSED DOWN
        * `os_mode`   — the user's switch, on disk (`memory.config_manager`);
        * `confirmation_open` — `core.confirm.pending_title()`, which already
          answers "is a banner on screen" and already expires on its own;
        * `own_window_focused` — Qt, and therefore the one fact that can only
          be true when this program has a window at all. With no window there
          is nothing of ours to have focus, and the workspace gestures are not
          running either, so the hand may drive the desktop.

    A MISSING PIECE IS `False`, never an exception: this is called on every
    frame, from a thread whose failure would be a frozen cursor.
    """
    from core import gesture_os

    return gesture_os.Context(
        os_mode=gesture_bridge_enabled(),
        own_window_focused=_own_window_focused(shell),
        confirmation_open=_confirmation_open(),
        modal_open=False,
        now=time.monotonic() if now is None else now,
    )


def gesture_bridge_enabled() -> bool:
    """The saved switch, read fresh so a change needs no restart.

    A config read per frame is a small file read on the Qt thread at 12 fps.
    It is deliberate: the alternative is a cached copy that disagrees with the
    disk after the user switches the feature off, and the disagreement would be
    "the hand is still clicking".
    """
    try:
        from memory.config_manager import get_gesture_os_enabled

        return bool(get_gesture_os_enabled())
    except Exception:                               # noqa: BLE001
        return False


def _confirmation_open() -> bool:
    try:
        from core import confirm

        return bool(confirm.pending_title())
    except Exception:                               # noqa: BLE001
        # UNREADABLE MEANS "A BANNER MIGHT BE UP". Freezing the pointer when we
        # cannot tell is the safe direction: the cost is a hand that does not
        # move for a frame, and the alternative is a webcam click on a
        # confirmation for a bank transfer.
        return True


def _own_window_focused(shell) -> bool:
    """Whether one of this program's windows is the active window.

    `False` when there is no window to ask — that is the ambient case, where the
    overlay is a HUD and the desktop behind it is the user's.
    """
    window = getattr(shell, "_voice_overlay", None)
    window = getattr(window, "_window", None)
    if window is None:
        return False
    try:
        return bool(window.isActiveWindow())
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

    def __init__(self, shell, controller=None, bridge=None):
        self._shell = shell
        self._controller = controller
        self._timer = None
        self._started = False
        self._error = ""
        # THE BRIDGE IS BUILT HERE AND ENABLED ONLY IF THE USER SAID SO. Off
        # means the object exists and holds no pointer, no pyautogui import and
        # no pyautogui reference — the disabled path cannot click anything
        # because there is nothing to click with.
        if bridge is None:
            from core.gesture_bridge import GestureBridge

            bridge = GestureBridge()
        self._bridge = bridge
        if gesture_bridge_enabled():
            self._bridge.enable()

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

    @property
    def bridge(self):
        return self._bridge

    def poll(self) -> None:
        """One tick: the tile, then the desktop. Public so a test can run it
        without a timer.

        THE SAME SAMPLE FEEDS BOTH, and in this order on purpose. The tile is
        what the user is looking at while they learn the gestures, so it is
        updated even on a frame the policy refuses — which is exactly the frame
        where the reason matters. The pointer is second because a frame that
        draws nothing must still not move the cursor.
        """
        poll_hand(self._shell, self._controller)
        self._pump_bridge()

    def _pump_bridge(self) -> None:
        """Hand one sample to the policy and let it decide. Never raises."""
        try:
            controller = self._controller
            if controller is None or not camera_state(controller):
                return
            overlay = getattr(self._shell, "_voice_overlay", None)
            paused = bool(getattr(overlay, "gestures_paused", False))
            # PAUSED IS ALSO A STOP, not just a hidden tile: the policy releases
            # a held button when the hand disappears, which is what Ctrl+Alt+G
            # has to do to a drag the user was in the middle of.
            sample = None if paused else (controller.sample() or (None,))[0]
            self._bridge.pump(sample, gesture_context(self._shell))
        except Exception as exc:                    # noqa: BLE001
            _note(self._shell, f"gesture not delivered — "
                               f"{type(exc).__name__}: {exc}")

    def stop(self) -> None:
        """Stop the timer, let go of the mouse, then stop the camera.

        THE BRIDGE GOES FIRST OF ALL. A button held when the session ends is the
        one failure the user cannot undo by waving, and `disable()` releases it
        through the same `release_now()` the policy uses — not through a second
        definition of "let go".
        """
        self._stop_timer()
        try:
            self._bridge.disable()
        except Exception as exc:                    # noqa: BLE001
            _note(self._shell, f"could not let go of the mouse — "
                               f"{type(exc).__name__}: {exc}")
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


def set_gesture_os(shell: "AmbientShell", enabled: bool) -> bool:
    """Turn bare-hand OS control on or off, persist it, and apply it now.

    Returns whether the pipeline is now live. `False` can mean the user asked
    for it and this machine cannot deliver it — no pyautogui, no camera — and
    that is said rather than swallowed: a switch that appears on and moves
    nothing is worse than one that refuses with a reason.

    The saved value is written even when enabling fails, because the failure is
    about THIS machine's dependencies and not about the user's intent; a repaired
    install must come up with the feature they asked for.
    """
    wanted = bool(enabled)
    try:
        from memory.config_manager import save_gesture_os_enabled

        save_gesture_os_enabled(wanted)
    except Exception as exc:                        # noqa: BLE001
        _note(shell, f"gesture setting not saved — {type(exc).__name__}: {exc}")
    feed = getattr(shell, "_hand_feed", None)
    if feed is None:
        return False
    bridge = getattr(feed, "bridge", None)
    if bridge is None:
        return False
    if not wanted:
        bridge.disable()
        return False
    return bool(bridge.enable())


__all__ = [
    "HandFeed", "camera_state", "gesture_bridge_enabled", "gesture_context",
    "poll_hand", "set_gesture_os",
]
