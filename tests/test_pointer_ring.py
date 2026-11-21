"""The pointer ring: one definition, two places, and the rules for showing it.

The interesting part is not the circle. It is that the desktop ring must be
drawn from the cursor's ACTUAL position rather than from where the hand asked
it to go, and that it must disappear under exactly the conditions the pointer
stops working — otherwise the ring becomes a claim the program cannot keep.
"""
from __future__ import annotations

import ast
import importlib.util
import sys
import types
from pathlib import Path

from core import pointer_ring as ring

ROOT = Path(__file__).resolve().parent.parent


# ── one definition, not two that happen to match ──────────────────────────

def test_the_workspace_ring_consumes_the_shared_definition():
    """Two copies of a stylesheet are "the same pointer" only until somebody
    edits one of them. The workspace ring must READ these, not spell them."""
    source = (ROOT / "ui" / "hand_gesture.py").read_text(encoding="utf-8")
    tree = ast.parse(source)

    # The literal stylesheet that used to live here is gone.
    literals = [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant)
                and isinstance(n.value, str)]
    assert not any("border-radius: 21px" in s for s in literals), \
        "a second copy of the ring stylesheet is back"

    # And the shared module is what it uses.
    assert "_ring.style(" in source
    assert "_ring.where(" in source
    assert "_ring.size()" in source


def test_the_resting_and_pinched_rings_differ_visibly():
    """A pinch that does not look different is a click the user cannot time."""
    assert ring.style(True) != ring.style(False)
    assert ring.style(True) == ring.style(True), "not deterministic"


def test_the_ring_is_a_touch_target_sized_circle():
    assert ring.SIZE == ring.RADIUS * 2
    assert ring.size() == ring.SIZE


def test_the_ring_is_centred_on_the_point_it_is_given():
    assert ring.where(500, 300) == (500 - ring.RADIUS, 300 - ring.RADIUS)
    assert ring.where(0, 0) == (-ring.RADIUS, -ring.RADIUS)


def test_the_ring_does_not_re_scale_the_pointer_position():
    """`where()` offsets; it never re-derives. If it scaled, the ring and the
    cursor would disagree at the screen edges — exactly where a user looks to
    check whether the gesture works."""
    tree = ast.parse((ROOT / "core" / "pointer_ring.py").read_text(encoding="utf-8"))
    where = [n for n in ast.walk(tree)
             if isinstance(n, ast.FunctionDef) and n.name == "where"][0]
    body = ast.dump(where)
    assert "Mult" not in body and "Div" not in body, \
        "where() does arithmetic on the coordinate; it must only offset"


# ── when the ring may be on screen ────────────────────────────────────────

class _Fit:
    def __init__(self, allowed=True):
        self.allowed = allowed


def test_the_ring_shows_only_while_the_pointer_is_actually_driven():
    assert ring.visible(_Fit(True), enabled=True, frozen=False) is True


def test_a_mode_that_is_off_gets_no_ring():
    """A ring on the desktop for a mode that is off is a pointer the user
    cannot explain — and cannot get rid of."""
    assert ring.visible(_Fit(True), enabled=False, frozen=False) is False


def test_a_frozen_pointer_gets_no_ring():
    """The hand is not touching anything while JARVIS has focus or a
    confirmation is up. A ring there reads as "about to press"."""
    assert ring.visible(_Fit(True), enabled=True, frozen=True) is False


def test_a_platform_that_cannot_be_driven_gets_no_ring():
    assert ring.visible(_Fit(False), enabled=True, frozen=False) is False


# ── the desktop overlay ───────────────────────────────────────────────────

class _Label:
    def __init__(self, *a, **k):
        self._style = ""
        self._pos = (0, 0)
        self.shown = 0
        self.hidden = 0
        self.raised = 0
        self.flags = None

    def setWindowFlags(self, f): self.flags = f      # noqa: N802
    def setAttribute(self, *a): pass                 # noqa: N802
    def setFixedSize(self, *a): pass                 # noqa: N802
    def setAccessibleName(self, *a): pass            # noqa: N802
    def setStyleSheet(self, s): self._style = s      # noqa: N802
    def styleSheet(self): return self._style         # noqa: N802
    def move(self, x, y): self._pos = (x, y)         # noqa: N802
    def show(self): self.shown += 1                  # noqa: N802
    def hide(self): self.hidden += 1                 # noqa: N802
    def raise_(self): self.raised += 1


