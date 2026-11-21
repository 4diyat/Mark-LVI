"""A camera that watches for something, and the three things it must never do.

WHY THIS IS NOT "RECORD EVERYTHING AND ASK THE MODEL LATER"
    Pointing a camera at a room and letting a model look at it on a schedule
    builds a continuous record of a home. That record is a liability the moment
    it exists: it is the most personal data this program could hold, it is
    exactly what a prompt injection would ask to read, and there is no honest
    way to promise it will never be copied. So the design has no continuous
    recording at all. Frames live in memory for the length of one check and
    are then dropped; only the SENTENCE the check produced is kept.

THE THREE RULES
    1. OFF BY DEFAULT, AND OFF MEANS NO CAMERA. Not "a camera that discards
       frames". The loop does not open the device when the setting is off, so
       the light does not come on and nothing is acquired. This matters more
       here than anywhere else in the program: an operating-system camera
       indicator is a promise to the user, and a watcher that opens the device
       to decide whether it should be open breaks it.

    2. IT NEVER SPEAKS FIRST — IT ASKS. A watcher that interrupts the room
       whenever it sees something is a smoke alarm with no idea what smoke is.
       Results go to the activity log and a desktop notification; the model is
       told only if the user asks. `core/notify.py` already decides whether a
       banner is welcome; this module does not get a second opinion.

    3. NOTHING LEAVES THE MACHINE UNLESS THE USER ASKED FOR IT. `check_now`
       is a tool call: the model asked, on the user's instruction, and sending
       that one frame is the same act as `screen_process`. But it is NOT
       permission to send a frame per tick of a loop; `tick()` never uploads.
       A watched room must not become a stream of uploads nobody agreed to.

WHY THE DIFFERENCE IS SMALL ON PURPOSE
    `check_now` reuses `actions/screen_processor.py`'s camera path — including
    `core/camera_lease.py`, so it cannot fight the live view or hand-gesture
    control for the device — and returns a frame to the same exchange a
    `screen_process` call would use. There is no second vision pipeline here to
    drift from the first one.

WHAT THE DIFFERENCE DETECTOR IS AND IS NOT
    It is not motion detection. A fan, a curtain and a television are all
    motion, and a watcher that reports them is one the user unplugs in a week.
    `tick()` compares a coarse, greyscale fingerprint of the frame against the
    baseline and reports only changes large enough to be worth a look, holding
    a countdown so a person walking through a frame produces one report, not
    fifteen. When the frames cannot be compared it says so once rather than
    pretending it is watching.
"""
from __future__ import annotations

import asyncio
import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime

from core import logbook

# How different a frame must be from the baseline before it is worth telling
# the user about. Chosen conservatively: a missed event is a missed
# notification, a false one is an assistant nobody believes.
_CHANGE_THRESHOLD = 0.18

# The fingerprint is the top-left of a coarse greyscale grid. Small enough that
# one comparison is microseconds, large enough that a moving object changes it.
_GRID_X, _GRID_Y = 32, 18

# A change is reported at most once per hold-off, so somebody walking past the
# camera produces one line in the log rather than one per tick.
_HOLD_OFF_SECONDS = 120.0

# The baseline is refreshed after this long even without a report, so a slow
# change of light (dusk, a lamp being switched on) does not read as a visitor.
_REBASE_SECONDS = 3600.0

# How often the loop looks. A camera busy being checked costs nothing between
# ticks; this is the "look at the room" rhythm, not a frame rate.
TICK_SECONDS = 20.0

# What was seen, oldest first. One line per look that mattered — never an
# image, and never more than this many lines, so "what happened while I was
# out" has an answer that cannot become a file of somebody's room.
_MAX_RECENT = 60
_recent: deque = deque(maxlen=_MAX_RECENT)

_state_lock = threading.RLock()
_last_report = 0.0
_baseline = None
_baseline_at = 0.0
_fingerprint_failed = False


@dataclass(frozen=True)
class Frame:
    """One look. Bytes stay in memory and are never written anywhere."""

    image: bytes
    mime: str
    at: str
    changed: bool
    difference: float

    def summary(self) -> str:
        """One line for the activity log."""
        when = self.at[11:19] if len(self.at) > 19 else self.at
        if self.changed:
            return (f"🔎 Camera check at {when}: something changed in view "
                    f"({self.difference:.0%} of the frame).")
        return f"🔎 Camera check at {when}: nothing changed in view."


