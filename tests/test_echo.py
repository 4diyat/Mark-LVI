"""Hearing our own voice and calling it the user's is a bug with a body count.

WHY THIS FILE EXAMINES WAVEFORMS RATHER THAN MOCKS
    `core/echo.py` decides whether a microphone block is the assistant's own
    echo or a person interrupting. It has three behaviours that only a real
    signal can distinguish, and all three are what a mock would paper over:

      * pure echo, arriving at the same loudness as a voice, must read as ECHO —
        a level test gets exactly this case wrong, which is why the module
        subtracts waveforms instead;
      * a different voice at that same loudness must read as SPEECH, because it
        cannot be cancelled by our own output;
      * a room too reverberant to judge must say so and demand corroboration,
        instead of guessing once and locking in the wrong answer.

    Every test below builds a few blocks of audio with numpy and asks the real
    guard. No microphone, no display, no network — the module has no other
    dependencies.
"""
from __future__ import annotations

import numpy as np
import pytest

from core import echo

SR = 16_000
BLOCK = 1_600          # 100 ms, the size the audio loop uses


def tone(freq: float, level: float = 0.3, seconds: float = 0.1) -> np.ndarray:
    t = np.arange(int(SR * seconds)) / SR
    return (level * np.sin(2 * np.pi * freq * t) * 32767).astype(np.int16)


def voice(level: float = 0.3, seconds: float = 0.1) -> np.ndarray:
    """A crude vowel: a fundamental and two formants, plus a little noise.

    Enough structure to live in different bands from a pure tone, which is the
    only distinction the content check makes.
    """
    n = int(SR * seconds)
    t = np.arange(n) / SR
    signal = (0.6 * np.sin(2 * np.pi * 220 * t)
              + 0.3 * np.sin(2 * np.pi * 900 * t)
              + 0.2 * np.sin(2 * np.pi * 2400 * t))
    signal += np.random.default_rng(0).normal(0, 0.02, n)
    return (level * signal * 32767 / 2).astype(np.int16)


# ── the fingerprint ─────────────────────────────────────────────────────────

def test_band_energies_are_one_number_per_band():
    energies = echo.band_energies(tone(1000), SR)
    assert energies.shape == (len(echo._BAND_EDGES) - 1,)
    assert energies.sum() > 0


def test_a_tone_lands_in_the_band_it_belongs_to():
    """The whole method rests on bands meaning where a sound sits."""
    energies = echo.band_energies(tone(300), SR)
    loudest = int(np.argmax(energies))
    low = echo._BAND_EDGES[loudest] <= 300 < echo._BAND_EDGES[loudest + 1]
    assert low, f"300 Hz landed in band {loudest}, edges {echo._BAND_EDGES}"


def test_a_block_too_short_to_be_a_sound_is_silence_not_a_crash():
    assert echo.band_energies(np.zeros(8, dtype=np.int16), SR).sum() == 0


def test_silence_has_no_energy():
    assert echo.band_energies(np.zeros(BLOCK, dtype=np.int16), SR).sum() == 0


# ── the two signals it must tell apart ─────────────────────────────────────

def test_pure_echo_is_not_the_user():
    """Our own tone, coming back at full strength, must read as our own."""
    guard = echo.EchoGuard()
    played = tone(800, level=0.4)
    # Long enough to warm the estimate AND to have it confirmed 8 times: the
    # gain estimate only counts blocks after the warm-up, so `calibrated` needs
    # both. Ten blocks of a test is cheaper than a documented constant that
    # nothing exercises.
    for i in range(echo._WARMUP + 12):
        guard.note_output(played, SR, level=0.4, when=100.0 + i * 0.1)
        assert guard.is_user_speech(played, SR, level=0.4,
                                    when=100.0 + i * 0.1) is False
    assert guard.calibrated is True
    assert guard.last_similarity > 0.8, guard.last_similarity


def test_a_different_voice_at_the_same_loudness_is_the_user():
    """The case a level test gets wrong: same loudness, different sound.

    This is the test the module's docstring is an argument for. If it fails,
    the assistant talks over the person interrupting it.
    """
    guard = echo.EchoGuard()
    played = tone(800, level=0.4)
    for i in range(echo._WARMUP + 2):
        guard.note_output(played, SR, level=0.4, when=100.0 + i * 0.1)
        guard.is_user_speech(played, SR, level=0.4, when=100.0 + i * 0.1)

    # Same input level, completely different spectrum.
    assert guard.is_user_speech(voice(level=0.4), SR, level=0.4,
                                when=100.0 + 1.2) is True


def test_a_quiet_voice_after_silence_is_the_user():
    """Nothing playing that we know of — anything audible is theirs."""
    guard = echo.EchoGuard()
    assert guard.is_user_speech(voice(0.2), SR, level=0.2) is True


def test_a_silent_block_while_playing_is_not_a_voice():
    guard = echo.EchoGuard()
    guard.note_output(tone(800), SR, level=0.4)
    assert guard.is_user_speech(np.zeros(BLOCK, dtype=np.int16), SR,
                                level=0.0) is False


def test_headphones_are_learned_rather_than_mistaken_for_a_voice():
    """No echo at all is a normal setup, and must not look like someone talking.

    Left unhandled, the window stays empty and the first thing the user says is
    taken for the calibration sample — the guard then treats their voice as the
    norm and goes deaf to it.
    """
    guard = echo.EchoGuard()
    for i in range(echo._WARMUP + 2):
        guard.note_output(tone(800, level=0.4), SR, level=0.4, when=100.0 + i * 0.1)
        assert guard.is_user_speech(np.zeros(BLOCK, dtype=np.int16), SR,
                                    level=0.0, when=100.0 + i * 0.1) is False

    # With the floor learned near zero, a voice is unmistakable.
    assert guard.floor < 0.05
    assert guard.is_user_speech(voice(0.4), SR, level=0.4,
                                when=100.0 + 2.0) is True


