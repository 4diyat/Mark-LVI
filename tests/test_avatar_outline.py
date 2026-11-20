import math

from core.avatar_outline import convex_outline


def test_outline_excludes_interior_and_duplicate_vertices():
    xs, ys = [0, 2, 2, 0, 1, 0, 1], [0, 0, 2, 2, 1, 0, 0]
    hull = convex_outline(xs, ys)
    assert [(xs[i], ys[i]) for i in hull] == [(0, 0), (2, 0), (2, 2), (0, 2)]


def test_outline_tracks_a_changed_projection():
    assert convex_outline([0, 2, 2, 0, 3], [0, 0, 2, 2, 1]) == [0, 1, 4, 2, 3]
    assert convex_outline([0, 2, 2, 0, 1], [0, 0, 2, 2, 1]) == [0, 1, 2, 3]


def test_outline_rejects_degenerate_and_nonfinite_points():
    for xs, ys in (([], []), ([0, 1], [0, 1]), ([0, 1, 2], [0, 1, 2]),
                   ([0, math.nan, 2], [0, 1, 2]), ([0, 1, math.inf], [0, 1, 0]),
                   ([0, 1, 2], [0, 1])):
        assert convex_outline(xs, ys) == []
