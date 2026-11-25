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
# The artboard's box. `b02()` — the new-UI command bar — draws 720 × 352 (the
# old `n03()` sheet drew 640 × 184; the new mockup is taller and carries an
# icon square and a subtitle under each result row). The window IS the box,
# so every number below is relative to it.
BAR_WIDTH, BAR_HEIGHT = 720, 352
FIELD_MARGIN, FIELD_HEIGHT = 24, 48

BASE = "#0c0d11"
PANEL = "#101820"
LINE = "#1c2028"
LINE_ACC = "#243040"
CYAN = "#3486fe"
AMBER = "#ff9a40"
TEXT = "#ffffff"
MUTED = "#5e636c"
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

# ── board 2's geometry, as numbers you can check ───────────────────────────
# Every value below is read off `b02()`. The box is 720 × 352 at (280, 178) on
# a 1280 × 720 desktop; the window is the box, so all of it is relative to it.
# The bar is taller than the old `n03()` sheet because each result row now
# carries a 28 px icon square plus a title AND a subtitle.
GEOMETRY = {
    "radius": 16,
    # the box's own border, drawn as the artboard's cyan-tinted outline
    "outline": True,
    "title": (26, 44, 400, 28),                  # the typed line, 19 px
    "caret": (26 + 176, 27, 2, 22),              # before the field takes over
    "esc": (610, 30, 44, 20),                    # the "Esc" chip, right-aligned
    "hint": (26, 68, BAR_WIDTH - 52, 16),        # "Konteks: …"
    "divider": (20, 82, BAR_WIDTH - 40, 1),
    # the three result rows: first y, pitch, and the icon square each carries
    "rows_y": 108, "rows_pitch": 70,
    "row_hl": (12, -20, BAR_WIDTH - 24, 62),     # the selected row's highlight
    "icon": (24, -8, 28, 28),                    # the 28 px square + glyph
    "row_title_x": 64, "row_title_y": 2, "row_title_size": 13,
    "row_sub_y": 20, "row_sub_size": 11,
    "row_enter": (BAR_WIDTH - 30, 12),           # the "↵" on the selected row
    # the footer, drawn inside the 352 px box
    "footer_rule": (20, BAR_HEIGHT - 44, BAR_WIDTH - 40, 1),
    "footer": (26, BAR_HEIGHT - 20, BAR_WIDTH - 52, 18),
}

#: The three result rows board 3 draws, in the order it draws them. The levels
#: are `core.risk_policy`'s, and `to_row()` turns one into the other.
ROW_LEVELS = ("safe", "medium", "risky")


@dataclass(frozen=True)
class Row:
    """One result line: what it would do, and what running it costs.

    `b02()` draws each row as a 28 px icon square with a glyph, a title (13 px)
    and a subtitle (11 px) beneath it, plus a "↵" on the selected row. The
    `dot` is the icon square's glyph colour — cyan for a level that runs at
    once, amber for one that asks first, muted for one that can be walked
    back. Those three assignments come from `_RISK_TOKENS` and are the only
    place the mapping exists.
    """

    label: str
    state: str
    level: str
    dot: str
    subtitle: str = ""


