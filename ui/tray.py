"""The notification-area icon — JARVIS when no window is open.

WHY THIS EXISTS
    The window used to be the whole application: `JarvisUI.__init__` called
    `showFullScreen()` unconditionally, so launching JARVIS covered the desktop
    and nothing behind it could be reached. That is a kiosk, not an assistant.
    Ambient mode starts with no window at all and this icon is the only thing
    on screen, so it carries three jobs that the window used to carry by simply
    being there:

      * a way BACK to the interface (left click, or the menu's first item),
      * a way to see whether JARVIS is listening (the tooltip),
      * a way to QUIT. This is not optional: closing the window is what used to
        end the program, and with no window there is nothing to close. An
        assistant with no quit item is a process the user has to hunt in Task
        Manager, which is not a thing to do to somebody.

WHY IT IS ITS OWN MODULE
    `ui/window.py` is ~4,000 lines and importing it needs PyQt6, a display and
    a constructed `MainWindow`. The tray needs none of that: it is a handful of
    Qt calls and a dictionary of callbacks. Keeping it separate means the
    behaviour can be tested against a small stub instead of a whole window, and
    it keeps `window.py` from growing.

WHAT IT DELIBERATELY DOES NOT DO
    It never decides anything. Every menu item and every click calls back into
    the caller's dictionary; the tray does not know what "summon" means, and it
    must not, because the same object will later serve the floating-face mode
    where summon means something else.
"""
from __future__ import annotations

from pathlib import Path

from typing import Callable, Mapping

# The menu, in order. Kept as data so the test can assert the items and their
# order without constructing Qt objects, and so a new item is one line.
#
# "Show" is first because it is what a user clicking the icon most often wants.
# "Quit" is last because it is the one item that must never be hit by accident.
# `presence` sits between sleeping and settings: it answers the same kind of
# question as "Go to sleep" (how much of the assistant is listening) but it is
# a mode rather than a moment, so it belongs after the momentary items.
#
# ONE ITEM, THREE MODES. Three menu entries for Aktif / Fokus / Senyap would be
# three chances to pick the wrong one and three labels to keep in step; a single
# item that cycles them carries the current mode in its own label instead.
MENU_ITEMS = (
    ("show", "Show JARVIS"),
    ("wake", "Wake up"),
    ("sleep", "Go to sleep"),
    ("presence", "Aktif — boleh menyela"),
    ("settings", "Settings"),
    ("autostart", "Start with this computer"),
    ("quit", "Quit"),
)

# The items that are a CHECKBOX rather than a plain action. Only one today, and
# it is the item whose label lies if it is not: "Start with this computer" next
# to a tick that is not there is the difference between reading a switch and
# guessing at one. The tray still decides nothing — the caller supplies
# `checked` for these keys and gets the toggle back.
CHECKABLE_ITEMS = frozenset({"autostart"})

# Items whose label is rewritten after the menu is built, because it states a
# value rather than naming an action. The tray itself still decides nothing:
# the caller supplies the text, exactly as it supplies `checked`.
DYNAMIC_ITEMS = frozenset({"presence"})


def icon_path() -> Path:
    """Where the tray icon is drawn to, generated on first use.

    `ui/icons.py` draws the arc reactor rather than shipping a binary, and it
    already writes to `config/jarvis.ico` for the desktop shortcut. Reusing that
    file means the tray icon and the shortcut icon cannot drift apart — and
    because `build_jarvis_icon` returns False rather than raising when Pillow is
    missing, a machine without Pillow still gets a tray with Qt's default icon
    instead of no tray at all.
    """
    return Path(__file__).resolve().parent.parent / "config" / "jarvis.ico"


