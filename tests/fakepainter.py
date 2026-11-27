"""A painter that draws nothing, made of PyQt6's real classes where it can be.

WHY THIS EXISTS, AND WHY `tests/qtstub.py` IS NOT IT
    `qtstub` replaces `PyQt6` in `sys.modules`, which is right for the widgets
    — there is no `QWidget` without `libxkbcommon`. But there is no `QWidget`
    needed to check a PAINTER, and a fake painter that invented `fillRect`
    would agree with any bug in `ui/voice_paint`. So this file prefers the real
    `QPainterPath`, `QColor`, `QPen`, `QRectF` and `QPointF` (they are pure
    `QtGui`/`QtCore` in PyQt6 wheels once loaded) and records every call.

    When even those cannot be imported — the sandbox has no
    `libxkbcommon.so.0`, so `QtGui` fails as a whole — the shapes below stand in,
    with the same signatures and the same *reasonable* argument handling. A
    drawing call that would raise on a real painter still raises here.

WHY IT RECORDS RATHER THAN ASSERTS
    The interesting question is not "did `drawText` get called" but "WHICH words,
    where, with which colour". Recording the calls makes that question a
    comparison of values a test can read, and keeps the expectations in the test
    file next to the reason they matter.
"""
from __future__ import annotations

import sys
import types


def _real_qt_gui():
    """(QColor, QPen, QPointF, QRectF, QRadialGradient, QPainterPath) or None.

    Returns None when `QtGui` cannot load — on a machine with no display that is
    an ImportError for a missing shared library, not a missing package.
    """
    try:
        from PyQt6.QtCore import QPointF, QRectF
        from PyQt6.QtGui import QColor, QPainterPath, QPen, QRadialGradient

        return QColor, QPen, QPointF, QRectF, QRadialGradient, QPainterPath
    except Exception:                               # noqa: BLE001
        return None


# ── stand-ins, used only when the real classes cannot load ──────────────────

class _Colour:
    def __init__(self, value="#" + "0" * 8, alpha=None):
        self.value = value if isinstance(value, str) else str(value)
        self.alpha = 1.0

    def setAlphaF(self, alpha):
        self.alpha = float(alpha)

    def alphaF(self):
        return self.alpha

    def name(self):
        return self.value

    def __repr__(self):
        return f"_Colour({self.value!r}, a={self.alpha})"


class _Pen:
    def __init__(self, colour=None, width=None):
        self.colour = colour
        self.width = width
        self.cap = None
        self.join = None
        self.dash = None

    def setWidth(self, width):
        self.width = width

    def setCapStyle(self, cap):
        self.cap = cap

    def setJoinStyle(self, join):
        self.join = join

    def setStyle(self, style):
        self.dash = style


class _Point:
    def __init__(self, x=0.0, y=0.0):
        self._x, self._y = float(x), float(y)

    def x(self):
        return self._x

    def y(self):
        return self._y

    def __iter__(self):
        return iter((self._x, self._y))

    def __repr__(self):
        return f"_Point({self._x:g}, {self._y:g})"


class _Rect:
    def __init__(self, x=0.0, y=0.0, w=0.0, h=0.0):
        self.x, self.y, self.w, self.h = float(x), float(y), float(w), float(h)

    def __repr__(self):
        return f"_Rect({self.x:g}, {self.y:g}, {self.w:g}, {self.h:g})"


class _Gradient:
    def __init__(self, centre=None, radius=0.0):
        self.centre = centre
        self.radius = radius
        self.stops = []

    def setColorAt(self, where, colour):
        self.stops.append((float(where), colour))


class _Path:
    def __init__(self):
        self.commands = []

    def moveTo(self, *xy):
        self.commands.append(("move", xy))

    def lineTo(self, *xy):
        self.commands.append(("line", xy))

    def quadTo(self, *args):
        self.commands.append(("quad", args))

    def cubicTo(self, *args):
        self.commands.append(("cubic", args))

    def closeSubpath(self):
        self.commands.append(("close", ()))

    def arcTo(self, *args):
        self.commands.append(("arc", args))


class _Font:
    def __init__(self):
        self.size = 0

    def setPixelSize(self, size):
        self.size = int(size)

    def pixelSize(self):
        return self.size

    def __repr__(self):
        return f"_Font({self.size}px)"


