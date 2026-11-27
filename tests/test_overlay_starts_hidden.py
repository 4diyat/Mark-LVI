"""An overlay built for later must not be on screen now.

WHY THIS FILE EXISTS
    `start_voice_overlay` builds the overlay with `active=False` on every
    launch — "built now and shown later". The first version of
    `VoiceOverlay.start` called `window.show()` unconditionally and then set
    `_active = False`, so a 1280×720 frameless, always-on-top window sat at
    (0, 0) over the desktop from the first second, with a 12 fps timer painting
    into it.

    A visible window that is not `WindowTransparentForInput` takes the clicks.
    `window_flags` deliberately omits that flag so Esc can reach the overlay
    while it IS up — which means a window that is up but not listening
    swallows every click inside its rectangle. The tray panel behind it never
    gets one: "the surfaces are visible and nothing responds".

WHAT IS PROVEN
    The window is not shown and no timer runs when `active=False`, and both
    happen immediately when it is shown later. Not proven: the Windows hit
    testing that turns "visible" into "swallows clicks" — that is the
    documented reason the fix is to stay hidden, and it cannot be measured
    without the desktop.
"""
from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


class _Signal:
    def connect(self, _slot):
        pass


class _Timer:
    instances: list = []

    def __init__(self):
        self.interval = 0
        self.running = False
        self.timeout = _Signal()
        _Timer.instances.append(self)

    def setInterval(self, ms):
        self.interval = ms

    def start(self):
        self.running = True

    def stop(self):
        self.running = False


class _Widget:
    # `_VoiceCanvas(QWidget)` is constructed with its parent, so this accepts
    # one — a stub that refuses it fails the build path for a reason that has
    # nothing to do with show().
    def __init__(self, _parent=None):
        self.shown = False
        self.geometry = None

    def setWindowFlags(self, _f):
        pass

    def setAttribute(self, *_a):
        pass

    def setWindowTitle(self, _t):
        pass

    def setGeometry(self, *a):
        self.geometry = a

    def show(self):
        self.shown = True

    def hide(self):
        self.shown = False

    def raise_(self):
        pass

    def deleteLater(self):
        pass

    def keyPressEvent(self, _e):
        pass

    def setLayout(self, *_a):
        pass

    def setMouseTracking(self, *_a):
        pass

    def update(self):
        pass

    def width(self):
        return 1280

    def height(self):
        return 720


@pytest.fixture
def overlay_module():
    """The real `ui.voice_overlay` against a Qt that records show() and timers."""
    # ONLY PyQt6 IS SNAPSHOTTED. An earlier version also saved every `ui.*`
    # module and restored it afterwards, which put back a `ui.voice_overlay`
    # whose classes were built against THIS fixture's Qt stub — so
    # `test_voice_wiring`, running later, held a live reference to a module that
    # imported PyQt6 from a dict it no longer had. Restoring less is the fix:
    # the `ui` modules are re-imported cleanly, against whatever Qt exists then.
    saved = {k: v for k, v in sys.modules.items()
             if k == "PyQt6" or k.startswith("PyQt6.")}
    sys.modules["PyQt6"] = types.ModuleType("PyQt6")
    widgets = types.ModuleType("PyQt6.QtWidgets")
    widgets.QWidget = _Widget
    widgets.QApplication = types.SimpleNamespace(instance=lambda: object())
    core = types.ModuleType("PyQt6.QtCore")
    core.QTimer = _Timer
    core.Qt = types.SimpleNamespace(
        WidgetAttribute=types.SimpleNamespace(
            WA_TranslucentBackground=1, WA_ShowWithoutActivating=2),
        WindowType=types.SimpleNamespace(
            FramelessWindowHint=1, Tool=2, WindowStaysOnTopHint=4))
    sys.modules["PyQt6.QtWidgets"] = widgets
    sys.modules["PyQt6.QtCore"] = core
    for name in [k for k in sys.modules if k.startswith("ui.voice")]:
        sys.modules.pop(name, None)
    _Timer.instances = []
    import ui.voice_overlay as module

    yield module, _Timer
    # PUT PyQt6 BACK EXACTLY, and drop every `ui` module this fixture imported
    # so the next file re-imports them against its own Qt. Restoring the `ui`
    # modules instead is what caused a failure in a DIFFERENT test file.
    for name in [k for k in list(sys.modules)
                 if k == "PyQt6" or k.startswith("PyQt6.")
                 or k == "ui" or k.startswith("ui.")]:
        sys.modules.pop(name, None)
    sys.modules.update(saved)


def test_built_for_later_means_hidden_and_quiet(overlay_module):
    """DRIVE THE REAL FUNCTION, do not read it."""
    module, timers = overlay_module
    overlay = module.VoiceOverlay(on_close=lambda: None)

    assert overlay.start(active=False) is True

    assert overlay._window.shown is False, (
        "a 1280×720 always-on-top window was shown at startup; on Windows it "
        "takes every click in its rectangle")
    assert overlay.active is False
    assert timers.instances == [], (
        "a timer paints a hidden window: 12 fps of Qt-thread work whose only "
        "effect is to keep the loop busy")


def test_showing_later_shows_it_and_starts_drawing(overlay_module):
    """The hidden build must not have broken the visible one."""
    module, timers = overlay_module
    overlay = module.VoiceOverlay(on_close=lambda: None)
    overlay.start(active=False)

    overlay.show()

    assert overlay._window.shown is True
    assert overlay.active is True
    assert [t.running for t in timers.instances] == [True], (
        "the overlay became visible with no timer, so the hand and the glow "
        "would never move")


def test_asking_for_it_shown_builds_it_shown(overlay_module):
    """`active=True` is the other half of the contract."""
    module, timers = overlay_module
    overlay = module.VoiceOverlay(on_close=lambda: None)

    overlay.start(active=True)

    assert overlay._window.shown is True
    assert overlay.active is True
    assert timers.instances and timers.instances[0].running


def test_hiding_stops_the_work(overlay_module):
    """A hidden overlay that still ticks is the startup case, one step later."""
    module, timers = overlay_module
    overlay = module.VoiceOverlay(on_close=lambda: None)
    overlay.start(active=True)

    overlay.hide()

    assert overlay._window.shown is False
    assert overlay._timer is None, "the timer outlived the window being hidden"
