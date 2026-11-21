"""The transcript and the microphone's loudness — the two numbers the UI needs.

WHY THESE MOVED OUT OF main.py
    Both were reachable only through `import main`, which needs the Live SDK,
    sounddevice, numpy and Qt, so neither had a single test. They are the two
    places where incoming audio becomes something the user sees:

      * `clean_transcript` / `is_repeat_chunk` decide what appears in the
        activity log. Both have history here — control tokens leaking into the
        log as literal `<ctrl23>`, and the server re-sending the tail of an
        answer across the several turn_completes one tool-using turn produces.
      * `pcm_level` maps raw int16 PCM to the 0..1 number the HUD waveform
        draws. A function that raises on a malformed block takes down the
        receive loop that is playing the answer.

    Neither needs a session to test, and both are pure once numpy is present.
    so they live here and `main.py` keeps the wiring.

WHAT IS DELIBERATELY NOT HERE
    `pcm_visemes` — the formant analysis for the avatar's mouth — stays in the
    repository's speech path (`core/speech_sync.py`, `core/viseme.py`) because
    it is a signal-processing concern with its own review history. This module
    is the small, boring, testable layer underneath the UI, not a new home for
    everything audio.
"""
from __future__ import annotations

import re

import numpy as np

# ── Loudness ────────────────────────────────────────────────────────────────
# RMS below which 16-bit PCM is treated as room silence; above _LEVEL_FULL it
# is treated as full scale. Both are measured against real capture, not guessed:
# a quiet talker in a normal room sits well below _LEVEL_FULL, and the bars
# still move for them because the floor is room tone rather than zero.
LEVEL_FLOOR = 60.0
LEVEL_FULL = 2600.0


def pcm_level(samples) -> float:
    """Map a block of int16 PCM samples to a 0.0–1.0 loudness level.

    Accepts an int16 array (what the audio callbacks actually pass) and also raw
    PCM `bytes`, which is what the receive path sometimes holds. The `bytes`
    case is decoded explicitly: `np.asarray(b"...", dtype=np.float32)` raises,
    so the old code returned 0.0 for every block of that shape — the waveform
    and the echo guard were both handed a permanent silence that looked like a
    legitimate measurement.

    Returns 0.0 on empty or invalid input so it can NEVER raise: this runs
    inside the microphone callback and the receive loop, where an exception
    costs the session rather than one bar of the waveform.
    """
    try:
        if isinstance(samples, (bytes, bytearray, memoryview)):
            raw = bytes(samples)
            if len(raw) < 2:
                return 0.0
            # Odd byte counts cannot be int16; the trailing byte is dropped
            # rather than handed to numpy as an error.
            x = np.frombuffer(raw[:len(raw) - (len(raw) % 2)],
                              dtype=np.int16).astype(np.float32)
        else:
            x = np.asarray(samples, dtype=np.float32)
        if x.size == 0:
            return 0.0
        rms = float(np.sqrt(np.mean(x * x)))
    except Exception:                        # noqa: BLE001 — see docstring
        return 0.0
    # A non-finite RMS must be answered here, not by the arithmetic below:
    # `np.asarray(None)` is a nan, nan compares False against the floor, and
    # `min(1.0, nan)` returns 1.0 — so a block that is not audio at all drew a
    # FULL-HEIGHT bar. Silence that looks like a measurement is worse than a
    # visible failure.
    if not np.isfinite(rms) or rms <= LEVEL_FLOOR:
        return 0.0
    return min(1.0, (rms - LEVEL_FLOOR) / (LEVEL_FULL - LEVEL_FLOOR))


# ── Transcript ──────────────────────────────────────────────────────────────
# The server emits control markers inline with speech. They were reaching the
# activity log verbatim, so the log showed a sentence the user never heard the
# model say.
_CTRL_RE = re.compile(r"<ctrl\d+>", re.IGNORECASE)

# Chunks shorter than this may legitimately repeat — "yes, yes" is a real
# sentence — so only longer ones are treated as duplicates of what came before.
REPEAT_MIN = 12


def clean_transcript(text: str) -> str:
    """Strip control markers and unprintable characters, then trim.

    Never raises: a fragment of a multi-byte character can arrive mid-chunk,
    and the receive loop must not die for one bad frame.
    """
    text = _CTRL_RE.sub("", text or "")
    text = re.sub(r"[\x00-\x08\x0b-\x1f]", "", text)
    return text.strip()


def is_repeat_chunk(txt: str, buf) -> bool:
    """True if this transcript chunk has already been seen this turn.

    Guards against the API re-sending the tail of a response across the several
    turn_completes a tool-using turn produces. Short chunks are compared only
    with the IMMEDIATELY previous one, because a repeated short word is ordinary
    speech; longer chunks are compared with the whole turn, because a repeated
    long sentence never is.
    """
    if len(txt) < REPEAT_MIN:
        return bool(buf) and txt == buf[-1]
    joined = " ".join(buf)
    return txt in joined


__all__ = ["LEVEL_FLOOR", "LEVEL_FULL", "REPEAT_MIN", "clean_transcript",
           "is_repeat_chunk", "pcm_level"]