class TrayIcon:
    """A `QSystemTrayIcon` plus the menu it needs, wired to plain callbacks.

    `actions` maps a key from `MENU_ITEMS` to a callable. A missing key is
    simply a menu item that does nothing — reported by `available`, not
    raised — because the tray is the last thing standing between a working app
    and an invisible process, and it must never be the reason the app dies.
    """

    def __init__(self, actions: Mapping[str, Callable[[], None]], app=None,
                 logger: Callable[[str], None] | None = None,
                 checked: Callable[[str], bool] | None = None,
                 label: Callable[[str], str] | None = None):
        self._actions = dict(actions)
        # Asked once, while the menu is built, for every key in DYNAMIC_ITEMS.
        # Same reason as `checked`: the answer is a value, not a constant, and
        # a cached one is a menu that lies after the mode changes.
        self._label = label
        # Asked once, while the menu is built, for every key in CHECKABLE_ITEMS.
        # A callable rather than a dict because the answer can change between
        # two builds of the menu, and the tray must not cache a stale tick.
        self._checked = checked
        self._app = app
        self._logger = logger
        self._tray = None
        self._menu = None
        self._state = "idle"
        self._error = ""
        # Everything that went wrong and was survived. Kept rather than printed
        # and forgotten: the tray is the surface for a headless app, so a fault
        # here is invisible by construction and needs somewhere to be read.
        self._notes: list[str] = []

    @property
    def notes(self) -> tuple[str, ...]:
        """Non-fatal failures seen so far, oldest first."""
        return tuple(self._notes)

    def _note(self, text: str) -> None:
        """Record a survived failure. Never raises.

        This codebase forbids `except Exception: pass` (see
        tests/test_silent_except.py) for a reason that applies double here: the
        tray is the only surface a windowless JARVIS has, so a silently dead
        menu item would look exactly like a working one.
        """
        line = f"Tray: {text}"
        self._notes.append(line)
        if self._logger is not None:
            try:
                self._logger(line)
            except Exception as e:                  # noqa: BLE001
                self._note(f"logger failed too — {type(e).__name__}: {e}")
                return
        else:
            print(f"[JARVIS] {line}")

    # ── what happened ────────────────────────────────────────────────────────

    @property
    def available(self) -> bool:
        """True once an icon is actually on screen.

        Callers check this rather than assuming: a Linux desktop without a
        notification area, or a session where the tray protocol is missing, has
        to fall back to showing the window. Otherwise the user has an assistant
        they cannot see, reach or quit, which is worse than a window.
        """
        return self._tray is not None

    @property
    def error(self) -> str:
        """Why the tray could not be created, for the log. Empty when fine."""
        return self._error

    # ── lifecycle ────────────────────────────────────────────────────────────

    def start(self) -> bool:
        """Build the icon and show it. Returns `available`.

        Never raises. Every failure path leaves `error` set and returns False,
        so the caller can show the window instead of starting a headless ghost.
        """
        if self._tray is not None:
            return True
        try:
            from PyQt6.QtGui import QIcon
            from PyQt6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

            app = self._app or QApplication.instance()
            if app is None:
                self._error = "no QApplication to attach a tray icon to"
                return False
            if not QSystemTrayIcon.isSystemTrayAvailable():
                self._error = "this desktop has no notification area"
                return False

            icon = QIcon(str(icon_path()))
            if icon.isNull():
                # Pillow missing, or the file could not be drawn. The tray still
                # works — Qt substitutes its own icon — so this is a fallback,
                # not a failure.
                icon = app.windowIcon()

            menu = QMenu()
            for key, label in MENU_ITEMS:
                # A dynamic item states a VALUE ("Aktif — boleh menyela"), so
                # the constant in MENU_ITEMS is only the fallback for a caller
                # that supplies no provider.
                if key in DYNAMIC_ITEMS and self._label is not None:
                    try:
                        label = self._label(key) or label
                    except Exception as e:          # noqa: BLE001
                        # The menu is still usable with the fallback text; a
                        # probe that throws must not cost the user the menu.
                        self._note(f"label for {key!r} failed — "
                                   f"{type(e).__name__}: {e}")
                action = menu.addAction(label)
                if key in CHECKABLE_ITEMS:
                    action.setCheckable(True)
                    try:
                        action.setChecked(bool(self._checked(key)) if self._checked else False)
                    except Exception:              # noqa: BLE001
                        # A probe that throws must not cost the user the whole
                        # menu; the tick is simply not set.
                        action.setChecked(False)
                action.triggered.connect(self._make_handler(key, action))

            tray = QSystemTrayIcon(icon, app)
            tray.setToolTip(self._tooltip())
            tray.setContextMenu(menu)
            tray.activated.connect(self._on_activated)
            tray.show()

            self._tray, self._menu, self._app = tray, menu, app
            return True
        except Exception as e:                      # noqa: BLE001
            self._tray = None
            self._error = f"{type(e).__name__}: {e}"
            return False

    def stop(self) -> None:
        """Take the icon down. Safe to call twice, or after a failed start."""
        tray, self._tray = self._tray, None
        self._menu = None
        if tray is not None:
            try:
                tray.hide()
            except Exception as e:                  # noqa: BLE001
                self._note(f"could not hide the icon — {type(e).__name__}: {e}")

    # ── state the user can see ───────────────────────────────────────────────

    def set_state(self, state: str) -> None:
        """Reflect the assistant's state in the tooltip.

        Deliberately cheap and idempotent: `main.py` calls `set_state` on every
        transition, from several threads, and this may be reached often. A tray
        icon that redraws on every keystroke would be a hidden cost in the one
        place nobody looks.
        """
        self._state = str(state or "idle").strip().lower() or "idle"
        if self._tray is None:
            return
        try:
            self._tray.setToolTip(self._tooltip())
        except Exception as e:                      # noqa: BLE001
            self._note(f"could not set the tooltip — {type(e).__name__}: {e}")

    @property
    def state(self) -> str:
        return self._state

    def _tooltip(self) -> str:
        # Short. Windows truncates tray tooltips at 127 characters and a tooltip
        # is a glance, not a status bar.
        return f"JARVIS — {self._state}"

    # ── internals ────────────────────────────────────────────────────────────

    def _make_handler(self, key: str, action=None):
        def _fire(*_args) -> None:
            # A CHECKABLE action has already flipped its own tick by the time
            # this runs, and Qt's default position is "it worked". It may not
            # have: a registry write can be refused, a LaunchAgent folder can
            # be unwritable. So for those items the callback's return value is
            # what the tick is set to — `core.autostart.enable/disable` report
            # the truth by reading the entry back.
            cb = self._actions.get(key)
            if cb is None:
                return
            try:
                result = cb()
                if action is not None and key in CHECKABLE_ITEMS and isinstance(result, bool):
                    action.setChecked(result)
                if action is not None and key in DYNAMIC_ITEMS and self._label:
                    # The callback just changed the value; the label has to say
                    # so, or the menu shows the mode it had before the click.
                    try:
                        action.setText(self._label(key) or action.text())
                    except Exception as e:          # noqa: BLE001
                        self._note(f"relabelling {key!r} failed — "
                                   f"{type(e).__name__}: {e}")
            except Exception as e:                  # noqa: BLE001
                # A failing menu item must not take the icon down with it — the
                # icon is how the user gets back to a working interface. Said
                # out loud, because the item would otherwise look broken and
                # silent, which is indistinguishable from the app being dead.
                # The TYPE as well as the message: an exception with a bare
                # message ("no", "None") is what makes a log line useless.
                self._note(f"the {key!r} menu item failed — {type(e).__name__}: {e}")
                if action is not None and key in CHECKABLE_ITEMS:
                    action.setChecked(False)      # never show a tick for a failure
        return _fire

    def _on_activated(self, reason) -> None:
        """Left click summons the interface; right click is Qt's own menu."""
        try:
            from PyQt6.QtWidgets import QSystemTrayIcon
        except ImportError:
            return                 # no Qt to ask; nothing was clicked after all
        if reason != QSystemTrayIcon.ActivationReason.Trigger:
            return
        self._make_handler("show")()
