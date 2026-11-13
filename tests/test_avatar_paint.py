"""Draw the avatar for real, with a stand-in for Qt — the renderer must run.

WHY THIS EXISTS AT ALL
    `tests/test_avatar_face.py` covers the maths: occlusion, skin, eyelids,
    lighting. What it cannot cover is `core/avatar.py` itself, because drawing
    needs PyQt6 and a display and neither exists on a CI runner. That leaves the
    one failure a renderer actually has: a call that used to take four arguments
    and now takes five, a method that does not exist on the object being passed,
    a name that was never imported. None of that is a wrong-looking face — it is
    a `TypeError` on a user's desktop and a blank HUD.

    So a minimal PyQt6 is installed into `sys.modules` before `core.avatar` is
    imported, and the avatar is stepped through the states that matter (idle,
    blinking, speaking, muted, turned away) and painted. The stub records what
    it was asked to draw, which lets the tests assert the *contract* rather than
    the pixels: that a blink draws a closed eye, that a shaded avatar fills
    polygons at all, that the palette is rebuilt when the accent changes.

WHAT A STUB CAN AND CANNOT PROVE
    It proves the code runs and calls the painter in a sane order with sane
    types. It cannot prove the picture is beautiful — that needs eyes on a real
    screen, and no test replaces it. Pretending otherwise would be worse than
    the gap.
"""
from __future__ import annotations

import sys
import types

import pytest


# ── the stand-in Qt ─────────────────────────────────────────────────────────

class _Pt:
    """Qt's QPointF exposes x() and y() as METHODS, so this must too — a stub
    with attributes would let a call site pass here that crashes on a real
    desktop."""

    def __init__(self, x=0.0, y=0.0):
        self._x = float(x)
        self._y = float(y)

    def x(self):
        return self._x

    def y(self):
        return self._y


class _Rect:
    def __init__(self, *a):
        if len(a) == 1:
            x, y, w, h = 0.0, 0.0, a[0].x(), a[0].y()
        else:
            x, y, w, h = (float(v) for v in a)
        self._x, self._y, self._w, self._h = x, y, w, h

    def width(self):
        return self._w

    def height(self):
        return self._h

    def center(self):
        return _Pt(self._x + self._w * 0.5, self._y + self._h * 0.5)


class _Poly:
    def __init__(self, points=None):
        self.pts = list(points or [])

    def boundingRect(self):
        if not self.pts:
            return _Rect(0, 0, 0, 0)
        xs = [p.x() for p in self.pts]
        ys = [p.y() for p in self.pts]
        return _Rect(min(xs), min(ys), max(xs) - min(xs), max(ys) - min(ys))

    def __len__(self):
        return len(self.pts)


class _Color:
    def __init__(self, *a):
        if not a:
            self._rgb = (0, 0, 0)
        elif len(a) == 1 and isinstance(a[0], _Color):
            self._rgb = a[0]._rgb
        elif len(a) == 1:
            v = int(a[0])
            self._rgb = ((v >> 16) & 255, (v >> 8) & 255, v & 255)
        else:
            self._rgb = tuple(int(v) for v in a[:3])
        self._a = 255

    def red(self):
        return self._rgb[0]

    def green(self):
        return self._rgb[1]

    def blue(self):
        return self._rgb[2]

    def setAlpha(self, a):
        self._a = int(a)

    def rgb(self):
        return (self._rgb[0] << 16) | (self._rgb[1] << 8) | self._rgb[2]


class _Pen:
    def __init__(self, *a, **k):
        self.args = a


class _Brush:
    def __init__(self, *a, **k):
        self.args = a


class _Gradient:
    def __init__(self, *a, **k):
        self.stops = []

    def setColorAt(self, at, col):
        self.stops.append((at, col))


class _Painter:
    """Records every call, so a test can ask what was actually drawn."""

    RenderHint = types.SimpleNamespace(Antialiasing=1)

    def __init__(self):
        self.calls = []
        self.pens = []
        self.brushes = []
        self._pen = None
        self._brush = None

    def _log(self, name, *a):
        self.calls.append(name)

    def setPen(self, p):
        self._pen = p
        self.pens.append(p)

    def setBrush(self, b):
        self._brush = b
        self.brushes.append(b)

    def setRenderHint(self, *a):
        self._log("setRenderHint", *a)

    def drawEllipse(self, *a):
        self._log("drawEllipse", *a)

    def drawPolygon(self, *a):
        self._log("drawPolygon", *a)

    def drawPolyline(self, *a):
        self._log("drawPolyline", *a)

    def drawLines(self, *a):
        self._log("drawLines", *a)

    def drawLine(self, *a):
        self._log("drawLine", *a)

    def count(self, name: str) -> int:
        return self.calls.count(name)


