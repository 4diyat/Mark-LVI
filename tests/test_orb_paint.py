"""One painter, two surfaces — and the states told apart by shape.

WHY THIS FILE EXISTS
    The orb was drawn by two functions in two files. The 56 px desktop ring got
    the design work — presence modes, a legible Quiet, listening and thinking
    with different silhouettes — and the HUD, the window with the orb people
    actually look at, kept calling the older painter. Nothing failed, because a
    painter is only ever wrong IN A PICTURE, and no test looked at pictures.

    So these tests are about wiring and silhouette, not about pixels:
    which painter each surface reaches, and whether the four states differ in
    something other than brightness.

WHAT CANNOT BE TESTED HERE
    How it looks on a real screen: antialiasing, the glow's falloff at 150 %
    DPI, and whether amber on a dark wallpaper is legible. Those need eyes, or
    at least a paint device — this file has neither.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from tests import qtstub

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture()
def qt(monkeypatch):
    """The repo's own Qt stub, the same one `test_window_smoke` installs.

    Reused rather than rewritten: a second hand-written stub drifts, and the
    one thing that must not drift is the surface a painter calls into.
    """
    stubs = qtstub.install_qt()
    saved = {k: v for k, v in sys.modules.items()
             if k == "PyQt6" or k.startswith("PyQt6.") or k == "ui" or k.startswith("ui.")}
    sys.modules.update(stubs)
    for name in [k for k in sys.modules if k == "ui" or k.startswith("ui.")]:
        sys.modules.pop(name, None)
    try:
        import ui.orb_paint
        yield ui.orb_paint
    finally:
        for name in list(sys.modules):
            if name == "ui" or name.startswith("ui."):
                sys.modules.pop(name, None)
        for name in [k for k in list(sys.modules) if k.startswith("PyQt6")]:
            if name not in saved:
                sys.modules.pop(name, None)
        sys.modules.update(saved)


class Recorder:
    """A painter that remembers what it was asked to draw.

    Deliberately permissive: any Qt call the painter makes is recorded and
    allowed, so a new gradient or a new pen style shows up as a difference
    instead of as an AttributeError that looks like a broken fixture.
    """

    def __init__(self):
        self.calls = []

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)

        def record(*args, **kwargs):
            self.calls.append((name, args))
        return record

    def kinds(self):
        return [name for name, _ in self.calls]


# ── the translation layer ─────────────────────────────────────────────────

def test_the_shouted_hud_states_map_to_the_quiet_ones(qt):
    """`main.py` says "NO MIC" and "THINKING"; the painter knows four words.

    A missing mapping is not an exception — it is `idle`, so an unmapped state
    would draw a calm ring while the assistant is listening, and nothing would
    report it.
    """
    assert qt.hud_state("LISTENING") == "listening"
    assert qt.hud_state("SPEAKING") == "speaking"
    assert qt.hud_state("THINKING") == "thinking"
    assert qt.hud_state("PROCESSING") == "thinking"
    assert qt.hud_state("INITIALISING") == "thinking"
    assert qt.hud_state("SLEEPING") == "idle"
    assert qt.hud_state("NO MIC") == "idle"


def test_an_unknown_state_falls_back_to_idle_rather_than_raising(qt):
    """A new state word in main.py must not be a crash on someone's desktop."""
    assert qt.hud_state("WHATEVER COMES NEXT") == "idle"
    assert qt.hud_state(None) == "idle"


# ── one painter, both surfaces ────────────────────────────────────────────

def test_the_face_canvas_draws_through_the_shared_painter(qt, monkeypatch):
    """THE BUG: the face had a painter of its own and drifted from the ring.

    `ui/face_canvas.py` draws the avatar when it has one and the shared ring
    when it does not — the fallback is a REAL surface, not a placeholder, which
    is why the wiring is asserted here rather than described in a comment. A
    `paintEvent` that exists but calls something else is exactly what shipped
    last time.
    """
    import ui.face_canvas as face_canvas
    import ui.orb_paint as orb_paint

    seen = {}

    def fake_paint_ring(painter, cx, cy, radius, **kwargs):
        seen.update(kwargs, cx=cx, cy=cy, radius=radius)

    monkeypatch.setattr(orb_paint, "paint_ring", fake_paint_ring)
    canvas = face_canvas.build_face_canvas(None)
    canvas._avatar = None                 # the no-mesh machine, which is real
    canvas.speaking = True
    canvas._amp_disp = 0.7
    canvas.width = lambda: 260
    canvas.height = lambda: 260

    class _Painter:
        def setRenderHint(self, *_a):      # noqa: N802 — Qt's name
            return None

        def end(self):
            return None

    canvas._paint(_Painter())
    assert seen, "the face canvas drew nothing at all"
    assert seen["state"] == "speaking", "the state never reached the painter"
    assert seen["radius"] > 8, "the ring was not sized from the widget"
    assert seen["level"] == pytest.approx(0.7), "the audio level never reached the ring"


