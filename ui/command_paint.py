"""Board 3's drawing: the box, its rows, and the marks on them.

WHY THIS IS A SECOND MODULE
    `ui/command_bar.py` is the state machine — open, type, Esc, recall, the
    focus ledger — and it sat at 540 lines once board 3's surface was drawn into
    it. The 600-line ceiling in `ui/` exists so "just add it here" costs a
    conversation, and the split it forced is the honest one: everything here is
    Qt calls and geometry, everything there is what the bar DOES.

    It is the same split `toast_card.py` / `toast_queue.py` makes, and the same
    one `voice_paint.py` makes for board 6: a painter that can be driven by the
    test stub is a painter whose marks can be asserted.

WHAT IS IN HERE
    Geometry and paint code for the command input, recent audit outcomes and
    their status legend. The audit records are not proof of the actual result.
"""
from __future__ import annotations

from dataclasses import dataclass

# ── board 3's tokens, declared here rather than borrowed ────────────────────
# Same rule as `ui/confirm_banner.py`: an ambient surface copies the sheet's
# numbers and never reads `ui.theme.C`, which still carries the look of the
# window ambient mode replaced.
# Dimensions are adapted from the mockup, with space for delivery feedback.
BAR_WIDTH, BAR_HEIGHT = 960, 490
FIELD_MARGIN, FIELD_HEIGHT = 30, 76

BASE = "#121720"
PANEL = "#171c25"
LINE = "#292f39"
LINE_ACC = "#353c49"
CYAN = "#3486fe"
AMBER = "#ff9a40"
TEXT = "#ffffff"
MUTED = "#a6bbcb"
# Colours represent recorded outcomes, not the action's risk classification.
GREEN = "#1fe393"
YELLOW = "#ffcc00"
RED = "#f44a42"
#: The box's own vertical gradient, top to bottom, from `n03()`.
FILL_TOP, FILL_BOTTOM = "#182639", "#10151d"
#: The row the bar is on, lifted out of the fill so the selection is visible in
#: a screenshot and in a stylesheet.
ROW_ACTIVE = "#0E2130"
SECONDARY = "#C4D6DE"

#: `FONT` in the sheet is a fallback chain; Space Grotesk is not on every
#: machine, and a bar with no font at all is a bar in the system default.
FONT = "Space Grotesk, Segoe UI, Arial"
MONO = "SFMono-Regular, Consolas, monospace"

# ── panel geometry ────────────────────────────────────────────────────────
GEOMETRY = {
    "radius": 18,
    "outline": True,
    "title": (103, 87, 735, 42),
    "caret": (103, 92, 2, 27),
    "esc": (BAR_WIDTH - 60, 22, 32, 32),
    "hint": (32, 149, BAR_WIDTH - 64, 17),
    "divider": (30, 168, BAR_WIDTH - 60, 1),
    "rows_y": 171, "rows_pitch": 82,
    "row_hl": (30, 0, BAR_WIDTH - 60, 72),
    "icon": (46, 10, 52, 52),
    "row_title_x": 134, "row_title_y": 12, "row_title_size": 14,
    "row_sub_y": 39, "row_sub_size": 11,
    "row_enter": (BAR_WIDTH - 48, 12),
    "footer_rule": (30, BAR_HEIGHT - 59, BAR_WIDTH - 60, 1),
    "footer": (30, BAR_HEIGHT - 45, BAR_WIDTH - 60, 22),
}

#: The three result rows board 3 draws, in the order it draws them. The levels
#: are `core.risk_policy`'s, and `to_row()` turns one into the other.
ROW_LEVELS = ("safe", "medium", "risky")


@dataclass(frozen=True)
class Row:
    """A read-only audit row or a legacy classified-risk row."""

    label: str
    state: str
    level: str
    dot: str
    subtitle: str = ""


# Legacy risk classification used by to_row; audit rows use outcome mapping.
_RISK_TOKENS = {
    "safe": ("aman · langsung", GREEN),
    "medium": ("sedang · bisa diurungkan", YELLOW),
    "risky": ("berisiko · konfirmasi", RED),
}


def to_row(label: str, tool: str, args: dict | None = None,
           subtitle: str = "") -> Row:
    """One row, with its level asked of the gate rather than guessed.

    `core.tool_risk.classify` is the same call the execution gate makes, so a
    row that says "berisiko" and an action that runs without asking is a bug
    this function cannot produce. A classifier that raises — a broken import, a
    table edited wrongly — answers `risky`, which is the strict end and the
    same default `risk_policy.level_of` uses.

    `subtitle` is the second line `b02()` draws under each result's title: what
    running it actually does. It is passed in rather than derived, because the
    only thing that knows what a tool does is the caller that has the tool.
    """
    level = "risky"
    try:
        from core import tool_risk

        level = str(tool_risk.classify(tool, args).level or "risky")
    except Exception:                               # noqa: BLE001
        level = "risky"
    if level not in _RISK_TOKENS:
        level = "risky"
    state, dot = _RISK_TOKENS[level]
    return Row(str(label), state, level, dot, str(subtitle or ""))


