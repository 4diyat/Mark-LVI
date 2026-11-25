"""Which palette the tray panel is drawn in, and where that answer comes from.

WHY THIS IS NOT INSIDE `ui/tray_panel.py`
    Three things decide the colour of the panel and they must not be confused:

      * the SETTING  — `auto` / `dark` / `light`, stored by
        `memory.config_manager` and read once at startup;
      * the ANSWER   — `auto` resolved against what the operating system says,
        which is `resolve_theme()` below and nothing else;
      * the PALETTE  — two dictionaries of hex strings, in `ui/tray_pages.py`.

    The panel used to hold all three, which meant a widget knew about a config
    key, and it also pushed `ui/tray_panel.py` to exactly 599 lines — one line
    under the 600-line ceiling. A file that is one line from failing a rule is
    a file that will fail it during the next change, so the boundary moved
    here rather than the rule moving down.

WHY THE OS ANSWER IS NOT ASKED OF QT
    `ui/theme.py` must not import PyQt6 at module scope (a structural test
    pins it), the panel is built before anybody sees its colours, and the whole
    point of `auto` is that it has to work on a machine where the panel is the
    ONLY surface. So the answer is read from config, through
    `memory.config_manager.system_prefers_light()`, which never raises and
    defaults to dark — the palette the mockup has drawn since board 5.

    A consequence, stated rather than hidden: `auto` follows a value written to
    `config/api_keys.json` (`ui_os_theme`), not a live desktop query. On a
    machine where that key is absent — every Linux desktop, and Windows until
    something writes it — `auto` is dark. Detecting the live setting is a
    `QGuiApplication.styleHints()` question and belongs to whoever owns the
    QApplication, not to this module.
"""
from __future__ import annotations

# The three values the SETTING accepts. `memory.config_manager.THEMES` is the
# same tuple written out again: this module must not import the config layer,
# which reads a file on import, and the panel must be able to validate a value
# before a config file exists. A test asserts the two tuples match.
THEMES = ("auto", "dark", "light")


def resolve_theme(requested: str) -> str:
    """`auto`/`dark`/`light` -> the palette name actually used. Never raises.

    THE OS ANSWER COMES FROM `memory.config_manager`, NOT FROM QT. `ui/theme.py`
    must not import PyQt6 at module scope (a test pins that), and the panel is
    built before anybody has looked at its colours — so asking Qt here would
    put a Qt import on a path that has to work headless.
    """
    name = str(requested or "").strip().lower()
    if name in ("dark", "light"):
        return name
    try:
        from memory.config_manager import system_prefers_light

        return "light" if system_prefers_light() else "dark"
    except Exception:                                # noqa: BLE001
        return "dark"




def _rgba(hex_colour: str, alpha: float) -> str:
    """`#RRGGBB` + alpha -> the `rgba(...)` a Qt stylesheet understands.

    Lives beside the palettes it formats rather than in the painter: a colour
    helper that reads a hex string is a fact about the palette, and moving it
    here is what let the painter stop importing anything but `PALETTES`.
    """
    value = hex_colour.lstrip("#")
    r, g, b = (int(value[i:i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r}, {g}, {b}, {alpha:.2f})"


# ── the theme control ───────────────────────────────────────────────────────
# FOUR METHODS THAT WERE ON `TrayPanel` AND NEVER NEEDED TO BE. They are policy
# about a three-valued setting with two palettes, and none of them touch a
# widget: `apply` takes the state it changes and returns the new one. Moving
# them here kept `tray_panel` under its 600-line ceiling when the memory list
# gained an identity-based open, and the split is honest — the panel is
# lifecycle and dispatch; this is what "auto" means.

def cycle(requested: str) -> str:
    """auto -> dark -> light -> auto.

    Cycles rather than showing three segments: the header has room for one
    28 px control and the segments already belong to the presence mode. A third
    segmented control in the same header would make two rows of three-letter
    words that look identical.
    """
    order = THEMES
    try:
        index = order.index(requested)
    except ValueError:
        index = 0
    return order[(index + 1) % len(order)]


def is_valid(requested: str) -> bool:
    """Whether a name is one of the three the panel accepts."""
    return str(requested or "").strip().lower() in THEMES


def resolve(requested: str, default: str = "dark") -> tuple[str, str]:
    """(what was asked for, what is on screen), or (`default`, `default`).

    THREE VALUES, TWO PALETTES. `auto` is not a palette: it is the answer to
    "which one does the OS use", asked once per call and never per paint. The
    caller keeps both numbers because the panel has to be able to SAY "auto"
    while painting dark.
    """
    name = str(requested or "").strip().lower()
    if name not in THEMES:
        return default, default
    return name, resolve_theme(name)


__all__ = ["THEMES", "_rgba", "cycle", "is_valid", "resolve",
           "resolve_theme"]
