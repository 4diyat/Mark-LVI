"""The command bar: one line of text, opened from anywhere, closed by Esc.

WHY IT IS A WINDOW AND NOT A FIELD IN THE HUD
    The bar exists for the case where the interface is NOT up — ambient mode,
    the orb in the corner, the user mid-task in another program. Putting it
    inside the window would mean summoning the window first, which is the thing
    it exists to avoid.

WHY THE FOCUS RULES ARE A SEPARATE, QT-FREE OBJECT
    "Esc returns focus to the window you came from" is the whole promise, and it
    is also the part that cannot be checked on a machine with no window manager:
    `activateWindow()` is a REQUEST on X11 and macOS, and whether it is honoured
    depends on the WM. So the bookkeeping — who had focus, was it captured, what
    to restore to — lives in `FocusLedger`, where it is decided and tested, and
    the Qt calls are made from `CommandBar` next to it.

    The ledger is honest rather than optimistic: `activateWindow()` returns
    nothing, so there is no way to KNOW the focus came back. What the ledger
    records is the request and whether the handle still existed, which is the
    difference between "asked and probably worked" and "never even asked".

WHAT IT DOES NOT DO
    It does not run commands. `on_submit` is given the text and decides; a bar
    that could execute would be a second dispatcher with its own copy of the
    risk policy.

WHAT IT DID NOT DRAW, AND NOW DOES
    Until board 3 was implemented this window was a translucent box with a
    `QLineEdit` floating in it: no fill, no border, no caret, no hint row, no
    result rows. Board 3 draws all of them, plus a footer that says what the
    keys do. Everything drawn here comes from `docs/mockups/build.py: n03()` —
    the gradient, the 16 px radius, the 2 px cyan rule, the three result rows
    with their 3 px dots, and the `Esc` chip — and the three rows are FED BY
    `core.tool_risk`, so "aman · langsung", "sedang · bisa diurungkan" and
    "berisiko · konfirmasi" are read from the same classifier the gate uses
    rather than typed into a label.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

# The number of remembered entries. Ten is the point past which a recall list
# stops being a memory aid and becomes something to read through.
HISTORY_MAX = 10

# A single line. The bar is one sentence to the assistant, not a document; a
# paste that arrives with newlines is flattened rather than truncated, because
# truncating silently loses the second half of an instruction.
MAX_CHARS = 2000

# Geometry, in one place because the test asserts the field fits inside the
# window rather than re-deriving the numbers from the board.
BAR_WIDTH, BAR_HEIGHT = 640, 184
FIELD_MARGIN, FIELD_HEIGHT = 24, 48

# ── board 3's tokens, declared here rather than borrowed ────────────────────
# Same rule as `ui/confirm_banner.py`: an ambient surface copies the sheet's
# numbers and never reads `ui.theme.C`, which still carries the look of the
# window ambient mode replaced.
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


def flatten(text: str) -> str:
    """One line, no leading/trailing space, capped.

    Newlines become spaces rather than being cut: a pasted two-paragraph
    instruction is still one instruction, and the Enter key means "send".
    """
    flat = " ".join(str(text or "").split())
    return flat[:MAX_CHARS]


@dataclass
class FocusLedger:
    """Who to give focus back to, and whether the attempt was even made."""

    previous: object = None
    captured: bool = False
    restorations: int = 0
    last_result: str = ""

    def capture(self, window) -> None:
        """Remember the window that had focus when the bar opened."""
        self.previous = window
        self.captured = window is not None
        self.last_result = "captured" if self.captured else "nothing to restore"

    def take(self):
        """The handle to restore to, once. A second call gets None.

        Outside a window manager there is nothing to hand focus to. Returning
        the handle once means Esc restores focus even if the bar is dismissed
        twice — for example Esc followed by a lost-focus close — without
        fighting over which window that is.
        """
        window, self.previous = self.previous, None
        return window if self.captured else None

    def restored(self, ok: bool) -> None:
        self.restorations += 1
        self.last_result = "restored" if ok else "the window manager refused"

    @property
    def restore_attempted(self) -> bool:
        return self.restorations > 0


class CommandBar:
    """The bar's state machine: open, type, Esc or Enter, closed.

    Qt is reached only through `_build()`, and every Qt call that can fail is
    wrapped: the bar is opened by a global chord, so an exception here would
    surface as a dead keyboard shortcut with no explanation.
    """

    def __init__(self, on_submit: Callable[[str], None] | None = None,
                 on_close: Callable[[], None] | None = None,
                 placeholder: str = "Perintah atau pertanyaan…"):
        self._on_submit = on_submit
        self._on_close = on_close
        self._placeholder = placeholder
        self._window = None
        self._field = None
        self._ledger = FocusLedger()
        self._open = False
        self._history: list[str] = []
        self._recall = -1
        self._error = ""
        # The three result rows and the context line are BOARD 3's, and they
        # are built from `core.tool_risk` rather than from a literal in a
        # painter. A caller that has a real list calls `set_rows`.
        self._rows: list[Row] = default_rows()
        self._hint: str = ""

    # ── what happened ────────────────────────────────────────────────────────

    @property
    def available(self) -> bool:
        return self._window is not None

    @property
    def is_open(self) -> bool:
        return self._open

    @property
    def error(self) -> str:
        return self._error

    @property
    def ledger(self) -> FocusLedger:
        """Exposed so a caller (and a test) can ask what Esc will restore to."""
        return self._ledger

    @property
    def history(self) -> list[str]:
        return list(self._history)

    # ── lifecycle ────────────────────────────────────────────────────────────

    def open(self, previous=None) -> bool:
        """Show the bar and capture `previous` for Esc to return to.

        `previous` is passed in rather than looked up: Qt's way to ask "who has
        focus" is `QApplication.activeWindow()`, which is None on several
        compositors. The caller knows which window the user came from — the tray
        knows, the hotkey's owner knows — so it is given, not guessed.
        """
        self._ledger.capture(previous if previous is not None else _active_window())
        if not self._build():
            return False
        try:
            self._window.show()
            self._window.raise_()
            self._window.activateWindow()
            self._field.setFocus()
            self._field.clear()
            self._recall = -1
            self._open = True
            return True
        except Exception as e:                      # noqa: BLE001
            self._error = f"{type(e).__name__}: {e}"
            self._open = False
            return False

    def close(self) -> None:
        """Hide the bar and hand focus back. Safe to call when already closed."""
        if not self._open and self._window is None:
            return
        self._open = False
        window = self._window
        if window is not None:
            try:
                window.hide()
            except Exception as e:                  # noqa: BLE001
                print(f"[JARVIS] Command bar: could not hide — {type(e).__name__}: {e}")
        target = self._ledger.take()
        if target is None:
            self._ledger.restored(False)
        else:
            try:
                target.raise_()
                target.activateWindow()
                self._ledger.restored(True)
            except Exception as e:                  # noqa: BLE001
                # Some window managers refuse; the bar is closed either way, and
                # saying so is better than claiming the focus came back.
                print(f"[JARVIS] Command bar: focus not returned — "
                      f"{type(e).__name__}: {e}")
                self._ledger.restored(False)
        cb = self._on_close
        if cb is not None:
            try:
                cb()
            except Exception as e:                  # noqa: BLE001
                print(f"[JARVIS] Command bar: close handler failed — "
                      f"{type(e).__name__}: {e}")

    def toggle(self, previous=None) -> bool:
        if self._open:
            self.close()
            return False
        return self.open(previous)

    # ── typing ───────────────────────────────────────────────────────────────

    def submit(self, text: str | None = None) -> bool:
        """Send the line. Empty input closes quietly; it never calls `on_submit`.

        Returns whether anything was sent, so the caller can decide between
        "nothing happened" and "the assistant has it".
        """
        raw = self._field.text() if text is None and self._field is not None else text
        line = flatten(raw)
        if not line:
            self.close()
            return False
        self._remember(line)
        self.close()
        cb = self._on_submit
        if cb is None:
            return False
        try:
            cb(line)
            return True
        except Exception as e:                      # noqa: BLE001
            # The bar is already closed and the text is already in the history,
            # so the user can recall it and try again.
            print(f"[JARVIS] Command bar: submit handler failed — "
                  f"{type(e).__name__}: {e}")
            return False

    def _remember(self, line: str) -> None:
        # Consecutive duplicates are dropped: pressing Enter twice on the same
        # line is a repeat, not two things the user wants to find again.
        if self._history and self._history[0] == line:
            return
        self._history.insert(0, line)
        del self._history[HISTORY_MAX:]

    def recall(self, step: int = -1) -> str:
        """Walk the history. `step=-1` is one older, `+1` one newer.

        Index 0 is the NEWEST line and -1 means "nothing recalled, field empty".
        Walking older increases the index, walking newer decreases it. Both ends
        stop rather than wrap: a recalled command that silently becomes a
        different one is worse than a key that stops responding, and Down past
        the newest correctly gives the empty field back.
        """
        if not self._history:
            return ""
        if step < 0:
            # -1 + 1 == 0: the first walk older lands on the newest line, so
            # there is no special case to write here. (There was one, and it
            # turned out to be unreachable — every branch computed the same
            # index, which is a branch that only looks load-bearing.)
            index = min(self._recall + 1, len(self._history) - 1)
        else:
            index = self._recall - 1
            index = max(index, -1)
        self._recall = index
        line = "" if index < 0 else self._history[index]
        if self._field is not None:
            try:
                if line:
                    self._field.setText(line)
                else:
                    self._field.clear()
            except Exception as e:                  # noqa: BLE001
                print(f"[JARVIS] Command bar: recall not shown — "
                      f"{type(e).__name__}: {e}")
        return line

    # ── the Qt half ──────────────────────────────────────────────────────────

    def _build(self) -> bool:
        """Create the window once. False (with `error`) if Qt cannot."""
        if self._window is not None:
            return True
        try:
            from PyQt6.QtCore import Qt
            from PyQt6.QtWidgets import QLineEdit

            window = _BarWindow()
            window.setWindowFlags(Qt.WindowType.FramelessWindowHint
                                  | Qt.WindowType.Tool
                                  | Qt.WindowType.WindowStaysOnTopHint)
            window.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
            window.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, False)
            window.setWindowTitle(_assistant_name())
            # 640 × 184 from the artboard: one line, one hint row, no scroll.
            window.setFixedSize(BAR_WIDTH, BAR_HEIGHT)

            field = QLineEdit(window)
            field.setPlaceholderText(self._placeholder)
            # The field is TRANSPARENT and sits exactly on the title line, so
            # the drawing and the text control are one thing rather than a
            # styled box with an unstyled control on top of it. `paint_bar`
            # draws the caret only while the field is empty.
            _style_field(field)
            g = GEOMETRY
            field.setGeometry(g["title"][0], g["title"][1] - 22,
                              BAR_WIDTH - g["title"][0] * 2, 28)
            # Enter sends, Esc closes, Up/Down walk the history. Bound on the
            # widget rather than through QShortcut: a shortcut needs the window
            # to have focus, and the whole point is that it just got it.
            field.returnPressed.connect(self.submit)
            window.keyPressEvent = self._on_key

            window._rows = self._rows
            window._hint = self._hint
            window._field = field
            self._window, self._field = window, field
            return True
        except Exception as e:                      # noqa: BLE001
            self._window = None
            self._field = None
            self._error = f"{type(e).__name__}: {e}"
            return False

    # ── what the box says ────────────────────────────────────────────────────

    @property
    def rows(self) -> list[Row]:
        """The three lines under the divider, in the order they are drawn."""
        return list(self._rows)

    def set_rows(self, rows: list[Row]) -> None:
        """Replace the result rows. Used when a real result list arrives."""
        self._rows = shown_rows(rows)
        window = self._window
        if window is not None:
            try:
                window._rows = self._rows
                window.update()
            except Exception as e:                  # noqa: BLE001
                print(f"[JARVIS] Command bar: rows not repainted — "
                      f"{type(e).__name__}: {e}")

    @property
    def hint(self) -> str:
        return self._hint

    def set_hint(self, text: str) -> None:
        """The "Konteks: …" line. Empty is honest when nothing is selected."""
        self._hint = str(text or "")
        window = self._window
        if window is not None:
            try:
                window.update()
            except Exception as e:                  # noqa: BLE001
                print(f"[JARVIS] Command bar: hint not repainted — "
                      f"{type(e).__name__}: {e}")

    def _on_key(self, event) -> None:
        """Esc closes and hands focus back; Up/Down recall."""
        from PyQt6.QtCore import Qt
        try:
            key = event.key()
            if key == Qt.Key.Key_Escape:
                self.close()
                event.accept()
            elif key == Qt.Key.Key_Up:
                self.recall(-1)
                event.accept()
            elif key == Qt.Key.Key_Down:
                self.recall(+1)
                event.accept()
        except Exception as e:                      # noqa: BLE001
            print(f"[JARVIS] Command bar: key not handled — {type(e).__name__}: {e}")


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


def _assistant_name() -> str:
    """The name the user gave the assistant, for the window title.

    Not a translated string: it is a value the user typed, and `i18n.label()`
    has no key for it. Falling back on any failure, because a widget constructor
    that raises because a config file is unreadable turns a cosmetic surface
    into a crash.
    """
    try:
        from memory.config_manager import get_assistant_name

        return str(get_assistant_name() or "JARVIS")
    except Exception:                               # noqa: BLE001
        return "JARVIS"


def _active_window():
    """Qt's answer to "who had focus", or None.

    Wrapped because `QApplication.activeWindow()` returns None on several
    compositors and raises on none — but the import can fail on a machine that
    has no Qt at all, and the caller must get a bar or a bool, not an
    ImportError from a bookkeeping function.
    """
    try:
        from PyQt6.QtWidgets import QApplication

        return QApplication.activeWindow()
    except Exception:                               # noqa: BLE001
        return None