#: `safe` runs now, `medium` runs and can be undone, `risky` asks first. The
#: WORDS are board 3's; the mapping is `core.risk_policy`'s three levels.
_RISK_TOKENS = {
    "safe": ("aman · langsung", CYAN),
    "medium": ("sedang · bisa diurungkan", MUTED),
    "risky": ("berisiko · konfirmasi", AMBER),
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


def default_rows() -> list[Row]:
    """The three rows `b02()` draws, fed by three real tools.

    `b02()`'s own three lines are drawn as written, with the subtitle each row
    carries. The tools are real — every name is in `core.risk_policy.registered()`
    — so no level here is invented by this module: `screen_processor` reads the
    screen, `send_message` leaves the machine, `open_app` changes state with an
    undo. The subtitles say what running each one actually does, matching the
    artboard's second line under each title.
    """
    return [
        to_row("Ringkas dan buat catatan rapat", "screen_processor",
               subtitle="Menulis ringkasan 14 baris lalu menyimpannya"),
        to_row("Hitung ulang subtotal dengan kurs BI", "send_message",
               subtitle="Menawarkan pratinjau sebelum mengubah sel"),
        to_row("Kirim ke tim keuangan", "open_app",
               subtitle="Aksi sedang — bisa diurungkan 10 menit"),
    ]


def shown_rows(rows: list[Row]) -> list[Row]:
    """What fits in a 352 px box: three. A fourth would be under the footer."""
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
#: Board 2's footer, drawn as written, as three segments at the artboard's
#: own x positions. Two literals rather than catalogue keys, for the reason
#: `KEYS_HINT` in `ui/confirm_banner.py` gives: "Esc", "Ctrl+Space", "↑↓" and
#: "↵" are the names PRINTED ON KEYBOARDS, and a translation of them is a
#: legend for keys the user does not own.
FOOTER = (("↑↓ pilih", 26), ("↵ jalankan", 106), ("Ctrl+Space tutup", 196))


def _style_field(field) -> None:
    """Make the control disappear into the drawing.

    No frame, no fill, the sheet's typeface, and a text cursor in the accent
    colour so the caret the artboard draws is the caret Qt really blinks.
    """
    try:
        from PyQt6.QtGui import QFont

        font = QFont(FONT.split(",")[0].strip().strip("'"), 19)
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

    # 2. the artboard's radial glow, drawn behind everything but clipped to
    #    the box: `b02()` paints a cyan radial gradient above the fill. It is
    #    a decoration, so it is drawn with no pen and never affects the rows.
    try:
        from PyQt6.QtGui import QRadialGradient

        glow = QRadialGradient(QPointF(w / 2.0, 0.0), max(w, h) * 0.9)
        g_inner = QColor(CYAN)
        g_inner.setAlphaF(0.0)
        g_outer = QColor(CYAN)
        g_outer.setAlphaF(0.22)
        glow.setColorAt(0.0, g_inner)
        glow.setColorAt(1.0, g_outer)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(glow)
        painter.drawRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1),
                                g["radius"], g["radius"])
    except Exception:                               # noqa: BLE001, S110
        # A glow that cannot be built is a decoration: the bar still draws.
        pass

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

    # 7. the three rows. `b02()` draws each as a 28 px icon square with a
    #    three-line glyph, a 13 px title and an 11 px subtitle beneath it; the
    #    selected row carries a highlight card and a right-aligned "↵".
    rows = shown_rows(list(getattr(window, "_rows", []) or []))
    for index, row in enumerate(rows):
        y = g["rows_y"] + index * g["rows_pitch"]
        # the selected row's highlight card
        if index == 0:
            hx, hy, hw, hh = g["row_hl"]
            painter.setPen(QPen(QColor(LINE_ACC)))
            painter.setBrush(QColor(ROW_ACTIVE))
            painter.drawRoundedRect(QRectF(hx, y + hy, hw, hh), 10, 10)
        # the icon square and its three-line glyph
        ix, iy, iw, ih = g["icon"]
        painter.setPen(QPen(QColor(LINE)))
        painter.setBrush(QColor("#0B1A22"))
        painter.drawRoundedRect(QRectF(ix, y + iy, iw, ih), 8, 8)
        glyph = QColor(row.dot)
        painter.setPen(QPen(glyph, 2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        cx0 = ix + 9.0
        for k in range(3):
            painter.drawLine(QPointF(cx0, y + iy + 6.0 + k * 5.0),
                             QPointF(cx0 + (10.0 if k < 2 else 6.0),
                                     y + iy + 6.0 + k * 5.0))
        # the title and subtitle
        painter.setPen(QColor(TEXT if index == 0 else SECONDARY))
        _text(painter, g["row_title_x"], y + g["row_title_y"],
              w - g["row_title_x"] - 40, 20, row.label,
              g["row_title_size"], weight=500)
        if row.subtitle:
            painter.setPen(QColor(MUTED))
            _text(painter, g["row_title_x"], y + g["row_sub_y"],
                  w - g["row_title_x"] - 40, 18, row.subtitle,
                  g["row_sub_size"])
        # the enter glyph on the selected row
        if index == 0:
            ex, ey = g["row_enter"]
            painter.setPen(QColor(CYAN))
            _text(painter, ex, y + ey, 30, 20, "↵", 12, weight=500,
                  mono=True, align="right")

    # 8. the footer rule and the three legend segments
    fx, fy, fw, _fh = g["footer_rule"]
    painter.setPen(QPen(QColor(LINE)))
    painter.drawLine(QPointF(fx, fy), QPointF(fx + fw, fy))
    tx, ty, tw, th = g["footer"]
    painter.setPen(QColor(MUTED))
    for label, lx in FOOTER:
        _text(painter, lx, ty, tw, th, label, 10.5)


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