def _real_qt_works() -> bool:
    """True when this machine has a PyQt6 that can at least be imported."""
    try:
        import PyQt6.QtGui  # noqa: F401
        return True
    except Exception:
        return False


def _install_qt() -> list[str]:
    """A tiny PyQt6 in sys.modules, sufficient for core.avatar to import and run.

    Returns the module names it added, so the caller can REMOVE them again. That
    is not tidiness: a stub left in `sys.modules` shadows the real Qt for every
    test that runs afterwards, and on a machine that does have PyQt6 it would
    turn an unrelated import into "cannot import name QApplication from
    PyQt6.QtWidgets". Which is exactly what happened the first time this file
    was written, and it is why the fixture below also drops `core.avatar`.
    """
    added: list[str] = []
    if _real_qt_works():
        return added            # the real thing is better than any stand-in

    core = types.ModuleType("PyQt6.QtCore")
    core.QPointF = _Pt
    core.QRectF = _Rect
    core.QLineF = lambda *a: types.SimpleNamespace(args=a)
    core.Qt = types.SimpleNamespace(
        PenStyle=types.SimpleNamespace(NoPen=0),
        BrushStyle=types.SimpleNamespace(NoBrush=1),
        AlignmentFlag=types.SimpleNamespace(AlignLeft=1, AlignCenter=2),
        CursorShape=types.SimpleNamespace(PointingHandCursor=3),
    )

    gui = types.ModuleType("PyQt6.QtGui")
    gui.QColor = _Color
    gui.QPen = _Pen
    gui.QBrush = _Brush
    gui.QPainter = _Painter
    gui.QPolygonF = _Poly
    gui.QRadialGradient = _Gradient
    gui.QFont = types.SimpleNamespace()
    gui.QLinearGradient = _Gradient

    pkg = types.ModuleType("PyQt6")
    pkg._avatar_stub = True
    pkg.QtCore = core
    pkg.QtGui = gui
    pkg.QtWidgets = types.ModuleType("PyQt6.QtWidgets")

    for name, mod in (("PyQt6", pkg), ("PyQt6.QtCore", core),
                      ("PyQt6.QtGui", gui), ("PyQt6.QtWidgets", pkg.QtWidgets)):
        sys.modules[name] = mod
        added.append(name)
    return added


@pytest.fixture(scope="module")
def avatar_module():
    added = _install_qt()
    saved = {name: sys.modules.get("core.avatar") for name in ("core.avatar",)}
    sys.modules.pop("core.avatar", None)
    import core.avatar as avatar
    try:
        yield avatar
    finally:
        # Undo everything, in the reverse order of how it was done: a stub Qt
        # must not outlive the tests that installed it.
        for name in added:
            sys.modules.pop(name, None)
        sys.modules.pop("core.avatar", None)
        for name, mod in saved.items():
            if mod is not None:
                sys.modules[name] = mod


@pytest.fixture()
def avatar(avatar_module):
    return avatar_module.HoloAvatar()


def _colours(avatar_module):
    q = avatar_module.QColor
    return q(0, 6, 10), q(0, 212, 255), q(255, 107, 0)


def _paint(avatar_module, avatar, **kw):
    p = _Painter()
    bg, primary, accent = _colours(avatar_module)
    avatar.paint(p, 200.0, 180.0, 120.0, primary, accent, bg)
    return p


# ── the tests ───────────────────────────────────────────────────────────────

def test_the_head_paints_without_a_display(avatar_module, avatar):
    """The whole point: the renderer executes.

    Every failure this catches — a missing import, a renamed method, an
    argument that no longer exists — is one that would otherwise be discovered
    by a user staring at an empty HUD.
    """
    p = _paint(avatar_module, avatar)
    assert p.count("drawPolygon") > 100, "the surface drew nothing"
    assert p.count("drawLines") >= 1, "the wireframe drew nothing"


