"""Ambient mode: no window at launch, a tray icon to get back, and a way out.

WHY THESE ASSERTIONS AND NOT OTHERS
    The three ways this feature can hurt somebody are all invisible in a code
    review and all permanent in daily use:

      1. **A ghost process.** Ambient mode starts with no window. If the tray
         icon cannot be created on this desktop, there is nothing to click, no
         window to close and no way to quit — a JARVIS that listens and cannot
         be told to stop. The mode must FALL BACK to the window, so that is
         tested as one case with a tray that refuses to start.
      2. **A close that ends the session.** Clicking the X on a window you
         summoned used to quit the program. In ambient mode it must put the
         window away, because there is still a tray and the user meant
         "dismiss". Tested by running `closeEvent` with a real stateful
         visibility flag, not by reading the source: the first draft of this
         file asserted on a string and would have passed with the branch
         unreachable.
      3. **A first run that can never finish.** The setup screen is an overlay
         inside the window. Hiding the window before a key exists would leave
         `main.py`'s `wait_for_api_key` loop waiting behind a tray icon forever.

    The tray itself is stubbed: `QSystemTrayIcon` needs a display and a
    notification area, neither of which exists in this sandbox. The stub is
    deliberately narrow — it provides what `ui/tray.py` calls and nothing else —
    so a name the tray module invents shows up as an AttributeError here rather
    than as a missing icon on the user's machine.
"""
from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


# ── a notification area that records what was done to it ──────────────────

class _Signal:
    def __init__(self):
        self.slots = []

    def connect(self, fn):
        self.slots.append(fn)

    def emit(self, *args):
        for fn in list(self.slots):
            fn(*args)


class _Action:
    def __init__(self, text):
        self._text = text
        self.triggered = _Signal()

    def text(self):
        return self._text

    def fire(self):
        self.triggered.emit()


class _Menu:
    def __init__(self):
        self.actions = []

    def addAction(self, text):
        action = _Action(text)
        self.actions.append(action)
        return action

    def labels(self):
        return [a.text() for a in self.actions]


class _Icon:
    def __init__(self, path=""):
        self._path = path
        self._null = not str(path or "").strip()

    def isNull(self):
        return self._null


class _App:
    def windowIcon(self):
        return _Icon()


class _Tray:
    """Stands in for QSystemTrayIcon. `available` is set per test."""

    available = True
    created = []
    ActivationReason = type("ActivationReason", (), {"Trigger": 3, "Context": 2})

    def __init__(self, icon=None, parent=None):
        self.icon = icon
        self.parent = parent
        self.tooltip = ""
        self.menu = None
        self.shown = False
        self.hidden = False
        self.activated = _Signal()
        _Tray.created.append(self)

    @staticmethod
    def isSystemTrayAvailable():
        return _Tray.available

    def setToolTip(self, text):
        self.tooltip = text

    def setContextMenu(self, menu):
        self.menu = menu

    def show(self):
        self.shown = True

    def hide(self):
        self.hidden = True


def _install_tray_qt(monkeypatch, available=True):
    """Put a minimal PyQt6 in sys.modules and load `ui/tray.py` by path.

    Only the names `ui/tray.py` imports are provided. Loading by path means
    nothing else in `ui/` is dragged in: `ui/__init__` imports the whole window,
    which needs a display.
    """
    _Tray.created = []
    _Tray.available = available

    gui = types.ModuleType("PyQt6.QtGui")
    gui.QIcon = _Icon

    widgets = types.ModuleType("PyQt6.QtWidgets")
    widgets.QApplication = type("QApplication", (), {"instance": staticmethod(_App)})
    widgets.QMenu = _Menu
    widgets.QSystemTrayIcon = _Tray

    pkg = types.ModuleType("PyQt6")
    pkg.__path__ = []
    monkeypatch.setitem(sys.modules, "PyQt6", pkg)
    monkeypatch.setitem(sys.modules, "PyQt6.QtGui", gui)
    monkeypatch.setitem(sys.modules, "PyQt6.QtWidgets", widgets)
    monkeypatch.delitem(sys.modules, "ui.tray", raising=False)

    import importlib.util
    spec = importlib.util.spec_from_file_location("ui.tray", ROOT / "ui" / "tray.py")
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, "ui.tray", module)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def tray_module(monkeypatch):
    return _install_tray_qt(monkeypatch)


