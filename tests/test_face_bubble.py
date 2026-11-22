"""The floating face: a small always-on-top window with the avatar in it.

WHY IT IS TESTED AGAINST THE REAL CANVAS
    The interesting failure is not "did we create a QWidget" — it is whether a
    the canvas survives being re-parented into a fixed 260-pixel frameless
    window and being told the assistant's state in words it already understands.
    the canvas is an animated widget that starts its own QTimer; if the
    bubble got any of that wrong the symptom on the user's desktop would be a
    grey square, which is exactly the class of bug `qtstub.py` exists
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

from tests import qtstub

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
    stubs = qtstub.install_qt()
    saved = {k: v for k, v in sys.modules.items()
             if k == "PyQt6" or k.startswith("PyQt6.") or k == "ui" or k.startswith("ui.")}
    sys.modules.update(stubs)
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
    builds a genuine canvas inside the genuine stub window — geometry is
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
    made = qt.face_bubble.FaceBubble(
        "face.png", "JARVIS", on_double_click=lambda: made.double_clicked.append(1))
    made.double_clicked = []
    assert made.start() is True, "the real construction must work"
    # Real canvas kept; window swapped for one with geometry.
    real_canvas = made.canvas
    assert type(real_canvas).__name__ == "FaceCanvas"
    made._window = _FakeWindow(made._size)
    made._placed = False
    made._place()
    yield made
    made._window = _FakeWindow(made._size)


def test_the_face_is_an_actual_avatar_canvas(qt, bubble):
    """A placeholder widget would look identical here and broken on screen."""
    assert type(bubble.canvas).__name__ == "FaceCanvas"
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
    made = qt.face_bubble.FaceBubble("face.png", "JARVIS")
    assert made.start() is True
    assert made.available is True
    assert type(made.canvas).__name__ == "FaceCanvas", "no face was put in the window"
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


# ── the surfaces, driven ──────────────────────────────────────────────────

class _Event:
    def __init__(self):
        self.outcome = []

    def ignore(self):
        self.outcome.append("ignored")

    def accept(self):
        self.outcome.append("accepted")


class _FakeBubble:
    """A face that records show/hide instead of drawing."""

    def __init__(self, ok=True):
        self.ok = ok
        self.available = ok
        self.shown = True
        self._window = self
        self.started = False

    def start(self):
        self.started = True
        return self.ok

    def setVisible(self, visible):
        self.shown = bool(visible)

    @property
    def visible(self):
        return self.shown

    def set_state(self, state):
        self.state = state


def _shell(monkeypatch, qt, tray_ok=True, bubble_ok=True):
    """A real `AmbientShell`, with the surfaces replaced by recorders.

    The real construction of each surface has its own test above; this fixture
    is for the LIFECYCLE — what `start_interface`, `summon` and `dismiss` do to
    them, which only needs the calls to mean something.
    """
    import importlib
    tray_mod = importlib.import_module("ui.tray")
    from ui import lifecycle

    state = {"tray_ok": tray_ok, "bubble_ok": bubble_ok, "tray_starts": 0,
             "orb_starts": 0, "bar_starts": 0}

    def _tray_start(self):
        state["tray_starts"] += 1
        return state["tray_ok"]

    monkeypatch.setattr(tray_mod.TrayIcon, "start", _tray_start)
    monkeypatch.setattr(tray_mod.TrayIcon, "available",
                        property(lambda self: state["tray_ok"]))

    def _bubble_start(self):
        if not state["bubble_ok"]:
            self.error = "no window"
            return False
        self._window = _FakeBubble(True)
        return True

    monkeypatch.setattr(qt.face_bubble.FaceBubble, "available",
                        property(lambda self: getattr(self, "_window", None) is not None))
    monkeypatch.setattr(qt.face_bubble.FaceBubble, "start", _bubble_start)
    monkeypatch.setattr(qt.face_bubble.FaceBubble, "visible",
                        property(lambda self: bool(getattr(self._window, "shown", False))))

    monkeypatch.setattr(lifecycle, "start_orb",
                        lambda shell: state.__setitem__("orb_starts", state["orb_starts"] + 1) or True)
    monkeypatch.setattr(lifecycle, "start_command_bar",
                        lambda shell: state.__setitem__("bar_starts", state["bar_starts"] + 1) or True)

    shell = qt.AmbientShell("face.png", "JARVIS")
    shell.state = state
    lifecycle.start_interface(shell)
    return shell


@pytest.fixture()
def shell(monkeypatch, qt):
    """A real `AmbientShell` with a working tray and a working face."""
    return _shell(monkeypatch, qt)


def test_every_surface_is_started(shell):
    assert shell.state["tray_starts"] == 1
    assert shell.state["orb_starts"] == 1
    assert shell.state["bar_starts"] == 1
    assert shell._bubble is not None
    assert shell.ambient is True


def test_a_failed_face_degrades_to_the_tray_not_to_a_window(monkeypatch, qt):
    """"Less" is acceptable; a window the user asked not to have is not.

    The face is the one surface with a picture in it, so its failure is the one
    that tempts a fallback to "show the window". There is no window in this
    build — which makes the temptation smaller and the rule easier to keep.
    """
    shell = _shell(monkeypatch, qt, bubble_ok=False)
    assert shell._bubble is None
    assert shell._tray is not None, "the tray is the fallback for everything"
    assert shell.ambient is True


def test_a_failure_to_build_a_surface_does_not_stop_the_others(monkeypatch, qt):
    """Each surface starts on its own. One refusal is not a cascade.

    This is the failure that leaves an assistant holding a microphone with
    nothing on screen, so it is asserted rather than assumed.
    """
    shell = _shell(monkeypatch, qt, tray_ok=False, bubble_ok=False)
    assert shell._tray is None
    assert shell._bubble is None
    assert shell.state["orb_starts"] == 1, "the orb gave up because the tray did"
    assert shell.state["bar_starts"] == 1


def test_the_orb_starts_even_when_the_face_cannot(monkeypatch, qt):
    shell = _shell(monkeypatch, qt, bubble_ok=False)
    assert shell.state["orb_starts"] == 1


def test_the_face_steps_aside_and_comes_back(shell):
    """Summon shows the face, dismiss hides it — and the orb is never hidden."""
    bubble = shell._bubble._window
    shell.dismiss()
    assert bubble.shown is False, "the face stayed up after a dismiss"
    shell.summon()
    assert bubble.shown is True, "the face did not come back"


def test_dismiss_never_hides_the_orb(shell):
    """The orb is the mark that says the assistant is there.

    Hiding it from a tray item would leave a process the user cannot see, which
    is the one state this project refuses to create. Quiet dims the orb; it
    never removes it.
    """
    source = (ROOT / "ui" / "lifecycle.py").read_text(encoding="utf-8")
    start = source.index("def dismiss(shell")
    body = source[start:source.index("def toggle_interface(shell")]
    assert "_orb" not in body, "dismiss touches the orb"


def test_the_tray_is_started_before_anything_that_could_fail(shell):
    """The tray is the only surface that can always get the user back."""
    source = (ROOT / "ui" / "lifecycle.py").read_text(encoding="utf-8")
    start = source.index("def start_interface(shell")
    body = source[start:source.index("def start_summon_hotkey(shell")]
    assert body.index("start_tray(shell)") < body.index("start_orb(shell)")
    assert body.index("start_tray(shell)") < body.index("start_bubble(shell)")


def test_no_surface_at_all_is_said_out_loud(monkeypatch, qt, capsys):
    """Running, listening, and invisible is the one outcome worth shouting about."""
    shell = _shell(monkeypatch, qt, tray_ok=False, bubble_ok=False)
    monkeypatch.setattr(shell, "state", dict(shell.state, orb_starts=0, bar_starts=0))
    from ui import lifecycle
    lifecycle.start_orb = lambda s: False
    lifecycle.start_command_bar = lambda s: False
    lifecycle.start_interface(shell)
    out = capsys.readouterr().out
    assert "No ambient surface" in out
