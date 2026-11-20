"""Bounded, non-executable data for an interactive numeric visualization."""
import math

MAX_POINTS = 48
MAX_ABS_VALUE = 1e12


def _text(value, name, limit, *, required=True):
    if not isinstance(value, str) or len(value) > limit or any(ord(c) < 32 for c in value):
        raise ValueError(f"Invalid {name}.")
    value = value.strip()
    if required and not value:
        raise ValueError(f"{name} is required.")
    return value


def validate(payload):
    """Make a detached safe snapshot. The source is a claim, not verified provenance."""
    if not isinstance(payload, dict):
        raise ValueError("Expected a visualization object.")
    title = _text(payload.get("title"), "title", 100)
    source = _text(payload.get("source"), "source", 160)
    observed = _text(payload.get("observed", ""), "data time", 80, required=False)
    unit = _text(payload.get("unit", ""), "unit", 24, required=False)
    chart_type = payload.get("chart_type", "line")
    if not isinstance(chart_type, str) or chart_type not in ("line", "bar"):
        raise ValueError("Use line or bar chart.")
    points = payload.get("points")
    if not isinstance(points, list) or not 2 <= len(points) <= MAX_POINTS:
        raise ValueError(f"Provide 2 to {MAX_POINTS} points.")
    result = []
    for point in points:
        if not isinstance(point, dict):
            raise ValueError("Invalid data point.")
        label = _text(point.get("label"), "point label", 64)
        value = point.get("value")
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("Values must be numbers.")
        if abs(value) > MAX_ABS_VALUE or not math.isfinite(value):
            raise ValueError("Values must be finite and within the supported range.")
        result.append({"label": label, "value": float(value)})
    return {"title": title, "source": source, "observed": observed, "unit": unit,
            "chart_type": chart_type, "points": result}


def positions(points, left, top, width, height):
    """Plot coordinates; include zero so positive/negative values are honest."""
    if not points or width <= 0 or height <= 0:
        return []
    values = [point["value"] for point in points]
    low, high = min(0.0, min(values)), max(0.0, max(values))
    if high == low:
        high = low + 1.0
    step = width / max(1, len(points) - 1)
    return [(left + i * step, top + (high - value) / (high - low) * height)
            for i, value in enumerate(values)]


def bar_rectangles(points, left, top, width, height):
    """(x, y, width, height) and zero baseline; zero values have zero height."""
    if not points or width <= 0 or height <= 0:
        return [], top
    values = [point['value'] for point in points]
    low, high = min(0.0, min(values)), max(0.0, max(values))
    if high == low:
        high = low + 1.0
    baseline = top + high / (high - low) * height
    step = width / len(points)
    bar_width = step * 0.7
    rects = []
    for i, value in enumerate(values):
        end = top + (high - value) / (high - low) * height
        rects.append((left + (i + 0.5) * step - bar_width / 2,
                      min(end, baseline), bar_width, abs(baseline - end)))
    return rects, baseline