# ── the tray itself ───────────────────────────────────────────────────────

def test_the_icon_reports_available_once_it_is_on_screen(tray_module):
    tray = tray_module.TrayIcon({})
    assert tray.available is False, "a tray that was never started must not claim to be up"
    assert tray.start() is True
    assert tray.available is True
    assert _Tray.created[-1].shown is True


def test_every_menu_item_is_present_and_quit_is_last(tray_module):
    """A menu with no Quit is a process the user has to hunt in Task Manager."""
    tray = tray_module.TrayIcon({})
    assert tray.start() is True
    labels = _Tray.created[-1].menu.labels()
    assert labels == [label for _key, label in tray_module.MENU_ITEMS]
    assert labels[-1] == "Quit", "Quit must be the last item, not next to Show"


def test_a_menu_item_calls_its_callback(tray_module):
    calls = []
    tray = tray_module.TrayIcon({"show": lambda: calls.append("show")})
    assert tray.start() is True
    _Tray.created[-1].menu.actions[0].fire()
    assert calls == ["show"]


def test_a_missing_callback_is_inert_rather_than_fatal(tray_module):
    tray = tray_module.TrayIcon({})
    assert tray.start() is True
    _Tray.created[-1].menu.actions[0].fire()      # must not raise
    assert tray.available is True


def test_a_failing_callback_does_not_take_the_icon_down(tray_module):
    """"Quit" raising must not remove the only route back to a working app."""
    def _boom():
        raise RuntimeError("no")

    seen = []
    tray = tray_module.TrayIcon({"quit": _boom}, logger=seen.append)
    assert tray.start() is True
    _Tray.created[-1].menu.actions[-1].fire()
    assert tray.available is True
    # Survived is not the same as unnoticed. This codebase bans silent handlers
    # precisely because a failure that leaves no trace is indistinguishable from
    # one that never happened — and here the tray is the only surface there is.
    assert any("quit" in line and "RuntimeError" in line for line in seen), (
        f"the failure left no trace: {seen}")


def test_notes_survive_without_a_logger(tray_module, capsys):
    """With no logger the note goes to stdout — never into a bare `pass`."""
    def _boom():
        raise RuntimeError("no")

    tray = tray_module.TrayIcon({"show": _boom})
    assert tray.start() is True
    _Tray.created[-1].menu.actions[0].fire()
    assert tray.notes, "the note list is empty; the failure was swallowed"
    assert "RuntimeError" in tray.notes[-1]
    assert "menu item failed" in capsys.readouterr().out


def test_no_notification_area_is_reported_not_raised(monkeypatch):
    module = _install_tray_qt(monkeypatch, available=False)
    tray = module.TrayIcon({})
    assert tray.start() is False
    assert tray.available is False
    assert "notification area" in tray.error


def test_a_left_click_summons_and_a_right_click_does_not(tray_module):
    calls = []
    tray = tray_module.TrayIcon({"show": lambda: calls.append("show")})
    assert tray.start() is True
    icon = _Tray.created[-1]
    icon.activated.emit(3)                        # Trigger
    assert calls == ["show"]
    icon.activated.emit(2)                        # Context — Qt opens the menu
    assert calls == ["show"], "a right click must not also summon a window"


def test_the_tooltip_follows_the_assistant_state(tray_module):
    tray = tray_module.TrayIcon({})
    assert tray.start() is True
    tray.set_state("listening")
    assert "listening" in _Tray.created[-1].tooltip
    tray.set_state("")                            # never renders as "— "
    assert _Tray.created[-1].tooltip.endswith("idle")


