"""The VoiceAuth engine, driven by a controlled fake embedder.

The policy is tested in test_voice_auth.py; here the engine's state (enroll,
attempts, lockout, timeout, forget) is exercised with an embedder whose
vectors are chosen by the test, so verification outcomes are deterministic.
The real `BandEnergyEmbedder` gets one sanity test with synthetic tones at the
end, to prove the pipeline works on actual PCM — not just on fakes.
"""
from __future__ import annotations

import numpy as np

from core.voice_auth import (
    MAX_ATTEMPTS,
    VERIFY_TIMEOUT_SECONDS,
    VoiceAuth,
)


class FakeEmbedder:
    """Embedder that returns a fixed vector for a given label.

    `embed` looks at a per-call hook so a test can make the "wrong voice"
    return a different vector from the enrolled one.
    """

    name = "fake"

    def __init__(self, owner=None, stranger=None):
        self.owner = np.asarray(owner if owner is not None else [1.0, 0.0, 0.0],
                                dtype=np.float32)
        self.stranger = np.asarray(stranger if stranger is not None else [0.0, 1.0, 0.0],
                                   dtype=np.float32)
        self.use_stranger = False

    def embed(self, pcm, sr):
        vec = self.stranger if self.use_stranger else self.owner
        n = float(np.linalg.norm(vec))
        return vec / n if n > 0 else vec


class FakeStore:
    """Minimal in-memory stand-in for the voiceprint store."""

    def __init__(self):
        self.saved = None

    def load(self):
        return self.saved

    def save(self, embedding, *, embedder, samples):
        self.saved = {"embedder": embedder, "samples": samples,
                      "embedding": list(embedding)}

    def delete(self):
        self.saved = None
        return True


def _engine(store=None, enabled=True):
    embedder = FakeEmbedder()
    eng = VoiceAuth(embedder=embedder, store=store or FakeStore(),
                    enabled_reader=lambda: enabled)
    return eng, embedder


def test_off_by_default_without_a_reader():
    eng = VoiceAuth(store=FakeStore())
    assert eng.is_enabled() is False
    assert eng.state() == "off"


def test_unenrolled_when_enabled_but_no_voiceprint():
    eng, _ = _engine()
    assert eng.is_enabled() is True
    assert eng.is_enrolled() is False
    assert eng.state() == "unenrolled"
    r = eng.verify(b"\x00\x00")
    assert r.passed is False
    assert "no voiceprint" in r.reason


def test_enroll_then_verify_passes():
    store = FakeStore()
    eng, embedder = _engine(store)
    res = eng.enroll([b"a", b"b", b"c"], sr=16000)
    assert res.ok is True
    assert eng.is_enrolled() is True
    assert eng.state() == "locked"          # enrolled but not yet verified

    r = eng.verify(b"speech")
    assert r.passed is True
    assert eng.state() == "verified"


def test_wrong_voice_fails_and_counts_attempts():
    eng, embedder = _engine()
    eng.enroll([b"a", b"b"], sr=16000)

    embedder.use_stranger = True
    r = eng.verify(b"stranger speech")
    assert r.passed is False
    assert "does not match" in r.reason
    assert eng.attempts() == 1


def test_lockout_after_max_attempts():
    eng, embedder = _engine()
    eng.enroll([b"a", b"b"], sr=16000)
    embedder.use_stranger = True

    for _ in range(MAX_ATTEMPTS):
        r = eng.verify(b"stranger")
        assert r.passed is False

    # The next attempt — even with the right voice — is locked out.
    embedder.use_stranger = False
    r = eng.verify(b"owner")
    assert r.passed is False
    assert "locked" in r.reason
    assert eng.state() == "locked"


def test_reset_clears_attempts_but_keeps_enrollment():
    eng, embedder = _engine()
    eng.enroll([b"a", b"b"], sr=16000)
    embedder.use_stranger = True
    eng.verify(b"stranger")
    assert eng.attempts() == 1

    eng.reset()
    assert eng.attempts() == 0
    assert eng.is_enrolled() is True


def test_forget_removes_the_voiceprint():
    store = FakeStore()
    eng, _ = _engine(store)
    eng.enroll([b"a", b"b"], sr=16000)
    assert eng.is_enrolled() is True
    assert eng.forget() is True
    assert eng.is_enrolled() is False
    assert store.saved is None


def test_enroll_rejects_empty_samples():
    eng, _ = _engine()
    res = eng.enroll([], sr=16000)
    assert res.ok is False
    assert "no samples" in res.reason


def test_verified_state_expires_after_timeout():
    eng, _ = _engine()
    eng.enroll([b"a", b"b"], sr=16000)
    eng.verify(b"owner")
    assert eng.state() == "verified"

    # Roll the verified timestamp back past the window.
    eng._verified_at = eng._verified_at - VERIFY_TIMEOUT_SECONDS - 1
    assert eng.state() == "locked"


def test_enroll_rolls_back_when_store_fails():
    class BrokenStore:
        def load(self):
            return None
        def save(self, *a, **k):
            raise OSError("disk on fire")
        def delete(self):
            return True

    eng, _ = _engine(store=BrokenStore())
    res = eng.enroll([b"a", b"b"], sr=16000)
    assert res.ok is False
    assert "could not be stored" in res.reason
    assert eng.is_enrolled() is False       # rolled back, not half-enrolled


# ── Real embedder sanity check with synthetic PCM ──────────────────────────

def _tone(freq: float, seconds: float = 1.5, sr: int = 16000) -> bytes:
    """A sine tone as int16 PCM — distinct frequencies sit in distinct bands,
    so the band-energy fingerprint separates them."""
    import math
    n = int(seconds * sr)
    out = bytearray()
    for i in range(n):
        v = int(12000 * math.sin(2 * math.pi * freq * i / sr))
        out += v.to_bytes(2, "little", signed=True)
    return bytes(out)


def test_real_embedder_separates_distinct_voices():
    from core.voice_auth import BandEnergyEmbedder, VoiceAuth
    store = FakeStore()
    embedder = BandEnergyEmbedder()
    eng = VoiceAuth(embedder=embedder, store=store, enabled_reader=lambda: True)

    # The "owner" enrols a low, warm tone; a "stranger" is a high, bright one.
    owner_a = _tone(180.0)
    owner_b = _tone(190.0)
    res = eng.enroll([owner_a, owner_b], sr=16000)
    assert res.ok is True

    r = eng.verify(_tone(185.0), sr=16000)
    assert r.passed is True, r.reason

    stranger = eng.verify(_tone(1200.0), sr=16000)
    assert stranger.passed is False, stranger.reason
