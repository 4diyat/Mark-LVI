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

from tests import qtstub

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
    """Mirrors the QAction API `ui/tray.py` uses — including the checkable half.

    A stub that only knows `text()` and `triggered` passes for every menu that
    is a list of verbs, and fails the moment one of them is a SWITCH. The
    auto-start item is a switch, and Qt's own behaviour is copied here: a
    checkable action flips its state before `triggered` fires.
    """

    def __init__(self, text):
        self._text = text
        self.triggered = _Signal()
        self._checkable = False
        self._checked = False

    def text(self):
        return self._text

    def setCheckable(self, value):
        self._checkable = bool(value)

    def isCheckable(self):
        return self._checkable

    def setChecked(self, value):
        self._checked = bool(value)

    def isChecked(self):
        return self._checked

    def fire(self):
        if self._checkable:
            self._checked = not self._checked     # Qt does this before the signal
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


def _menu_label(module, key: str) -> str:
    """The label `MENU_ITEMS` gives a key, so a reworded item does not break a test."""
    return dict(module.MENU_ITEMS)[key]


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


def test_the_autostart_item_is_a_switch_that_shows_the_real_state(tray_module):
    """The tick is only worth drawing if it is read from disk, not remembered.

    `checked` is a CALLABLE precisely so the menu can be built again after the
    setting changes; caching it in the tray would show yesterday's answer.
    """
    asked = []

    def _checked(key):
        asked.append(key)
        return True

    tray = tray_module.TrayIcon({}, checked=_checked)
    assert tray.start() is True
    assert asked == ["autostart"], "exactly the checkable item should be asked"
    action = next(a for a in _Tray.created[-1].menu.actions
                  if a.text() == _menu_label(tray_module, "autostart"))
    assert action.isCheckable() is True
    assert action.isChecked() is True


def test_a_switch_whose_callback_fails_is_not_left_ticked(tray_module):
    """Qt flips the tick before the callback runs; a failed toggle must flip back.

    A tick that says "on" over a registry write that was refused is the exact
    class of lie this whole change set out to remove.
    """
    def _boom():
        raise OSError("registry refused")

    tray = tray_module.TrayIcon({"autostart": _boom}, checked=lambda key: False)
    assert tray.start() is True
    action = next(a for a in _Tray.created[-1].menu.actions
                  if a.text() == _menu_label(tray_module, "autostart"))
    action.fire()
    assert action.isChecked() is False, "a failed toggle must not stay ticked"
    assert tray.notes, "and it must say so somewhere"


def test_a_switch_reports_what_the_callback_actually_did(tray_module):
    """The callback's return value wins, because it read the state back."""
    tray = tray_module.TrayIcon({"autostart": lambda: False},
                                checked=lambda key: True)
    assert tray.start() is True
    action = next(a for a in _Tray.created[-1].menu.actions
                  if a.text() == _menu_label(tray_module, "autostart"))
    action.fire()
    assert action.isChecked() is False, (
        "the toggle tried, and reported back that it is NOT on")


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


# ── the launch path, read from the source ─────────────────────────────────

# Launch/summon/dismiss live in `ui/lifecycle.py`, which is now the whole
# application: there is no window for `ui/window.py` to hold.
LIFECYCLE = ROOT / "ui" / "lifecycle.py"


def _launch_body() -> str:
    source = LIFECYCLE.read_text(encoding="utf-8")
    start = source.index("def start_interface(shell")
    return source[start:source.index("def start_summon_hotkey(shell")]


def test_the_launch_path_has_no_window_to_show():
    """THE POINT OF THE CUT. The launch path cannot fall back to a window.

    `ui/lifecycle.py` used to branch on `mode == "hud"` and call
    `showFullScreen()` twice — once for the mode, once as the no-tray fallback.
    Both branches existed because the window was the thing that could always be
    shown. Now nothing can, so the fallback that replaced it has to be a
    DIFFERENT surface plus a spoken reason, not a silently smaller app.
    """
    body = _launch_body()
    assert "showFullScreen" not in body, "a fullscreen fallback survived the cut"
    assert "_win" not in body, "the launch path still reaches for a window"