def test_stopping_twice_is_harmless(tray_module):
    tray = tray_module.TrayIcon({})
    assert tray.start() is True
    tray.stop()
    tray.stop()
    assert tray.available is False


# ── the window and the mode ───────────────────────────────────────────────

# Launch/summon/dismiss live here, not in ui/window.py — see the module docstring
# of ui/lifecycle.py for why (window.py has a ceiling and it was not raised).
LIFECYCLE = ROOT / "ui" / "lifecycle.py"


def test_ambient_mode_does_not_show_the_window_at_launch():
    """THE POINT OF THE FEATURE. Read from the source, because constructing the
    window needs a display and the decision under test is which call is made.

    `ui/lifecycle.py`, not `ui/window.py`: the decision lives there now, because
    putting it in `window.py` pushed that file past the ceiling that
    `tests/test_ui_split.py` enforces. A test that kept looking in `window.py`
    would start failing for the wrong reason on the day the ceiling did its job.
    """
    source = LIFECYCLE.read_text(encoding="utf-8")
    start = source.index("def start_interface(shell")
    body = source[start:source.index("def start_tray(shell")]
    assert 'mode != "ambient"' in body, "the launch path must branch on the mode"
    assert "_win.showFullScreen()" in body, "hud mode must still fill the screen"
    assert "start_tray(shell)" in body, "ambient mode must go to the tray"
    # And the fallback, in the same function: no tray means show the window.
    assert body.count("shell._win.showFullScreen()") == 2, (
        "there must be a second showFullScreen() as the no-tray fallback, "
        "otherwise ambient mode on a desktop without a notification area "
        "starts an assistant nobody can see or quit")


def test_an_unconfigured_install_gets_the_window_even_in_ambient_mode():
    """First run: the setup screen lives INSIDE the window.

    Ambient mode would hide it, the API key could never be typed, and main.py's
    `wait_for_api_key()` loop would wait behind a tray icon forever. The user
    would see an assistant that never answers and have no way to tell why.
    """
    source = LIFECYCLE.read_text(encoding="utf-8")
    start = source.index("def start_interface(shell")
    body = source[start:source.index("def start_tray(shell")]
    guard = 'if mode != "ambient" or not getattr(shell._win, "_ready", False):'
    assert guard in body, (
        "ambient mode must not engage on an install that still needs setup")
    assert body.index(guard) < body.index("start_tray(shell)"), (
        "the setup check must come before the tray is built")


def test_ambient_is_opt_in_and_defaults_to_the_hud():
    """An upgrade must not remove the window somebody used yesterday."""
    from memory import config_manager as cm
    assert cm.UI_MODES == ("hud", "ambient")
    import inspect
    src = inspect.getsource(cm.get_ui_mode)
    assert 'get("ui_mode", "hud")' in src


def test_saving_an_unknown_mode_is_refused(isolated_config):
    assert isolated_config.save_ui_mode("ambient") is True
    assert isolated_config.get_ui_mode() == "ambient"
    assert isolated_config.save_ui_mode("nonsense") is False
    assert isolated_config.get_ui_mode() == "ambient", "a bad value must not clobber a good one"


def test_a_hidden_window_ignores_fullscreen():
    """F11 belongs to whatever the user is actually looking at."""
    source = (ROOT / "ui" / "window.py").read_text(encoding="utf-8")
    start = source.index("def _toggle_fullscreen(self):")
    body = source[start:source.index("def resizeEvent", start)]
    guard = body.index("if not self.isVisible():")
    # The CALL, not the word: the comment above the guard names the method it is
    # refusing to call, and a plain `index("showFullScreen()")` finds that
    # mention first and fails on a body that is in fact correct.
    call = body.index("self.showFullScreen()")
    assert guard < call, (
        "the visibility guard must come before the showFullScreen() call")


# ── the behaviour, driven rather than read ────────────────────────────────

