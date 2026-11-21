"""What the app SAYS about the microphone, as opposed to what it does.

`_listen_audio` is 155 lines of callback and device loop; the sentences it emits
are a handful of lines inside it, and they are what the user actually
experiences. Three of them were wrong in ways nobody could see from reading the
loop:

  * "Microphone found — listening again" could be SKIPPED. The flag that gated
    it, `_mic_recovered`, was set when a device appeared and never cleared, so
    on the second loss-and-return the app silently resumed listening and the
    user was left waiting for a confirmation that never came.

  * "Mic stream open" repeated on every recovery — a debug print behaving like a
    status line, once per device flap.

  * The failure sentence was suppressed while `_deaf` was set, which is right
    (a line every two seconds makes a transcript unreadable) but had the side
    effect that a DIFFERENT failure right after a loss was never named.

So the rule is here, as data and as two small functions, and `main.py` asks
rather than decides.

WHAT THIS IS NOT
    It is not the device loop and it never opens anything. Whether a device
    exists is `core/audio_devices.py`; whether it works is the host's answer.
    This module only decides what is worth saying, given what just happened.
"""
from __future__ import annotations

from dataclasses import dataclass

# States the UI is painted with, kept as names because a typo in a bare string
# is a silently blank HUD.
NO_MIC = "NO MIC"
LISTENING = "LISTENING"
SLEEPING = "SLEEPING"


@dataclass(frozen=True)
class MicEvent:
    """What just happened to the microphone.

    `recovered_first_time` is separate from `recovered` because a microphone
    that comes back after a loss is news ONCE. Repeating it every time the device
    flaps turns the activity log into a metronome.
    """
    opened: bool = False             # a stream just opened
    lost: bool = False               # a stream ended or failed
    recovered: bool = False          # opened after having been lost
    recovered_first_time: bool = True
    problem: str = ""                # the host's sentence, for the log
    stream_ended: bool = False       # distinguished from "could not open"


def state_for(awake: bool) -> str:
    """The state a working microphone implies.

    NOT always LISTENING: with the wake word on, the assistant comes up asleep
    and the microphone is gated, so a recovered device must return the HUD to
    SLEEPING rather than claim it is listening to someone it is still ignoring.
    """
    return LISTENING if awake else SLEEPING


def messages(event: MicEvent) -> tuple[str | None, str | None]:
    """`(log_line, print_line)` for what just happened. Each may be None.

    A log line is for the user in the activity panel; a print line is for the
    terminal. They are returned together because they are always about the same
    event, and splitting them was how one of them went stale.
    """
    if event.opened:
        # Every recovery is announced, not just the first. The flag that used to
        # gate this was set and never cleared, so the SECOND loss-and-return
        # resumed listening in silence. `recovered_first_time` changes what is
        # PRINTED (the terminal already showed the loss once), never whether the
        # user is told.
        if event.recovered:
            line = ("[JARVIS] 🎤 Input device appeared, stream open"
                    if event.recovered_first_time
                    else "[JARVIS] 🎤 Mic stream reopened")
            return "SYS: Microphone found — listening again.", line
        return None, "[JARVIS] 🎤 Mic stream open"

    if event.stream_ended:
        return "SYS: Microphone stream stopped — retrying.", None

    if event.lost:
        detail = f" ({event.problem})" if event.problem else ""
        return (f"SYS: The microphone could not start or stopped{detail}. "
                f"I will keep retrying; typing still works.", None)
    return None, None


def should_repeat_failure(said_already: bool) -> bool:
    """Is another copy of the failure sentence worth saying?

    No, while the same absence is still being retried every two seconds — a log
    line at that rate is how a transcript becomes unreadable. Yes, the first time
    it happens.
    """
    return not said_already


__all__ = ["LISTENING", "MicEvent", "NO_MIC", "SLEEPING", "messages",
           "should_repeat_failure", "state_for"]