def test_the_tray_is_attempted_first_and_its_failure_is_named():
    """On a desktop with no notification area, silence is the failure mode.

    The tray is the only surface that can always get the user back to the app,
    so it goes first — and when it is missing, `start_interface` says so on
    stdout instead of leaving a process nobody can see or quit.
    """
    body = _launch_body()
    assert body.index("start_tray(shell)") < body.index("start_orb(shell)")
    assert body.index("start_tray(shell)") < body.index("start_bubble(shell)")
    assert "No ambient surface" in body, (
        "a launch with nothing on screen must not be silent")


def test_an_unconfigured_install_is_never_left_headless():
    """First run: no API key and nothing on screen is an app that never answers.

    `main.py` blocks in `wait_for_api_key()`, so the only thing that can say
    what is wrong is a surface. `AmbientShell.wait_for_api_key` notifies via the
    tray — this asserts that the surface exists and that the wait says
    something, because the window that used to carry the setup screen is gone.
    """
    shell_src = (ROOT / "ui" / "shell.py").read_text(encoding="utf-8")
    start = shell_src.index("def wait_for_api_key")
    body = shell_src[start:start + 2000]
    assert "notify" in body, "the key prompt must reach a surface, not only stdout"
    assert "API key" in body


def test_ambient_is_opt_in_and_defaults_to_the_hud():
    """An upgrade must not remove the interface somebody used yesterday."""
    from memory import config_manager as cm
    # Three values — "bubble" was added in phase 2, which is exactly why ui_mode
    # is a string and not a bool (phase 1 said so and was right). All three are
    # ambient variants now; "hud" keeps its name because it is on disk.
    assert cm.UI_MODES == ("hud", "ambient", "bubble")
    import inspect
    src = inspect.getsource(cm.get_ui_mode)
    assert 'get("ui_mode", "hud")' in src


def test_saving_an_unknown_mode_is_refused(isolated_config):
    assert isolated_config.save_ui_mode("ambient") is True
    assert isolated_config.get_ui_mode() == "ambient"
    assert isolated_config.save_ui_mode("nonsense") is False
    assert isolated_config.get_ui_mode() == "ambient", "a bad value must not clobber a good one"


# ── the behaviour, driven rather than read ────────────────────────────────

@pytest.fixture()
def shell(monkeypatch):
    """A real `AmbientShell` over the repo's own Qt stub.

    `tests/qtstub.py` carries a narrow PyQt stand-in built from the `.pyi`
    files, and constructing the real object against it is the pattern that
    caught three shipped bugs in this project. The surfaces themselves are
    replaced by recorders: this file is about the MODE, and a real tray icon
    needs a notification area that CI does not have.
    """
    stubs = qtstub.install_qt()
    saved = {k: v for k, v in sys.modules.items()
             if k == "PyQt6" or k.startswith("PyQt6.") or k == "ui" or k.startswith("ui.")}
    sys.modules.update(stubs)
    for name in [k for k in sys.modules if k == "ui" or k.startswith("ui.")]:
        sys.modules.pop(name, None)
    try:
        import importlib
        import ui
        import ui.face_bubble
        from ui import lifecycle
        from memory import config_manager as cm

        state = {"tray_ok": True, "mode": "ambient", "bubble_shown": True,
                 "orb_started": 0, "bar_started": 0, "notices": 0}
        tray_mod = importlib.import_module("ui.tray")
        monkeypatch.setattr(tray_mod.TrayIcon, "start",
                            lambda self: state["tray_ok"])
        monkeypatch.setattr(tray_mod.TrayIcon, "available",
                            property(lambda self: state["tray_ok"]))
        class _FaceWindow:
            """Records show/hide so `visible` means something."""

            def __init__(self):
                self.shown = True

            def setVisible(self, visible):        # noqa: N802 — Qt's name
                self.shown = bool(visible)

            def isVisible(self):                  # noqa: N802 — Qt's name
                return self.shown

        def _start_face(self):
            self._window = _FaceWindow()
            return True

        monkeypatch.setattr(ui.face_bubble.FaceBubble, "start", _start_face)
        monkeypatch.setattr(ui.face_bubble.FaceBubble, "available",
                            property(lambda self: True))
        monkeypatch.setattr(lifecycle, "start_orb",
                            lambda s: state.__setitem__(
                                "orb_started", state["orb_started"] + 1) or True)
        monkeypatch.setattr(lifecycle, "start_command_bar",
                            lambda s: state.__setitem__(
                                "bar_started", state["bar_started"] + 1) or True)
        monkeypatch.setattr(cm, "get_ui_mode", lambda: state["mode"])
        monkeypatch.setattr(cm, "save_ui_mode", lambda m: True)
        monkeypatch.setattr(ui.AmbientShell, "notify",
                            lambda self, text, *a, **k: state.__setitem__(
                                "notices", state["notices"] + 1))
        shell = ui.AmbientShell("face.png", "JARVIS")
        lifecycle.start_interface(shell)
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
    assert instance.tray_available is True
    assert state["orb_started"] == 1 and state["bar_started"] == 1


