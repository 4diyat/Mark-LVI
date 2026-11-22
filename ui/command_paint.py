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
    `GEOMETRY`     every number from `docs/mockups/build.py: n03()`, in one dict
    `default_rows` the three result lines, CLASSIFIED by `core.tool_risk`
    `paint_bar`    the drawing: gradien, 16 px radius, cyan rule, Esc chip,
                   caret, context line, three rows with 3 px dots, footer
"""
from __future__ import annotations

from dataclasses import dataclass

# ── board 3's tokens, declared here rather than borrowed ────────────────────
# Same rule as `ui/confirm_banner.py`: an ambient surface copies the sheet's
# numbers and never reads `ui.theme.C`, which still carries the look of the
# window ambient mode replaced.
# The artboard's box. The window IS the box, so every number below is relative.
BAR_WIDTH, BAR_HEIGHT = 640, 184
FIELD_MARGIN, FIELD_HEIGHT = 24, 48

BASE = "#04080D"
PANEL = "#0A1722"
LINE = "#17323F"
LINE_ACC = "#2A6477"
CYAN = "#4FD8F0"
AMBER = "#F5A524"
TEXT = "#E6F4F8"
MUTED = "#8FA9B5"
#: The box's own vertical gradient, top to bottom, from `n03()`.
FILL_TOP, FILL_BOTTOM = "#0C1E29", "#081319"
#: The row the bar is on, lifted out of the fill so the selection is visible in
#: a screenshot and in a stylesheet.
ROW_ACTIVE = "#0E2130"
SECONDARY = "#C4D6DE"

#: `FONT` in the sheet is a fallback chain; Space Grotesk is not on every
#: machine, and a bar with no font at all is a bar in the system default.
FONT = "Space Grotesk, Segoe UI, Arial"
MONO = "SFMono-Regular, Consolas, monospace"

# ── board 3's geometry, as numbers you can check ────────────────────────────
# Every value below is read off `n03()`. The box is 640 × 184 at (320, 268) on
# a 1280 × 720 desktop; the window is the box, so all of it is relative.
GEOMETRY = {
    "radius": 16,
    "rule": (16, 1, BAR_WIDTH - 32, 2),          # 2 px cyan top rule
    "title": (24, 46, 400, 24),                  # the typed line
    "caret": (196, 30, 2, 20),                   # before the field takes over
    "esc": (BAR_WIDTH - 74, 28, 50, 22),
    "hint": (24, 68, BAR_WIDTH - 48, 16),        # "Konteks: …"
    "divider": (18, 82, BAR_WIDTH - 36, 1),
    "rows_y": 106, "rows_pitch": 26, "dot_x": 32, "dot_r": 3,
    "row_label": 46, "row_state_right": 26,
    # The footer fits INSIDE the 184 px box the artboard measures — it has to,
    # because the window is the box. Rows end at 158, so the rule goes at 166
    # (18 px, the artboard's own inset) and the legend's 18 px line at 166-184.
    # The artboard puts its legend further down because ITS box is taller; the
    # numbers it pins (inset 18, 10.5 px, muted) are kept.
    "footer_rule": (18, 166, BAR_WIDTH - 36, 1),
    "footer": (26, 166, BAR_WIDTH - 52, 18),
}

#: The three result rows board 3 draws, in the order it draws them. The levels
#: are `core.risk_policy`'s, and `to_row()` turns one into the other.
ROW_LEVELS = ("safe", "medium", "risky")


@dataclass(frozen=True)
class Row:
    """One result line: what it would do, and what running it costs.

    `dot` is the colour of the 3 px mark at the left — cyan for a level that
    runs at once, amber for one that asks first, muted for one that can be
    walked back. Those three assignments come from `_RISK_TOKENS` and are the
    only place the mapping exists.
    """

    label: str
    state: str
    level: str
    dot: str


#: `safe` runs now, `medium` runs and can be undone, `risky` asks first. The
#: WORDS are board 3's; the mapping is `core.risk_policy`'s three levels.
_RISK_TOKENS = {
    "safe": ("aman · langsung", CYAN),
    "medium": ("sedang · bisa diurungkan", MUTED),
    "risky": ("berisiko · konfirmasi", AMBER),
}


def to_row(label: str, tool: str, args: dict | None = None) -> Row:
    """One row, with its level asked of the gate rather than guessed.

    `core.tool_risk.classify` is the same call the execution gate makes, so a
    row that says "berisiko" and an action that runs without asking is a bug
    this function cannot produce. A classifier that raises — a broken import, a
    table edited wrongly — answers `risky`, which is the strict end and the
    same default `risk_policy.level_of` uses.
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
    return Row(str(label), state, level, dot)


