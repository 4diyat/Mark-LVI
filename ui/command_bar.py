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

WHAT IT DRAWS
    The command field and a read-only view of recent audit outcomes. Those
    outcomes are refreshed on open; risk classification is not an execution
    result and must not be displayed as one. Enter sends the typed field, not
    any of the audit rows.

"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

# The drawing half: tokens, geometry, the risk rows and `paint_bar`. Imported
# rather than defined here because the 600-line ceiling in `ui/` is what put the
# tray panel into three files, and it applies to this one too. Nothing in
# `ui/command_paint.py` imports this module back.
from ui.command_paint import (  # noqa: F401 — re-exported for the tests
    AMBER, BAR_HEIGHT, BAR_WIDTH, BASE, CYAN, FIELD_HEIGHT, FIELD_MARGIN,
    FILL_BOTTOM, FILL_TOP, FONT, FOOTER, GEOMETRY, GREEN, LINE, LINE_ACC, MONO,
    MUTED, PANEL, RED, ROW_ACTIVE, ROW_LEVELS, SECONDARY, TEXT, YELLOW, Row,
    _BarWindow, _style_field, default_rows, paint_bar, shown_rows, to_row,
)

# The number of remembered entries. Ten is the point past which a recall list
# stops being a memory aid and becomes something to read through.
HISTORY_MAX = 10

# A single line. The bar is one sentence to the assistant, not a document; a
# paste that arrives with newlines is flattened rather than truncated, because
# truncating silently loses the second half of an instruction.
MAX_CHARS = 2000

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
        # Audit results are read-only and refreshed whenever the bar opens.
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
        self.set_rows(default_rows())
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
                              g["esc"][0] - g["title"][0] - 16, 28)
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
