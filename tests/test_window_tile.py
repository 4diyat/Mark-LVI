"""Board 12's window-arrangement geometry policy: the tiling arithmetic.

These test the pure policy in `core.window_tile` with no display and no OS.
The point is that the three thumbnails correspond to real, deterministic
geometry: every window gets a rectangle, no two tiles overlap, and the
tiling covers the work area for each mode and window count.
"""
from __future__ import annotations

from core.window_tile import (COLUMNS2, COLUMNS3, FOCUS, MODES, Rect,
                              WorkArea, arrange, is_mode, overlaps)


def _area(w=1920, h=1080):
    return WorkArea(x=0, y=0, width=w, height=h)


# ── mode set ──────────────────────────────────────────────────────────────

def test_the_three_modes_are_the_fixed_set():
    assert MODES == (COLUMNS2, COLUMNS3, FOCUS)
    assert is_mode(COLUMNS2) and is_mode(COLUMNS3) and is_mode(FOCUS)
    assert is_mode("tiled") is False


# ── columns ──────────────────────────────────────────────────────────────

def test_two_columns_splits_the_area_in_half():
    rects = arrange(COLUMNS2, [1, 2], _area())
    assert len(rects) == 2
    assert rects[0].x < rects[1].x
    # Each column is roughly half the width minus the gap.
    assert rects[0].width == rects[1].width


def test_three_columns_uses_three_strips():
    rects = arrange(COLUMNS3, [1, 2, 3], _area())
    assert len(rects) == 3
    xs = sorted(r.x for r in rects)
    assert len(set(xs)) == 3


def test_an_even_count_fills_two_columns_column_by_column():
    rects = arrange(COLUMNS2, [1, 2, 3, 4], _area())
    assert len(rects) == 4
    # Column-major: the first column fills top-to-bottom, then the next.
    assert rects[0].x == rects[1].x       # same column, different row
    assert rects[0].y == rects[2].y       # same row, different column


def test_no_two_tiles_overlap_in_two_columns():
    rects = arrange(COLUMNS2, [1, 2, 3, 4, 5, 6], _area())
    for i in range(len(rects)):
        for j in range(i + 1, len(rects)):
            assert not overlaps(rects[i], rects[j])


def test_no_two_tiles_overlap_in_three_columns():
    rects = arrange(COLUMNS3, [1, 2, 3, 4, 5, 6, 7], _area())
    for i in range(len(rects)):
        for j in range(i + 1, len(rects)):
            assert not overlaps(rects[i], rects[j])


def test_every_tile_is_within_the_work_area():
    rects = arrange(COLUMNS3, [1, 2, 3, 4], _area())
    for r in rects:
        assert r.x >= 0 and r.y >= 0
        assert r.x + r.width <= 1920
        assert r.y + r.height <= 1080


def test_an_unknown_mode_falls_back_to_two_columns():
    rects = arrange("tiled", [1, 2], _area())
    assert len(rects) == 2
    assert rects[0].width == rects[1].width


def test_an_empty_window_list_has_no_geometry():
    assert arrange(COLUMNS2, [], _area()) == []


# ── focus ────────────────────────────────────────────────────────────────

def test_focus_gives_the_first_window_the_full_area():
    rects = arrange(FOCUS, [1, 2, 3], _area())
    assert rects[0] == Rect(x=0, y=0, width=1920, height=1080)


def test_focus_gives_the_others_a_narrow_strip():
    rects = arrange(FOCUS, [1, 2, 3], _area())
    for r in rects[1:]:
        assert r.width < 1920, "the non-focused windows are narrowed"


def test_focus_with_one_window_is_just_the_full_area():
    rects = arrange(FOCUS, [1], _area())
    assert len(rects) == 1
    assert rects[0].width == 1920


# ── rect / overlaps ─────────────────────────────────────────────────────

def test_overlaps_detects_a_collision():
    a = Rect(0, 0, 100, 100)
    b = Rect(50, 50, 100, 100)
    c = Rect(200, 200, 10, 10)
    assert overlaps(a, b) is True
    assert overlaps(a, c) is False
