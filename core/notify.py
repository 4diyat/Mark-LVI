"""Native desktop notifications — JARVIS saying "done" when nobody is looking.

WHY THIS EXISTS
    In ambient mode there is no window, and until now the only thing that
    changed when the assistant finished a task was a tray tooltip nobody
    watches. `ui/tray.py` carries the always-on readout; this carries the one
    moment that actually matters: an answer arrived while you were in another
    application.

WHY IT IS A SHAPED THING AND NOT A CALL TO `notify-send`
    `actions/reminder.py` already proves the mechanism on all three desktops
    (plyer, `win10toast`, `osascript`, `notify-send`). What it does not have,
    and what a status-driven notification needs, is a REASON not to fire:

      * a status cycle runs dozens of times a minute (LISTENING → THINKING →
        SPEAKING → LISTENING). One notification per transition is a machine
        that buzzes until you turn it off — and then you have lost the feature.
      * a banner is worth showing when the answer arrived while you were NOT
        looking, and worth nothing when the window is already on screen saying
        the same thing in more detail.
      * the same answer must not be announced twice because a reconnect
        replayed it.

    So this module owns a small policy — cooldown, quiet-while-visible, one
    notification per completed turn — and the platform call is one line at the
    bottom. That split is also what makes it testable here: the policy is
    checked without a desktop, and the platform part is a subprocess this
    sandbox can be told not to run.

WHAT IT DELIBERATELY DOES NOT DO
    It never raises, never blocks, and never waits. A notification is the least
    important thing the program does, and it must not be able to delay the
    answer it is announcing.
"""
from __future__ import annotations

import platform
import shutil
import subprocess
import threading
import time
from typing import Callable

_OS = platform.system()

# The title every notification carries. The assistant's own name is not used
# here on purpose: `memory.config_manager.get_assistant_name()` is user-editable
# and a banner titled "FRIDAY" from an unknown app is worse than one that says
# what it is.
TITLE = "J.A.R.V.I.S"

# Statuses that mean "a turn just finished and there is something to read".
# SPEAKING is deliberately NOT one: it fires before the answer exists, and the
# user hears the answer anyway.
ANNOUNCE_ON = ("LISTENING",)

# One notification per this many seconds, at most. The gap between "JARVIS
# finished" and "JARVIS is listening again" is a fraction of a second, so without
# this every single turn would announce.
COOLDOWN_S = 45.0

# The status that has to have happened in between for a LISTENING to count as
# "a turn finished". A LISTENING that follows a LISTENING is a reconnect or a
# mic change, not an answer.
_TURN_PREFIX = ("THINKING", "SPEAKING")


