"""Board 24 — Senyap: the orb shrinks to 18 px, and says so.

WHY THESE TESTS EXIST
    The artboard states the rule in words and then draws the result:

        "Orb menyusut 28 -> 18 px, glow hilang, cincin berubah jadi titik-titik."
        "Alasan: status harus terbaca tanpa warna."

    The code had the second two — focus and quiet both drop the glow, quiet
    draws a dotted ring and dims to alpha 110 — but not the first. Quiet was
    drawn at 14 px, which is not the artboard's 18, and the "Senyap" label the
    artboard writes under the orb did not exist at all.

    A DIM ORB IS NOT A LABELLED ORB. Dimming is a visual difference: it is
    invisible to a screenshot comparison on a dark desktop, to a user with low
    contrast vision, and to anyone who was not looking at the orb at the moment
    it changed. The artboard says the state must be readable WITHOUT colour,
    which is what a word does and an alpha value does not.

    The 14 px was not arbitrary either — it was a plausible-looking number
    written from memory of the artboard rather than from the artboard. That is
    the class of bug this file exists to catch: a magic number that no test
    compares against the drawing.
"""
from __future__ import annotations

from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture()
def qt():
    """The repo's own Qt stub, and BOTH module families put back afterwards.

    WHY THE RESTORE IS THE POINT. This fixture installs `PyQt6.*` into
    `sys.modules` and leaves it there unless it is removed — and a later test
    that expects no Qt at all (`test_shell_setup`'s "with no Qt it says where
    the key goes") then finds a fake `QPainter` and fails for a reason that has
    nothing to do with the code it tests. That is not hypothetical: it is what
    happened, and it only showed up in the full suite because the file order
    changed.

    `tests/test_orb_paint.py` restores only `ui.*`; this one restores `PyQt6`
    too, because this file is run alongside tests that assert its ABSENCE.
    """
    import sys

    from tests import qtstub

    stubs = qtstub.install_qt()
    saved = {k: v for k, v in sys.modules.items()
             if k == "PyQt6" or k.startswith("PyQt6.")
             or k == "ui" or k.startswith("ui.")}
    sys.modules.update(stubs)
    for name in [k for k in sys.modules if k == "ui" or k.startswith("ui.")]:
        sys.modules.pop(name, None)
    try:
        yield
    finally:
        for name in [k for k in sys.modules
                     if k == "PyQt6" or k.startswith("PyQt6.")
                     or k == "ui" or k.startswith("ui.")]:
            sys.modules.pop(name, None)
        sys.modules.update(saved)


# ── 1. the sizes, as the artboard states them ───────────────────────────────

def test_quiet_is_eighteen_not_fourteen():
    """The artboard's own sentence: "Orb menyusut 28 -> 18 px". Both numbers are
    literals in `n08()`, so both are asserted."""
    from ui import orb_paint

    assert orb_paint.RADIUS == 28, "the full orb is the artboard\'s 28"
    assert orb_paint.appearance("quiet").radius == 18, (
        "Senyap draws the orb at 18 px — the artboard says so twice, in the "
        "sentence and in the circle it draws")


def test_quiet_still_drops_the_glow_and_goes_dotted():
    """The other two claims in the same sentence, kept under test so a radius
    change cannot quietly take them with it."""
    look = __import__("ui.orb_paint", fromlist=["appearance"]).appearance("quiet")
    assert look.glow is False, "a faint glow still reads as lit up"
    assert look.dotted is True, "the ring becomes dots"


def test_focus_is_not_quieter_than_quiet():
    """A smaller, fainter orb in Fokus than in Senyap would invert the two
    modes: Fokus still answers, Senyap is the quietest this app goes."""
    from ui import orb_paint

    focus = orb_paint.appearance("focus")
    quiet = orb_paint.appearance("quiet")
    assert quiet.radius <= focus.radius
    assert quiet.alpha <= focus.alpha


def test_the_overlay_box_does_not_shrink_with_the_orb():
    """Board 1\'s 146 px frame is identical in every mode, and `window_size`
    says why: a window that resizes under the cursor moves its own centre and
    the click lands on nothing. The ring shrinks INSIDE a fixed frame."""
    from ui import orb_place

    assert orb_place.window_size("quiet") == orb_place.window_size("active")
    assert orb_place.window_size("quiet") == (orb_place.OVERLAY_PX,) * 2


# ── 2. the label ────────────────────────────────────────────────────────────

def test_the_orb_can_write_a_label_under_itself():
    """`txt(1180, 662, "Senyap", ...)` in the artboard: the mode\'s name, 10 px,
    MUTED, centred under the ring.

    Read from the source because the label is drawn by a painter, and a painter
    needs a real QPainter. Asserting the source is weaker than drawing it — and
    it is what this build can do — so the assertion names the exact call rather
    than "a label exists somewhere".
    """
    from ui import orb_paint

    assert hasattr(orb_paint, "label_for"), (
        "the orb has no way to say which mode it is in — dimming alone is a "
        "difference no screenshot can show on a dark desktop")
    assert orb_paint.label_for("quiet"), "quiet has no label"
    assert orb_paint.label_for("active"), "active has no label"


