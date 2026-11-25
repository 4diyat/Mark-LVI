"""ui/theme.py — the colours, and the only place they are written.

WHY THIS LEFT ui.py
    `class C` is read by almost every widget in the app (`C.PRI`, `C.PANEL`…),
    which is exactly why the accent code that REBINDS those attributes has to
    live next to it and nowhere else. Moving it into a module of its own makes
    the ownership obvious: assign to `C` here, read `C` anywhere.

    This is a move, not a rewrite — the functions are the ones that were in
    `ui.py`, unchanged. `ui.py` re-exports every name, so `ui.C`, `ui.qcol`,
    `ui.apply_ui_accent` and `ui.current_palette` keep working for the rest of
    the project and for plugins written against it.
"""
from __future__ import annotations

import colorsys

# Imported at the call site in `qcol`, so `ui.theme` — and therefore every
# module that reads the palette — is importable on a machine with no PyQt6.
# The contrast tests and the structural tests both need the COLOURS, not a
# paint device.


class C:
    # ── New-UI palette (design/new-ui-proposal) ─────────────────────────────
    # The agreed mockups render a deep blue-black ambient with a bright blue
    # accent (not the old neutral-dark + cyan-orange sheet). These tokens are
    # read by every widget and painter, so they are the single source of the
    # new look; the structural tests that pin colour compare against these.
    BG        = "#0c0d11"
    PANEL     = "#101820"
    PANEL2    = "#14181c"
    BORDER    = "#1c2028"
    BORDER_B  = "#2a3240"
    BORDER_A  = "#243040"
    PRI       = "#3486fe"
    PRI_DIM   = "#1c79e1"
    PRI_GHO   = "#0a2a55"
    ACC       = "#ff9a40"
    ACC2      = "#ffcc00"
    GREEN     = "#1fe393"
    GREEN_D   = "#15a872"
    RED       = "#f44a42"
    MUTED_C   = "#e73f39"
    TEXT      = "#ffffff"
    TEXT_DIM  = "#5e636c"
    TEXT_MED  = "#878f9e"
    WHITE     = "#ffffff"
    DARK      = "#0c0d11"
    BAR_BG    = "#14181c"
    # Neutral desktop chrome is independent of the customizable HUD accent.
    DESKTOP_PANEL = "#15212f"
    DESKTOP_SIDEBAR = "#1b2a3b"
    DESKTOP_BAR = "#0b1725"
    DESKTOP_BORDER = "#3b5269"
    DESKTOP_TEXT = "#eef5fd"
    DESKTOP_MUTED = "#aabbd0"
    DESKTOP_DOCK = "#25384d"
    DOCK_BLUE = "#268ce3"
    DOCK_TEAL = "#287eac"
    DOCK_PURPLE = "#646e9a"
    DOCK_CHARCOAL = "#485e73"
    DOCK_GREEN = "#417f85"
    DOCK_ORANGE = "#8b746a"


def workspace_stylesheet() -> str:
    """Shared, accessible workspace controls; HUD accent remains independent."""
    return f"""
        QDialog, QWidget {{ background: {C.DESKTOP_PANEL}; color: {C.DESKTOP_TEXT}; }}
        QLabel, QCheckBox, QRadioButton {{ background: transparent; color: {C.DESKTOP_TEXT}; }}
        QPushButton, QToolButton {{ background: {C.DESKTOP_DOCK}; color: {C.DESKTOP_TEXT};
            border: 1px solid {C.DESKTOP_BORDER}; border-radius: 9px; padding: 6px; }}
        QPushButton:hover, QToolButton:hover {{ background: {C.DESKTOP_SIDEBAR}; }}
        QPushButton:focus, QToolButton:focus {{ border: 1px solid #4b9fff; }}
        QPushButton:disabled, QToolButton:disabled {{ color: {C.DESKTOP_MUTED}; }}
        QPushButton#WorkspacePrimary {{ background: #286dcc; color: #ffffff;
            border: 1px solid #4089e8; font-weight: bold; }}
        QPushButton#WorkspacePrimary:hover {{ background: #347fdf; }}
        QPushButton#WorkspacePrimary:disabled {{ background: {C.DESKTOP_DOCK};
            color: {C.DESKTOP_MUTED}; border-color: {C.DESKTOP_BORDER}; }}
        QWidget#WorkspaceSection {{ background: {C.DESKTOP_SIDEBAR};
            border: 1px solid {C.DESKTOP_BORDER}; border-radius: 10px; }}
        QLineEdit, QPlainTextEdit, QTextEdit, QListWidget, QSpinBox, QComboBox {{
            background: {C.DESKTOP_BAR}; color: {C.DESKTOP_TEXT};
            border: 1px solid {C.DESKTOP_BORDER}; border-radius: 8px; padding: 5px;
            selection-background-color: #286dcc; selection-color: #ffffff; }}
        QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QListWidget:focus,
        QSpinBox:focus, QComboBox:focus {{ border: 1px solid #4b9fff; }}
        QMenu {{ background: {C.DESKTOP_SIDEBAR}; color: {C.DESKTOP_TEXT};
            border: 1px solid {C.DESKTOP_BORDER}; padding: 4px; }}
        QMenu::item {{ padding: 6px 20px; border-radius: 4px; }}
        QMenu::item:selected {{ background: #286dcc; color: #ffffff; }}
        QTabWidget::pane {{ border: 1px solid {C.DESKTOP_BORDER}; border-radius: 5px; }}
        QTabBar::tab {{ background: {C.DESKTOP_SIDEBAR}; color: {C.DESKTOP_TEXT};
            padding: 8px 14px; margin-right: 3px; border: 1px solid {C.DESKTOP_BORDER};
            border-top-left-radius: 6px; border-top-right-radius: 6px; }}
        QTabBar::tab:selected {{ background: {C.DESKTOP_DOCK}; border-bottom: 2px solid #4b9fff; }}
    """


