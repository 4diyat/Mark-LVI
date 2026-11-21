"""Should the assistant stop talking because somebody started to?

WHY THIS IS A MODULE AND NOT SIX LINES IN THE MICROPHONE CALLBACK
    The decision has three inputs, one of which is learned at runtime, and it
    is wrong in two directions at once. Too eager and the assistant cuts itself
    off because the room echoed its own sentence; too cautious and a person
    says "stop" four times and still hears the rest of the paragraph. A rule
    that can be wrong in both directions is exactly the kind of thing that has
    to be written down, given a name, and tested — not inlined in an audio
    callback where nobody can compare two runs.

    There is a second reason: `main.py` already carries a note where this used
    to be attempted, saying it was removed until it could be tried on real
    hardware. The geometry is settled here; the hardware part is a manual check
    in `docs/verification.md`. Nothing in this file touches a microphone.

WHAT IT IS NOT
    Not speech recognition. It does not try to hear the word "stop". A small
    vocabulary needs a model, a language, and a wake word already covers the
    addressing problem; trying to recognise four words from a room recording
    would be the least reliable part of the app. What it detects is *a person
    speaking over the assistant*, which is a question the echo guard can answer
    and the vocabulary cannot.

WHAT MAKES IT SAFE
    Three gates, and all three have to agree:

    1. The assistant must actually be speaking. When it is not, talking is the
       conversation — interrupting there would end every turn the user starts.
    2. The block must be the USER, per `EchoGuard.is_user_speech`, which is the
       existing, calibrated answer to "is this our own voice". This module never
       second-guesses it with a raw level test.
    3. It must be sustained: `required_blocks` consecutive positive blocks,
       which the guard already widens when the room is too reverberant to judge
       confidently. And it must be CONSECUTIVE from the *last frame* — a run
       that starts on frame f never completes on frame g, and say g is after a
       gap, because that is counting frames rather than listening to speech.

    The whole thing also refuses to act before the guard has calibrated
    (`EchoGuard.calibrated`). A guard that has not heard its own echo yet calls
    the first loud block a voice, and the first loud block of a reply is the
    reply.

ONE CALL SITE
    `barge_in()` is the whole of it: `main.py`'s microphone callback passes one
    block and the callable to stop with. The class it lives in has a line
    ceiling enforced by `tests/test_ui_split.py`, and that ceiling is the reason
    the decision is not inlined there — a rule this easy to get wrong needs to
    be readable on its own, and a 2,400-line class is not.

THE FLOOR
    Whatever else is true, a block quieter than `MIN_LEVEL` is room noise. It
    resets the run rather than merely not adding to it: a pause in the middle
    of "stop it" means the user stopped talking, and the count should not
    survive a silence it did not hear.
"""
from __future__ import annotations

# Below this, a block is room noise — the same floor the echo guard uses to
# decide it has nothing to judge (`core/echo.py:_MIN_LEVEL`). Kept here as a
# number rather than read from there: this is the floor for an INTERRUPT
# decision, and the two are allowed to diverge.
MIN_LEVEL = 0.06

# What the guard always needs, even at its most confident.
MIN_BLOCKS = 2