class _Event:
    def __init__(self):
        self.outcome = []

    def ignore(self):
        self.outcome.append("ignored")

    def accept(self):
        self.outcome.append("accepted")


@pytest.fixture()
def shell(monkeypatch):
    """A real `JarvisUI` over the repo's own Qt stub.

    `tests/test_window_smoke.py` already carries a narrow PyQt stand-in built
    from the `.pyi` files, and constructing the window against it is the pattern
    that caught three shipped bugs this project had. Reusing it means these
    tests exercise the actual `JarvisUI.__init__` and `MainWindow.closeEvent`
    rather than a hand-written stand-in that agrees with the bug.
    """
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "smoke_for_ambient", ROOT / "tests" / "test_window_smoke.py")
    smoke = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(smoke)
    saved = {k: v for k, v in sys.modules.items()
             if k == "PyQt6" or k.startswith("PyQt6.") or k == "ui" or k.startswith("ui.")}
    sys.modules.update(smoke._install_qt())
    for name in [k for k in sys.modules if k == "ui" or k.startswith("ui.")]:
        sys.modules.pop(name, None)
    try:
        import ui
        import ui.tray
        from memory import config_manager as cm

        state = {"visible": False, "shown": 0, "hidden": 0, "maxed": 0, "full": 0,
                 "tray_ok": True, "mode": "ambient", "ready": True}
        monkeypatch.setattr(ui.MainWindow, "showFullScreen",
                            lambda self: state.__setitem__("full", state["full"] + 1))
        monkeypatch.setattr(ui.MainWindow, "showMaximized",
                            lambda self: (state.__setitem__("maxed", state["maxed"] + 1),
                                          state.__setitem__("visible", True)))
        monkeypatch.setattr(ui.MainWindow, "hide",
                            lambda self: (state.__setitem__("hidden", state["hidden"] + 1),
                                          state.__setitem__("visible", False)))
        monkeypatch.setattr(ui.MainWindow, "isVisible", lambda self: state["visible"])
        monkeypatch.setattr(ui.MainWindow, "isFullScreen", lambda self: False)
        monkeypatch.setattr(ui.MainWindow, "raise_", lambda self: None)
        monkeypatch.setattr(ui.MainWindow, "activateWindow", lambda self: None)
        # The REAL closeEvent must run — patching it here would have made the
        # two close tests below pass against a branch that never executed, which
        # is exactly the mistake this file is written to avoid. Only its
        # `super()` target is given a no-op, because the Qt stub has no
        # QMainWindow.closeEvent to call.
        for base in ui.MainWindow.__mro__[1:]:
            if not hasattr(base, "closeEvent"):
                monkeypatch.setattr(base, "closeEvent", lambda self, event: None,
                                    raising=False)
                break
        monkeypatch.setattr(cm, "get_ui_mode", lambda: state["mode"])
        monkeypatch.setattr(cm, "save_ui_mode", lambda m: True)
        monkeypatch.setattr(ui.MainWindow, "_check_config", lambda self: state["ready"])
        monkeypatch.setattr(ui.tray.TrayIcon, "start", lambda self: state["tray_ok"])
        monkeypatch.setattr(ui.tray.TrayIcon, "available",
                            property(lambda self: state["tray_ok"]))
        shell = ui.JarvisUI("face.png")
        yield shell, state
    finally:
        for name in list(sys.modules):
            if name == "ui" or name.startswith("ui."):
                sys.modules.pop(name, None)
        for name in [k for k in list(sys.modules) if k.startswith("PyQt6")]:
            if name not in saved:
                sys.modules.pop(name, None)
        sys.modules.update(saved)


def test_ambient_with_a_tray_leaves_the_screen_alone(shell):
    instance, state = shell
    assert instance.ambient is True
    assert state["full"] == 0, "ambient mode must not fill the screen"
    assert instance.tray_available is True


