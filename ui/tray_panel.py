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
      * board 05a — the same page with Fokus lit, plus the hold strip: toasts are
        held, counted and shown later. The strip is drawn from the snapshot, so
        the number is the number `core.presence_mode` holds.
      * board 08a — the history page: undoable rows with their own button, the
        last three audit lines, and the two buttons at the bottom.
      * board 06a — the privacy page: three indicators, four explicit switches,
        and the erase button.
      * board 17a — the same widget with the light palette. The palette is a
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

from ui import tray_theme as theme_policy
from ui.tray_theme import THEMES, _rgba, resolve_theme  # noqa: F401
from ui.tray_paint import (  # noqa: F401 — re-exported for the smoke tool
    apply_style, mark_segments, paint, paint_history, paint_permissions,
    paint_theme, show_page,
)
from ui.tray_pages import (
    PAGE_HISTORY, PAGE_MAIN, PAGE_PRIVACY, PAGES, PALETTES, PANEL_H, PANEL_W,
    build_history, build_main, build_permissions, panel_position,
)
from ui.tray_panel_model import (
    ALL_QUICK_KEYS, MODE_LABELS, MODE_ORDER, PERMISSIONS, Snapshot, _t,
    snapshot,
)


class TrayPanel:
    """One 460×660 panel, three pages, two palettes.

    `actions` maps a key to a callable, exactly like `TrayIcon`'s dictionary:

        presence_set(mode)   the user pressed a segment
        quick(key)           one of ALL_QUICK_KEYS
        permission(key, on)  one of PERMISSIONS (never a `fixed` one)
        undo()               board 08a's Urungkan
        history_export()     board 08a's Ekspor log
        history_clear()      board 08a's Hapus riwayat
        erase()              board 06a's Hapus semua data lokal
        command(text)        the field at the bottom of board 5

    A missing key is a control that does nothing, reported by `notes`, never
    raised: the panel is a door to the assistant, and a door that throws when
    opened is not a door.
    """

    def __init__(self, actions: Mapping[str, Callable], theme: str = "dark",
                 app=None, on_close: Callable[[], None] | None = None,
                 logger: Callable[[str], None] | None = None):
        self._actions = dict(actions)
        # `theme` is a RESOLVED palette name here, always one of PALETTES. The
        # three-state setting (`auto`/`dark`/`light`) is `set_theme`'s job: a
        # widget that has to consult the OS on every paint is a widget that
        # changes colour halfway through somebody's morning.
        self._requested = "dark"
        self._theme = theme if theme in PALETTES else "dark"
        # `theme` above is a PALETTE; `_requested` is the three-state SETTING.
        self._requested = theme if theme in THEMES else "dark"
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
        # What the last click on a memory or a search chose. See
        # `ui/panel_target.py` — extracted because it is view state, and it was
        # the second thing to push this module over the 600-line ceiling.
        from ui.panel_target import PanelTarget

        self._view = PanelTarget()
        # Board 12's "Tandai aman": a DISPLAY decision that lasts until the
        # clipboard text changes or the panel is reopened. See
        # `pages_actions.tools_mark_safe` for why it cannot be more than that.
        self._marked_safe = False
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

    # ── board 10's target, and board 12's hits ───────────────────────────────

    @property
    def target(self) -> tuple[str, str]:
        """The `(category, key)` the memory detail page is showing."""
        return self._view.target

    def target_memory(self) -> tuple[str, str]:
        """Same as `target`, as a method — `pages_paint` calls it."""
        return self._view.target

    def open_memory(self, index: int) -> bool:
        """Board 9's row button -> board 10, holding the memory that was clicked."""
        opened = self._view.open_memory(index)
        if opened:
            self.set_page("memory_one")
        return opened

    def open_memory_id(self, category: str, key: str) -> bool:
        """Board 9's row -> board 10, by identity rather than by position."""
        opened = self._view.open_memory_id(category, key)
        if opened:
            self.set_page("memory_one")
        return opened

    def run_search(self, query: str) -> int:
        """Board 12's file search, run on the click path. Returns how many hits."""
        return self._view.run_search(query, refresh=self.refresh)

    @property
    def hits(self) -> tuple:
        """The last search's results, for `pages_paint.paint_tools`."""
        return self._view.hits

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
        """Dark ↔ light ↔ auto (board 17a). Unknown themes are refused.

        THREE VALUES, TWO PALETTES. `auto` is not a palette: it is the answer
        to "which one does the OS use", asked once per call and never per
        paint. `self._requested` keeps what the user asked for (so the panel
        can say "auto"), `self._theme` keeps what is on screen.
        """
        if not theme_policy.is_valid(theme):
            return False                                 # "sepia" is not a theme
        requested, shown = theme_policy.resolve(theme)
        self._requested, self._theme = requested, shown
        if self._window is not None:
            self._style()
            self._paint(self._snapshot)
        return True

    def press_theme(self) -> str:
        """The header control: cycle, then tell the caller so it can be saved.

        SAVED BY THE CALLER, not here. `ui/` must not import
        `memory.config_manager` on the click path — the panel is one widget and
        the config file is one file, and a surface that writes config is a
        surface that can be made to write it on a thread nobody expects.

        When no handler is wired (a test, a host that has not asked for it) the
        cycle still happens: the palette change is visible either way, and the
        worst case is a choice that does not survive a restart — reported
        through `_note`, never raised.
        """
        name = self.cycle_theme()
        self._call("theme", name)
        return name

    def cycle_theme(self) -> str:
        """auto -> dark -> light -> auto, and say what it is now.

        Cycles rather than showing three segments: the header has room for one
        28 px control and the segments already belong to the presence mode. A
        third segmented control in the same header would make two rows of
        three-letter words that look identical.
        """
        self.set_theme(theme_policy.cycle(self._requested))
        return self._requested

    @property
    def requested_theme(self) -> str:
        """What the user asked for: 'auto', 'dark' or 'light'."""
        return self._requested

    # ── dispatch ─────────────────────────────────────────────────────────────

    def _call(self, key: str, *args):
        # A PAGE ACTION FIRST, THEN THE SHELL'S HANDLERS.
        #
        # Switching pages, remembering which memory board 10 shows and storing a
        # hit list are the panel's own state; every host that builds a panel
        # would otherwise have to wire them, including the tests.
        local = self._local_action(key)
        if local is not None:
            return local(*args)
        cb = self._actions.get(key)
        if cb is None:
            self._note(f"no handler for {key!r}")
            return None
        try:
            return cb(*args)
        except Exception as e:                       # noqa: BLE001
            self._note(f"{key!r} failed — {type(e).__name__}: {e}")

    def _local_action(self, key: str):
        """The handlers the panel owns. None for anything it does not.

        THE BOUNDARY IS "DOES IT NEED THE SHELL". Switching pages and picking a
        row are panel state; everything that reaches a store goes to the shell,
        because the shell is what owns those modules.
        """
        if key == "page":
            return lambda name: self.set_page(str(name))
        if key == "memory_open":
            return lambda index: self.open_memory(int(index))
        if key == "memory_open_id":
            return self.open_memory_id
        if key == "tools_find":
            return lambda query: self.run_search(str(query))
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
        """Board 08a's Urungkan. Refused when there is nothing to undo, because
        a button that reports success on an empty stack is a lie."""
        if not self._snapshot.can_undo:
            return False
        self._call("undo")
        self.refresh()
        return True

    def press_quick(self, key: str) -> bool:
        """Press one quick row. Accepts BOTH modes' rows.

        Board 5 draws four and board 05a draws three — "Lihat yang tertahan",
        "Akhiri fokus sekarang", "Jeda semua penjadwalan". A panel that refused
        the second list would have three rows that answer False.
        """
        if key not in ALL_QUICK_KEYS:
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
            self._load_saved_theme()
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
        # THE THEME SWITCH. Board 17a draws the same panel in light colours and
        # the mockup has no button for it, because a mockup cannot click. This
        # one is a 30 px control in the header, where it is out of the way of
        # every reading path, and it cycles auto -> dark -> light.
        #
        # Without it the light palette existed and NOBODY COULD REACH IT: the
        # settings drawer that would have held the switch is deleted, and
        # `set_theme` was a method only a test called.
        theme_button = QPushButton(window)
        theme_button.setGeometry(408, 22, 28, 24)
        theme_button.setToolTip(_t("ui.panel.theme"))
        theme_button.clicked.connect(self.press_theme)
        self._buttons["theme"] = theme_button
        self._labels["theme"] = theme_button

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

        # Board 05a's hold strip. Hidden entirely outside Fokus: a strip that
        # says "0 tertahan" in a mode that holds nothing is noise.
        self._labels["held"] = _placed(window, QLabel, 32, 128, 396, 96, "")
        self._labels["held"].hide()

        page = QWidget(window)
        from ui.pages_build import make_page

        page = make_page(window, QWidget, PAGE_MAIN)
        self._pages[PAGE_MAIN] = page
        build_main(self, page)
        self._pages[PAGE_HISTORY] = make_page(window, QWidget, PAGE_HISTORY)
        build_history(self, self._pages[PAGE_HISTORY])
        self._pages[PAGE_PRIVACY] = make_page(window, QWidget, PAGE_PRIVACY)
        build_permissions(self, self._pages[PAGE_PRIVACY])
        # Every board page, from one list in `ui/pages_build.py`. Fourteen
        # `_page(...)` pairs inline put this method at exactly 600 lines.
        from ui.pages_build import build_board_pages

        build_board_pages(self, window)

    def _load_saved_theme(self) -> None:
        """Start from the saved setting, once, when the window is first built.

        ONCE, not on every open: a user who cycled the theme while the panel
        was up is not overruled by the file the next time they click the tray.
        """
        try:
            from memory.config_manager import get_ui_theme

            self.set_theme(get_ui_theme())
        except Exception as e:                       # noqa: BLE001
            self._note(f"saved theme not applied — {type(e).__name__}: {e}")

    # ── painting ─────────────────────────────────────────────────────────────
    #
    # The drawing lives in `ui/tray_paint.py`. It is pure of state — it reads a
    # Snapshot and writes widgets — so keeping it here only meant this module
    # held two jobs and sat 43 lines over the 600-line ceiling. The methods
    # below are the surface the rest of the file (and the tests) use.

    def _paint(self, snap: Snapshot) -> None:
        paint(self, snap)

    def _paint_theme(self) -> None:
        paint_theme(self)

    def _show_page(self) -> None:
        show_page(self)

    def _style(self) -> None:
        apply_style(self)


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


__all__ = [
    "PAGE_HISTORY", "PAGE_MAIN", "PAGE_PRIVACY", "PAGES", "PALETTES",
    "PANEL_H", "PANEL_W", "THEMES", "TrayPanel", "panel_position",
    "resolve_theme",
]