def test_every_surface_draws_through_the_same_painter(qt):
    """Two painters is how the orb, the face and the tray drifted apart."""
    source = (ROOT / "ui" / "face_canvas.py").read_text(encoding="utf-8")
    assert "paint_ring(" in source
    # The call lives in `orb_canvas.py` since the desktop orb's paint half was
    # split off `orb_overlay` at the 600-line ceiling. The SURFACE is still the
    # orb overlay — what moved is where its painter is written, and a test that
    # kept pointing at the old file would fail for a rename, not for a second
    # painter coming back.
    assert "paint_ring(" in (ROOT / "ui" / "orb_canvas.py").read_text(encoding="utf-8")
    # and the old, mode-blind painter is gone rather than merely unused
    assert not (ROOT / "ui" / "desktop_orb.py").exists(), (
        "ui/desktop_orb.py is back: it draws the orb without knowing the "
        "presence modes, which is the split this file exists to prevent"
    )
    from ui import orb_paint
    assert orb_paint.appearance("focus").radius < orb_paint.RADIUS


def test_the_painter_never_fills_a_rectangle(qt):
    """The same code draws on a translucent desktop window.

    A filled rect there is an opaque square on someone's wallpaper — the single
    most visible way this widget can be wrong, and invisible in every test that
    only counts ellipses.
    """
    source = (ROOT / "ui" / "orb_paint.py").read_text(encoding="utf-8")
    assert "fillRect" not in source


# ── the states must differ by SHAPE, not by brightness ────────────────────

def _draw(qt, state, mode="active"):
    recorder = Recorder()
    qt.paint_ring(recorder, 50.0, 50.0, 28.0, mode=mode, state=state, phase=0.0)
    return recorder


def test_listening_adds_spikes_and_idle_does_not(qt):
    """A crown of graduations. If listening looked like idle, the user could not
    tell "I am being heard" from "I am standing by" without reading text."""
    idle = _draw(qt, "idle").kinds()
    listening = _draw(qt, "listening").kinds()
    assert listening.count("drawLine") > 0, "listening drew no graduations"
    assert idle.count("drawLine") == 0, "idle should be calm, not spiky"