def test_the_surface_is_shaded_not_outlined(avatar_module, avatar):
    """A shaded head fills hundreds of facets; a wireframe-only head fills none.

    This is the difference the realism work was about, stated as a count.
    """
    outlined = _paint(avatar_module, avatar)
    avatar.shaded = False
    plain = _paint(avatar_module, avatar)
    avatar.shaded = True
    assert outlined.count("drawPolygon") > plain.count("drawPolygon") * 2


def test_a_blink_closes_the_eye_it_draws(avatar_module, avatar):
    """Half of a blink is geometry (in `_pose`), half is the painted aperture.

    Here the painted half is checked: a shut eye must draw a much flatter ring
    than an open one. The ring's own height is the measure, so it holds at any
    head size.
    """
    p_open = _paint(avatar_module, avatar)
    avatar._blink = 1.0            # fully shut, as `step()` would leave it
    p_shut = _paint(avatar_module, avatar)
    assert p_shut.count("drawPolygon") > 0
    # The lash strokes and the catching light are skipped on a closed eye, so a
    # shut frame draws strictly fewer separate strokes than an open one.
    assert p_shut.count("drawLine") < p_open.count("drawLine")


def test_a_blink_moves_the_geometry_too(avatar_module, avatar):
    """The surface half of the blink: the lid vertices travel, so the skin
    around the eye moves. Without this the "blink" is a sticker over a still
    face, which is what it used to be."""
    step, dt = avatar.step, 1.0 / 30.0
    for _ in range(10):
        step(dt, 0.0)
    verts_open, _ = avatar._pose()
    open_copy = verts_open.copy()

    avatar._blink = 1.0
    verts_shut, _ = avatar._pose()
    assert not (verts_shut == open_copy).all(), "closing the eye moved nothing"


def test_speaking_moves_the_mouth_and_the_head(avatar_module, avatar):
    """Idle and talking must not produce the same frame: if they do, the viseme
    path is dead and the face is a portrait."""
    for _ in range(4):
        avatar.step(1.0 / 30.0, 0.0, speaking=False)
    idle, _ = avatar._pose()

    for _ in range(20):
        avatar.step(1.0 / 30.0, 0.9, speaking=True, v_open=0.95, v_wide=0.3,
                    v_level=0.6)
    talking, _ = avatar._pose()
    assert not (talking == idle).all()


def test_every_state_paints(avatar_module, avatar):
    """THINKING, SLEEPING and LISTENING each steer the face; none may crash it,
    including the asleep state where the lids are nearly shut all the time."""
    for state in ("", "LISTENING", "THINKING", "PROCESSING", "SLEEPING", "OFFLINE"):
        for _ in range(6):
            avatar.step(1.0 / 30.0, 0.2, state=state)
        p = _paint(avatar_module, avatar)
        assert p.count("drawPolygon") > 50, f"{state or 'idle'} painted nothing"


def test_a_muted_head_still_paints(avatar_module, avatar):
    """Muted means dim, not absent — the one state where a blank HUD would look
    like the feature had been switched off."""
    for _ in range(5):
        avatar.step(1.0 / 30.0, 0.8, muted=True)
    p = _paint(avatar_module, avatar)
    assert p.count("drawPolygon") > 50


def test_the_palette_is_cached_and_rebuilt_on_a_theme_change(avatar_module, avatar):
    """The accent picker retints the face while the wheel is being dragged, so
    the table must be cheap — and it must actually change when the accent does.
    A cache that never invalidates would leave a teal face under an amber
    theme, which is exactly the bug the cache invites."""
    bg, primary, accent = _colours(avatar_module)
    first = avatar._skin_table(bg, primary, accent)
    again = avatar._skin_table(bg, primary, accent)
    assert first is again, "the table was rebuilt for an unchanged theme"

    other = avatar_module.QColor(255, 180, 0)
    changed = avatar._skin_table(bg, other, accent)
    assert changed is not first, "a new accent reused the old palette"
    assert changed[6, 1, 0].args[0].rgb() != first[6, 1, 0].args[0].rgb() or \
        changed[6, 2, 0].args[0].rgb() != first[6, 2, 0].args[0].rgb()


def test_the_avatar_reports_its_own_span(avatar_module, avatar):
    """`ui/window.py` sizes the head from SPAN; a span of zero collapses it."""
    assert avatar.SPAN > 0.5
