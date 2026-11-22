"""The tray panel — boards 5, 23, 26, 27 and 28.

WHY A PANEL AT ALL, WHEN THERE IS ALREADY A MENU
    `ui/tray.py` draws a `QMenu`: seven items, one line each. That is the right
    thing for "bring it back" and "quit" and the wrong thing for everything the
    mockups actually ask of this corner of the screen — a mode you switch with
    three visible segments, the quick actions WITH their chords, today's
    suggestion, the permission switches, the task history with an Urungkan
    button. None of that fits a menu item, and a menu that tried would be a
    list of eight submenus.

    So the menu stays — it is what a right click gives on every desktop, and it
    is the fallback when this panel cannot be built — and this is the panel a
    LEFT click opens, which is what board 5 draws.

WHAT EACH BOARD BECOMES, IN ORDER
      * board 5  — the default page: segments, four quick actions, the quota
        line, three permission toggles, the command field.
      * board 23 — the same page with Fokus lit, plus the hold strip: toasts are
        held, counted and shown later. The strip is drawn from the snapshot, so
        the number is the number `core.presence_mode` holds.
      * board 26 — the history page: undoable rows with their own button, the
        last three audit lines, and the two buttons at the bottom.
      * board 27 — the privacy page: three indicators, four explicit switches,
        guest mode, and the erase button.
      * board 28 — the same widget with the light palette. The palette is a
        table in `ui/tray_pages.py`, not a second widget: one panel that can be
        either colour is the only version of this that cannot drift.

WHY THE WIDGETS ARE IN ANOTHER MODULE
    This module is lifecycle, dispatch and truth. `ui/tray_pages.py` is the
    dozen coordinates per page and the two palettes. The split exists because
    `ui/` has a 600-line ceiling and this crossed it — but it is the right line
    anyway: nothing below `_paint` decides anything, and nothing in the pages
    module reads the world.

WHAT IT DOES NOT DO
    It draws and it reports. Every switch and every row calls back into the
    `actions` mapping the caller supplied, which is the same contract
    `ui/tray.py` uses, for the same reason: the panel must not know what
    "Senyap" means, because the object that decides it is `core.presence_mode`
    and there must be exactly one of those.

    It also does not decide WHEN to refresh. `refresh()` re-reads the world and
    the caller may call it whenever the world has changed — on every presence
    change, on every undo, on every toast held.
"""
from __future__ import annotations

from typing import Callable, Mapping

from ui.tray_pages import (
    PAGE_HISTORY, PAGE_MAIN, PAGE_PRIVACY, PAGES, PALETTES, PANEL_H, PANEL_W,
    build_history, build_main, build_privacy, panel_position,
)
from ui.tray_panel_model import (
    MODE_LABELS, MODE_ORDER, PERMISSIONS, QUICK_ACTIONS, Snapshot, _t, snapshot,
)


def _rgba(hex_colour: str, alpha: float) -> str:
    """`#RRGGBB` + alpha → the `rgba(...)` a stylesheet understands."""
    value = hex_colour.lstrip("#")
    r, g, b = (int(value[i:i + 2], 16) for i in (0, 2, 4))
    return f"rgba({r}, {g}, {b}, {alpha:.2f})"


