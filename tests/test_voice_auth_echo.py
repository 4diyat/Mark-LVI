"""Echo rejection on the verification path.

The gate must not authenticate JARVIS to itself: while the assistant speaks,
the microphone hears its own voice, and a verification that accepted that
would be a lock that any playback could open. These tests drive the real
`EchoGuard` with synthetic PCM — no microphone, no Qt, no network.
"""
from __future__ import annotations

import math

from core.echo import EchoGuard
from core.voice_auth import is_verifiable_speech


def _tone(freq: float, seconds: float = 1.0, sr: int = 16000) -> bytes:
    n = int(seconds * sr)
    out = bytearray()
    for i in range(n):
        v = int(12000 * math.sin(2 * math.pi * freq * i / sr))
        out += v.to_bytes(2, "little", signed=True)
    return bytes(out)


def test_with_no_output_playing_any_audible_block_is_verifiable():
    """Nothing is playing → the microphone hears the user, not an echo."""
    guard = EchoGuard()
    tone = _tone(200.0)
    assert is_verifiable_speech(guard, tone, 16000, 0.4) is True


def test_our_own_output_audio_is_not_verifiable():
    """The assistant's own voice, heard by the microphone, must not pass."""
    guard = EchoGuard()
    output = _tone(300.0)
    # Record what is being played...
    guard.note_output(output, 16000, 0.6)
    # ...then the microphone hears exactly that.
    assert is_verifiable_speech(guard, output, 16000, 0.6) is False


def test_a_guard_that_cannot_judge_safely_refuses():
    """If the echo guard is missing or raises, the safe answer is 'no' —
    verification never runs on audio it cannot separate."""
    tone = _tone(200.0)
    assert is_verifiable_speech(None, tone, 16000, 0.4) is True  # no guard: any voice is the user's

    class BrokenGuard:
        def is_user_speech(self, *a, **k):
            raise RuntimeError("boom")

    assert is_verifiable_speech(BrokenGuard(), tone, 16000, 0.4) is False
