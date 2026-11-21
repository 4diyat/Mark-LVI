"""The floating face: a small always-on-top window with the avatar in it.

WHY IT IS TESTED AGAINST THE REAL `HudCanvas`
    The interesting failure is not "did we create a QWidget" — it is whether a
    `HudCanvas` survives being re-parented into a fixed 260-pixel frameless
    window and being told the assistant's state in words it already understands.
    `HudCanvas` is a 548-line animated widget that starts its own QTimer; if the
    bubble got any of that wrong the symptom on the user's desktop would be a
    grey square, which is exactly the class of bug `test_window_smoke.py` exists
    to catch. So this builds the real thing over the repo's own PyQt stub.

WHAT CANNOT BE TESTED HERE
    A frameless window on a real window manager: `WA_TranslucentBackground`,
    the taskbar behaviour of the Tool flag, and whether the drag follows the
    cursor. Those are read from the code and driven through the stub's events;
    none of them has been seen on a real desktop.
"""
from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


class _Flag:
    """A distinct window-flag bit, so OR-ing can be verified.

    The repo's Qt stub uses one sentinel enum that compares False to everything
    (`_Enum.__eq__` returns False) — correct for `if x == Qt.AlignLeft` checks,
    useless for "were all three flags set". This file needs the second thing.
    """

    def __init__(self, bit):
        self.bit = bit

    def __or__(self, other):
        return _Flag(self.bit | getattr(other, "bit", 0))

    def __ror__(self, other):
        return self.__or__(other)

    def __and__(self, other):
        return self.bit & getattr(other, "bit", 0)

    def __eq__(self, other):
        return self.bit == getattr(other, "bit", other)

    def __hash__(self):
        return self.bit

    def __int__(self):
        return self.bit


WINDOW_FLAGS = {"FramelessWindowHint": 0x800, "Tool": 0x2,
                "WindowStaysOnTopHint": 0x40000}


def test_window_flags_asks_for_all_three(qt):
    """Read directly: a missing bit here is a window with a title bar, or one
    that sinks behind whatever the user is looking at.

    `Qt` is a stand-in with only these three names, because the repo's stub
    returns the same sentinel for every attribute and OR-ing it proves nothing.
    """
    WindowType = types.SimpleNamespace(
        **{name: _Flag(bit) for name, bit in WINDOW_FLAGS.items()})
    combined = qt.face_bubble.window_flags(types.SimpleNamespace(WindowType=WindowType))
    for name, bit in WINDOW_FLAGS.items():
        assert (combined & _Flag(bit)) == bit, f"{name} is not in the flag set"


def test_window_flags_names_are_the_three_the_mode_needs(qt):
    """A name that does not exist in the real enum would raise on the user's
    desktop, not here — so the list is pinned to what the mode is for."""
    assert tuple(qt.face_bubble._FLAGS) == (
        "FramelessWindowHint", "Tool", "WindowStaysOnTopHint")


@pytest.fixture()
def qt(monkeypatch):
    """The window smoke-test's PyQt stand-in, scoped to this file.

    Imported by path and installed the same way `test_window_smoke` does, so
    this file cannot drift from the Qt surface the rest of the suite trusts.
    """
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "smoke_for_bubble", ROOT / "tests" / "test_window_smoke.py")
    smoke = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(smoke)
    saved = {k: v for k, v in sys.modules.items()
             if k == "PyQt6" or k.startswith("PyQt6.") or k == "ui" or k.startswith("ui.")}
    sys.modules.update(smoke._install_qt())
    for name in [k for k in sys.modules if k == "ui" or k.startswith("ui.")]:
        sys.modules.pop(name, None)
    try:
        import ui
        import ui.face_bubble
        yield ui
    finally:
        for name in list(sys.modules):
            if name == "ui" or name.startswith("ui."):
                sys.modules.pop(name, None)
        for name in [k for k in list(sys.modules) if k.startswith("PyQt6")]:
            if name not in saved:
                sys.modules.pop(name, None)
        sys.modules.update(saved)