class TrayPanel:
    """One 460×660 panel, three pages, two palettes.

    `actions` maps a key to a callable, exactly like `TrayIcon`'s dictionary:

        presence_set(mode)   the user pressed a segment
        quick(key)           one of QUICK_ACTIONS
        permission(key, on)  one of PERMISSIONS (never a `fixed` one)
        undo()               board 26's Urungkan
        history_export()     board 26's Ekspor log
        history_clear()      board 26's Hapus riwayat
        guest(on)             board 27's mode tamu
        erase()              board 27's Hapus semua data lokal
        command(text)        the field at the bottom of board 5

    A missing key is a control that does nothing, reported by `notes`, never
    raised: the panel is a door to the assistant, and a door that throws when
    opened is not a door.
    """

    def __init__(self, actions: Mapping[str, Callable], theme: str = "dark",
                 app=None, on_close: Callable[[], None] | None = None,
                 logger: Callable[[str], None] | None = None):
        self._actions = dict(actions)
        self._theme = theme if theme in PALETTES else "dark"
        self._app = app
        self._on_close = on_close
        self._logger = logger
        self._window = None
        self._field = None
        self._pages: dict = {}
        self._page = PAGE_MAIN
        self._snapshot: Snapshot = Snapshot()
        self._notes: list[str] = []
        # Every widget whose text is a VALUE rather than a constant, so
        # `_paint` has one list to walk instead of a dozen attributes that
        # someone will forget to update.
        self._labels: dict = {}
        self._buttons: dict = {}
        self._error = ""

    # ── what happened ────────────────────────────────────────────────────────

    @property
    def available(self) -> bool:
        return self._window is not None

    @property
    def error(self) -> str:
        return self._error

    @property
    def notes(self) -> tuple[str, ...]:
        return tuple(self._notes)

    @property
    def page(self) -> str:
        return self._page

    @property
    def theme(self) -> str:
        return self._theme

    @property
    def snapshot(self) -> Snapshot:
        return self._snapshot

    def _note(self, text: str) -> None:
        line = f"Tray panel: {text}"
        self._notes.append(line)
        if self._logger is not None:
            try:
                self._logger(line)
                return
            except Exception as e:                   # noqa: BLE001
                self._notes.append(f"Tray panel: logger failed — {type(e).__name__}: {e}")
                return
        print(f"[JARVIS] {line}")

    # ── lifecycle ────────────────────────────────────────────────────────────

    def refresh(self) -> Snapshot:
        """Re-read the world and put it on the widgets.

        Safe before `build()`: the snapshot is taken and stored, and the paint
        happens on the next build. That matters because `main.py` calls this on
        every presence change, including the ones before anyone opened the
        panel.
        """
        try:
            self._snapshot = snapshot()
        except Exception as e:                       # noqa: BLE001
            self._note(f"could not read the world — {type(e).__name__}: {e}")
        if self._window is not None:
            try:
                self._paint(self._snapshot)
            except Exception as e:                   # noqa: BLE001
                self._note(f"could not paint the snapshot — {type(e).__name__}: {e}")
        return self._snapshot

    def toggle(self, point=None) -> bool:
        """Open if closed, close if open. Returns whether it is now open."""
        if self._window is not None and self._visible():
            self.close()
            return False
        return self.open(point)

    def open(self, point=None) -> bool:
        """Build (once), refresh, place and show. False if Qt refused."""
        if self._window is None and not self._build():
            return False
        self.refresh()
        try:
            self._window.move(*self._position(point))
            self._window.show()
            self._window.raise_()
            self._window.activateWindow()
            return True
        except Exception as e:                       # noqa: BLE001
            self._error = f"{type(e).__name__}: {e}"
            self._note(f"could not open — {self._error}")
            return False

    def close(self) -> None:
        """Hide, and tell the caller, so the tray can put its own state back."""
        window = self._window
        if window is not None:
            try:
                window.hide()
            except Exception as e:                   # noqa: BLE001
                self._note(f"could not hide — {type(e).__name__}: {e}")
        cb = self._on_close
        if cb is not None:
            try:
                cb()
            except Exception as e:                   # noqa: BLE001
                self._note(f"close handler failed — {type(e).__name__}: {e}")

    def stop(self) -> None:
        window, self._window = self._window, None
        self._field = None
        self._labels.clear()
        self._buttons.clear()
        self._pages = {}
        if window is None:
            return
        try:
            window.hide()
            window.deleteLater()
        except Exception as e:                       # noqa: BLE001
            self._note(f"could not remove the window — {type(e).__name__}: {e}")

    def _visible(self) -> bool:
        try:
            return bool(self._window.isVisible())
        except Exception:                            # noqa: BLE001
            return False

    def _position(self, point=None) -> tuple[int, int]:
        try:
            from PyQt6.QtWidgets import QApplication

            screen = QApplication.primaryScreen()
            if screen is None:
                return 0, 0
            return panel_position(screen.availableGeometry(), (PANEL_W, PANEL_H), point)
        except Exception as e:                       # noqa: BLE001
            self._note(f"no screen geometry — {type(e).__name__}: {e}")
            return 0, 0

    # ── pages ────────────────────────────────────────────────────────────────

    def set_page(self, page: str) -> bool:
        """Switch pages. Unknown pages are refused, not stored."""
        name = str(page or "").strip().lower()
        if name not in PAGES:
            return False
        self._page = name
        self._show_page()
        return True

    def set_theme(self, theme: str) -> bool:
        """Dark ↔ light (board 28). Unknown themes are refused."""
        name = str(theme or "").strip().lower()
        if name not in PALETTES:
            return False
        self._theme = name
        if self._window is not None:
            self._style()
            self._paint(self._snapshot)
        return True

    # ── dispatch ─────────────────────────────────────────────────────────────

    def _call(self, key: str, *args):
        cb = self._actions.get(key)
        if cb is None:
            self._note(f"no handler for {key!r}")
            return None
        try:
            return cb(*args)
        except Exception as e:                       # noqa: BLE001
            self._note(f"{key!r} failed — {type(e).__name__}: {e}")
            return None

    def press_mode(self, mode: str) -> bool:
        """One segment. The mode is applied by the caller, then re-read."""
        name = str(mode or "").strip().lower()
        if name not in MODE_ORDER:
            return False
        self._call("presence_set", name)
        self.refresh()
        return True

    def press_permission(self, key: str, on: bool) -> bool:
        """One switch. A `fixed` switch is refused — there is nothing behind it."""
        if key not in {k for k, _n, _s in PERMISSIONS}:
            return False
        if self._snapshot.permissions.get(key, {}).get("fixed"):
            self._note(f"{key!r} is a fact about this machine, not a setting")
            return False
        self._call("permission", key, bool(on))
        self.refresh()
        return True

    def press_undo(self) -> bool:
        """Board 26's Urungkan. Refused when there is nothing to undo, because
        a button that reports success on an empty stack is a lie."""
        if not self._snapshot.can_undo:
            return False
        self._call("undo")
        self.refresh()
        return True

    def press_quick(self, key: str) -> bool:
        if key not in {k for k, _n, _c in QUICK_ACTIONS}:
            return False
        self._call("quick", key)
        return True

    def submit_command(self, text: str | None = None) -> bool:
        raw = self._field_text() if text is None else text
        line = " ".join(str(raw or "").split())
        if not line:
            return False
        self._call("command", line)
        if self._field is not None:
            try:
                self._field.clear()
            except Exception as e:                   # noqa: BLE001
                self._note(f"could not clear the field — {type(e).__name__}: {e}")
        return True

    def _field_text(self) -> str:
        try:
            return self._field.text() if self._field is not None else ""
        except Exception:                            # noqa: BLE001
            return ""

    # ── the Qt half ──────────────────────────────────────────────────────────

    def _build(self) -> bool:
        """Create the window once. False (with `error`) if Qt cannot."""
        if self._window is not None:
            return True
        try:
            from PyQt6.QtCore import Qt
            from PyQt6.QtWidgets import QLabel, QPushButton, QWidget

            window = QWidget()
            window.setWindowFlags(Qt.WindowType.FramelessWindowHint
                                  | Qt.WindowType.Tool
                                  | Qt.WindowType.WindowStaysOnTopHint)
            window.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
            # A window title is UI text like any other; the assistant's own
            # name is a value the user typed, and `i18n` has no key for it.
            window.setWindowTitle(_t("ui.panel.title"))
            window.setFixedSize(PANEL_W, PANEL_H)
            window.keyPressEvent = self._on_key
            self._window = window
            self._build_body(window, QWidget, QLabel, QPushButton)
            self._style()
            self._show_page()
            self._paint(self._snapshot)
            return True
        except Exception as e:                       # noqa: BLE001
            self._window = None
            self._error = f"{type(e).__name__}: {e}"
            self._note(f"could not build — {self._error}")
            return False

    def _build_body(self, window, QWidget, QLabel, QPushButton) -> None:
        """Every widget the three pages need, built once.

        Built once and hidden/shown per page rather than rebuilt: rebuilding
        would drop the field's contents every time the user glanced at history,
        and a search box that forgets what you typed is a search box you stop
        using.
        """
        # The header is on every page: the assistant's name is the one thing
        # that must never be ambiguous about WHICH window this is.
        self._labels["title"] = _placed(window, QLabel, 24, 22, 200, 24,
                                        _t("ui.panel.title"))
        self._labels["subtitle"] = _placed(window, QLabel, 24, 46, 412, 20, "")

        # Segments, board 5. One button per mode with the active one filled —
        # a segmented control, not three checkboxes and not a dropdown.
        for index, mode in enumerate(MODE_ORDER):
            # The artboard's own three words. A mode label is not translated
            # because "Aktif / Fokus / Senyap" is what board 5 draws in every
            # locale; the catalogue carries them anyway for the day it is.
            button = QPushButton(_t(f"ui.panel.mode.{mode}") or MODE_LABELS[mode],
                                 window)
            button.setGeometry(24 + index * 138, 74, 136, 38)
            button.clicked.connect(lambda _checked=False, m=mode: self.press_mode(m))
            self._buttons[f"mode:{mode}"] = button

        # Board 23's hold strip. Hidden entirely outside Fokus: a strip that
        # says "0 tertahan" in a mode that holds nothing is noise.
        self._labels["held"] = _placed(window, QLabel, 32, 128, 396, 96, "")
        self._labels["held"].hide()

        page = QWidget(window)
        page.setGeometry(0, 0, PANEL_W, PANEL_H)
        self._pages[PAGE_MAIN] = page
        build_main(self, page)
        self._pages[PAGE_HISTORY] = _page(window, QWidget, PAGE_HISTORY)
        build_history(self, self._pages[PAGE_HISTORY])
        self._pages[PAGE_PRIVACY] = _page(window, QWidget, PAGE_PRIVACY)
        build_privacy(self, self._pages[PAGE_PRIVACY])

    # ── painting ─────────────────────────────────────────────────────────────

    def _paint(self, snap: Snapshot) -> None:
        """Put one snapshot on the widgets. Never raises."""
        labels = self._labels

        labels["title"].setText(snap.title)
        labels["subtitle"].setText(snap.subtitle)
        labels["quota"].setText(snap.quota_line)
        labels["suggestion"].setText(
            snap.suggestion or _t("ui.panel.suggestion.empty"))

        for mode in MODE_ORDER:
            self._buttons[f"mode:{mode}"].setChecked(mode == snap.mode)
        self._mark_segments(snap)

        # Board 23's strip: only in Fokus, because only Fokus holds anything.
        held = labels["held"]
        if snap.mode == "focus":
            held.setText("\n".join((_t("ui.panel.focus.active_until", time="17.00"),
                                     _t("ui.panel.focus.held"),
                                     snap.held_line)))
            held.show()
        else:
            held.hide()

        for key, _name, _sub in PERMISSIONS[:3]:
            button = self._buttons[f"perm:{key}"]
            state = snap.permissions.get(key, {})
            button.setChecked(bool(state.get("on")))
            button.setEnabled(not bool(state.get("fixed")))

        self._paint_history(snap)
        self._paint_privacy(snap)

    def _mark_segments(self, snap: Snapshot) -> None:
        """The lit segment is filled; the others are outlines.

        Colour alone is not enough — the active segment also carries the
        heavier weight, so the difference survives a grey-scale screenshot and
        the checked state survives a reader who cannot see the fill.
        """
        pal = PALETTES[self._theme]
        for mode in MODE_ORDER:
            button = self._buttons[f"mode:{mode}"]
            if mode == snap.mode:
                button.setStyleSheet(
                    f"background:{pal['accent']};color:{pal['on_accent']};"
                    f"border:none;border-radius:9px;font-weight:600;")
            else:
                button.setStyleSheet(
                    f"background:transparent;color:{pal['muted']};"
                    f"border:1px solid {pal['line']};border-radius:9px;")

    def _paint_history(self, snap: Snapshot) -> None:
        labels = self._labels
        labels["history_count"].setText(snap.history_subtitle)
        rows = list(snap.history)[:4]
        for index in range(4):
            row = rows[index] if index < len(rows) else None
            labels[f"history:{index}"].setText(str(row["label"]) if row else "")
            labels[f"history_meta:{index}"].setText(
                _t("ui.panel.history.state.undoable") if row else "")
            button = self._buttons[f"undo:{index}"]
            # Only the OLDEST row may carry the button, because undo is a
            # stack and `undo_last()` reverses the oldest entry. Two buttons
            # for one operation would be two buttons that always do the same
            # thing, in the two places a user would least expect it.
            show = bool(row) and index == len(rows) - 1 and snap.can_undo
            button.setVisible(show)
        labels["audit"].setText(
            "\n".join(snap.audit) or _t("ui.panel.audit.empty"))

    def _paint_privacy(self, snap: Snapshot) -> None:
        labels = self._labels
        for key, _name, _sub in PERMISSIONS[:3]:
            state = snap.permissions.get(key, {})
            on = bool(state.get("on"))
            note = str(state.get("note") or "")
            labels[f"indicator_state:{key}"].setText(
                note or _t("ui.panel.indicator.on" if on else "ui.panel.indicator.off"))
        for key, _name, _sub in PERMISSIONS:
            button = self._buttons[f"permx:{key}"]
            state = snap.permissions.get(key, {})
            button.setChecked(bool(state.get("on")))
            # A fixed switch is DISABLED, not merely refused on click: drawing
            # a live switch over something no click can change is a control
            # that teaches the user not to trust the panel.
            button.setEnabled(not bool(state.get("fixed")))

    def _show_page(self) -> None:
        for name, page in self._pages.items():
            try:
                page.show() if name == self._page else page.hide()
            except Exception as e:                   # noqa: BLE001
                self._note(f"page {name!r} would not switch — {type(e).__name__}: {e}")

    def _style(self) -> None:
        """One stylesheet for the whole panel, rebuilt when the palette changes.

        Set on the window rather than per widget, so board 28 is a palette swap
        and not a second set of colours in twelve places.
        """
        window = self._window
        if window is None:
            return
        pal = PALETTES[self._theme]
        try:
            window.setStyleSheet(f"""
                QWidget {{ background:{pal['panel']};color:{pal['text']}; }}
                QLabel {{ background:transparent;color:{pal['text']}; }}
                QPushButton {{ background:{pal['card']};color:{pal['text']};
                              border:1px solid {pal['line']};border-radius:10px;
                              text-align:left;padding-left:14px; }}
                QPushButton:checked {{ border:1px solid {pal['accent']};
                                      background:{_rgba(pal['accent'], 0.12)}; }}
                QPushButton:disabled {{ color:{pal['muted']}; }}
                QLineEdit {{ background:{pal['card']};color:{pal['text']};
                            border:1px solid {pal['line']};border-radius:20px;
                            padding-left:18px; }}
            """)
        except Exception as e:                       # noqa: BLE001
            self._note(f"stylesheet refused — {type(e).__name__}: {e}")

    # ── keys ─────────────────────────────────────────────────────────────────

    def _on_key(self, event) -> None:
        """Esc closes. The pages are buttons, not keys."""
        from PyQt6.QtCore import Qt

        try:
            if event.key() == Qt.Key.Key_Escape:
                self.close()
                event.accept()
        except Exception as e:                       # noqa: BLE001
            self._note(f"key not handled — {type(e).__name__}: {e}")


def _placed(parent, cls, x: int, y: int, w: int, h: int, text: str):
    """One positioned label with text. `setGeometry` + `setText`, twice."""
    label = cls(parent)
    label.setGeometry(x, y, w, h)
    label.setText(text)
    return label


def _page(window, cls, name: str):
    """A hidden child page, ready to be filled. Hidden: board 5 is what opens."""
    page = cls(window)
    page.setGeometry(0, 0, PANEL_W, PANEL_H)
    page.setObjectName(name)
    page.hide()
    return page


__all__ = [
    "PAGE_HISTORY", "PAGE_MAIN", "PAGE_PRIVACY", "PAGES", "PALETTES",
    "PANEL_H", "PANEL_W", "TrayPanel", "panel_position",
]