def _config() -> dict:
    """The settings section, read per call through the one config reader.

    Read fresh rather than cached: the switch is a checkbox, and a watcher
    that needs a restart to stop watching is the failure mode this module
    exists to avoid.
    """
    from memory.config_manager import load_api_keys

    section = (load_api_keys() or {}).get("security_camera")
    return section if isinstance(section, dict) else {}


def enabled() -> bool:
    """Is the watcher on? Only a literal `True` counts.

    `"true"`, `1`, `"yes"` and a malformed section all read as off, the same
    rule `core/file_access.py` follows — and for the same reason: a config
    problem must never be able to switch a camera on.
    """
    return _config().get("enabled") is True


def interval() -> float:
    """Seconds between looks, clamped to something a camera tolerates.

    A user who types 1 wants a video stream, which is a different feature with
    a different consent conversation; the floor is where this module stops
    being a watcher and starts being a recorder.
    """
    try:
        value = float(_config().get("interval_seconds", TICK_SECONDS))
    except (TypeError, ValueError):
        return TICK_SECONDS
    return max(10.0, min(value, 3600.0))


def describe() -> str:
    """One line for SETUP: what is on, and what it does not do."""
    if not enabled():
        return ("Security camera: OFF — the camera is not opened at all, so the "
                "device light stays off.")
    return (f"Security camera: ON — one look every {int(interval())}s. Frames are "
            "held in memory for the check and dropped; only a one-line result "
            "is kept, and nothing is uploaded unless you ask.")


def _fingerprint(frame) -> list[int] | None:
    """A coarse greyscale grid, or None when numpy/cv2 cannot make one.

    Kept deliberately ugly and cheap: the comparison is what matters, and a
    detector that needs a model is a detector that needs to download one.
    """
    try:
        import cv2
    except ImportError:
        return None
    try:
        small = cv2.resize(frame, (_GRID_X, _GRID_Y), interpolation=cv2.INTER_AREA)
        grey = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        return [int(v) for v in grey.flatten()]
    except Exception:                       # noqa: BLE001 — a bad frame
        return None


def _difference(a, b) -> float:
    """Mean absolute difference, as a fraction of full scale.

    Not a squared error and not an image hash: this number is quoted to the
    user as a percentage of the frame, and it has to mean that.
    """
    if not a or not b or len(a) != len(b):
        return 1.0
    return sum(abs(x - y) for x, y in zip(a, b)) / (len(a) * 255.0)


def _capture():
    """One frame, through the existing camera path, or raise a sentence.

    Deliberately the SAME function `screen_process` uses: the camera index
    detection, the backend choice, the lease and the JPEG settings all belong
    to one place, and a second implementation of them here would be a second
    set of bugs.
    """
    from actions.screen_processor import _capture_camera

    return _capture_camera()


def tick() -> Frame | None:
    """Look once. Returns None when the watcher is off or the camera refused.

    UPLOADS NOTHING. That is the contract of this function, and it is the
    reason a watcher can exist at all: a loop that sends a frame somewhere
    every twenty seconds is a live feed of somebody's room.
    """
    global _last_report, _baseline, _baseline_at, _fingerprint_failed

    # Unconditional: there is no "just this once" parameter on purpose. A
    # caller that can override the switch is a switch that does not mean what
    # the drawer says, and an `force=True` nobody uses today is the hole
    # somebody finds tomorrow.
    if not enabled():
        return None

    try:
        image, mime = _capture()
    except Exception as e:                  # noqa: BLE001 — the user sees why
        logbook.get(__name__).info("camera check skipped: %s", e)
        return None

    now = time.monotonic()
    difference = 0.0
    changed = False

    fingerprint = _decode_and_fingerprint(image)
    with _state_lock:
        if fingerprint is None:
            if not _fingerprint_failed:
                # Said once, not every twenty seconds. A watcher that repeats
                # "I cannot tell" is noise pretending to be vigilance.
                _fingerprint_failed = True
                logbook.get(__name__).warning(
                    "camera frames cannot be compared (numpy/cv2 unavailable); "
                    "the watcher will report every look without a difference")
        else:
            _fingerprint_failed = False
            if _baseline is None or (now - _baseline_at) > _REBASE_SECONDS:
                _baseline = fingerprint
                _baseline_at = now
            else:
                difference = _difference(_baseline, fingerprint)
                changed = difference >= _CHANGE_THRESHOLD
                if changed and (now - _last_report) >= _HOLD_OFF_SECONDS:
                    _last_report = now
                    # The baseline moves to what was just seen, so the same
                    # change is not reported again after the hold-off expires.
                    _baseline = fingerprint
                    _baseline_at = now
                elif changed:
                    # Inside the hold-off: still a change, but already said.
                    # Reported as unchanged so the caller does not notify twice.
                    changed = False

    frame = Frame(image=image, mime=mime,
                  at=datetime.now().isoformat(timespec="seconds"),
                  changed=changed, difference=difference)
    if changed:
        # Only changes are remembered. A list of "nothing happened" every
        # twenty seconds would be a log of the user's absence, which is a
        # different fact from the one they asked for.
        _recent.append({"at": frame.at, "difference": round(difference, 3)})
    return frame


