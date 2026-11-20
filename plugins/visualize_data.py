"""Present supplied numeric data, never fetch data or execute content."""
from core.visual_content import validate

PLUGIN = {
    "name": "visualize_data",
    "description": (
        "Display an interactive chart and table for numeric data explicitly supplied by the user "
        "or returned by a tool. Use bar for category comparisons, line for ordered trends. "
        "Do not invent numbers, source or dates. Provide the actual source; "
        "the displayed source is an unverified attribution. Never use this to execute actions or trades."
    ),
    "parameters": {"type": "OBJECT", "properties": {
        "title": {"type": "STRING", "description": "Chart title"},
        "source": {"type": "STRING", "description": "Source as supplied; not verified"},
        "observed": {"type": "STRING", "description": "Actual data timestamp or period; empty if unknown"},
        "unit": {"type": "STRING", "description": "Common value unit; empty if none"},
        "chart_type": {"type": "STRING", "description": "bar for category comparisons; line for ordered trends"},
        "points": {"type": "ARRAY", "items": {"type": "OBJECT", "properties": {
            "label": {"type": "STRING"}, "value": {"type": "NUMBER"}},
            "required": ["label", "value"]}},
    }, "required": ["title", "source", "points"]},
    "tier": "extra",
}


def run(parameters, player=None, session_memory=None):
    del session_memory
    try:
        data = validate(parameters)
        show = getattr(player, "show_visual_content", None) if player else None
        if not callable(show):
            return "Interactive visual content requires the JARVIS desktop. No chart was opened."
        result = show(data)
        if not isinstance(result, dict):
            return "The chart display result could not be confirmed."
        return str(result.get("message") or "The chart display result could not be confirmed.")
    except ValueError as exc:
        return f"Cannot display a chart: {exc} No chart was opened."
    except Exception:
        return "The chart could not be opened."