# Keys tied to the accent colour — status colours (ACC, GREEN, RED…) stay fixed
_HUE_LINKED = (
    "BG", "PANEL", "PANEL2", "BORDER", "BORDER_B", "BORDER_A",
    "PRI", "PRI_DIM", "PRI_GHO", "TEXT", "TEXT_DIM", "TEXT_MED",
    "WHITE", "DARK", "BAR_BG",
)
_PALETTE_DEFAULTS: dict[str, str] = {k: getattr(C, k) for k in _HUE_LINKED}

DEFAULT_UI_COLOR = _PALETTE_DEFAULTS["PRI"]


def apply_ui_accent(accent_hex: str) -> bool:
    """
    Re-derives the accent-linked palette from the chosen accent colour
    (hue shift — brightness/saturation ratios are preserved, design stays intact).
    Painted elements (HUD, waveform, metrics) pick up the new colour on the next
    frame; stylesheet-based panels pick it up when they are rebuilt.
    """
    accent_hex = (accent_hex or "").strip().lower()
    if not (accent_hex.startswith("#") and len(accent_hex) == 7):
        return False
    try:
        int(accent_hex[1:], 16)
    except ValueError:
        return False

    def _hsv(h: str) -> tuple[float, float, float]:
        r = int(h[1:3], 16) / 255
        g = int(h[3:5], 16) / 255
        b = int(h[5:7], 16) / 255
        return colorsys.rgb_to_hsv(r, g, b)

    base_h            = _hsv(_PALETTE_DEFAULTS["PRI"])[0]
    acc_h, acc_s, _av = _hsv(accent_hex)
    dh   = acc_h - base_h
    grey = acc_s < 0.08   # near-grey accent → the whole theme is desaturated

    for key, hex0 in _PALETTE_DEFAULTS.items():
        h, s, v = _hsv(hex0)
        if grey:
            s *= 0.15
        r, g, b = colorsys.hsv_to_rgb((h + dh) % 1.0, s, v)
        setattr(C, key, "#{:02x}{:02x}{:02x}".format(
            int(r * 255 + 0.5), int(g * 255 + 0.5), int(b * 255 + 0.5)))
    return True


def current_palette() -> dict[str, str]:
    """A snapshot of the accent-linked colours currently on class C."""
    return {k: getattr(C, k) for k in _HUE_LINKED}


def retheme_all_widgets(old: dict[str, str], new: dict[str, str]) -> None:
    """
    LIVE full theme change. Replaces the old palette colours with the new ones
    in EVERY widget's stylesheet across the app and repaints them. This way the
    colour change applies INSTANTLY across the whole interface — panels, buttons,
    borders included — not just the painted elements. No restart needed.
    """
    mapping = {old[k].lower(): new[k].lower()
               for k in old if old[k].lower() != new.get(k, old[k]).lower()}
    if not mapping:
        return
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance()
    if app is None:
        return
    for w in app.allWidgets():
        try:
            ss = w.styleSheet()
            if ss:
                s2 = ss
                for o, n in mapping.items():
                    if o in s2:
                        s2 = s2.replace(o, n)
                if s2 != ss:
                    w.setStyleSheet(s2)
            w.update()
        except Exception as e:
            # One widget that refuses a stylesheet must not stop the rest of
            # the window being repainted. The name is the useful part when a
            # colour change "did not take" on exactly one panel.
            retheme_log(f"theme: {type(w).__name__} refused the new sheet: {e}")


def qcol(h: str, a: int = 255):
    """A `QColor` from a hex string, with an alpha byte. Needs Qt at CALL time."""
    from PyQt6.QtGui import QColor
    c = QColor(h); c.setAlpha(a); return c


def retheme_log(message: str) -> None:
    """Where a widget that refused a new stylesheet is reported.

    A logbook logger rather than a print: this runs while the whole window is
    being repainted, and one widget that raises must not stop the rest — which
    is what the bare `except: pass` here used to guarantee, silently.
    """
    try:
        from core.logbook import get
        get("ui.theme").debug("%s", message)
    except Exception:
        pass