def test_the_label_is_the_translated_mode_name():
    """Not a new set of words: `ui.panel.mode.*` already exists in both
    catalogues and the tray uses them. A second vocabulary for the same three
    modes is how "Senyap" becomes "Diam" on one surface and stays "Senyap" on
    another."""
    from core import i18n
    from ui import orb_paint

    i18n.reload()
    i18n.set_locale("id")
    try:
        assert orb_paint.label_for("quiet") == "Senyap"
        assert orb_paint.label_for("focus") == "Fokus"
        assert orb_paint.label_for("active") == "Aktif"
    finally:
        i18n.set_locale("en")


def test_an_unknown_mode_gets_the_same_label_as_the_fallback_appearance():
    """`appearance()` falls back to `active` rather than to `quiet`, because a
    hidden orb is indistinguishable from a crashed app. The label must agree
    with the paint — an orb drawn as Aktif under the word "Senyap" is worse than
    either."""
    from ui import orb_paint

    assert orb_paint.label_for("nonsense") == orb_paint.label_for("active")
    assert orb_paint.appearance("nonsense") == orb_paint.appearance("active")


def _recording_painter():
    """A painter that keeps every call, so a test can read what was DRAWN.

    WHY NOT a source check: the first version of these two tests grepped
    `orb_canvas.py` for the string "label_for" and failed against correct code,
    because the canvas passes `label_room` and `paint_ring` does the drawing.
    Asserting the text of a function one hop away from the work is how a test
    passes on a comment and fails on a refactor.
    """
    from PyQt6.QtGui import QPainter

    class Recording(QPainter):
        def __init__(self):
            self.texts = []

        def drawText(self, *a):
            self.texts.append((a,))

        def __getattr__(self, name):
            return lambda *a, **k: None

    return Recording()


def test_the_overlay_draws_the_label_across_every_mode(qt):
    """The whole point: the orb SAINTS its mode. Drive the real `paint_orb`
    with a recording painter and read the words it drew."""
    from core import i18n
    from ui import orb_canvas

    i18n.reload()
    i18n.set_locale("id")
    try:
        for mode, expected in (("quiet", "Senyap"), ("focus", "Fokus"),
                               ("active", "Aktif")):
            painter = _recording_painter()
            orb_canvas.paint_orb(painter, orb_canvas.OVERLAY_PX, mode, "idle")
            drawn = " ".join(str(call[0][2] if len(call[0]) > 2 else "") 
                             for call in painter.texts)
            assert expected in drawn, (
                f"mode {mode!r} drew {painter.texts!r} — no {expected!r} label")
    finally:
        i18n.set_locale("en")


def test_the_label_is_centred_on_the_ring(qt):
    """The text rect is centred on the ring's x, not the window's left edge.
    A caption at x=0 reads as a caption for the desktop, not for the orb."""
    from ui import orb_canvas

    painter = _recording_painter()
    orb_canvas.paint_orb(painter, orb_canvas.OVERLAY_PX, "quiet", "idle")
    assert painter.texts, "nothing was drawn with text at all"
    rect = painter.texts[0][0][0]
    centre = rect.x() + rect.width() / 2.0
    assert abs(centre - orb_canvas.OVERLAY_PX / 2.0) < 1.0, (
        f"label centre {centre} is not the ring centre "
        f"{orb_canvas.OVERLAY_PX / 2.0}")


def test_the_label_sits_below_the_ring_not_over_it():
    """Board 24 draws it under the circle. A caption across the ring would
    obscure the one thing it describes."""
    from ui.orb_paint import appearance, label_y

    look = appearance("quiet")
    y = label_y(73.0, look.radius)
    assert y > 73.0 + look.radius, "the label is inside the ring"
    assert y < 146.0, "the label falls outside the 146 px overlay window"


def test_a_surface_with_no_room_draws_no_caption(qt):
    """The HUD shares `paint_ring`. A 10 px caption drawn over its own content
    is a caption in the way, so the label is opt-in by available height.

    MUTATION-DRIVEN, AND THE FIRST VERSION OF THIS TEST WAS WRONG. It used a
    painter that could not answer `font()`, so it passed for the other reason:
    `draw_label` bailed out on the painter before it ever looked at the room.
    Removing the room check left the test green. This painter CAN draw text, so
    the only thing that can stop the caption is the room.
    """
    from ui import orb_paint

    painter = _recording_painter()
    assert orb_paint.draw_label(painter, 48.0, 48.0, 28.0, "quiet", room=0.0) is False
    assert painter.texts == [], "a caption was drawn with no room for it"

    # and the same painter DOES draw when there is room — otherwise this test
    # would also pass on a `draw_label` that never draws anything.
    assert orb_paint.draw_label(painter, 48.0, 48.0, 28.0, "quiet", room=40.0) is True
    assert painter.texts, "no caption was drawn even with 40 px of room"