class VoiceInterrupt:
    """Decides, block by block, whether speech should stop.

    One instance per session. `feed()` from the microphone callback (an audio
    thread), `reset()` when playback starts, ends, or the session is torn down.
    Every method is cheap, allocation-free and never raises: an audio callback
    that throws is a microphone that dies.
    """

    def __init__(self, guard) -> None:
        self._guard = guard
        self._run = 0
        self._armed = False
        self._last_fired = 0.0

    # ── state, for the log and for tests ────────────────────────────────────

    @property
    def run(self) -> int:
        """Consecutive user-speech blocks right now."""
        return self._run

    @property
    def armed(self) -> bool:
        """True when a completed run would actually stop the assistant."""
        return self._armed

    def arm(self) -> None:
        """Playback started: begin watching, with a clean count.

        Called when the assistant starts speaking rather than when it stops,
        because the count has to be zero at the moment speech begins — carrying
        a partial run across a whole answer would make the next answer's first
        two blocks enough.
        """
        self._armed = True
        self._run = 0

    def disarm(self) -> None:
        """Playback stopped: nothing to interrupt."""
        self._armed = False
        self._run = 0

    def reset(self) -> None:
        self._armed = False
        self._run = 0

    # ── the decision ────────────────────────────────────────────────────────

    def feed(self, indata, sample_rate: int, level: float,
             now: float | None = None) -> bool:
        """One microphone block. True exactly once, when speech should stop.

        Returns True at the END of a completed run and then disarms: a single
        interruption may fire once, and re-arming is the playback path's job
        (the assistant is no longer speaking, so there is nothing to stop).
        """
        try:
            if not self._armed:
                return False

            # Silence breaks the run. Not merely "does not extend it": a pause
            # in the middle of speech is the user having finished, and a count
            # that survives it would eventually fire on two unrelated sounds.
            if float(level) < MIN_LEVEL:
                self._run = 0
                return False

            # The guard is the only thing that can tell the user from our own
            # echo, and an uncalibrated guard mistakes the start of a reply for
            # a voice. So: no judging until it has heard itself at least once.
            if not getattr(self._guard, "calibrated", False):
                return False

            if not self._guard.is_user_speech(indata, sample_rate, level, now):
                self._run = 0
                return False

            self._run += 1
            need = max(MIN_BLOCKS, int(getattr(self._guard, "required_blocks", MIN_BLOCKS)))
            if self._run < need:
                return False

            self._run = 0
            self._armed = False
            self._last_fired = float(now or 0.0)
            return True
        except Exception:                 # noqa: BLE001 — an audio thread
            self._run = 0
            return False


def describe(decider: VoiceInterrupt) -> str:
    """One line for the log, used when an interruption actually fires.

    The numbers matter after the fact: "it stopped for no reason" and "it did
    not stop" are both diagnosed from the run length and the guard's own state,
    and neither is recoverable once the moment has passed.
    """
    guard = getattr(decider, "_guard", None)
    blocks = getattr(guard, "required_blocks", "?")
    floor = getattr(guard, "floor", None)
    where = f", echo floor {floor:.2f}" if isinstance(floor, float) else ""
    return (f"voice interrupt after {blocks} sustained blocks"
            f"{where}{'' if getattr(guard, 'reliable', True) else ', noisy room'}")


def arm_for(decider: VoiceInterrupt | None, speaking: bool) -> None:
    """Keep the decider in step with the speaking flag. Never raises.

    Called from `set_speaking`, which runs on the playback path: a failure here
    must not be able to stop audio, so it is caught and dropped rather than
    propagated. Kept in this module so `main.py` carries one line, not six.
    """
    if decider is None:
        return
    try:
        decider.arm() if speaking else decider.disarm()
    except Exception as e:                # noqa: BLE001 — an audio path
        from core.logbook import get as _log
        _log(__name__).debug("could not arm the barge-in counter: %s", e)


def barge_in(decider: VoiceInterrupt | None, indata, sample_rate: int,
             level: float, stop) -> bool:
    """Feed one block and stop the answer if it completes a run.

    The whole call site, in one function: `main.py`'s microphone callback is on
    the hot path and inside a class that has a line ceiling, and the reasoning
    behind the decision lives in this module's docstring where it can be read
    without scrolling through a 2,400-line class.

    `stop` is `JarvisLive.interrupt` — the same call the HUD's stop button
    makes, so there is one way to stop an answer rather than two.

    Returns True when an interruption was requested.
    """
    if decider is None:
        return False
    if not decider.feed(indata, sample_rate, level):
        return False
    try:
        print(f"[JARVIS] ✋ {describe(decider)}")
    except Exception:                     # noqa: BLE001 — an audio thread
        decider._last_fired = decider._last_fired   # the decision still stands
    stop()
    return True
