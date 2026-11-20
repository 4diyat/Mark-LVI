"""Bounded layout for the central avatar and its three caption lines."""
import math


def avatar_layout(width, height, span):
    """Return (cx, cy, radius, name_y, tagline_y, state_y), or None.

    Coordinates are widget-local. The avatar occupies span * radius vertically;
    its projection origin is one radius below its crown. A fixed caption block
    keeps live state visible rather than drawing over the face or dock.
    """
    if (not all(isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)
                for x in (width, height, span)) or width <= 0 or height < 112 or span <= 1):
        return None
    caption_height, gap, top = 82.0, 6.0, 5.0
    radius = min(width * .33, (height - caption_height - gap - top) / span)
    if radius <= 0:
        return None
    available = height - caption_height - gap - top
    crown = top + max(0.0, (available - span * radius) / 2)
    name_y = crown + span * radius + gap
    return width / 2, crown + radius, radius, name_y, name_y + 27, name_y + 49