class Notifier:
    """Policy for status-driven desktop notifications.

    `send` is the platform call, injected so the policy can be tested without a
    desktop and so a caller can supply a better mechanism later. `visible` is a
    callable answering "is the interface on screen right now" — quiet-while-
    visible is the rule that keeps hud mode exactly as quiet as it was.
    """

    def __init__(self, send: Callable[[str, str], bool] | None = None,
                 visible: Callable[[], bool] | None = None,
                 clock: Callable[[], float] = time.monotonic,
                 cooldown: float = COOLDOWN_S,
                 os_name: str | None = None):
        self._send = send or (lambda title, body: send_native(title, body,
                                                             os_name=os_name))
        self._visible = visible or (lambda: False)
        self._clock = clock
        self._cooldown = float(cooldown)
        self._last_at = None            # monotonic time of the last notification
        self._after_turn = False        # a THINKING/SPEAKING happened since
        self._last_status = ""
        self._sent = 0
        self._suppressed = 0

    # ── what happened (for the log and for tests) ────────────────────────────

    @property
    def sent(self) -> int:
        return self._sent

    @property
    def suppressed(self) -> int:
        """How many announcements the policy held back. Reported, not hidden:
        a feature that never fires and a feature that is correctly quiet look
        identical from the outside."""
        return self._suppressed

    # ── the decision ─────────────────────────────────────────────────────────

    def observe(self, status: str, text: str = "") -> bool:
        """Feed a status transition. Returns whether a notification was sent.

        Called from `JarvisUI.set_state`, which runs on several threads, so the
        bookkeeping is behind a lock and the platform call is on a worker
        thread — a notification that blocks would delay the audio it describes.
        """
        status = str(status or "").strip().upper()
        if not status:
            return False

        with _LOCK:
            previous, self._last_status = self._last_status, status

            if status in _TURN_PREFIX:
                self._after_turn = True
                return False

            if status not in ANNOUNCE_ON:
                return False

            # A LISTENING that did not follow an answer is a reconnect, a mic
            # change, or the user waking the assistant. Nothing to announce.
            if not self._after_turn:
                return False
            self._after_turn = False

            if previous == status:
                return False

            try:
                if self._visible():
                    self._suppressed += 1
                    return False
            except Exception as e:              # noqa: BLE001
                # An unknown visibility is treated as "not visible": showing a
                # redundant banner is a smaller failure than swallowing an
                # answer.
                print(f"[JARVIS] Notifier: visibility unknown — "
                      f"{type(e).__name__}: {e}")

            now = self._clock()
            if self._last_at is not None and now - self._last_at < self._cooldown:
                self._suppressed += 1
                return False

            body = (text or "").strip() or "I have finished."
            self._last_at = now
            self._sent += 1

        threading.Thread(target=self._deliver, args=(body,),
                         name="notify", daemon=True).start()
        return True

    def _deliver(self, body: str) -> None:
        try:
            self._send(TITLE, body[:180])
        except Exception as e:                  # noqa: BLE001
            # A notification failing is not worth a dialog, but it is worth a
            # line: "the desktop refused" is the whole answer to "why did I
            # never see anything".
            print(f"[JARVIS] Notifier: delivery failed — "
                  f"{type(e).__name__}: {e}")


_LOCK = threading.Lock()


# ── the platform call ───────────────────────────────────────────────────────

def _commands(os_name: str) -> list[list[str]]:
    """The shell commands to try, best first, for this desktop.

    Windows has no command that is universally present, so it falls through to
    plyer and then to nothing — see `send_native`.
    """
    if os_name == "Darwin":
        return []                           # osascript is built below, it needs
                                            # the text escaped rather than argv
    if os_name == "Linux":
        return [["notify-send", "--urgency=normal", "--expire-time=8000"]]
    return []


def send_native(title: str, body: str, os_name: str | None = None,
                runner: Callable[..., object] | None = None) -> bool:
    """Push one notification. Returns whether anything accepted it.

    Never raises and never blocks longer than the command itself: every
    subprocess is given a timeout and `check=False`, because the exit code of
    `notify-send` is not worth acting on.
    """
    os_name = os_name or _OS
    run = runner or subprocess.run
    for cmd in _commands(os_name):
        if shutil.which(cmd[0]) is None:
            continue
        try:
            run(cmd + [title, body], timeout=5, check=False,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        except Exception as e:              # noqa: BLE001
            print(f"[JARVIS] Notifier: {cmd[0]} failed — "
                  f"{type(e).__name__}: {e}")

    if os_name == "Darwin":
        # `display notification` takes BOTH strings inside quoted AppleScript
        # literals, so both are escaped rather than stripped — stripping them
        # would silently change what the user is told. Escaping only the body
        # left a title with a quote in it producing a malformed script, which
        # osascript rejects while returning success.
        def _quote(text: str) -> str:
            return text.replace("\\", "\\\\").replace('"', '\\"')

        script = (f'display notification "{_quote(body)}" '
                  f'with title "{_quote(title)}"')
        try:
            run(["osascript", "-e", script], timeout=5, check=False,
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        except Exception as e:              # noqa: BLE001
            print(f"[JARVIS] Notifier: osascript failed — "
                  f"{type(e).__name__}: {e}")

    try:
        from plyer import notification as _plyer     # optional, as in reminder.py
        _plyer.notify(title=title, message=body, timeout=8)
        return True
    except Exception as e:                  # noqa: BLE001
        # The last resort, and the commonest outcome on a Windows machine with
        # neither plyer nor win10toast installed. Said out loud once per attempt
        # because silence here is a user wondering why nothing ever appears.
        print(f"[JARVIS] Notifier: no notification backend — "
              f"{type(e).__name__}: {e}")
    return False