def test_ambient_without_a_tray_still_has_a_surface(monkeypatch):
    """The case that decides whether the user has a usable app or a process."""
    # The tray is rebuilt under a machine that refuses it.
    stubs = qtstub.install_qt()
    saved = {k: v for k, v in sys.modules.items()
             if k == "PyQt6" or k.startswith("PyQt6.") or k == "ui" or k.startswith("ui.")}
    sys.modules.update(stubs)
    for name in [k for k in sys.modules if k == "ui" or k.startswith("ui.")]:
        sys.modules.pop(name, None)
    try:
        import importlib
        import ui
        import ui.face_bubble
        from ui import lifecycle

        tray_mod = importlib.import_module("ui.tray")
        started = {"orb": 0, "bar": 0, "bubble": 0, "notice": 0}
        monkeypatch.setattr(tray_mod.TrayIcon, "start", lambda self: False)
        monkeypatch.setattr(tray_mod.TrayIcon, "available",
                            property(lambda self: False))
        monkeypatch.setattr(ui.face_bubble.FaceBubble, "start",
                            lambda self: started.__setitem__("bubble", 1) or True)
        monkeypatch.setattr(lifecycle, "start_orb",
                            lambda s: started.__setitem__("orb", 1) or True)
        monkeypatch.setattr(lifecycle, "start_command_bar",
                            lambda s: started.__setitem__("bar", 1) or True)
        monkeypatch.setattr(ui.AmbientShell, "notify",
                            lambda self, *a, **k: started.__setitem__("notice", 1))
        shell = ui.AmbientShell("face.png", "JARVIS")
        lifecycle.start_interface(shell)
        assert shell._tray is None
        assert started["orb"] == 1, "no tray, and no orb either"
        assert started["bar"] == 1, "the command bar is the fallback, not a window"
        assert started["bubble"] == 1, "the face is the other fallback"
    finally:
        for name in list(sys.modules):
            if name == "ui" or name.startswith("ui."):
                sys.modules.pop(name, None)
        for name in [k for k in list(sys.modules) if k.startswith("PyQt6")]:
            if name not in saved:
                sys.modules.pop(name, None)
        sys.modules.update(saved)


def test_summon_and_dismiss_round_trip(shell):
    """One surface at a time, and the orb never leaves."""
    instance, _state = shell
    bubble = instance._bubble
    assert instance.ambient is True
    instance.dismiss()
    assert bubble.visible is False
    instance.summon()
    assert bubble.visible is True
    assert instance.ambient is True, "summon must not end ambient mode"