class _Metrics:
    def horizontalAdvance(self, text):
        return len(text) * 7


class RecordingPainter:
    """Every call `ui/voice_paint` makes, in order, with its arguments.

    `calls` is a list of `(name, args, kwargs)`; the convenience selectors at
    the bottom answer the three questions the tests ask most.
    """

    def __init__(self):
        self.calls = []
        self._pen = None
        self._brush = None
        self._font = _Font()

    # every setter is recorded too: the colour of a line is part of the frame
    def _add(self, name, *args, **kwargs):
        self.calls.append((name, args, kwargs))

    def setPen(self, value):
        self._pen = value
        self._add("setPen", value)

    def pen(self):
        return self._pen

    def setBrush(self, value):
        self._brush = value
        self._add("setBrush", value)

    def brush(self):
        return self._brush

    def setFont(self, font):
        self._font = font
        self._add("setFont", font)

    def font(self):
        return self._font

    def fontMetrics(self):
        return _Metrics()

    def fillRect(self, *args):
        self._add("fillRect", *args)

    def drawRect(self, *args):
        self._add("drawRect", *args)

    def drawRoundedRect(self, *args):
        self._add("drawRoundedRect", *args)

    def drawEllipse(self, *args):
        self._add("drawEllipse", *args)

    def drawLine(self, *args):
        self._add("drawLine", *args)

    def drawText(self, *args):
        self._add("drawText", *args)

    def drawPath(self, *args):
        self._add("drawPath", *args)

    def setRenderHint(self, *args):
        self._add("setRenderHint", *args)

    def setRenderHints(self, *args):
        self._add("setRenderHints", *args)

    def save(self):
        self._add("save")

    def restore(self):
        self._add("restore")

    def end(self):
        self._add("end")

    def translate(self, *args):
        self._add("translate", *args)

    def rotate(self, *args):
        self._add("rotate", *args)

    def scale(self, *args):
        self._add("scale", *args)

    def setOpacity(self, *args):
        self._add("setOpacity", *args)

    # ── what the tests ask ──────────────────────────────────────────────────

    def texts(self) -> list[str]:
        """Every string drawn, in the order it reached the screen."""
        out = []
        for name, args, _ in self.calls:
            if name == "drawText" and args and isinstance(args[-1], str):
                out.append(args[-1])
        return out

    def drawn_words(self) -> str:
        return " | ".join(self.texts())

    def names(self) -> list[str]:
        return [name for name, _, _ in self.calls]


_FAKE_QT_GUI = None


def install_fake_qt_gui() -> types.ModuleType:
    """Register a minimal `PyQt6.QtGui`/`QtCore` when the real one cannot load.

    Returns the fake `QtGui` module. Idempotent: the second call returns the
    same module rather than replacing classes that painters already hold.
    """
    global _FAKE_QT_GUI
    if _FAKE_QT_GUI is not None:
        return _FAKE_QT_GUI

    core = types.ModuleType("PyQt6.QtCore")

    class Qt:                                   # the enums the painters use
        class PenStyle:
            NoPen = 'none'

        class PenCapStyle:
            RoundCap = "round"
            SquareCap = "square"
            FlatCap = "flat"

        class PenJoinStyle:
            RoundJoin = "round"
            BevelJoin = "bevel"

        class BrushStyle:
            NoBrush = "none"
            SolidPattern = "solid"

        class GlobalColor:
            white = "white"
            transparent = "transparent"

    core.Qt = Qt
    core.QPointF = _Point
    core.QRectF = _Rect
    core.QRect = _Rect

    gui = types.ModuleType("PyQt6.QtGui")
    gui.QColor = _Colour
    gui.QPen = _Pen
    gui.QRadialGradient = _Gradient
    gui.QLinearGradient = _Gradient
    gui.QPainterPath = _Path
    gui.QPainter = RecordingPainter
    gui.QFont = _Font

    sys.modules["PyQt6.QtCore"] = core
    sys.modules["PyQt6.QtGui"] = gui
    _FAKE_QT_GUI = gui
    return gui


def qt_or_fake():
    """`(module_name, used_fake)` — for a test that wants to report which it got."""
    real = _real_qt_gui()
    if real is not None:
        return "PyQt6.QtGui", False
    install_fake_qt_gui()
    return "fake", True