def default_rows(*, strict=False) -> list[Row]:
    """Recent recorded outcomes, newest first; never invent completed work.

    The audit can contain request/confirmation events as well as outcomes.
    Only terminal outcomes have a matching status colour; in-progress or
    unknown entries must not be advertised as done, unverified or failed.
    """
    try:
        from core import audit_log
        entries = audit_log.shared().entries(50, strict=True) if strict else audit_log.shared().entries(50)
    except Exception as exc:  # noqa: BLE001
        print(f"[JARVIS] Command bar: audit unavailable — {type(exc).__name__}: {exc}")
        if strict:
            raise
        return []
    from ui.tray_panel_model import _t

    mapping = {
        "done": ("ui.command.outcome.done", GREEN),
        "unverified": ("ui.command.outcome.unverified", YELLOW),
        "failed": ("ui.command.outcome.failed", RED),
    }
    rows = []
    for entry in reversed(entries):
        outcome = str(entry.get("outcome") or "").lower()
        if outcome not in mapping:
            continue
        label = str(entry.get("tool") or "").strip()
        if not label:
            continue
        state_key, colour = mapping[outcome]
        rows.append(Row(label=label, state=_t(state_key), level=outcome,
                        dot=colour, subtitle=str(entry.get("detail") or "")))
        if len(rows) == 3:
            break
    return rows


def shown_rows(rows: list[Row]) -> list[Row]:
    """The panel has space for at most three rows."""
    return list(rows or [])[:3]


# The legend describes recorded outcomes; row icons also distinguish statuses.
FOOTER = (("done", 252), ("unverified", 447), ("failed", 668))


_font_loaded = False


def _ensure_font() -> None:
    """Load the bundled font even when the main window has never opened."""
    global _font_loaded
    if _font_loaded:
        return
    try:
        from pathlib import Path
        from PyQt6.QtGui import QFontDatabase
        path = Path(__file__).resolve().parent.parent / 'assets/fonts/SpaceGrotesk-Variable.ttf'
        _font_loaded = QFontDatabase.addApplicationFont(str(path)) >= 0
    except Exception:  # noqa: BLE001, S110 — system font fallback
        pass


def _style_field(field) -> None:
    """Make the control disappear into the drawing.

    No frame, no fill, the sheet's typeface, and a text cursor in the accent
    colour so the caret the artboard draws is the caret Qt really blinks.
    """
    try:
        from PyQt6.QtGui import QFont

        _ensure_font()
        font = QFont(FONT.split(",")[0].strip().strip("'"), 14)
        font.setWeight(QFont.Weight.Normal)
        field.setFont(font)
        field.setStyleSheet(
            f"QLineEdit {{ background: transparent; border: none;"
            f" color: {TEXT}; padding: 0; selection-background-color: {LINE_ACC}; }}"
            f" QLineEdit {{ selection-color: {TEXT}; }}")
    except Exception as e:                          # noqa: BLE001
        print(f"[JARVIS] Command bar: field not styled — {type(e).__name__}: {e}")


class _BarWindow:
    """Factory for the frameless box, kept as a class so the paint hook is one
    line to find.

    A subclass would have to be defined after `QWidget` is imported, which is
    inside `_build()` — a Qt subclass at module scope is the pattern this repo
    forbids, because it imports Qt on a machine that may not have it. So the
    class is built on demand.
    """

    def __new__(cls):                               # noqa: N804 — a factory
        from PyQt6.QtWidgets import QWidget

        class _CmdBar(QWidget):
            _rows: list = []
            _hint: str = ""
            _field = None

            def paintEvent(self, _event):           # noqa: N802 — Qt's name
                try:
                    from PyQt6.QtGui import QPainter

                    painter = QPainter(self)
                    try:
                        paint_bar(painter, self)
                    finally:
                        painter.end()
                except Exception as e:              # noqa: BLE001
                    print(f"[JARVIS] Command bar: paint failed — "
                          f"{type(e).__name__}: {e}")

        return _CmdBar()


_ICON_CACHE = {}


