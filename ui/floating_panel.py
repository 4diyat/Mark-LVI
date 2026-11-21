"""Taking a widget out of the window, and putting it back.

WHY THIS FILE EXISTS
    `ui/window.py` has a hard ceiling (`tests/test_ui_split.py`) and is at it.
    The window needs to answer three questions about a floating widget — may it
    leave, where does it go, how does it come back — and all three are a
    sentence here instead of twenty lines there.

WHAT IT OWNS
    One `core.floating.State` for the process, the `Dock` each floating widget
    came from, and the saved position each one gets back. Nothing about the
    widgets themselves: this file never reads what a caption says.

THE TWO THINGS IT MUST NOT DO
    * It must not open the settings file on a hot path. Positions are read once
      per float and written once per move, not per frame.
    * It must not raise into the Qt thread. Every failure — no config, no
      screen, a widget already deleted — leaves the widget where it was and
      logs the reason. A widget that fails to float is a smaller problem than a
      window that stops drawing.
"""
from __future__ import annotations

from core import floating, logbook

# Default geometry per widget, used the first time it floats and whenever the
# saved record is unusable. Chosen to be out of the way of the middle of the
# screen without being flush against an edge.
_DEFAULTS = {
    "speech_caption": (24, 24, 420, 96),
    "metric_bar": (24, 140, 240, 120),
    "camera_preview": (24, 280, 320, 240),
    "hud": (24, 24, 260, 260),
}


class FloatingPanel:
    """The window's side of floating widgets."""

    def __init__(self, window, os_name: str = "", session: str = ""):
        self._window = window
        # Detected here rather than passed in: the window would have to know
        # which session type it is running under, and it has no other reason to.
        import platform

        from core import platform_support

        self._os_name = os_name or platform.system()
        self._session = (session if session is not None and os_name
                         else platform_support._linux_session())
        self.state = floating.State()
        self._docks: dict = {}
        self._widgets: dict = {}

    # ── the question ──────────────────────────────────────────────────────

    def may_float(self, name: str) -> floating.Fit:
        return floating.fit(name, self._os_name, self._session)

    def is_floating(self, name: str) -> bool:
        return self.state.is_floating(name)

    # ── the act ───────────────────────────────────────────────────────────

    def toggle(self, name: str, widget) -> bool:
        """Float it if it is docked, dock it if it is floating. True = floating."""
        name = (name or "").lower()
        if self.state.is_floating(name):
            self.dock(name)
            return False
        return self.float(name, widget)

    def float(self, name: str, widget) -> bool:
        """Take one widget out onto the desktop. False when it may not leave."""
        name = (name or "").lower()
        if widget is None:
            return False
        fit = self.may_float(name)
        if not fit.allowed:
            self._log(fit.reason)
            return False

        try:
            from ui import floating_window
            import sys as _sys

            # A SUBMODULE import, not `from PyQt6.QtCore import Qt`. The latter
            # resolves `PyQt6` as a package and executes `PyQt6/__init__.py`,
            # which is 60 lines of Qt theme plumbing this file has no use for —
            # and which fails outright on a machine where Qt is stubbed.
            Qt = _sys.modules["PyQt6.QtCore"].Qt
            placement = self._placement_for(name, widget)
            dock = floating_window.attach(widget, Qt, fit, placement)
        except Exception as e:              # noqa: BLE001 — a Qt edge
            logbook.get(__name__).warning("could not float %s: %s", name, e)
            self._log(f"could not float {name}")
            return False

        self._docks[name] = dock
        self._widgets[name] = widget
        self.state.add(name, placement)
        # Saved on the way OUT as well as on the way back: a widget that is
        # still floating when the program closes has no "way back" to save it
        # from, and would reappear in the default corner next time.
        self._remember(name)
        if fit.note:
            self._log(fit.note)
        return True

    def dock(self, name: str) -> bool:
        """Put it back where it came from, at the index it came from."""
        name = (name or "").lower()
        widget = self._widgets.get(name)
        if widget is None:
            self.state.remove(name)
            return False
        self._remember(name)
        try:
            from ui import floating_window
            import sys as _sys

            Qt = _sys.modules["PyQt6.QtCore"].Qt
            floating_window.detach(widget, Qt, self._docks.get(name))
        except Exception as e:              # noqa: BLE001
            logbook.get(__name__).warning("could not dock %s: %s", name, e)
            return False
        self._docks.pop(name, None)
        self._widgets.pop(name, None)
        self.state.remove(name)
        return True

    def dock_all(self) -> None:
        """Used on close, so a floating widget does not outlive its window."""
        for name in list(self.state.names()):
            self.dock(name)

    # ── where it goes, and remembering that ───────────────────────────────

    def _placement_for(self, name: str, widget) -> floating.Placement:
        default = _DEFAULTS.get(name, (24, 24, 320, 120))
        screen = self._screen_size()
        saved = self._read_saved(name)
        placement = floating.place(saved, default, screen)
        try:
            if not placement.stored:
                # Nothing saved yet: use the widget's own size, which is the
                # only informed guess about how big it wants to be.
                size = widget.size()
                width = max(120, min(size.width() or default[2], screen[0]))
                height = max(80, min(size.height() or default[3], screen[1]))
                placement = floating.place(
                    {**placement.as_dict(), "width": width, "height": height},
                    default, screen)
        except Exception as e:              # noqa: BLE001 — a stub widget
            logbook.get(__name__).debug("could not read the widget size: %s", e)
        return placement

    def _screen_size(self) -> tuple[int, int]:
        try:
            screen = self._window.screen() or self._window.windowHandle().screen()
            area = screen.availableGeometry()
            return (area.width(), area.height())
        except Exception as e:              # noqa: BLE001 — no display in a test
            logbook.get(__name__).debug("no screen geometry: %s", e)
            return (1920, 1080)

    def _remember(self, name: str) -> None:
        placement = self.state.floating.get(name)
        if placement is None:
            return
        try:
            # Through the module, not `from ... import update_config`: the
            # function reads `CONFIG_FILE` from its own module at call time, and
            # binding it by name is how a write ends up somewhere the reader is
            # not looking. (Found by a test that saw `float()` return True while
            # the config stayed empty.)
            from memory import config_manager

            def _apply(data: dict) -> None:
                section = data.get("floating_widgets")
                if not isinstance(section, dict):
                    section = {}
                section[name] = placement.as_dict()
                data["floating_widgets"] = section

            if not config_manager.update_config(_apply):
                logbook.get(__name__).warning(
                    "the position of %s was not saved; the next float will use "
                    "the default", name)
        except Exception as e:              # noqa: BLE001
            logbook.get(__name__).debug("could not save the position: %s", e)

    def _read_saved(self, name: str) -> dict | None:
        try:
            from memory.config_manager import load_api_keys
            section = (load_api_keys() or {}).get("floating_widgets")
            return section.get(name) if isinstance(section, dict) else None
        except Exception as e:              # noqa: BLE001
            logbook.get(__name__).debug("could not read a saved position: %s", e)
            return None

    def _log(self, message: str) -> None:
        """Say it where the user can see it — a silent refusal is a dead end."""
        try:
            self._window.write_log(f"SYS: {message}")
        except Exception as e:              # noqa: BLE001
            logbook.get(__name__).debug("no activity log to write to: %s", e)


__all__ = ["FloatingPanel"]
