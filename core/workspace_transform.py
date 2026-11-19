"""Geometry for two-hand manipulation of JARVIS-owned workspace windows.

This module is pure arithmetic: it cannot see the desktop or generate OS
input. The UI applies the result only to its own active QMdiSubWindow.
"""
import math


def transform_window(initial_hands, current_hands, geometry, viewport, minimum):
    """Translate and scale around the original two-hand midpoint, bounded to the viewport.

    Returns (x, y, width, height) or None for invalid or too-close points.
    When a Qt minimum size exceeds the viewport the minimum is preserved; the
    window cannot physically fit, so its top-left stays at zero on that axis.
    """
    try:
        (x1, y1), (x2, y2) = initial_hands
        (u1, v1), (u2, v2) = current_hands
        x, y, width, height = geometry
        vw, vh = viewport
        min_w, min_h = minimum
        values = (x1, y1, x2, y2, u1, v1, u2, v2, x, y, width, height, vw, vh, min_w, min_h)
        if not all(math.isfinite(value) for value in values):
            return None
        if width <= 0 or height <= 0 or vw <= 0 or vh <= 0 or min_w < 0 or min_h < 0:
            return None
        old = math.hypot(x2 - x1, y2 - y1)
        if old < 40:
            return None
        new = math.hypot(u2 - u1, v2 - v1)
        scale = max(.5, min(2., new / old))
        new_w = max(1, min_w, min(vw, round(width * scale)))
        new_h = max(1, min_h, min(vh, round(height * scale)))
        before_x, before_y = (x1 + x2) / 2, (y1 + y2) / 2
        after_x, after_y = (u1 + u2) / 2, (v1 + v2) / 2
        # Use the actual clamped dimension ratios so the focal point remains
        # consistent even when one axis hits the window's minimum size.
        nx = round(after_x + (x - before_x) * new_w / width)
        ny = round(after_y + (y - before_y) * new_h / height)
        return (max(0, min(max(0, vw - new_w), nx)),
                max(0, min(max(0, vh - new_h), ny)), new_w, new_h)
    except (TypeError, ValueError, OverflowError):
        return None


class FlickTracker:
    """Estimate a short, bounded throw from recent confirmed drag positions."""
    def __init__(self):
        self.points = []

    def add(self, point, timestamp):
        try:
            x, y = point
            if not all(math.isfinite(value) for value in (x, y, timestamp)):
                self.points.clear()
                return
            if self.points and timestamp < self.points[-1][0]:
                self.points.clear()
            if not self.points or (x, y) != self.points[-1][1:]:
                self.points.append((timestamp, x, y))
            self.points = [p for p in self.points if timestamp - p[0] <= .20][-12:]
        except (TypeError, ValueError, OverflowError):
            self.points.clear()

    def displacement(self, timestamp):
        """Return displacement only for a recent, deliberate rapid drag."""
        try:
            if not math.isfinite(timestamp) or len(self.points) < 2:
                return None
            first, last = self.points[0], self.points[-1]
            elapsed = last[0] - first[0]
            if not .04 <= elapsed <= .20 or not 0 <= timestamp - last[0] <= .12:
                return None
            dx, dy = last[1] - first[1], last[2] - first[2]
            speed = math.hypot(dx, dy) / elapsed
            if speed < 800 or math.hypot(dx, dy) < 35:
                return None
            # Short extrapolation, capped independently of frame rate.
            factor = min(.18 / elapsed, 240 / math.hypot(dx, dy))
            return (round(dx * factor), round(dy * factor))
        except (TypeError, ValueError, OverflowError, ZeroDivisionError):
            return None


def bounded_flick(position, delta, viewport):
    """Keep the title of a thrown window reachable inside its workspace."""
    try:
        x, y = position
        dx, dy = delta
        width, height = viewport
        if not all(math.isfinite(v) for v in (x, y, dx, dy, width, height)) or width <= 0 or height <= 0:
            return None
        return (round(max(0, min(max(0, width - 40), x + dx))),
                round(max(0, min(max(0, height - 33), y + dy))))
    except (TypeError, ValueError, OverflowError):
        return None


def hand_rotation_delta(initial_hands, current_hands):
    """Signed screen-space angle change in degrees, normalized to [-180, 180).

    Hand identity/order must already be stable. Both hand separations must be
    large enough to avoid unstable angles. This computes geometry only; it
    does not rotate windows or synthesize any input.
    """
    try:
        (x1, y1), (x2, y2) = initial_hands
        (u1, v1), (u2, v2) = current_hands
        if not all(math.isfinite(v) for v in (x1, y1, x2, y2, u1, v1, u2, v2)):
            return None
        if math.hypot(x2 - x1, y2 - y1) < 40 or math.hypot(u2 - u1, v2 - v1) < 40:
            return None
        before = math.atan2(y2 - y1, x2 - x1)
        after = math.atan2(v2 - v1, u2 - u1)
        return (math.degrees(after - before) + 180) % 360 - 180
    except (TypeError, ValueError, OverflowError):
        return None


# Kinds are the names registered by the workspace, not window titles or URLs.
# Unknown kinds fail closed until explicitly reviewed. This policy is not yet
# connected to a rotating workspace implementation.
_ROTATABLE_KINDS = frozenset({
    'assistant', 'chat', 'files', 'navigation', 'video', 'camera',
    'model_viewer', 'code_editor', 'image_editor', 'trading', 'ssh_manager',
})


def rotation_allowed(kind, *, is_dialog):
    """Policy for future rotation: browser, dialogs and unknown types stay upright.

    ``is_dialog`` describes a separate modal/popup, not the QDialog base class
    of a document embedded as a workspace widget. Only a trusted UI caller may
    classify the target; this function does not inspect Qt or enforce access.
    """
    return is_dialog is False and isinstance(kind, str) and kind in _ROTATABLE_KINDS
