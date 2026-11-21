"""When a batch of audio actually becomes audible.

The mouth and the captions are scheduled against a wall-clock time, and getting
that time wrong is not a crash — it is a face that moves half a second behind
the voice. That is what happened: the anchor was `stream.latency`, which reports
how much can be queued ahead (300–500 ms on Windows), not how long the first
byte takes to sound. The stream has been running since launch and pulling
silence, so the first bytes arrive about one callback period later.

These tests exist so nobody re-derives the anchor from `latency`.
"""
from __future__ import annotations

import ast
from pathlib import Path

from core import playback_timing as pt

ROOT = Path(__file__).resolve().parent.parent
RATE = 24000
BLOCK = 1024          # CHUNK_SIZE
# The slack is NOT restated here. A test that supplies its own copy cannot
# notice when the caller stops passing one, which is exactly the mutant that
# survived the first version of this file.
SLACK = pt.SLACK


def sched(now, cursor, latency=0.20, n=2400):
    return pt.schedule(now=now, cursor=cursor, out_latency=latency,
                       block_frames=BLOCK, n_samples=n, rate=RATE)


# ── the two primitives ────────────────────────────────────────────────────

def test_the_first_sound_is_one_callback_period_not_a_hardware_buffer():
    """THE BUG. `latency` is queue capacity, not time-to-first-sound."""
    assert pt.first_sound(BLOCK, RATE) == BLOCK / RATE
    assert pt.first_sound(BLOCK, RATE) < 0.05, "a buffer's worth of delay is back"


def test_the_first_sound_does_not_depend_on_latency_at_all():
    """It takes (block_frames, rate) and nothing else, by construction."""
    tree = ast.parse((ROOT / "core" / "playback_timing.py").read_text(encoding="utf-8"))
    fn = next(n for n in tree.body
              if isinstance(n, ast.FunctionDef) and n.name == "first_sound")
    args = [a.arg for a in fn.args.args]
    assert args == ["block_frames", "rate"], args


def test_a_batch_lasts_as_long_as_its_samples():
    assert pt.batch_seconds(24000, RATE) == 1.0
    assert pt.batch_seconds(480, RATE) == 0.02


def test_a_silly_rate_cannot_divide_by_zero():
    assert pt.first_sound(BLOCK, 0) == 0.0
    assert pt.batch_seconds(480, 0) == 0.0
    assert pt.first_sound(-5, RATE) == 0.0


# ── anchoring ─────────────────────────────────────────────────────────────

def test_the_first_batch_is_anchored_one_callback_period_ahead_of_now():
    at, nxt = sched(now=100.0, cursor=0.0)
    assert at == 100.0 + BLOCK / RATE
    assert nxt == at + 2400 / RATE


def test_a_cursor_inside_the_possible_window_is_kept():
    """After the anchor nothing needs measuring: the device consumes at exactly
    realtime, so each batch sounds one batch-duration after the last."""
    now = 100.0
    at, nxt = sched(now=now, cursor=now + 0.1)
    assert at == now + 0.1, "the cursor was re-anchored without a reason"


def test_a_cursor_behind_now_is_re_anchored():
    """Behind `now` means the device drained and this batch starts a fresh
    stretch of speech. Without this the mouth would replay a finished timeline."""
    now = 100.0
    at, _ = sched(now=now, cursor=now - 0.5)
    assert at > now


def test_a_cursor_further_ahead_than_the_buffer_holds_is_re_anchored():
    """Past the buffer is physically impossible — it has drifted."""
    now = 100.0
    at, _ = sched(now=now, cursor=now + 5.0)
    assert at == now + BLOCK / RATE


def test_the_window_is_the_device_latency_plus_a_margin():
    """The boundary itself: just inside is kept, just outside is not."""
    now = 100.0
    inside = now + 0.20 + SLACK - 1e-6
    outside = now + 0.20 + SLACK + 1e-6
    assert sched(now=now, cursor=inside)[0] == inside
    assert sched(now=now, cursor=outside)[0] != outside


def test_the_cursor_advances_by_the_batch_itself_even_with_no_samples():
    """A block too short to analyse still takes time on the wire; not advancing
    would shift everything after it out of step with the sound."""
    at, nxt = sched(now=100.0, cursor=0.0, n=0)
    assert nxt == at, "the cursor moved for a batch with no samples"
    _, nxt2 = sched(now=100.0, cursor=0.0, n=4800)
    assert nxt2 > at


def test_consecutive_batches_stay_in_step_across_a_second():
    """Thirty batches of 40 ms each must land 40 ms apart, not drift.

    `now` advances with the batches, as it does in the play loop: the schedule
    is checked against the wall clock once per batch, not against a frozen one.
    """
    times = []
    cursor = 0.0
    now = 100.0
    for _ in range(30):
        at, cursor = sched(now=now, cursor=cursor, n=960, latency=0.2)
        times.append(at)
        now += 0.04
    for a, b in zip(times, times[1:]):
        assert abs((b - a) - 0.04) < 1e-9


def test_a_timeline_that_drifted_past_the_buffer_moves_back_to_now():
    """When the cursor is further ahead than the device can hold, that stretch
    of the timeline is not real — the device cannot have queued it. Re-anchoring
    to `now` is a correction, not a backwards jump: the sound really is being
    produced at `now`, and anything scheduled ahead of the buffer would be a
    caption for audio that has not arrived.
    """
    now = 100.0
    at, _ = sched(now=now, cursor=now + 0.9)
    assert at == now + BLOCK / RATE
    assert at < now + 0.9


# ── the wiring ────────────────────────────────────────────────────────────

def test_main_uses_the_module_and_keeps_no_second_anchor_rule():
    source = (ROOT / "main.py").read_text(encoding="utf-8")
    assert "_timing.schedule(" in source
    # The old constant and its use are gone; a leftover would be a second rule.
    assert "_FIRST_SOUND" not in source
    tree = ast.parse(source)
    literals = [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant)
                and isinstance(n.value, str)]
    assert not any("become audible" in s and "stream.latency" in s for s in literals)


def test_the_slack_is_the_modules_own_default_and_main_does_not_pass_one():
    """A caller that supplies its own slack has re-introduced the second copy."""
    source = (ROOT / "main.py").read_text(encoding="utf-8")
    assert "slack=" not in source, "main.py is passing its own slack again"
    assert "_CURSOR_SLACK" not in source


def test_the_slack_is_wide_enough_to_survive_ordinary_jitter():
    """Zero slack would re-anchor on every batch whose timing wobbles by a
    millisecond, and each re-anchor restarts the mouth — visibly."""
    assert pt.SLACK >= 0.05
    now = 100.0
    # A cursor 20 ms late (a scheduler hiccup) must be KEPT, not re-anchored.
    assert sched(now=now, cursor=now + 0.20 + 0.02)[0] == now + 0.20 + 0.02


def test_the_module_needs_no_audio_device_or_clock():
    """`now` is a parameter. A function that reads the clock cannot be tested on
    a machine with no speaker, which is every CI runner this project has."""
    tree = ast.parse((ROOT / "core" / "playback_timing.py").read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert imported <= {"__future__"}, imported