class _FakeWindow:
    """A window with position and size, for the behaviour that needs them.

    The repo's Qt stub answers `None` to every call (`_Object.__getattr__`
    returns a lambda), so `width()`, `pos()` and `windowFlags()` say nothing
    there. A widget per test would have to re-implement the stub's whole
    constructor surface; this is only what the bubble itself uses. The REAL
    construction is covered by `test_the_face_is_an_actual_hud_canvas`, which
    builds a genuine `HudCanvas` inside the genuine stub window — geometry is
    the part this fake takes over, and Qt places windows, not this file.
    """

    def __init__(self, size):
        self._size = size
        self._pos = [0, 0]
        self.moves = []
        self.shown = 0
        self.hidden = 0
        self._visible = False
        self._deleted = False

    # size / position
    def setFixedSize(self, *_a):
        pass

    def setGeometry(self, *_a):
        pass

    def setMinimumSize(self, *_a):
        pass

    def width(self):
        return self._size

    def height(self):
        return self._size

    def move(self, point):
        self._pos = [point.x, point.y]
        self.moves.append((point.x, point.y))

    def x(self):
        return self._pos[0]

    def y(self):
        return self._pos[1]

    def pos(self):
        class _P:
            def __init__(self, p):
                self.x, self.y = p

            def __add__(self, delta):
                return _P([self.x + delta.x, self.y + delta.y])

            def __sub__(self, other):
                return _P([self.x - other.x, self.y - other.y])
        return _P(self._pos)

    # lifecycle
    def show(self):
        self.shown += 1
        self._visible = True

    def hide(self):
        self.hidden += 1
        self._visible = False

    def deleteLater(self):
        self._deleted = True

    def isVisible(self):
        return self._visible

    def windowFlags(self):
        return "flags"


def _attach_fake(shell_or_bubble, size):
    window = _FakeWindow(size)
    if hasattr(shell_or_bubble, "_window"):
        shell_or_bubble._window = window
    return window


@pytest.fixture()
def bubble(qt):
    """A real `FaceBubble` whose window is the fake above."""
    from ui.hud_canvas import HudCanvas
    made = qt.face_bubble.FaceBubble(
        "face.png", "JARVIS", on_double_click=lambda: made.double_clicked.append(1))
    made.double_clicked = []
    assert made.start() is True, "the real construction must work"
    # Real canvas kept; window swapped for one with geometry.
    real_canvas = made.canvas
    assert isinstance(real_canvas, HudCanvas)
    made._window = _FakeWindow(made._size)
    made._placed = False
    made._place()
    yield made
    made._window = _FakeWindow(made._size)


def test_the_face_is_an_actual_hud_canvas(qt, bubble):
    """A placeholder widget would look identical here and broken on screen."""
    from ui.hud_canvas import HudCanvas
    assert isinstance(bubble.canvas, HudCanvas)
    assert bubble._size == bubble._window.width() == bubble._window.height(), (
        "the face must be square")


def test_the_bubble_places_itself_into_a_corner_and_only_once(qt, bubble):
    first = (bubble._window.x(), bubble._window.y())
    bubble._place()
    assert (bubble._window.x(), bubble._window.y()) == first


# ── construction ──────────────────────────────────────────────────────────

def test_the_bubble_is_frameless_and_on_top(qt):
    """Construction itself, over the real stub — the flags are pinned by name in
    `test_window_flags_asks_for_all_three` because the stub cannot compare them."""
    from ui.hud_canvas import HudCanvas
    made = qt.face_bubble.FaceBubble("face.png", "JARVIS")
    assert made.start() is True
    assert made.available is True
    assert isinstance(made.canvas, HudCanvas), "no face was put in the window"
    made.stop()


def test_a_button_that_is_not_left_starts_no_drag(qt, bubble):
    class _Buttons:
        def __init__(self):
            self.LeftButton = object()     # a different object: not equal
            self.OtherButton = self

    class _Event:
        def button(self):
            return _Buttons()

    bubble._on_press(_Event())
    assert bubble._drag is None


def test_dragging_moves_the_window_by_the_cursor_delta(qt, bubble):
    class _Point:
        """A point with BOTH interfaces the bubble uses: `.x/.y` attributes and
        `+-` returning another point. The first draft only had the arithmetic,
        and the code under test reads `.x` — which is the shape Qt actually
        has, so the fake was the thing that was wrong."""

        def __init__(self, x, y):
            self.x, self.y = x, y

        def __sub__(self, other):
            return _Point(self.x - other.x, self.y - other.y)

        def __add__(self, other):
            return _Point(self.x + other.x, self.y + other.y)

        def toPoint(self):
            return self

    class _Button:
        """`event.button()` returns the enum, and the enum has the names."""

        def __init__(self):
            self.LeftButton = self

    class _Press:
        def button(self):
            return _Button()

        def globalPosition(self):
            return _Point(100, 100)

    class _Move:
        def globalPosition(self):
            return _Point(140, 130)

    start = (bubble._window.x(), bubble._window.y())
    bubble._on_press(_Press())
    assert bubble._drag is not None, "the press was not accepted"
    bubble._on_move(_Move())
    assert (bubble._window.x(), bubble._window.y()) == (start[0] + 40, start[1] + 30)
    bubble._on_release(None)
    assert bubble._drag is None, "the drag must end on release or the face follows the mouse"


