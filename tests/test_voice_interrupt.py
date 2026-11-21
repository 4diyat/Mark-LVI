"""Barge-in: stop talking when a person talks over you, and only then.

The whole risk is in the word "only". A decider that fires too easily makes the
assistant cut itself off on its own echo — every answer dies after three words.
One that fires too rarely makes the user repeat "stop" and still hear the rest
of the paragraph. Neither is visible from inside a unit test of `EchoGuard`;
both are visible here, because this module is the decision and nothing else.
"""
from __future__ import annotations

from core import voice_interrupt as vi


class Guard:
    """A stand-in for EchoGuard with the three properties that matter."""

    def __init__(self, speech=True, calibrated=True, blocks=5, reliable=True,
                 floor=0.10):
        self.speech = speech
        self.calibrated = calibrated
        self.required_blocks = blocks
        self.reliable = reliable
        self.floor = floor
        self.asked = 0

    def is_user_speech(self, indata, sample_rate, level, now=None):
        self.asked += 1
        return self.speech


def block():
    return b"\x00\x00" * 512


def feed(decider, guard, count, level=0.5):
    """Feed `count` blocks; return how many were needed to fire, or 0.

    The count is within THIS call, so `feed(..., 5) == 5` means "the fifth of
    these five", and a following `feed(..., 1) == 1` means "the very next one".
    """
    for i in range(1, count + 1):
        if decider.feed(block(), 16_000, level):
            return i
    return 0


# ── the gate that matters most ──────────────────────────────────────────────

def test_nothing_is_interrupted_when_the_assistant_is_silent():
    """Talking is the conversation when nobody is talking over anything. An
    interruption here would end every turn the user starts."""
    guard = Guard()
    decider = vi.VoiceInterrupt(guard)
    assert feed(decider, guard, 50) == 0
    assert guard.asked == 0, "the guard must not even be consulted"


def test_disarming_stops_all_watching():
    guard = Guard()
    decider = vi.VoiceInterrupt(guard)
    decider.arm()
    decider.disarm()
    assert feed(decider, guard, 50) == 0


def test_arming_zeroes_the_count_from_the_previous_answer():
    """Otherwise a run left over from the last answer means two blocks are
    enough at the start of the next one — and the assistant stops on the first
    syllable of the reply."""
    guard = Guard(blocks=5)
    decider = vi.VoiceInterrupt(guard)
    decider.arm()
    assert feed(decider, guard, 4) == 0      # four of five, not yet
    decider.arm()                            # a NEW answer starts
    assert feed(decider, guard, 1) == 0      # one block is not five
    assert decider.run == 1


# ── the evidence ────────────────────────────────────────────────────────────

def test_a_completed_run_of_user_speech_fires_exactly_once():
    guard = Guard(blocks=5)
    decider = vi.VoiceInterrupt(guard)
    decider.arm()
    assert feed(decider, guard, 4) == 0
    assert feed(decider, guard, 1) == 1, "the fifth consecutive block is the one"
    assert feed(decider, guard, 20) == 0, "one interruption per answer"


def test_our_own_echo_never_counts():
    """The echo guard says no; this module is not allowed a second opinion."""
    guard = Guard(speech=False)
    decider = vi.VoiceInterrupt(guard)
    decider.arm()
    assert feed(decider, guard, 200) == 0


def test_an_uncalibrated_guard_is_not_allowed_to_decide():
    """Before the guard has heard its own echo, the first loud block of a reply
    reads as a voice — so it would interrupt the assistant with itself."""
    guard = Guard(calibrated=False)
    decider = vi.VoiceInterrupt(guard)
    decider.arm()
    assert feed(decider, guard, 200) == 0
    guard.calibrated = True
    assert feed(decider, guard, 5) == 5     # all five, from a standing start


def test_silence_breaks_the_run_instead_of_merely_pausing_it():
    """A gap in the middle of speech means the user stopped. Carrying the count
    across it eventually fires on two unrelated sounds minutes apart."""
    guard = Guard(blocks=5)
    decider = vi.VoiceInterrupt(guard)
    decider.arm()
    assert feed(decider, guard, 4) == 0
    assert decider.feed(block(), 16_000, 0.01) is False   # a pause
    assert decider.run == 0
    assert feed(decider, guard, 4) == 0                   # must start over
    assert feed(decider, guard, 1) == 1