def default_rows() -> list[Row]:
    """The three rows board 3 draws, fed by three real tools.

    Two of the artboard's own three lines are drawn as written. The third —
    "Susun jendela 2 kolom" — is NOT: there is no window-snapping code in this
    tree, and board 5's row for it already refuses out loud (recorded in
    `docs/mockups/NOT-IN-MOCKUP.md`). A bar that offered it would be offering a
    thing the assistant cannot do, in the surface where the user types
    instructions. Its slot carries a real `medium` action instead, so the third
    dot and the third state string still appear and still mean what they say.

    Every tool name below is in `core.risk_policy.registered()`, so no level
    here is invented by this module: `screen_processor` reads the screen,
    `send_message` leaves the machine, `open_app` changes state with an undo.
    """
    return [
        to_row("Ringkas 14 baris terpilih", "screen_processor"),
        to_row("Kirim ke tim keuangan", "send_message"),
        to_row("Buka anggaran.xlsx", "open_app"),
    ]


def shown_rows(rows: list[Row]) -> list[Row]:
    """What fits in a 184 px box: three. A fourth would be under the footer."""
    return list(rows or [])[:3]


# ── the drawn half ──────────────────────────────────────────────────────────
#
# WHY A PAINTED BOX AND NOT A STYLESHEET
#     Two of board 3's marks cannot be written in Qt style sheets at all: the
#     box is a vertical GRADIENT with a 2 px cyan rule clipped to a 16 px
#     radius on its top corners, and the three result rows carry a 3 px dot
#     whose colour is the row's risk level. `border-radius` on a translucent
#     frameless window also draws the corner of the RECTANGLE unless the paint
#     path is antialiased. So the box is drawn, and the only real Qt widget in
#     it is the one that takes typing.
#
# WHY IT IS A SEPARATE FUNCTION
#     `paint_bar(painter, window)` takes the painter and reads three attributes
#     off the window: `_rows`, `_hint` and `_field`. That is enough for the
#     repo's Qt stub to drive it, which is the only way this drawing is
#     verified on a machine with no display — see
#     `tests/test_command_bar.py::test_the_bar_draws_board_3s_box`.

#: Board 3's footer, drawn as written. Two literals rather than catalogue keys,
#: for the reason `KEYS_HINT` in `ui/confirm_banner.py` gives: "Esc",
#: "Ctrl+Space", "↑↓" and "↵" are the names PRINTED ON KEYBOARDS, and a
#: translation of them is a legend for keys the user does not own.
FOOTER = "↑↓ pilih    ↵ jalankan    Esc tutup"


def _style_field(field) -> None:
    """Make the control disappear into the drawing.

    No frame, no fill, the sheet's typeface, and a text cursor in the accent
    colour so the caret the artboard draws is the caret Qt really blinks.
    """
    try:
        from PyQt6.QtGui import QFont

        font = QFont(FONT.split(",")[0].strip().strip("'"), 13)
        font.setWeight(QFont.Weight.Medium)
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