# ── the way back ──────────────────────────────────────────────────────────

def test_double_clicking_the_face_summons_the_interface(qt, bubble):
    class _Event:
        def __init__(self):
            self.accepted = False

        def accept(self):
            self.accepted = True

    event = _Event()
    bubble._on_double_click_event(event)
    assert bubble.double_clicked == [1]
    assert event.accepted is True


def test_a_failing_summon_does_not_kill_the_face(qt):
    """The bubble is the only visible surface in this mode."""
    def _boom():
        raise RuntimeError("no window today")

    made = qt.face_bubble.FaceBubble("face.png", "JARVIS", on_double_click=_boom)
    assert made.start() is True
    made._on_double_click_event(types.SimpleNamespace(accept=lambda: None))
    assert made.available is True
    made.stop()


def test_no_callback_is_harmless(qt):
    made = qt.face_bubble.FaceBubble("face.png", "JARVIS", on_double_click=None)
    assert made.start() is True
    made._on_double_click_event(types.SimpleNamespace(accept=lambda: None))
    made.stop()


# ── state, audio, lips ────────────────────────────────────────────────────

def test_the_state_reaches_the_avatar_in_the_words_the_canvas_uses(qt, bubble):
    bubble.set_state("speaking")
    assert bubble.canvas.state == "SPEAKING"
    assert bubble.canvas.speaking is True
    bubble.set_state("sleeping")
    assert bubble.canvas.state == "SLEEPING"
    assert bubble.canvas.speaking is False


def test_the_face_keeps_the_state_it_was_given_before_it_existed(qt):
    """`set_state` is called from startup, before a bubble may be built."""
    made = qt.face_bubble.FaceBubble("face.png", "JARVIS")
    made.set_state("thinking")            # no window yet — must not raise
    assert made.start() is True
    assert made.canvas.state == "THINKING"
    made.stop()


def test_audio_and_visemes_reach_the_bubble_canvas(qt, bubble):
    """Without this the floating face mouths nothing while JARVIS speaks, which
    reads as broken rather than muted."""
    levels, visemes = [], []
    bubble.canvas.set_audio_level = levels.append
    bubble.canvas.push_visemes = lambda f, h, a: visemes.append((f, h, a))
    bubble.set_audio_level(0.42)
    bubble.push_visemes([(0.1, 0.2, 0.3)], 0.02, 1234.5)
    assert levels == [0.42]
    assert visemes == [([(0.1, 0.2, 0.3)], 0.02, 1234.5)]


def test_a_canvas_fault_never_escapes_into_the_audio_thread(qt, bubble):
    """These are called from the audio callback. An exception there is a dropped
    frame of speech, not a crash worth taking."""
    def _boom(*_a, **_k):
        raise RuntimeError("canvas gone")

    bubble.canvas.set_audio_level = _boom
    bubble.canvas.push_visemes = _boom
    bubble.set_audio_level(0.5)                  # must not raise
    bubble.push_visemes([], 0.02, 0.0)


# ── the modes, driven ─────────────────────────────────────────────────────

class _Event:
    def __init__(self):
        self.outcome = []

    def ignore(self):
        self.outcome.append("ignored")

    def accept(self):
        self.outcome.append("accepted")


