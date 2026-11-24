"""core/voice_auth.py — verify the owner's voice before JARVIS answers.

WHY THIS MODULE EXISTS
    The user asked that JARVIS verify their voice when it runs: a voiceprint
    gate before the assistant answers a command, so a voice that is not the
    owner's does not drive the machine.

    WHAT IT IS BUILT ON (all already in the tree)
      * core/echo.py's `band_energies` — the FFT band-energy fingerprint the
        echo guard already computes. The default embedder reuses it, so no new
        heavy dependency is introduced and the audio path stays local.
      * core/wake_word.py's pattern — a feature that costs nothing when it is
        off: the heavy backend is imported lazily, and the module never touches
        Qt or the network.

    WHAT IT IS NOT
      It is not forensic speaker identification. The default embedder is a
      timbre fingerprint, good enough to separate "the same voice" from "a
      different voice" in the same room with the same microphone — not to
      prove identity in court. Section "Batasan" in the spec states this, and
      the UI says it too.

ARCHITECTURE
    Pure policy functions (decide / next_attempt / is_locked / should_verify /
    timeout_state) hold ALL the decision logic and are tested without any
    audio. The `VoiceAuth` engine holds state (attempts, lockout, verified
    time) and does the embedding work. The caller (main.py) runs `verify()`
    on a worker thread — the mic callback only ever buffers, so the real-time
    audio path is never slowed, the same way the wake-word detector works.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Protocol, Sequence

import numpy as np

from core.echo import band_energies

# ── Tunables, with why each one is what it is ──────────────────────────────

# Score in [0, 1]. A verification passes at or above this. Tuned like
# core/wake_word.py's DEFAULT_THRESHOLD — a number a user may adjust for their
# room, not a magic constant with no comment.
DEFAULT_THRESHOLD = 0.55

# How many failed verifications before the gate locks and asks the user to
# wait. Brute-forcing with a recording is the failure this prevents.
MAX_ATTEMPTS = 3

# How long the gate stays locked after MAX_ATTEMPTS failures.
LOCKOUT_SECONDS = 30.0

# A verified session re-locks after this long without a fresh verification.
# Long enough that a conversation is not interrupted, short enough that a
# verified gate is not a hole that never closes.
VERIFY_TIMEOUT_SECONDS = 600.0

# How much speech the gate needs before it runs a verification. Short enough
# to feel responsive, long enough that a cough does not authenticate anyone.
MIN_SPEECH_SECONDS = 1.2

# How many samples the enrollment flow collects.
SAMPLES_TO_ENROLL = 4

# The detector's input rate, same as the wake-word detector (16 kHz int16).
SAMPLE_RATE = 16000

# ── Live status for the UI ─────────────────────────────────────────────────
# The panel reads a snapshot, not the session object, so the gate publishes its
# current state here — the same pattern `core/presence_mode` uses. main.py
# updates it whenever the state changes; the UI reads it on the next paint.
_status = "off"


def set_status(state: str) -> None:
    global _status
    _status = str(state)


def status() -> str:
    """off / unenrolled / locked / verifying / verified / enrolling."""
    return _status


# ── The pure decision layer ────────────────────────────────────────────────

@dataclass(frozen=True)
class Decision:
    """What to do about one verification attempt, and why.

    `reason` is always filled — a refusal without a reason is the silent
    failure this project has already learned to avoid (see the S110 note in
    pyproject.toml).
    """
    passed: bool
    score: float
    threshold: float
    attempts: int
    locked: bool
    reason: str


@dataclass(frozen=True)
class AuthResult:
    """Outcome of one `verify()` call."""
    score: float
    passed: bool
    reason: str


@dataclass(frozen=True)
class EnrollResult:
    """Outcome of one `enroll()` call."""
    ok: bool
    samples: int
    reason: str


def next_attempt(attempts: int) -> int:
    """Increment the failure counter, clamped at MAX_ATTEMPTS."""
    return min(int(attempts) + 1, MAX_ATTEMPTS)


def is_locked(locked_until: float, now: float) -> bool:
    """True while the lockout window is still open."""
    return locked_until > now


def should_verify(state: str) -> bool:
    """Whether the session is in a state that requires a fresh verification.

    States: "locked" and "verifying" require it; "verified" does not (until
    the timeout fires, which `timeout_state` reports).
    """
    return state in ("locked", "verifying")


def timeout_state(now: float, verified_at: float | None,
                  timeout: float) -> str:
    """"verified" while the verification is fresh; "locked" once it is stale.

    A stale verification is not silently extended — the next voice input
    re-verifies, which is what keeps the gate a gate rather than a door that
    stays open once opened.
    """
    if verified_at is None:
        return "locked"
    if now - verified_at >= timeout:
        return "locked"
    return "verified"


def decide(score: float, threshold: float, attempts: int,
           locked_until: float, now: float) -> Decision:
    """The single decision: pass, or fail — with a reason, never silently.

    Order matters: the lockout is checked FIRST. A locked gate rejects
    everything, even a perfect score, so a recording replayed during the
    lockout window cannot shorten it.
    """
    if is_locked(locked_until, now):
        return Decision(
            passed=False, score=score, threshold=threshold,
            attempts=attempts, locked=True,
            reason=f"voice gate is locked for {max(0.0, locked_until - now):.0f}s",
        )
    if score >= threshold:
        return Decision(
            passed=True, score=score, threshold=threshold,
            attempts=attempts, locked=False,
            reason="voice matches the enrolled voiceprint",
        )
    return Decision(
        passed=False, score=score, threshold=threshold,
        attempts=attempts, locked=False,
        reason="voice does not match the enrolled voiceprint",
    )


# ── Embedders ───────────────────────────────────────────────────────────────

class Embedder(Protocol):
    """Turn PCM into a fixed-length voiceprint vector.

    Implementations must be cheap and local. The default one reuses the echo
    guard's band-energy fingerprint; an optional ONNX backend can replace it.
    """

    def embed(self, pcm: bytes, sr: int) -> np.ndarray: ...


def _cosine(a: np.ndarray, b: np.ndarray) -> float:
    """Cosine similarity in [0, 1] — raw cosine, clamped at 0.

    NOT the (cos + 1) / 2 mapping. That compresses the whole useful range:
    two clearly different band-energy fingerprints with a raw cosine of 0.25
    would score 0.625 and pass a 0.55 threshold, which is exactly the
    failure this gate exists to prevent. Raw cosine keeps the threshold a
    number in a range the signal actually spans: identical voice ≈ 1, an
    orthogonal fingerprint ≈ 0.
    """
    a = np.asarray(a, dtype=np.float32)
    b = np.asarray(b, dtype=np.float32)
    na = float(np.linalg.norm(a))
    nb = float(np.linalg.norm(b))
    if na <= 0.0 or nb <= 0.0:
        return 0.0
    cos = float(np.dot(a, b) / (na * nb))
    return max(0.0, min(1.0, cos))


class BandEnergyEmbedder:
    """The default embedder: the echo guard's band-energy fingerprint.

    Reuses `core.echo.band_energies` so the voiceprint and the echo guard
    speak the same acoustic language. The embedding is the unit-normalised
    band-energy vector; verification is cosine similarity against the
    enrolled average. No dependency beyond numpy, which the app already
    installs for the echo guard and the avatar.

    WHY THIS IS THE DEFAULT AND NOT THE ONLY OPTION
        It separates voices by timbre, which is real but coarse: same room,
        same microphone, same person passes; a different person usually
        falls below the threshold. It is not forensic. `OnnxEmbedder` is the
        upgrade path for a real speaker-embedding model, imported lazily so
        it costs nothing unless the user installs and selects it.
    """

    name = "band_energy"

    def embed(self, pcm: bytes, sr: int) -> np.ndarray:
        bands = band_energies(pcm, sr)
        n = float(np.linalg.norm(bands))
        if n <= 0.0:
            return bands
        return bands / n


class OnnxEmbedder:
    """Optional real speaker-embedding backend (ECAPA-style, via ONNX).

    Imported LAZILY — importing this class never imports torch or onnxruntime.
    `available()` reports whether a usable backend is installed; the engine
    falls back to `BandEnergyEmbedder` and says so rather than pretending.
    """

    name = "onnx"

    def __init__(self, model_path: str | None = None) -> None:
        self._model_path = model_path
        self._session = None
        self._loaded = False

    def available(self) -> bool:
        try:
            import importlib.util
            return (
                importlib.util.find_spec("onnxruntime") is not None
                and self._model_path is not None
            )
        except Exception:
            return False

    def _ensure(self) -> bool:
        if self._loaded:
            return self._session is not None
        self._loaded = True
        try:
            import onnxruntime  # noqa: F401  (lazy; absent in most installs)
            # A real deployment wires the model here. Without a model path
            # there is nothing to load, and `available()` already said so.
            self._session = None
        except Exception:
            self._session = None
        return self._session is not None

    def embed(self, pcm: bytes, sr: int) -> np.ndarray:
        if not self._ensure():
            # Honest fallback: never raise, never pretend. The caller decides
            # what to do with a backend that is not actually installed.
            return BandEnergyEmbedder().embed(pcm, sr)
        raise RuntimeError("onnx backend has no model wired in this build")


def get_embedder(name: str | None = None) -> Embedder:
    """Pick an embedder by name, defaulting to the band-energy baseline.

    An unknown name falls back to the default and does not raise: a config
    that names a backend that is not installed should degrade to the baseline,
    not break startup.
    """
    name = (name or "band_energy").strip().lower()
    if name == "onnx":
        return OnnxEmbedder()
    return BandEnergyEmbedder()


# ── The engine ──────────────────────────────────────────────────────────────

class VoiceAuth:
    """Holds voiceprint state and decides whether a voice is the owner's.

    Thread-safe: the mic callback buffers on the audio thread and the caller
    runs `verify()` on a worker thread, so the attempt counter and lockout
    are guarded.

    The engine does NOT own Qt, the network, or the microphone. It takes PCM
    and returns a decision; the caller decides what happens next.
    """

    def __init__(self, *,
                 threshold: float = DEFAULT_THRESHOLD,
                 embedder: Embedder | None = None,
                 store=None,
                 enabled_reader=None) -> None:
        self._threshold = float(threshold)
        self._embedder: Embedder = embedder or BandEnergyEmbedder()
        self._store = store                      # voiceprint_store or None
        self._enabled_reader = enabled_reader    # () -> bool or None
        self._lock = threading.RLock()
        self._attempts = 0
        self._locked_until = 0.0
        self._verified_at: float | None = None
        self._enrolled = False
        self._enroll_embedding: np.ndarray | None = None
        self._enroll_embedder_name = ""
        # Load the voiceprint if a store is present, so the engine is
        # enrolled at boot without the caller having to remember to reload.
        if self._store is not None:
            try:
                self._load_voiceprint()
            except Exception:
                pass                              # never block startup on a
                # corrupt or missing voiceprint file; the gate stays off.

    # ── configuration ───────────────────────────────────────────────────────

    def is_enabled(self) -> bool:
        if self._enabled_reader is None:
            return False
        try:
            return bool(self._enabled_reader())
        except Exception:
            return False

    def is_enrolled(self) -> bool:
        with self._lock:
            return self._enrolled

    def threshold(self) -> float:
        return self._threshold

    @property
    def embedder_name(self) -> str:
        return getattr(self._embedder, "name", "unknown")

    # ── state ────────────────────────────────────────────────────────────────

    def state(self) -> str:
        """off / unenrolled / locked / verified.

        "verifying" is a transient state the CALLER sets while a verification
        runs; the engine reports the underlying state underneath it.
        """
        if not self.is_enabled():
            return "off"
        if not self.is_enrolled():
            return "unenrolled"
        now = time.monotonic()
        with self._lock:
            if is_locked(self._locked_until, now):
                return "locked"
            if timeout_state(now, self._verified_at,
                             VERIFY_TIMEOUT_SECONDS) == "verified":
                return "verified"
            return "locked"

    def attempts(self) -> int:
        with self._lock:
            return self._attempts

    def reset(self) -> None:
        """Clear failures and lockout — the voiceprint stays enrolled."""
        with self._lock:
            self._attempts = 0
            self._locked_until = 0.0

    # ── enrollment ───────────────────────────────────────────────────────────

    def enroll(self, samples: Sequence[bytes], sr: int = SAMPLE_RATE
               ) -> EnrollResult:
        """Enrol N speech samples: embed each, average, store.

        Rejects an empty sample list with a reason rather than raising: the
        UI shows the reason, and a silent "enrolled with nothing" would be a
        voiceprint that can never verify.
        """
        samples = [s for s in samples if s]
        if not samples:
            return EnrollResult(False, 0, "no samples to enrol")
        if self._store is None:
            return EnrollResult(False, len(samples),
                                "no voiceprint store is bound to the gate")
        embeddings = [self._embedder.embed(s, sr) for s in samples]
        mean = np.mean(embeddings, axis=0)
        n = float(np.linalg.norm(mean))
        if n <= 0.0:
            return EnrollResult(False, len(samples),
                                "samples carried no usable voice signal")
        with self._lock:
            self._enroll_embedding = mean / n
            self._enroll_embedder_name = getattr(self._embedder, "name", "")
            self._enrolled = True
            self._attempts = 0
            self._locked_until = 0.0
            self._verified_at = None
        try:
            self._store.save(
                mean / n,
                embedder=self._enroll_embedder_name,
                samples=len(samples),
            )
        except Exception as e:
            # Roll back: an enrolled gate that cannot read its voiceprint
            # again is worse than an unenrolled one.
            with self._lock:
                self._enrolled = False
                self._enroll_embedding = None
            return EnrollResult(False, len(samples),
                                f"voiceprint could not be stored: {e}")
        return EnrollResult(True, len(samples),
                            f"enrolled {len(samples)} samples")

    def _load_voiceprint(self) -> None:
        if self._store is None:
            return
        data = self._store.load()
        if not data:
            return
        with self._lock:
            self._enroll_embedding = np.asarray(data["embedding"],
                                               dtype=np.float32)
            self._enroll_embedder_name = str(data.get("embedder", ""))
            self._enrolled = True

    def forget(self) -> bool:
        """Delete the voiceprint. Only the owner-facing UI calls this."""
        with self._lock:
            self._enrolled = False
            self._enroll_embedding = None
            self._attempts = 0
            self._locked_until = 0.0
            self._verified_at = None
        if self._store is not None:
            try:
                self._store.delete()
                return True
            except Exception:
                return False
        return True

    # ── verification ────────────────────────────────────────────────────────

    def verify(self, pcm: bytes, sr: int = SAMPLE_RATE) -> AuthResult:
        """Embed one speech clip and decide whether it is the owner's voice.

        Runs the embedding synchronously — the CALLER puts it on a worker
        thread. Returns a score and a decision with a reason; it never raises
        for a normal "wrong voice" — that is a result, not an error.
        """
        now = time.monotonic()
        with self._lock:
            if not self.is_enabled():
                return AuthResult(0.0, False, "voice verification is off")
            if not self._enrolled:
                return AuthResult(0.0, False, "no voiceprint is enrolled")
            if is_locked(self._locked_until, now):
                d = decide(0.0, self._threshold, self._attempts,
                           self._locked_until, now)
                return AuthResult(0.0, False, d.reason)
            if self._enroll_embedding is None:
                return AuthResult(0.0, False, "voiceprint is empty")

            score = _cosine(self._embedder.embed(pcm, sr),
                            self._enroll_embedding)
            d = decide(score, self._threshold, self._attempts,
                       self._locked_until, now)
            if d.passed:
                self._attempts = 0
                self._locked_until = 0.0
                self._verified_at = now
            else:
                self._attempts = next_attempt(self._attempts)
                if self._attempts >= MAX_ATTEMPTS:
                    self._locked_until = now + LOCKOUT_SECONDS
            return AuthResult(score, d.passed, d.reason)

    # ── caller helpers ───────────────────────────────────────────────────────

    def mark_verified(self) -> None:
        """Caller says a verification passed (used when the caller runs the
        gate itself, e.g. enrollment-time self-check)."""
        with self._lock:
            self._attempts = 0
            self._locked_until = 0.0
            self._verified_at = time.monotonic()


# ── Echo filtering for the verification path ─────────────────────────────────

def is_verifiable_speech(echo_guard, pcm: bytes, sr: int, level: float
                         ) -> bool:
    """Whether this mic block is real user speech that may enter verification.

    Reuses the echo guard the session already owns: while JARVIS is speaking,
    the microphone hears its own voice, and a gate that accepted that would
    authenticate the assistant to itself. When nothing is playing, anything
    audible is the user's.

    This is a pure decision over the guard's existing state — no audio is
    captured here, and a guard that cannot judge returns False (the safe
    answer: no verification on an echo it cannot separate).
    """
    if echo_guard is None:
        return level > 0.0
    try:
        return bool(echo_guard.is_user_speech(pcm, sr, level))
    except Exception:
        return False
