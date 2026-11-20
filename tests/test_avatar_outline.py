import math

from core.avatar_outline import convex_outline, rim_segments


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


def test_rim_is_brightest_on_sides_and_tracks_scale_and_translation():
    xs, ys = [-1, 0, 1, 1, 0, -1], [0, -1, 0, 2, 3, 2]
    outline = list(range(6))
    buckets = rim_segments(xs, ys, outline)
    assert (2, 3) in buckets[-1] and (5, 0) in buckets[-1]
    assert (0, 1) in buckets[2] and (3, 4) in buckets[2]
    assert sum(map(len, buckets)) == len(outline)
    assert rim_segments([x * 5 + 30 for x in xs], ys, outline) == buckets
    assert rim_segments(xs, ys, []) == [[], [], [], []]
