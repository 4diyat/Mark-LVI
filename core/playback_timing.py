"""When will this batch of audio actually be heard?

THE BUG THIS ENCODES
    The avatar's mouth and the captions are both scheduled against a wall-clock
    time. Anchoring that time on `stream.latency` put the whole schedule a full
    hardware buffer late — 300 to 500 ms on Windows — because `latency` reports
    how much can be QUEUED AHEAD, not how long the first byte takes to sound.
    The stream has been running since launch and has been pulling silence ever
    since, so the first bytes of a reply reach the speaker about one callback
    period later. That half second of lag is this file's reason to exist, and
    the comment in `main.py` used to be its only record.

    Pulling it out means the rule is now a function with tests instead of a
    paragraph with a rationale. The measurement that found it is quoted above so
    nobody re-derives it from `latency` and reintroduces it.

WHY IT IS PURE
    No audio, no device, no clock of its own: `now` is passed in. That is what
    makes "the mouth stays in step with the sound" testable on a machine with no
    speaker, which is every CI runner this project has.
"""
from __future__ import annotations

# How far past the device's own buffer the timeline may drift before it is
# re-anchored. The buffer is the hard limit on how much audio can be queued
# ahead, so anything beyond it plus a margin for clock error is impossible.
# It lives HERE, beside the function that applies it: a constant in main.py and
# its only reader in another module is how the two drift apart — and a test that
# supplies its own copy cannot notice when the caller stops passing one.
SLACK = 0.15


def first_sound(block_frames: int, rate: int) -> float:
    """Delay from handing the first bytes to a running stream until they sound.

    One callback period. NOT `stream.latency`, which is the queue capacity.
    """
    if rate <= 0:
        return 0.0
    return max(0, block_frames) / float(rate)


def batch_seconds(n_samples: int, rate: int) -> float:
    """How long a batch of `n_samples` mono int16 samples lasts on the wire."""
    if rate <= 0:
        return 0.0
    return max(0, n_samples) / float(rate)


def schedule(now: float, cursor: float, out_latency: float,
             block_frames: int, n_samples: int, rate: int,
             slack: float = SLACK) -> tuple[float, float]:
    """Where this batch starts sounding, and where the next one will.

    Returns `(at, next_cursor)`.

    The anchor rule, in order:
      * if the cursor is BEHIND `now`, the device drained and this batch starts
        a fresh stretch of speech — re-anchor;
      * if it is further ahead than the device buffer can hold, it has drifted
        past what is physically possible — re-anchor;
      * otherwise keep it. After the first batch nothing needs measuring: the
        device consumes at exactly realtime, so each batch sounds one
        batch-duration after the one before it.

    The cursor advances by the batch's own duration whether or not the batch
    yielded anything, so a block too short to analyse cannot shift everything
    after it out of step with the audio.
    """
    horizon = max(0.0, out_latency) + max(0.0, slack)
    if not (now <= cursor <= now + horizon):
        cursor = now + first_sound(block_frames, rate)
    at = cursor
    return at, cursor + batch_seconds(n_samples, rate)


__all__ = ["batch_seconds", "first_sound", "schedule"]