def paint_bar(painter, window) -> None:
    """Draw board 3's 640 × 184 box. Every number comes from `GEOMETRY`.

    Order matters: the fill, then the rule, then the text, then the rows, then
    the footer rule last so the row that sits closest to it is not clipped.
    """
    from PyQt6.QtCore import QPointF, QRectF, Qt
    from PyQt6.QtGui import QColor, QLinearGradient, QPen

    g = GEOMETRY
    w, h = BAR_WIDTH, BAR_HEIGHT
    painter.setRenderHint(_render_hint(painter), True)

    # 1. the fill, 16 px radius, with the artboard's gradient
    gradient = QLinearGradient(QPointF(0, 0), QPointF(0, h))
    gradient.setColorAt(0.0, QColor(FILL_TOP))
    gradient.setColorAt(1.0, QColor(FILL_BOTTOM))
    painter.setBrush(gradient)
    pen = QPen(QColor(LINE_ACC))
    pen.setWidth(1)
    painter.setPen(pen)
    painter.drawRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1), g["radius"], g["radius"])

    # 2. the 2 px cyan rule across the top, inset 16 px each side
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(CYAN))
    painter.setOpacity(0.7)
    rx, ry, rw, rh = g["rule"]
    painter.drawRoundedRect(QRectF(rx, ry, rw, rh), rh / 2, rh / 2)
    painter.setOpacity(1.0)

    # 3. the Esc chip, right-aligned on the title line
    ex, ey, ew, eh = g["esc"]
    painter.setBrush(Qt.BrushStyle.NoBrush)
    chip_pen = QPen(QColor(LINE))
    chip_pen.setWidth(1)
    painter.setPen(chip_pen)
    painter.drawRoundedRect(QRectF(ex, ey, ew, eh), 6, 6)
    painter.setPen(QColor(MUTED))
    _text(painter, ex, ey, ew, eh, "Esc", 10, weight=500, mono=True, align="center")

    # 4. the caret, drawn only while the field is empty — the real QLineEdit
    #    owns the caret once there is text, and two carets would be one lie.
    field = getattr(window, "_field", None)
    empty = True
    try:
        empty = not bool(field is not None and str(field.text() or ""))
    except Exception:                               # noqa: BLE001
        empty = True
    if empty:
        cx, cy, cw, ch = g["caret"]
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(CYAN))
        painter.drawRect(QRectF(cx, cy, cw, ch))

    # 5. the context line
    hint = str(getattr(window, "_hint", "") or "")
    hx, hy, hw, hh = g["hint"]
    if hint:
        painter.setPen(QColor(MUTED))
        _text(painter, hx, hy, hw, hh, hint, 10.5)

    # 6. the divider under it
    dx, dy, dw, _dh = g["divider"]
    painter.setPen(QPen(QColor(LINE)))
    painter.drawLine(QPointF(dx, dy), QPointF(dx + dw, dy))

    # 7. the three rows
    rows = shown_rows(list(getattr(window, "_rows", []) or []))
    for index, row in enumerate(rows):
        y = g["rows_y"] + index * g["rows_pitch"]
        if index == 0:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(ROW_ACTIVE))
            painter.drawRoundedRect(QRectF(12, y - 20, w - 24, 22), 8, 8)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(row.dot))
        painter.drawEllipse(QPointF(g["dot_x"], y - 4), g["dot_r"], g["dot_r"])
        painter.setPen(QColor(TEXT if index == 0 else SECONDARY))
        _text(painter, g["row_label"], y - 15, 420, 20, row.label, 12, weight=500)
        painter.setPen(QColor(row.dot))
        _text(painter, w - g["row_state_right"] - 300, y - 15, 300, 20,
              row.state, 10, align="right")

    # 8. the footer rule and legend
    fx, fy, fw, _fh = g["footer_rule"]
    painter.setPen(QPen(QColor(LINE)))
    painter.drawLine(QPointF(fx, fy), QPointF(fx + fw, fy))
    painter.setPen(QColor(MUTED))
    tx, ty, tw, th = g["footer"]
    _text(painter, tx, ty, tw, th, FOOTER, 10.5)


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
        painter.drawText(QRectF(x, y, w, h),
                         flags | Qt.AlignmentFlag.AlignVCenter, str(text))
    except Exception as e:                          # noqa: BLE001
        # A line is worth less than the drawing; say so and keep going.
        print(f"[JARVIS] Command bar: text not drawn — {type(e).__name__}: {e}")