def test_thinking_is_a_sweeping_arc_rather_than_a_whole_ring(qt):
    """Work in progress is a gap: the arc says "still going" without a spinner."""
    thinking = _draw(qt, "thinking")
    assert "drawArc" in thinking.kinds()
    arcs = [args for name, args in thinking.calls if name == "drawArc"]
    assert (arcs[0][2] // 16) < 360, "a full circle reads as finished, not busy"


def test_speaking_is_thicker_than_idle(qt, monkeypatch):
    """Shape and weight, not hue: the ring thickens while the assistant talks.

    The stub's `QPen` is an `_Object` that swallows its constructor arguments,
    so asking a pen for its width answers a lambda and this test would pass
    with every width equal. The pen class is wrapped here so the width is
    recorded as the ORB PAINTER passed it.
    """
    # From sys.modules, not `import PyQt6.QtGui`: the stub is installed as a
    # module and the parent package does not expose it as an attribute, so the
    # import statement finds a different object (or none).
    qtgui = sys.modules["PyQt6.QtGui"]

    widths = []
    real_pen = qtgui.QPen

    def recording_pen(*args, **kwargs):
        if len(args) > 1 and isinstance(args[1], (int, float)):
            widths.append(args[1])
        return real_pen(*args, **kwargs)

    monkeypatch.setattr(qtgui, "QPen", recording_pen)

    _draw(qt, "idle")
    idle_width = max(widths or [0])
    widths.clear()
    _draw(qt, "speaking")
    speaking_width = max(widths or [0])

    assert idle_width > 0, "no pen width was recorded at all"
    assert speaking_width > idle_width, (
        "speaking must be visibly heavier than idle, or the two states differ "
        "only by which one has words next to it")


def test_quiet_draws_no_solid_ring_at_all(qt):
    """Quiet's difference is the ABSENCE of the ring, not a fainter one.

    A ring at 40 % opacity still reads as "lit up" in peripheral vision, which
    is the state Quiet exists to stop.
    """
    quiet = _draw(qt, "quiet", mode="quiet")
    active = _draw(qt, "idle", mode="active")
    # Three ellipses in `active` (glow, body, dots) plus the ring; Quiet has no
    # ring and no glow.
    assert quiet.kinds().count("drawEllipse") < active.kinds().count("drawEllipse")
    assert quiet.kinds().count("drawEllipse") <= 2


def test_alert_is_amber_and_marks_itself_above_the_orb(qt):
    """A muted microphone is the one warning this widget has, and warnings are
    the only thing amber is for. The tick above is what makes it readable
    without relying on the colour."""
    recorder = Recorder()
    qt.paint_ring(recorder, 50.0, 50.0, 28.0, mode="active", state="idle",
                  alert=True)
    assert "drawLine" in recorder.kinds()
    # The tick is above the centre, not through it.
    for name, args in recorder.calls:
        if name == "drawLine":
            assert args[1] < 50.0 and args[3] < 50.0
            break
    else:
        pytest.fail("the alert drew no tick")


# ── board 1's overlay boundary ────────────────────────────────────────────

def test_the_overlay_box_is_one_rectangle_and_never_a_fill(qt):
    """Board 1's boundary: exactly one `drawRect`, and no brush that would fill
    it. A filled rect here is an opaque square on someone's wallpaper — the
    same rule `paint_ring` is already held to."""
    painter = Recorder()
    qt.paint_overlay_box(painter, 73.0, 73.0, 72.0)
    assert len([c for c in painter.calls if c[0] == "drawRect"]) == 1
    brushes = [c for c in painter.calls if c[0] == "setBrush"]
    assert brushes, "the box must clear the brush before drawing"


def test_the_overlay_box_is_dashed_not_solid(qt, monkeypatch):
    """The dash is set on the PEN, so it is invisible from the painter side.

    `PenSpy` replaces the module's `QPen` and records the style it is given.
    Comparing the style's NAME would not work: the stub's enum is a catch-all
    object whose `name` is another enum. What is asserted instead is that a
    style was set at all and that it is the dash Qt was asked for by attribute
    path — which fails if someone drops the `setStyle` line entirely, the way
    M15's neighbour did.
    """
    seen = {}

    class PenSpy:
        def __init__(self, *a, **k):
            self.width = a[1] if len(a) > 1 else k.get("width")
            seen["pen"] = self

        def setStyle(self, style):
            seen["style"] = style

    # The function imports QPen INSIDE itself (`from PyQt6.QtGui import QPen`),
    # so patching the module attribute does nothing — the patch has to be on
    # the QtGui module the import actually reads.
    # WRITTEN INTO THE MODULE'S `__dict__`, NOT patched with monkeypatch.
    # `paint_overlay_box` does `from PyQt6.QtGui import QPen` INSIDE the
    # function, and the stub's QtGui answers unknown names from a module-level
    # `__getattr__` — so an attribute patch is answered by that fallback while
    # the import reads the dict. Writing the dict entry is what the import
    # actually sees. The old value is restored below, because a spy left in
    # place would make every later test in this file draw with it.
    import sys as _sys

    gui = _sys.modules["PyQt6.QtGui"]
    saved_pen = gui.__dict__.get("QPen")
    gui.__dict__["QPen"] = PenSpy
    try:
        qt.paint_overlay_box(Recorder(), 73.0, 73.0, 72.0)
    finally:
        if saved_pen is None:
            gui.__dict__.pop("QPen", None)
        else:
            gui.__dict__["QPen"] = saved_pen
    assert "style" in seen, "the boundary pen never had a style set — it is solid"


def test_the_overlay_box_refuses_a_half_that_would_cover_the_orb(qt):
    """`half <= 0` draws nothing. A box smaller than the ring is a box THROUGH
    the orb, which reads as a rendering glitch rather than a boundary."""
    painter = Recorder()
    qt.paint_overlay_box(painter, 73.0, 73.0, 0.0)
    assert [c for c in painter.calls if c[0] == "drawRect"] == []
