"""Small Qt-free silhouette helper for the projected avatar head."""
import math


def convex_outline(xs, ys):
    """Indices of a counter-clockwise outer hull; reject invalid projections.

    Used only as a soft holographic edge, not as a face shape or hit target.
    Collinear/duplicate points collapse to a single boundary; degenerate inputs
    return no outline. The result follows animated and rotated mesh positions.
    """
    if len(xs) != len(ys) or len(xs) < 3:
        return []
    points = []
    for i, (x, y) in enumerate(zip(xs, ys)):
        x, y = float(x), float(y)
        if not math.isfinite(x) or not math.isfinite(y):
            return []
        points.append((x, y, i))
    points.sort()
    unique = []
    for point in points:
        if not unique or point[:2] != unique[-1][:2]:
            unique.append(point)
    if len(unique) < 3:
        return []

    def cross(a, b, c):
        return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])

    def chain(items):
        out = []
        for point in items:
            while len(out) >= 2 and cross(out[-2], out[-1], point) <= 0:
                out.pop()
            out.append(point)
        return out

    outline = chain(unique)[:-1] + chain(reversed(unique))[:-1]
    return [point[2] for point in outline] if len(outline) >= 3 else []


def rim_segments(xs, ys, outline):
    """Group outline edges by lateral light, independent of position and scale.

    The projection's sides glow more brightly than the crown and chin, as in
    the desktop concept. Returned pairs refer to the original mesh indices.
    """
    buckets = [[], [], [], []]
    if len(outline) < 3:
        return buckets
    left = min(float(xs[i]) for i in outline)
    right = max(float(xs[i]) for i in outline)
    width = right - left
    if not math.isfinite(width) or width <= 1e-9:
        return buckets
    centre = (left + right) * .5
    for a, b in zip(outline, outline[1:] + outline[:1]):
        x = (float(xs[a]) + float(xs[b])) * .5
        strength = min(1.0, abs(x - centre) * 2 / width)
        bucket = min(3, int(strength * 4))
        buckets[bucket].append((a, b))
    return buckets