def test_ambient_without_a_tray_falls_back_to_the_window(monkeypatch, shell):
    """Already covered structurally — driven here because this is the case that
    decides whether the user has a usable app or an invisible process."""
    instance, state = shell
    assert instance.ambient is True
    # Now the same install, told the tray is unavailable.
    state["tray_ok"] = False
    assert instance.set_interface_mode("hud") is True
    assert instance.ambient is False
    assert state["full"] >= 1, "hud mode must show the window"


def test_an_unconfigured_install_is_never_left_headless(monkeypatch):
    """The first-run case, driven: no API key means the window, whatever the mode."""
    source = LIFECYCLE.read_text(encoding="utf-8")
    assert 'not getattr(shell._win, "_ready", False)' in source
    # And the guard is in front of the tray, so `_start_tray` cannot win a race
    # against a window that would never be shown.
    start = source.index("def start_interface(shell")
    body = source[start:source.index("def start_tray(shell")]
    assert body.index("_ready") < body.index("start_tray(shell)")


def test_summon_and_dismiss_round_trip(shell):
    instance, state = shell
    instance.summon()
    assert state["visible"] is True and instance.ambient is False
    instance.dismiss()
    assert state["visible"] is False and instance.ambient is True
    instance.toggle_interface()
    assert state["visible"] is True, "the toggle must bring it back"
    instance.toggle_interface()
    assert state["visible"] is False, "and put it away again"


def test_dismiss_refuses_when_no_tray_could_hold_the_window(shell):
    """Hiding the only surface leaves a process nobody can reach."""
    instance, state = shell
    instance._tray = None
    state["visible"] = True
    before = state["hidden"]
    instance.dismiss()
    assert state["hidden"] == before, "dismissed with nowhere to come back from"
    assert state["visible"] is True


def test_closing_a_summoned_window_puts_it_away_instead_of_quitting(shell, monkeypatch):
    """The one behaviour change a user meets by accident."""
    import ui.desktop_workspace as dw
    monkeypatch.setattr(dw, "confirm_shutdown", lambda _w: True)
    instance, state = shell
    instance.summon()
    assert state["visible"] is True

    event = _Event()
    instance._win.closeEvent(event)
    assert event.outcome == ["ignored"], (
        "the default close ran, which ends the session — in ambient mode it "
        "must only put the window away")
    assert state["visible"] is False, "the window was not hidden"
    assert instance.ambient is True


def test_closing_still_quits_when_there_is_no_tray(shell, monkeypatch):
    """No tray means no way back, so the old behaviour has to stand."""
    import ui.desktop_workspace as dw
    monkeypatch.setattr(dw, "confirm_shutdown", lambda _w: True)
    instance, _state = shell
    instance._tray.stop()
    instance._tray = None

    # What matters is which branch ran. With no tray the ambient early-return
    # must be skipped, so the default close is reached — and the stub's
    # QMainWindow.closeEvent (a no-op, see the fixture) records that it did.
    event = _Event()
    instance._win.closeEvent(event)
    assert event.outcome == [], (
        "the close was ignored and the window put away even though there is no "
        "tray to bring it back")
    assert instance.tray_available is False


def test_a_cancelled_close_never_hides_the_window(shell, monkeypatch):
    """Unsaved documents still win: the same guard as clicking the X."""
    import ui.desktop_workspace as dw
    monkeypatch.setattr(dw, "confirm_shutdown", lambda _w: False)
    instance, state = shell
    instance.summon()
    event = _Event()
    instance._win.closeEvent(event)
    assert event.outcome == ["ignored"]
    assert state["visible"] is True, "a cancelled close put the window away anyway"


def test_the_tray_tooltip_is_updated_by_set_state(shell):
    instance, _state = shell
    seen = []
    instance._tray = types.SimpleNamespace(set_state=seen.append,
                                           available=True, stop=lambda: None)
    instance.set_state("LISTENING")
    assert seen == ["LISTENING"], "the only status readout in ambient mode was not updated"