def test_a_guard_that_has_run_out_of_history_says_so_instead_of_guessing():
    """`reliable` is about the ROOM; the history window is a separate question.

    The one thing that must not happen in a poor room is a guess on the first
    block after the output stopped: with nothing to compare against, the guard
    answers "cannot tell" and waits for corroboration.
    """
    guard = echo.EchoGuard()
    for i in range(echo._WARMUP + 2):
        guard.note_output(tone(800), SR, level=0.4, when=100.0 + i * 0.1)
        guard.is_user_speech(tone(800), SR, level=0.4, when=100.0 + i * 0.1)
    guard.reset()                      # playback just ended

    assert guard.is_user_speech(voice(0.4), SR, level=0.4,
                                when=100.0 + 30.0) is True


# ── the room decides how much evidence is needed ───────────────────────────

def test_a_reverberant_room_is_declared_unreliable_and_asks_for_more_blocks():
    """Better to say 'I cannot tell' than to guess once and lock it in."""
    guard = echo.EchoGuard()
    guard._floor = echo._UNRELIABLE_FLOOR + 0.01     # what a poor room measures

    assert guard.reliable is False
    assert guard.required_blocks == echo._BLOCKS_NOISY
    assert guard.required_blocks > echo._BLOCKS_NORMAL


def test_a_quiet_room_accepts_a_shorter_run():
    guard = echo.EchoGuard()
    guard._floor = 0.01

    assert guard.reliable is True
    assert guard.required_blocks == echo._BLOCKS_NORMAL


def test_the_threshold_rises_with_the_room_but_never_below_a_floor():
    guard = echo.EchoGuard()
    guard._head = 0.0
    assert guard.threshold == echo._MIN_USER

    guard._head = 0.5
    assert guard.threshold == pytest.approx(0.5 * echo._HEAD_MULT)


def test_the_calibration_flag_needs_real_echo_before_being_trusted():
    guard = echo.EchoGuard()
    assert guard.calibrated is False

    for i in range(echo._WARMUP + 12):
        guard.note_output(tone(800), SR, level=0.4, when=100.0 + i * 0.1)
        guard.is_user_speech(tone(800), SR, level=0.4, when=100.0 + i * 0.1)

    assert guard.calibrated is True
    assert guard.gain > 0, "the echo gain is only learned from confirmed echo"


def test_a_run_too_long_to_be_an_interruption_relearns_the_room():
    """Nobody talks over an assistant for seconds on end.

    A run that long means the room changed under us — the volume went up, the
    headphones came out — so the estimate is thrown away rather than trusted.
    The guard stops asking the model to interrupt, which is the safe direction
    while it re-characterises what it is hearing.

    THE HISTORY HAS TO KEEP UP, TOO. `note_output` is called from playback and
    `is_user_speech` from the microphone callback; a test that only feeds the
    microphone runs out of history, and "nothing we recognise is playing" is
    also a reason to call something a voice. Both streams are stepped together
    here, which is what the audio loop does.
    """
    guard = echo.EchoGuard()
    played = tone(800, level=0.4)
    for i in range(echo._WARMUP + 2):
        guard.note_output(played, SR, level=0.4, when=100.0 + i * 0.1)
        guard.is_user_speech(played, SR, level=0.4, when=100.0 + i * 0.1)

    other = voice(0.4)
    verdicts = []
    for i in range(echo._RELEARN_RUN + 2):
        when = 100.0 + 1.2 + i * 0.1
        guard.note_output(played, SR, level=0.4, when=when)
        verdicts.append(guard.is_user_speech(other, SR, level=0.4, when=when))

    assert verdicts[0] is True             # it did start as an interruption
    assert verdicts[-1] is False           # then the guard gave up and relearned
    assert echo._RELEARN_RUN > echo._BLOCKS_NOISY, (
        "a run shorter than the evidence bar would make the bar unreachable")


# ── bookkeeping must never disturb the audio thread ────────────────────────

def test_reset_clears_history_but_keeps_what_was_learned():
    guard = echo.EchoGuard()
    for i in range(12):
        guard.note_output(tone(800), SR, level=0.4, when=100.0 + i * 0.1)
        guard.is_user_speech(tone(800), SR, level=0.4, when=100.0 + i * 0.1)
    gained, floor = guard.gain, guard.floor

    guard.reset()

    assert guard._hist == []
    assert guard.last_similarity == 0.0
    assert (guard.gain, guard.floor) == (gained, floor)


def test_a_broken_block_cannot_raise_into_the_playback_path():
    """`note_output` runs from playback: a crash there stops the voice."""
    guard = echo.EchoGuard()
    guard.note_output(object(), SR, level=0.4)      # no __array__ at all
    guard.note_output(None, SR, level=0.4)          # and no shape


def test_old_history_is_forgotten():
    """Echo from a second ago explains nothing about this block."""
    guard = echo.EchoGuard()
    for i in range(12):
        guard.note_output(tone(800), SR, level=0.4, when=100.0 + i * 0.1)

    guard.note_output(tone(800), SR, level=0.4, when=200.0)

    assert len(guard._hist) == 1