def test_a_noisy_room_demands_more_evidence():
    """`required_blocks` is the guard's own answer for THIS room, and it is
    higher when the room cannot be judged confidently."""
    reliable = Guard(blocks=5, reliable=True, floor=0.05)
    noisy = Guard(blocks=12, reliable=False, floor=0.60)
    for guard, expected in ((reliable, 5), (noisy, 12)):
        decider = vi.VoiceInterrupt(guard)
        decider.arm()
        assert feed(decider, guard, expected - 1) == 0
        assert feed(decider, guard, 1) == 1, f"needed {expected} blocks"


def test_the_floor_is_a_floor():
    guard = Guard(blocks=5)
    decider = vi.VoiceInterrupt(guard)
    decider.arm()
    assert feed(decider, guard, 50, level=vi.MIN_LEVEL - 0.001) == 0
    assert guard.asked == 0, "room noise is not worth asking the guard about"


def test_a_guard_without_required_blocks_still_needs_two():
    class Bare:
        calibrated = True

        def is_user_speech(self, *a, **k):
            return True

    decider = vi.VoiceInterrupt(Bare())
    decider.arm()
    assert decider.feed(block(), 16_000, 0.5) is False
    assert decider.feed(block(), 16_000, 0.5) is True


# ── failure on the audio thread ─────────────────────────────────────────────

def test_a_guard_that_raises_does_not_take_the_microphone_with_it():
    class Broken:
        calibrated = True
        required_blocks = 5

        def is_user_speech(self, *a, **k):
            raise RuntimeError("fft failure")

    decider = vi.VoiceInterrupt(Broken())
    decider.arm()
    assert feed(decider, Broken(), 20) == 0
    assert decider.run == 0


def test_a_decider_of_none_is_not_an_exception():
    """`barge_in` is called from the mic callback with whatever the object
    holds; a missing decider must be a no-op, not a crash on every block."""
    calls = []
    assert vi.barge_in(None, block(), 16_000, 0.5, lambda: calls.append(1)) is False
    assert calls == []


def test_the_stop_callback_is_the_only_thing_that_stops_anything():
    guard = Guard(blocks=2)
    decider = vi.VoiceInterrupt(guard)
    decider.arm()
    stops = []
    assert vi.barge_in(decider, block(), 16_000, 0.5, lambda: stops.append("stop")) is False
    assert vi.barge_in(decider, block(), 16_000, 0.5, lambda: stops.append("stop")) is True
    assert stops == ["stop"]


def test_describe_says_what_actually_happened():
    """After the fact, "it stopped for no reason" and "it would not stop" are
    both diagnosed from this line, and the moment is gone by then."""
    line = vi.describe(vi.VoiceInterrupt(Guard(blocks=12, reliable=False, floor=0.61)))
    assert "12" in line and "noisy" in line


# ── it is actually wired, and in the one place it belongs ───────────────────

def test_the_microphone_callback_uses_it_while_speaking():
    from pathlib import Path
    src = (Path(__file__).resolve().parents[1] / "main.py").read_text(encoding="utf-8")
    assert "barge_in(self._barge_in" in src
    # Inside the `if jarvis_speaking:` branch — the only place it may fire.
    start = src.index("if jarvis_speaking:")
    branch = src[start:src.index("return", src.index("barge_in(self._barge_in"))]
    assert "barge_in(self._barge_in" in branch
    # And it stops through the same call the HUD's button makes.
    assert "self.interrupt)" in src


def test_the_counter_is_armed_from_the_speaking_flag():
    """An answer starting is the only moment "is there anything to interrupt"
    changes, so it is the only place the counter is reset."""
    from pathlib import Path
    src = (Path(__file__).resolve().parents[1] / "main.py").read_text(encoding="utf-8")
    start = src.index("def set_speaking(self, value: bool):")
    body = src[start:src.index("def ", start + 10)]
    assert "arm_for(" in body