def _launch(monkeypatch, mode="bubble", tray_ok=True, bubble_ok=True, ready=True,
            qt=None):
    """Build a real `JarvisUI` with the mode matrix as parameters."""
    if qt is None:
        raise RuntimeError("pass the qt fixture")
    ui = qt
    # Imported for its side effect (binding `ui.tray` so the patches below can
    # reach it) — but reach it through the module object, which is what a
    # redefinition lint cannot see past.
    import importlib
    tray_mod = importlib.import_module("ui.tray")
    from memory import config_manager as cm

    state = {"visible": False, "shown": 0, "hidden": 0, "full": 0,
             "tray_ok": tray_ok, "bubble_ok": bubble_ok, "mode": mode,
             "ready": ready}
    monkeypatch.setattr(ui.MainWindow, "showFullScreen",
                        lambda self: state.__setitem__("full", state["full"] + 1))
    monkeypatch.setattr(ui.MainWindow, "showMaximized",
                        lambda self: state.__setitem__("visible", True))
    monkeypatch.setattr(ui.MainWindow, "hide",
                        lambda self: state.__setitem__("visible", False))
    monkeypatch.setattr(ui.MainWindow, "isVisible", lambda self: state["visible"])
    monkeypatch.setattr(ui.MainWindow, "isFullScreen", lambda self: False)
    monkeypatch.setattr(ui.MainWindow, "raise_", lambda self: None)
    monkeypatch.setattr(ui.MainWindow, "activateWindow", lambda self: None)
    for base in ui.MainWindow.__mro__[1:]:
        if not hasattr(base, "closeEvent"):
            monkeypatch.setattr(base, "closeEvent", lambda self, event: None,
                                raising=False)
            break
    monkeypatch.setattr(cm, "get_ui_mode", lambda: state["mode"])
    monkeypatch.setattr(cm, "save_ui_mode", lambda m: state.__setitem__("mode", m))
    monkeypatch.setattr(cm, "get_assistant_name", lambda: "JARVIS")
    monkeypatch.setattr(ui.MainWindow, "_check_config", lambda self: state["ready"])
    monkeypatch.setattr(tray_mod.TrayIcon, "start", lambda self: state["tray_ok"])
    monkeypatch.setattr(tray_mod.TrayIcon, "available",
                        property(lambda self: state["tray_ok"]))
    def _fake_start(self):
        # Mirrors the real `start`'s contract: build a window (the fake, which
        # has geometry) and report whether the desktop would have it. The real
        # construction is covered by the tests above; this fixture is for the
        # MODE logic, which only needs show/hide to mean something.
        if not state["bubble_ok"]:
            return False
        self._window = _FakeWindow(self._size)
        return True
    monkeypatch.setattr(ui.face_bubble.FaceBubble, "start", _fake_start)
    monkeypatch.setattr(ui.face_bubble.FaceBubble, "available",
                        property(lambda self: state["bubble_ok"]))
    instance = ui.JarvisUI("face.png")
    instance.state = state
    return instance


@pytest.fixture()
def shell(monkeypatch, qt):
    """A real `JarvisUI` in bubble mode with a working face."""
    return _launch(monkeypatch, qt=qt), None


def test_bubble_mode_builds_the_face_and_leaves_the_screen_alone(shell):
    instance, _ = shell
    assert instance.state["full"] == 0, "bubble mode must not fill the screen"
    assert instance.ambient is True
    assert instance._bubble is not None


def test_a_failed_bubble_degrades_to_the_tray_not_to_a_window(monkeypatch, qt):
    """"Less" is acceptable; "a window the user asked not to have" is not.

    This needs a face that fails at LAUNCH, so it builds its own shell rather
    than reusing the one that succeeds — the first version asserted on a bubble
    that had never been asked to start, which is a test that passes by not
    happening.
    """
    ui = _launch(monkeypatch, mode="bubble", tray_ok=True, bubble_ok=False, qt=qt)
    assert ui._ambient is True, "a failed face must not leave the mode"
    assert ui._bubble is None
    assert ui.state["full"] == 0, "the user asked for no window and got one"


def test_the_face_steps_aside_while_the_window_is_up(shell):
    instance, _state = shell
    b = instance._bubble
    shown = {"v": True}
    b._window.show = lambda: shown.__setitem__("v", True)
    b._window.hide = lambda: shown.__setitem__("v", False)
    instance.summon()
    assert shown["v"] is False, "two copies of the avatar on screen at once"
    instance.dismiss()
    assert shown["v"] is True, "the face must come back when the window goes away"


def test_switching_to_the_tray_mode_removes_the_face(shell):
    instance, _ = shell
    assert instance._bubble is not None
    assert instance.set_interface_mode("ambient") is True
    assert instance._bubble is None, "the face outlived the mode it belonged to"
    assert instance.state["mode"] == "ambient"


def test_switching_to_hud_removes_both_the_face_and_the_tray(shell):
    instance, _ = shell
    instance.set_interface_mode("hud")
    assert instance._bubble is None
    assert instance.state["full"] >= 1, "hud mode must show the window"
    assert instance.ambient is False


def test_a_mode_that_cannot_be_delivered_is_refused_not_saved(shell):
    """A stored setting that does nothing is one the user re-toggles forever."""
    instance, _ = shell
    state = instance.state
    state["bubble_ok"] = False
    state["mode"] = "ambient"
    instance._bubble = None
    assert instance.set_interface_mode("bubble") is False
    assert state["mode"] == "ambient", "the refusal was saved as if it worked"


def test_bubble_mode_without_a_tray_falls_back_to_the_window(monkeypatch):
    """The tray is the fallback for everything, in every ambient variant."""
    source = (ROOT / "ui" / "lifecycle.py").read_text(encoding="utf-8")
    start = source.index("def start_interface(shell")
    body = source[start:source.index("def start_tray(shell")]
    guard = "if not start_tray(shell):"
    assert guard in body
    assert body.index(guard) < body.index("start_bubble(shell)"), (
        "the face must not be built before there is a tray to fall back on")
