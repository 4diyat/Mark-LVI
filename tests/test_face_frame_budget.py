"""The face bubble must not saturate the one thread Qt needs.

WHY THIS FILE EXISTS
    On Windows the tray icon appeared and then responded to nothing. The icon
    is created synchronously by `QSystemTrayIcon.show()`, so it paints before
    the event loop is running — which is exactly what makes "icon visible but
    dead" a signature of a blocked Qt thread rather than a failed start.

    The block was the avatar. `FaceCanvas` runs a 33 ms timer and every tick
    calls `HoloAvatar.paint`, which walks the visible half of a 1,554-facet
    head and issues one `drawPolygon` per facet — plus a `QPolygonF`, three
    `QPointF` and (on the smooth path) a `QLinearGradient` with two or three
    `setColorAt` calls each. Measured on this mesh: 893 visible facets, so
    ~26,790 polygons and >100,000 Qt calls per second, all on the Qt thread.
    The event loop then services the tray only between frames that take longer
    than the frame budget — the icon is there, the clicks are not.

WHY THE TEST MEASURES THE MESH RATHER THAN TIMING A PAINT
    A timing assertion is a flaky test on CI and passes on a fast machine while
    the bug remains. What is deterministic is the WORK: how many facets a frame
    is allowed to draw. That number is the contract, and it does not depend on
    the speed of whatever machine runs the suite.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parent.parent


def _face_canvas_source() -> str:
    return (ROOT / "ui" / "face_canvas.py").read_text(encoding="utf-8")


import types
def test_one_still_second_costs_five_repaints_not_thirty():
    """The rule, called directly. This is the number that starved the tray."""
    from ui import face_canvas

    repaints = 0
    last = 0.0
    for step in range(30):                        # one second at 30 fps
        now_ms = step * face_canvas.FRAME_MS
        if face_canvas.should_repaint(now_ms, last, speaking=False):
            repaints += 1
            last = now_ms
    assert repaints <= 6, (
        f"{repaints} repaints in one still second — the whole mesh is redrawn "
        "every tick, which is what blocks the Qt thread")


def test_a_speaking_face_repaints_every_step():
    """The other direction: the throttle must not cost the mouth its frames."""
    from ui import face_canvas

    for step in range(10):
        now_ms = step * face_canvas.FRAME_MS
        assert face_canvas.should_repaint(now_ms, now_ms - 1, speaking=True)


def test_the_idle_repaint_rate_is_well_under_the_step_rate():
    from ui import face_canvas

    assert face_canvas.FRAME_MS <= 40, "the step rate stopped being 30 fps"
    assert face_canvas.IDLE_REPAINT_MS >= face_canvas.FRAME_MS * 4, (
        "the idle repaint rate is not meaningfully slower than the step rate")


def test_the_solid_fill_honours_the_stride():
    """`facet_stride` must change the NUMBER OF POLYGONS DRAWN.

    Measured on this mesh: 1,554 facets, 893 visible. One `drawPolygon` per
    facet plus its `QPolygonF`, three `QPointF` and a `QLinearGradient` is
    ~26,790 polygons and >100,000 Qt calls per second at 30 fps, all on the Qt
    thread — which is why the tray icon appeared and answered no clicks.

    Driven through `_paint_surface` with a painter that counts, so a mutation
    that computes the stride and then ignores it cannot pass.
    """
    full = _count_facets_drawn(1)
    strided = _count_facets_drawn(3)
    assert full > 100, f"the full fill drew only {full} polygons"
    assert strided < full, (
        f"facet_stride=3 drew {strided} polygons against {full}: ignored")
    assert strided >= full // 4, (
        f"facet_stride=3 culled too much ({full} -> {strided}); the face is "
        "supposed to lose interior detail, not its surface")


# ── machinery ───────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _restore_modules():
    """Put `sys.modules` back after every test in this file.

    THIS FILE INSTALLS A HAND-BUILT PyQt6, and a Python module left in
    `sys.modules` outlives the test that put it there. Without this, a later
    test that builds a `QTimer` gets this file's three-method fake and fails
    with `no attribute 'setInterval'` — for a reason that has nothing to do
    with what it is testing. The same leak, from the same direction, is why
    the board 05b fixture restores `PyQt6*` and `ui*` together.
    """
    saved = dict(sys.modules)
    real_qt = {name: mod for name, mod in saved.items()
               if name == "PyQt6" or name.startswith("PyQt6.")}
    yield
    for name in [n for n in sys.modules
                 if n == "PyQt6" or n.startswith("PyQt6.")
                 or n.startswith(("ui.face_canvas", "core.avatar"))]:
        del sys.modules[name]
    sys.modules.update(real_qt)

_AVATAR_QT: dict = {}


def _install_avatar_qt() -> None:
    """The smallest PyQt6 that `core/avatar.py` imports at module level.

    NOT `tests/qtstub.py`: that stub is built for `ui/` and falls through to
    the real package for names it does not know, which fails here because this
    machine has the PyQt6 wheel but not the system libraries behind it.
    """
    if _AVATAR_QT:
        return
    import sys
    import types

    def _cls(name):
        return type(name, (), {"__init__": lambda self, *a, **k: None})

    gui = types.ModuleType("PyQt6.QtGui")
    for name in ("QBrush", "QColor", "QLineF", "QLinearGradient",
                 "QPen", "QPointF", "QPolygonF", "QRadialGradient", "QRectF"):
        setattr(gui, name, _cls(name))
    gui.QPainter = type("QPainter", (), {
        "RenderHint": types.SimpleNamespace(Antialiasing=1)})

    class _Color(_cls("QColor")):
        def __init__(self, *a, **k):
            self._rgb = int(a[0].lstrip("#"), 16) if a and isinstance(a[0], str) else 0x204060

        def rgb(self):
            return self._rgb

        def red(self):
            return (self._rgb >> 16) & 255

        def green(self):
            return (self._rgb >> 8) & 255

        def blue(self):
            return self._rgb & 255

        def alpha(self):
            return 255

        def setAlpha(self, _a):
            pass

        def lighter(self, *_a):
            return self

    class _Brush(_cls("QBrush")):
        def __init__(self, *a, **k):
            self._c = a[0] if a else _Color()

        def color(self):
            return self._c

    gui.QColor = _Color
    gui.QBrush = _Brush
    core = types.ModuleType("PyQt6.QtCore")
    core.QLineF = gui.QLineF
    core.QPointF = gui.QPointF
    core.QRectF = gui.QRectF
    core.Qt = types.SimpleNamespace(
        PenStyle=types.SimpleNamespace(NoPen=0),
        BrushStyle=types.SimpleNamespace(NoBrush=0, SolidPattern=1))
    sys.modules["PyQt6"] = types.ModuleType("PyQt6")
    sys.modules["PyQt6.QtGui"] = gui
    sys.modules["PyQt6.QtCore"] = core
    _AVATAR_QT.update({"gui": gui, "core": core, "Qt": core.Qt})




def _count_facets_drawn(facet_stride: int) -> int:
    """How many triangles one solid surface pass asks Qt to draw.

    `core/avatar.py` imports PyQt6 at module level, so the stub goes in first.
    This machine has the wheel but not the system libraries Qt needs.
    """
    import numpy as np

    _install_avatar_qt()
    from core.avatar import HoloAvatar

    calls = {"n": 0}

    class _Painter:
        RenderHint = types.SimpleNamespace(Antialiasing=1)

        def setRenderHint(self, *a):
            pass

        def setPen(self, *a):
            pass

        def setBrush(self, *a):
            pass

        def drawPolygon(self, *a):
            calls["n"] += 1

    avatar = HoloAvatar()
    verts = avatar._v0
    # A REAL projection of the real mesh. Random or linspace coordinates put
    # every facet at ~0 area, the painter's own culling drops them all, and the
    # test then measures nothing — which is exactly how the first version of
    # this test read "0 polygons" and still passed its shape assertions.
    cam_d = 3.2
    w = np.maximum(cam_d - verts[:, 2], 0.35)
    k = (cam_d / w) * 60.0
    xs = 100.0 + verts[:, 0] * k
    ys = 100.0 - verts[:, 1] * k
    avatar._paint_surface(
        _Painter(), xs, ys, avatar._n0, verts,
        _Colour(), _Colour(), _Colour(), 1.0,
        smooth=True, facet_stride=facet_stride)
    return calls["n"]


class _Colour:
    """The three colours the table is built from, without importing Qt."""

    def __init__(self, rgb=0x112233):
        self._rgb = rgb

    def rgb(self):
        return self._rgb

    def red(self):
        return (self._rgb >> 16) & 255

    def green(self):
        return (self._rgb >> 8) & 255

    def blue(self):
        return self._rgb & 255

    def alpha(self):
        return 255

    def setAlpha(self, a):
        pass



def test_every_surface_in_start_interface_is_guarded():
    """`start_interface` runs on the Qt thread BEFORE `exec()`.

    An exception that escapes it kills the process with a tray icon already on
    the taskbar — Qt paints the icon synchronously in `show()` — and no event
    loop behind it. To the user that is "the app hung": the icon is there and
    nothing it offers works. Every surface call must therefore be inside a
    `try`, including the voice overlay and the summon chord, which were not.
    """
    source = (ROOT / "ui" / "lifecycle.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    fn = next(n for n in tree.body
              if isinstance(n, ast.FunctionDef) and n.name == "start_interface")
    guarded = set()
    for node in ast.walk(fn):
        if isinstance(node, ast.Try):
            for child in ast.walk(node):
                if isinstance(child, ast.Call) and isinstance(child.func, ast.Name):
                    if child.func.id.startswith("start_"):
                        guarded.add(child.func.id)
    bare = {n.func.id for n in ast.walk(fn)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
            and n.func.id.startswith("start_")} - guarded
    assert bare == set(), (
        "these surface starts can escape start_interface and kill startup: "
        f"{sorted(bare)}")


def test_the_widget_asks_for_the_strided_fill_while_idle():
    """`paintEvent` must pass `IDLE_FACET_STRIDE` when the face is not speaking.

    WHY THIS EXISTS SEPARATELY FROM THE SURFACE TEST
        The surface test proves the stride WORKS. This one proves the widget
        USES it — and it drives `paintEvent` with a recording painter rather
        than grepping for `facet_stride=` in the source, because a mutation
        that replaced the expression with the constant `1` would keep the grep
        green while the idle face went back to 893 polygons a frame.
    """
    seen = []

    face_canvas = _load_face_canvas(seen)
    canvas = _build_face_canvas(face_canvas)

    # `_paint` returns early on a degenerate size, so the widget has to look
    # like a real one before a frame means anything.
    canvas.width = lambda: 200
    canvas.height = lambda: 200
    canvas.speaking = False
    canvas.paintEvent(None)
    canvas.speaking = True
    canvas.paintEvent(None)

    assert len(seen) == 2, f"paintEvent did not reach the avatar: {seen}"
    assert seen[0] == face_canvas.IDLE_FACET_STRIDE, (
        f"an idle face asked for stride {seen[0]} — that is the full mesh, "
        "893 polygons per frame, which is what blocked the Qt thread")
    assert seen[1] == 1, (
        f"a speaking face asked for stride {seen[1]}; the mouth needs every "
        "facet")


def _load_face_canvas(seen):
    """`ui.face_canvas` with the avatar replaced by one that records strides."""
    import sys
    import types

    for name in [n for n in sys.modules
                 if n.startswith(("ui.face_canvas", "PyQt6",
                                  "core.avatar"))]:
        del sys.modules[name]
    # install_qt() refuses to overwrite a package it thinks is already real, so
    # the purge above has to happen before it is called, not after.

    class _Avatar:
        def step(self, *a, **k):
            pass

        def paint(self, *a, **k):
            seen.append(k.get("facet_stride"))

    stub = types.ModuleType("core.avatar")
    stub.HoloAvatar = _Avatar
    sys.modules["core.avatar"] = stub
    # NOT `tests/qtstub.install_qt()`: it sees a real PyQt6 in a machine that
    # has the wheel and defers to it, and this machine has the wheel without
    # the system libraries. This test needs a package it fully controls.
    _install_minimal_qt()
    from ui import face_canvas
    return face_canvas


def _install_minimal_qt() -> None:
    """Just enough PyQt6 for `ui/face_canvas.py` to build a widget."""
    import sys
    import types

    class _Widget:
        def __init__(self, *a, **k):
            self._attrs = {}

        def setAttribute(self, *a):
            pass

        def setGeometry(self, *a):
            pass

        def setMinimumSize(self, *a):
            pass

        def width(self):
            return 200

        def height(self):
            return 200

        def update(self):
            pass

        def isVisible(self):
            return False

        def setParent(self, *a):
            pass

    class _Timer:
        def __init__(self, *a, **k):
            self.timeout = types.SimpleNamespace(connect=lambda *a, **k: None)

        def start(self, *a):
            pass

        def stop(self):
            pass

    class _Painter:
        RenderHint = types.SimpleNamespace(Antialiasing=1)

        def __init__(self, *a, **k):
            pass

        def setRenderHint(self, *a):
            pass

        def end(self):
            pass

    class _Color:
        def __init__(self, *a, **k):
            pass

        def setAlpha(self, _a):
            pass

        def name(self):
            return "#204060"

    gui = types.ModuleType("PyQt6.QtGui")
    gui.QPainter = _Painter
    gui.QColor = _Color
    core = types.ModuleType("PyQt6.QtCore")
    core.QTimer = _Timer
    core.Qt = types.SimpleNamespace(
        WidgetAttribute=types.SimpleNamespace(
            WA_TransparentForMouseEvents=1, WA_NoSystemBackground=2))
    widgets = types.ModuleType("PyQt6.QtWidgets")
    widgets.QWidget = _Widget
    sys.modules["PyQt6"] = types.ModuleType("PyQt6")
    sys.modules["PyQt6.QtGui"] = gui
    sys.modules["PyQt6.QtCore"] = core
    sys.modules["PyQt6.QtWidgets"] = widgets


def _build_face_canvas(face_canvas):
    """A widget from `build_face_canvas`, with Qt answered by the repo stub."""
    widget = face_canvas.build_face_canvas(None)
    widget.width = lambda: 200
    widget.height = lambda: 200
    return widget