def _decode_and_fingerprint(image: bytes) -> list[int] | None:
    """Fingerprint a JPEG without keeping the decoded picture."""
    try:
        import cv2
        import numpy as np
    except ImportError:
        return None
    try:
        buffer = np.frombuffer(image, dtype=np.uint8)
        frame = cv2.imdecode(buffer, cv2.IMREAD_COLOR)
        if frame is None:
            return None
        return _fingerprint(frame)
    except Exception:                       # noqa: BLE001
        return None


def recent(limit: int = 10) -> list[dict]:
    """The last few changes the watcher reported, newest last.

    In memory only, on purpose: an event record that survives a restart is a
    record of when somebody was and was not at home, kept on disk, for as long
    as they own the machine. The activity log still shows each line as it
    happens; this is the short-term answer to "did anything happen".
    """
    limit = max(1, min(int(limit or 10), _MAX_RECENT))
    with _state_lock:
        return list(_recent)[-limit:]


def report(limit: int = 10) -> str:
    """A sentence for the model, from the record — never from a new frame."""
    events = recent(limit)
    if not enabled():
        return ("The security camera is off, so I have not been watching "
                "anything. You can switch it on in the CONTROLS drawer.")
    if not events:
        return "The camera is watching, and nothing in view has changed yet."
    lines = [f"• {e['at'][11:19]}: a change of about {e['difference']:.0%}"
             for e in events]
    return ("Changes the camera has noticed (times are local, newest last):\n"
            + "\n".join(lines))


def reset() -> None:
    """Forget the baseline and the hold-off. Used when the switch is flipped.

    Without this, turning the watcher off and on again would compare a room
    against an hour-old picture and report the difference as an event.
    """
    global _last_report, _baseline, _baseline_at, _fingerprint_failed
    with _state_lock:
        _last_report = 0.0
        _baseline = None
        _baseline_at = 0.0
        _fingerprint_failed = False
        _recent.clear()


def save(enabled_flag: bool, interval_seconds: float | None = None) -> bool:
    """Turn the watcher on or off. Never called by a tool — see the module note."""
    from memory.config_manager import update_config

    def _apply(data: dict) -> None:
        if not enabled_flag:
            # The section is REMOVED, not set to false: leaving an interval
            # behind means the next person to switch it on inherits a cadence
            # they did not choose.
            data.pop("security_camera", None)
            return
        data["security_camera"] = {
            "enabled": True,
            "interval_seconds": float(interval_seconds or TICK_SECONDS),
        }

    ok = bool(update_config(_apply))
    if ok:
        reset()
    return ok


async def watch(ui=None) -> None:
    """The background loop. It lives HERE, not in `JarvisLive`.

    WHY A MODULE-LEVEL COROUTINE
        `JarvisLive` has a hard ceiling (`tests/test_ui_split.py`) and it is at
        it, so a loop written inside the class came out as a failed test rather
        than a review comment. Moving it here also puts the three rules next to
        the code they constrain instead of forty lines away in a class that
        also starts sockets.

    `ui` is anything with `write_log(str)`; it is optional so this can be run,
    and tested, without a window.
    """
    while True:
        await asyncio.sleep(interval())
        if not enabled():
            continue
        frame = await asyncio.to_thread(tick)
        if frame is None or not frame.changed:
            continue
        line = frame.summary()
        logbook.get(__name__).info("%s", line)
        if ui is not None:
            try:
                ui.write_log("SYS: " + line)
            except Exception as e:          # noqa: BLE001 — a log may fail
                # Already in the logbook above, which is the copy that matters.
                logbook.get(__name__).debug("could not write to the HUD: %s", e)
        try:
            from core import notify
            await asyncio.to_thread(notify.send_native, "Security camera", line)
        except Exception as e:              # noqa: BLE001 — a banner may be refused
            logbook.get(__name__).debug("notification refused: %s", e)


__all__ = ["Frame", "TICK_SECONDS", "describe", "enabled", "interval",
           "recent", "report", "reset", "save", "tick", "watch"]