def _draw_icon(painter, name, x, y, size=24):
    """Use bundled vector icons on Qt; Qt-less tests fall back to a glyph."""
    try:
        from PyQt6.QtCore import QSize
        from ui.hud_icons import icon
        key = (name, size)
        if key not in _ICON_CACHE:
            _ICON_CACHE[key] = icon(name, '#4ba2ff', size).pixmap(QSize(size, size))
        painter.drawPixmap(int(x), int(y), _ICON_CACHE[key])
    except Exception:  # noqa: BLE001 — non-Qt recording painters cannot load SVGs
        from PyQt6.QtGui import QColor
        painter.setPen(QColor('#4ba2ff'))
        _text(painter, x, y, size, size, '◇', 15, align='center')


def paint_bar(painter, window) -> None:
    """Draw the command bar from `GEOMETRY`.

    Order matters: the fill, then the rule, then the text, then the rows, then
    the footer rule last so the row that sits closest to it is not clipped.
    """
    from PyQt6.QtCore import QPointF, QRectF, Qt
    from PyQt6.QtGui import QColor, QLinearGradient, QPen

    g = GEOMETRY
    w, h = BAR_WIDTH, BAR_HEIGHT
    scale = getattr(window, '_layout_scale', 1.0)
    if scale != 1.0:
        painter.scale(scale, scale)
    painter.setRenderHint(_render_hint(painter), True)

    # 1. the fill, 16 px radius, with the artboard's gradient
    gradient = QLinearGradient(QPointF(0, 0), QPointF(0, h))
    gradient.setColorAt(0.0, QColor(FILL_TOP))
    gradient.setColorAt(1.0, QColor(FILL_BOTTOM))
    painter.setBrush(gradient)
    pen = QPen(QColor('#345277'))
    pen.setWidth(1)
    painter.setPen(pen)
    painter.drawRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1), g["radius"], g["radius"])

    # 2. the artboard's radial glow, drawn behind everything but clipped to
    #    the box: `b02()` paints a cyan radial gradient above the fill. It is
    #    a decoration, so it is drawn with no pen and never affects the rows.
    try:
        from PyQt6.QtGui import QRadialGradient

        glow = QRadialGradient(QPointF(w / 2.0, 0.0), max(w, h) * 0.9)
        g_inner = QColor(CYAN)
        g_inner.setAlphaF(0.09)
        g_outer = QColor(CYAN)
        g_outer.setAlphaF(0.0)
        glow.setColorAt(0.0, g_inner)
        glow.setColorAt(1.0, g_outer)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(glow)
        painter.drawRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1),
                                g["radius"], g["radius"])
    except Exception:                               # noqa: BLE001, S110
        # A glow that cannot be built is a decoration: the bar still draws.
        pass

    # Larger, softly lit input and header follow the supplied reference.
    painter.setPen(QColor('#63aeff'))
    _text(painter, 32, 22, 400, 26, 'J A R V I S', 14, weight=700)
    painter.setPen(QPen(QColor('#24476e'), 5))
    painter.setBrush(QColor('#141b25'))
    painter.drawRoundedRect(QRectF(30, 70, w - 60, 76), 14, 14)
    outline = QLinearGradient(QPointF(30, 70), QPointF(w - 30, 70))
    outline.setColorAt(0, QColor('#56aaff'))
    outline.setColorAt(1, QColor('#34475e'))
    painter.setPen(QPen(outline, 1.4))
    painter.drawRoundedRect(QRectF(30, 70, w - 60, 76), 14, 14)
    painter.setPen(QColor('#65b1ff'))
    _text(painter, 57, 90, 28, 36, '›', 26)

    # The hexagonal J mark is branding; Escape remains the close shortcut.
    _draw_icon(painter, 'hexagon', w - 58, 22, 27)
    painter.setPen(QColor('#69b5ff'))
    _text(painter, w - 58, 22, 27, 27, 'J', 11, weight=700, align='center')

    # The editable field owns its caret; do not paint a second one over it.

    # 5. the context line
    hint = str(getattr(window, "_hint", "") or "")
    hx, hy, hw, hh = g["hint"]
    if getattr(window, '_retry_visible', False):
        hw -= 130
    if hint:
        painter.setPen(QColor(MUTED))
        _text(painter, hx, hy, hw, hh, hint, 10.5)

    # 6. the divider under it
    dx, dy, dw, _dh = g["divider"]
    painter.setPen(QPen(QColor(LINE)))
    painter.drawLine(QPointF(dx, dy), QPointF(dx + dw, dy))

    # 7. Recent audit outcomes are read-only, not selectable commands.
    rows = shown_rows(list(getattr(window, "_rows", []) or []))
    if not rows:
        from ui.tray_panel_model import _t
        painter.setPen(QColor(MUTED))
        state = getattr(window, "_audit_state", "done")
        label = (_t('ui.command.outcome.loading') if state == 'loading' else
                 _t('ui.command.outcome.error') if state == 'error' else
                 _t("ui.command.outcome.empty"))
        _text(painter, 48, 186, w - 96, 24, label, 12)
    for index, row in enumerate(rows):
        y = g["rows_y"] + index * g["rows_pitch"]
        hx, hy, hw, hh = g["row_hl"]
        painter.setPen(QPen(QColor(LINE_ACC)))
        painter.setBrush(QColor(PANEL))
        painter.drawRoundedRect(QRectF(hx, y + hy, hw, hh), 10, 10)
        ix, iy, iw, ih = g["icon"]
        painter.setPen(QPen(QColor(LINE)))
        painter.setBrush(QColor(BASE))
        painter.drawRoundedRect(QRectF(ix, y + iy, iw, ih), 9, 9)
        icon_name = {'done': 'shield-check', 'unverified': 'file-text',
                     'failed': 'triangle-alert'}.get(row.level, 'shield')
        _draw_icon(painter, icon_name, ix + 10, y + iy + 10, 32)
        painter.setPen(QColor(TEXT))
        _text(painter, g["row_title_x"], y + g["row_title_y"],
              w - g["row_title_x"] - 92, 20, row.label,
              g["row_title_size"], weight=500)
        if row.subtitle:
            painter.setPen(QColor(SECONDARY))
            _text(painter, g["row_title_x"], y + g["row_sub_y"],
                  w - g["row_title_x"] - 92, 18, row.subtitle,
                  g["row_sub_size"])
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(row.dot))
        painter.drawEllipse(QRectF(w - 78, y + 29, 14, 14))

    # 8. the footer rule and the three legend segments
    fx, fy, fw, _fh = g["footer_rule"]
    painter.setPen(QPen(QColor(LINE)))
    painter.drawLine(QPointF(fx, fy), QPointF(fx + fw, fy))
    _tx, ty, _tw, th = g["footer"]
    painter.setPen(QPen(QColor(LINE_ACC)))
    for x in (425, 646):
        painter.drawLine(QPointF(x, ty + 2), QPointF(x, ty + th - 2))
    from ui.tray_panel_model import _t
    for (key, lx), color in zip(FOOTER, (GREEN, YELLOW, RED)):
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(color))
        painter.drawEllipse(QRectF(lx, ty + 6, 10, 10))
        painter.setPen(QColor(MUTED))
        _text(painter, lx + 19, ty, 175, th, _t('ui.command.outcome.' + key), 11)


