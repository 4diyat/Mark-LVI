"""Two-hand window geometry is local, bounded, and safe on invalid samples."""
import math
import pytest
from core.workspace_transform import transform_window


BASE = ((100, 150), (300, 150))
GEOMETRY = (80, 80, 400, 300)
VIEWPORT = (1000, 800)
MINIMUM = (150, 100)


def test_two_hands_translate_a_whole_workspace_window():
    result = transform_window(BASE, ((140, 180), (340, 180)), GEOMETRY, VIEWPORT, MINIMUM)
    assert result == (120, 110, 400, 300)


def test_two_hands_scale_about_their_midpoint():
    result = transform_window(BASE, ((0, 150), (400, 150)), GEOMETRY, VIEWPORT, MINIMUM)
    assert result == (0, 10, 800, 600)


def test_window_stays_within_viewport_and_honors_minimum():
    result = transform_window(BASE, ((-400, -400), (-300, -400)), GEOMETRY, VIEWPORT, MINIMUM)
    assert result == (0, 0, 200, 150)
    result = transform_window(BASE, ((-10000, 9000), (10000, 9000)), GEOMETRY, VIEWPORT, (450, 350))
    assert result[2:] == (800, 600)
    assert 0 <= result[0] <= VIEWPORT[0] - result[2]
    assert 0 <= result[1] <= VIEWPORT[1] - result[3]
    oversized = transform_window(BASE, BASE, GEOMETRY, (300, 200), (450, 350))
    assert oversized == (0, 0, 450, 350)


@pytest.mark.parametrize('initial,current', [
    (((1, 1), (2, 2)), BASE),
    (BASE, ((math.nan, 0), (5, 5))),
    (BASE, ((math.inf, 0), (5, 5))),
    (BASE, ((1, 2),)),
])
def test_invalid_tracking_cannot_change_geometry(initial, current):
    assert transform_window(initial, current, GEOMETRY, VIEWPORT, MINIMUM) is None


def test_fast_drag_yields_bounded_flick():
    from core.workspace_transform import FlickTracker, bounded_flick
    tracker = FlickTracker()
    tracker.add((100, 100), 1.0)
    tracker.add((200, 150), 1.1)
    delta = tracker.displacement(1.12)
    assert delta and delta[0] > 0 and delta[1] > 0
    assert math.hypot(*delta) <= 241
    assert bounded_flick((900, 750), delta, (1000, 800)) == (960, 767)


def test_flick_rejects_slow_stale_invalid_or_reversed_samples():
    from core.workspace_transform import FlickTracker, bounded_flick
    tracker = FlickTracker()
    tracker.add((0, 0), 1.0)
    tracker.add((20, 0), 1.1)
    assert tracker.displacement(1.1) is None
    tracker.add((200, 0), 1.15)
    assert tracker.displacement(1.3) is None
    tracker.add((math.nan, 0), 1.3)
    assert tracker.displacement(1.3) is None
    tracker.add((0, 0), 2)
    tracker.add((100, 0), 1)
    assert tracker.displacement(1) is None
    assert bounded_flick((0, 0), (math.inf, 1), (1000, 800)) is None


def test_hand_rotation_delta_signed_wrap_and_invalid_samples():
    from core.workspace_transform import hand_rotation_delta

    assert hand_rotation_delta(((0, 0), (100, 0)), ((0, 0), (0, 100))) == 90
    assert hand_rotation_delta(((0, 0), (100, 0)), ((0, 0), (0, -100))) == -90
    angle = hand_rotation_delta(((0, 0), (-100, 1)), ((0, 0), (-100, -1)))
    assert 1 < angle < 2  # crosses +180/-180 without a 360-degree jump
    assert hand_rotation_delta(((0, 0), (10, 0)), ((0, 0), (100, 0))) is None
    assert hand_rotation_delta(((0, 0), (100, 0)), ((0, 0), (0, 0))) is None
    assert hand_rotation_delta(((0, 0), (100, 0)), ((0, 0), (float('nan'), 100))) is None
    assert hand_rotation_delta(None, ((0, 0), (100, 0))) is None