def _load_desktop_ring(monkeypatch, cursor=(640, 480)):
    """`ui.desktop_ring` with Qt, the cursor and the theme stubbed.

    `QCursor.pos()` is the seam this whole file turns on, so the stub makes it
    answer a FIXED point rather than whatever the sandbox has.
    """
    class _Qt:
        class WindowType:
            FramelessWindowHint = 1
            Tool = 2
            WindowStaysOnTopHint = 4
            WindowTransparentForInput = 8

        class WidgetAttribute:
            WA_TransparentForMouseEvents = 16
            WA_TranslucentBackground = 32
            WA_ShowWithoutActivating = 64

    class _Cursor:
        @staticmethod
        def pos():
            return types.SimpleNamespace(x=lambda: cursor[0], y=lambda: cursor[1])

    qtcore = types.ModuleType("PyQt6.QtCore")
    qtcore.Qt = _Qt
    qtgui = types.ModuleType("PyQt6.QtGui")
    qtgui.QCursor = _Cursor
    qtwidgets = types.ModuleType("PyQt6.QtWidgets")
    qtwidgets.QLabel = _Label

    monkeypatch.setitem(sys.modules, "PyQt6.QtCore", qtcore)
    monkeypatch.setitem(sys.modules, "PyQt6.QtGui", qtgui)
    monkeypatch.setitem(sys.modules, "PyQt6.QtWidgets", qtwidgets)
    stub = types.ModuleType("ui")
    stub.__path__ = [str(ROOT / "ui")]
    monkeypatch.setitem(sys.modules, "ui", stub)

    spec = importlib.util.spec_from_file_location(
        "desktop_ring", ROOT / "ui" / "desktop_ring.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, _Label


def test_the_desktop_ring_lands_on_the_cursor_not_on_the_intent(monkeypatch):
    """THE POINT OF THIS FILE.

    Drawing the ring at `gesture_os.coordinate(x, y, ...)` would show where the
    hand ASKED the pointer to go. `pyautogui` clamps, platforms refuse moves,
    fullscreen windows swallow them — so that ring can show a position the
    pointer never reached, and the user finds out by clicking something.
    """
    module, _ = _load_desktop_ring(monkeypatch, cursor=(1000, 700))
    ring_overlay = module.DesktopRing()
    ring_overlay.show()

    assert ring_overlay._w._pos == (1000 - ring.RADIUS, 700 - ring.RADIUS)


def test_the_ring_follows_a_moving_cursor(monkeypatch):
    """`cursor_position` reads `QCursor.pos()` at CALL time, so replacing it on
    the module is the honest seam — patching the Qt stub's class instead would
    be testing the stub."""
    module, _ = _load_desktop_ring(monkeypatch)
    seen = iter([(100, 100), (900, 20)])
    monkeypatch.setattr(module, "cursor_position", lambda: next(seen))

    ring_overlay = module.DesktopRing()
    ring_overlay.show()
    first = ring_overlay._w._pos
    ring_overlay.tick()
    assert ring_overlay._w._pos != first


def test_a_ring_that_accepts_clicks_eats_the_gesture_it_shows(monkeypatch):
    """It sits on top of whatever the hand is about to click."""
    module, _ = _load_desktop_ring(monkeypatch)
    ring_overlay = module.DesktopRing()
    ring_overlay.show()
    flags = ring_overlay._w.flags
    assert flags & 8, "WindowTransparentForInput is missing"


def test_the_ring_takes_no_taskbar_entry_and_no_title_bar(monkeypatch):
    module, _ = _load_desktop_ring(monkeypatch)
    ring_overlay = module.DesktopRing()
    ring_overlay.show()
    flags = ring_overlay._w.flags
    assert flags & 1 and flags & 2, "frameless and Tool are what keep it out"


def test_the_ring_brightens_while_the_hand_holds_a_click(monkeypatch):
    module, _ = _load_desktop_ring(monkeypatch)
    ring_overlay = module.DesktopRing()
    ring_overlay.show(pinched=False)
    assert ring_overlay._w._style == ring.style(False)
    ring_overlay.show(pinched=True)
    assert ring_overlay._w._style == ring.style(True)


def test_the_ring_is_not_restyled_when_nothing_changed(monkeypatch):
    """`setStyleSheet` is a full restyle. Doing it 30 times a second for one
    changed boolean is how a decoration becomes a performance problem."""
    module, _ = _load_desktop_ring(monkeypatch)
    ring_overlay = module.DesktopRing()
    ring_overlay.show(pinched=False)
    widget = ring_overlay._w
    styles = []
    original = widget.setStyleSheet
    widget.setStyleSheet = lambda s: (styles.append(s), original(s))
    ring_overlay.tick(pinched=False)
    ring_overlay.tick(pinched=False)
    assert styles == [], "restyled with no change"


def test_an_unreadable_cursor_does_not_take_the_tracking_loop_down(monkeypatch):
    """A compositor that refuses the query must cost one frame, not the mode."""
    module, _ = _load_desktop_ring(monkeypatch)
    monkeypatch.setattr(module, "cursor_position", lambda: None)
    ring_overlay = module.DesktopRing()
    ring_overlay.show()               # must not raise
    ring_overlay.tick()


def test_hiding_twice_is_not_an_error(monkeypatch):
    """Called from stop paths that can run more than once."""
    module, _ = _load_desktop_ring(monkeypatch)
    ring_overlay = module.DesktopRing()
    ring_overlay.show()
    ring_overlay.hide()
    ring_overlay.hide()
    assert ring_overlay.visible is False


# ── the bridge tells the ring what to draw ────────────────────────────────

def _bridge(monkeypatch, window):
    """`ui.gesture_os_bridge` with `QApplication` answered for the WHOLE test.

    The stub has to outlive the module load: `feed()` calls `_modal_open()`,
    which imports `QApplication` at CALL time and returns True (fails SAFE) when
    it cannot. A stub removed after loading therefore freezes every frame and
    every assertion below quietly measures nothing. That mistake has now been
    made three times in this repository — hence the note.
    """
    widgets = types.ModuleType("PyQt6.QtWidgets")

    class _App:
        @staticmethod
        def activeModalWidget():
            return None

    widgets.QApplication = _App
    monkeypatch.setitem(sys.modules, "PyQt6.QtWidgets", widgets)

    spec = importlib.util.spec_from_file_location(
        "bridge_under_test", ROOT / "ui" / "gesture_os_bridge.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    bridge = module.GestureOsBridge(window)

    class _Sink:
        def apply(self, intent, screen=None):
            return True

    bridge._out = _Sink()
    return bridge


class _FreeWindow:
    """A window that is not focused and has no banner: the pointer is FREE."""

    _confirm_overlay = None
    active = False

    def isActiveWindow(self):                # noqa: N802
        return self.active


def test_the_bridge_reports_a_held_click_as_pinching(monkeypatch):
    """The ring glows for the WHOLE pinch, not on the two frames that carried an
    event: a ring that blinked would be a click the user cannot time."""
    bridge = _bridge(monkeypatch, _FreeWindow())
    bridge.set_enabled(True)

    # A free hand first: the first sample has no previous position, and a pinch
    # on it is not yet a pinch.
    bridge.feed([(0.5, 0.5, False, False)], now=0.0)

    # A pinch that is too brief to click: nothing held.
    bridge.feed([(0.5, 0.5, True, False)], now=0.05)
    assert bridge.pinching is False

    # Held past the threshold: now the button is down.
    bridge.feed([(0.5, 0.5, True, False)], now=0.6)
    assert bridge.pinching is True, "the ring would not glow during the click"

    # Released.
    bridge.feed([(0.5, 0.5, False, False)], now=0.7)
    assert bridge.pinching is False


def test_the_bridge_reports_itself_frozen_while_our_own_surfaces_have_focus(monkeypatch):
    """Read live, not remembered: between two frames the user can click back to
    JARVIS, and the ring must go with the pointer in that same frame."""
    window = _FreeWindow()
    bridge = _bridge(monkeypatch, window)

    assert bridge.frozen is True, "the mode is off, so nothing is being driven"

    bridge.set_enabled(True)
    assert bridge.frozen is False

    window.active = True
    assert bridge.frozen is True, "the ring kept glowing while JARVIS had focus"

    window.active = False
    window._confirm_overlay = types.SimpleNamespace(isVisible=lambda: True)
    assert bridge.frozen is True, "the ring glowed over a confirmation banner"