def _render_hint(painter):
    """`QPainter.RenderHint.Antialiasing`, or None on a stub that has no enum."""
    try:
        from PyQt6.QtGui import QPainter

        return QPainter.RenderHint.Antialiasing
    except Exception:                               # noqa: BLE001
        return None


def _text(painter, x, y, w, h, text, size, weight=400, mono=False, align="left"):
    """One line of text inside its box, vertically centred by baseline.

    Wrapped: a missing font or an unmapped alignment on a stub must cost the
    line, not the whole drawing — the bar is opened by a global chord, and a
    paint exception there is an invisible failure.
    """
    try:
        from PyQt6.QtCore import QRectF, Qt
        from PyQt6.QtGui import QFont

        family = MONO if mono else FONT
        font = QFont(family.split(",")[0].strip().strip("'"), int(size))
        font.setWeight(QFont.Weight.Medium if weight >= 500 else QFont.Weight.Normal)
        painter.setFont(font)
        align_map = {"left": Qt.AlignmentFlag.AlignLeft,
                     "right": Qt.AlignmentFlag.AlignRight,
                     "center": Qt.AlignmentFlag.AlignHCenter}
        flags = align_map.get(align, Qt.AlignmentFlag.AlignLeft)
        rendered = str(text)
        metrics = painter.fontMetrics() if hasattr(painter, 'fontMetrics') else None
        if metrics is not None and hasattr(metrics, 'elidedText'):
            rendered = metrics.elidedText(rendered, Qt.TextElideMode.ElideRight, int(w))
        painter.drawText(QRectF(x, y, w, h),
                         flags | Qt.AlignmentFlag.AlignVCenter, rendered)
    except Exception as e:                          # noqa: BLE001
        # A line is worth less than the drawing; say so and keep going.
        print(f"[JARVIS] Command bar: text not drawn — {type(e).__name__}: {e}")


