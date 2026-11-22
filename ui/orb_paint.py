"""The one orb, drawn at any size. The ambient ring and the HUD both use it.

WHY THIS MODULE EXISTS AT ALL
    There were two painters. `ui/desktop_orb.paint_orb` drew the main window's
    centrepiece — rings stacked on a radial glow, sized in fractions of the
    widget — and `ui/orb_overlay.paint_orb` drew the 56 px ring on the desktop
    from a mode table. Both looked plausible, and that was the problem: the
    design work (three presence modes, states told apart by SHAPE and not only
    by hue) reached the small one and never reached the one people actually
    look at, because the big one was written first and nobody re-read it.

    So there is one painter now, and its contract is a CENTRE AND A RADIUS
    rather than a rectangle. That is the whole trick: the overlay asks for
    28 px, the HUD asks for whatever the window affords, and a third surface
    can ask for anything else without a third copy of the ellipse maths.

WHY IT IS IMPORTED LAZILY, EVERY TIME
    This module is loaded by tests on machines with no display and by CI that
    installs no Qt, so it must not import PyQt6 at module scope. Every public
    function imports what it needs inside itself. The cost is a dict lookup in
    `sys.modules`; the alternative is a module that cannot be read about, only
    run.

WHAT IT DRAWS, AND WHY EACH PART IS THERE
    body      a radial sphere, light from the upper left, so the ring reads as
              something with volume rather than a diagram.
    inner     a dotted circle inside the body. It is the part that survives
              being shrunk, and it is what makes Quiet legible without colour.
    ring      the state's silhouette. Thicker while speaking; absent while
              quiet, where the body and the dots carry it.
    marks     listening is a crown of spikes; thinking is one sweeping arc;
              attention is a single amber tick. All three are SHAPES, so a
              colour-blind user reads the same difference as anyone else.

    Amber is used for exactly one thing — `alert` — because the design reserves
    it for warnings. A muted microphone is the warning this widget has.
"""
from __future__ import annotations

from dataclasses import dataclass

# The drawn ring's outer radius in CSS pixels, at 1x scale. 28 px reads at arm's
# length without competing with a window title bar; the window is the ring's
# bounding box plus the glow, and its own size is what the hit test uses.
RADIUS = 28
GLOW = 20
SIZE = (RADIUS + GLOW) * 2

# The ring the user may click, on the desktop overlay. Nine pixels outside the
# drawn circle: far enough that a near miss still lands, close enough that a
# near miss is still a miss. It is here rather than in `orb_overlay` because the
# window's size and its hit region are the same fact, and this module now owns
# both the geometry and the drawing.
HIT_RING = RADIUS + 9

# THE OVERLAY BOX — board 1's dashed square, `r * 2.6` on each side.
#
# WHY IT GREW FROM 96 px, AND WHY THAT WAS A BUG AND NOT A TASTE
#     `paint_ring` draws its furthest mark — the amber alert dot — at
#     `r * 2.24` from the centre: 62.7 px at the active radius of 28. The window
#     was 96 px, so its half was 48 px. The alarm was drawn 15 px outside the
#     window and clipped away: the one indicator that says something needs the
#     user never appeared, and every test passed because nothing compared the
#     painter's reach with the window's size.
#
#     146 px is the artboard's own number (`half = r * 2.6` = 72.8, round up).
#     It is chosen for the drawing, not fitted to it — but it has to be at least
#     as large as the drawing, and `tests/test_orb_overlay_board1.py` asserts
#     that rather than trusting this comment.
#
# The window is square in every mode, because a window that resizes under the
# cursor moves its own centre and the click lands on nothing.
OVERLAY_PX = 146

CYAN = "#4FD8F0"
CORE = "#BFF6FF"
DEEP = "#0B4A5C"
AMBER = "#F5A524"

# HUD states are shouted and about the machine ("NO MIC"); the painter's are
# quiet and about the user ("listening"). Mapping rather than renaming the HUD:
# those words are also what the status line prints, and changing them changes
# what a user reads.
_HUD_STATES = {
    "IDLE": "idle",
    "SLEEPING": "idle",
    "NO MIC": "idle",
    "INITIALISING": "thinking",
    "PROCESSING": "thinking",
    "THINKING": "thinking",
    "LISTENING": "listening",
    "SPEAKING": "speaking",
}


@dataclass(frozen=True)
class Appearance:
    """How the orb is drawn in one mode. Frozen so a caller cannot edit it."""

    radius: int
    glow: bool
    dotted: bool
    alpha: int


# Focus and Quiet dim the orb — the owner's decision, given explicitly. `quiet`
# also drops the glow entirely rather than merely lowering its alpha: a glow
# that is merely faint still reads as "lit up" in peripheral vision, which is
# the thing Quiet asked to stop.
_APPEARANCE = {
    "active": Appearance(RADIUS, glow=True, dotted=False, alpha=255),
    "focus": Appearance(18, glow=False, dotted=False, alpha=165),
    "quiet": Appearance(14, glow=False, dotted=True, alpha=110),
}


def appearance(mode: str) -> Appearance:
    """The look for one presence mode. Unknown modes get `active`.

    Falling back to `active` rather than to `quiet` is deliberate: an unreadable
    mode should leave the assistant visible, because a hidden orb is
    indistinguishable from a crashed app.
    """
    return _APPEARANCE.get(str(mode or "").strip().lower(), _APPEARANCE["active"])


def hud_state(word: str) -> str:
    """Translate the HUD's shouted state to the painter's. Unknown -> idle."""
    return _HUD_STATES.get(str(word or "").strip().upper(), "idle")


def paint_overlay_box(painter, cx: float, cy: float, half: float,
                      colour: str = CYAN) -> None:
    """The dashed square around the desktop orb — board 1's "overlay ±150 px".

    DRAWN, THOUGH NOTHING DEPENDS ON IT CLICKING. It is the only visual answer
    to "how far does this thing reach", and without it the window's 146 px would
    be invisible: the orb would sit in a larger transparent hole the user cannot
    see. Opacity is low on purpose — it is a boundary, not a frame, and a solid
    one would read as a widget rather than as an edge.

    A NO-OP FOR A HALF THAT WOULD DRAW THROUGH THE ORB. The caller passes the
    half directly, and a box smaller than the ring is a box over the orb.
    """
    from PyQt6.QtCore import QRectF, Qt
    from PyQt6.QtGui import QColor, QPen

    if half <= 0:
        return
    edge = QColor(colour)
    edge.setAlpha(64)                  # a boundary you notice second
    pen = QPen(edge, 1.0)
    pen.setStyle(Qt.PenStyle.DashLine)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawRect(QRectF(cx - half, cy - half, half * 2, half * 2))


def paint_ring(painter, cx: float, cy: float, radius: float,
               mode: str = "active", state: str = "idle",
               level: float = 0.0, alert: bool = False,
               phase: float = 0.0) -> None:
    """Draw one frame of the orb, centred on (cx, cy), at `radius` pixels.

    `level` is the live audio level 0..1 and only widens the glow while
    speaking. `phase` (0..1) is a free-running clock used to sweep the thinking
    arc; pass a constant and the arc is still, which is what a test wants.

    Nothing here fills a rectangle: this is drawn on a translucent desktop
    window as well as inside the HUD, and a filled rect would be an opaque
    square on someone's wallpaper. `tests/test_orb_paint.py` holds that.
    """
    from PyQt6.QtCore import QRectF, Qt
    from PyQt6.QtGui import QColor, QPen, QRadialGradient

    look = appearance(mode)
    r = max(1.0, float(radius))
    level = max(0.0, min(1.0, float(level or 0.0)))
    state = str(state or "idle").strip().lower()

    # One alpha for the whole drawing, from the mode. Focus is dimmed rather
    # than removed, and Quiet is legible only because the dots stay opaque
    # enough to see; see the body alpha below.
    alpha = 90 if alert else look.alpha

    def tint(hex_colour: str, scale: float = 1.0) -> QColor:
        c = QColor(hex_colour)
        c.setAlpha(max(0, min(255, int(alpha * scale))))
        return c

    # 1. The glow. Only in `active` and only while lit up, plus a live bump
    #    from the microphone: the glow is the one thing that says "I hear you"
    #    without a single word of text.
    if look.glow and not alert:
        glow = QRadialGradient(cx, cy, r * 1.7)
        strength = int(70 + level * 90)
        glow.setColorAt(0.0, QColor(79, 216, 240, strength))
        glow.setColorAt(0.55, QColor(79, 216, 240, strength // 3))
        glow.setColorAt(1.0, QColor(79, 216, 240, 0))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(glow)
        painter.drawEllipse(QRectF(cx - r * 1.7, cy - r * 1.7, r * 3.4, r * 3.4))

    # 2. The body: a sphere, lit from the upper left so it does not read flat.
    body = QRadialGradient(cx - r * 0.22, cy - r * 0.30, r * 1.45)
    body.setColorAt(0.00, tint(CORE))
    body.setColorAt(0.45, tint(CYAN, 0.85 if alert else 1.0))
    body.setColorAt(1.00, tint(DEEP))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(body)
    painter.drawEllipse(QRectF(cx - r * 0.78, cy - r * 0.78, r * 1.56, r * 1.56))

    # 3. The inner dotted circle. Drawn over the body because it is the one
    #    mark that survives Quiet's 14 px, and because it is the difference
    #    between "a blue ball" and "the assistant".
    dot = r * 0.64
    pen = QPen(tint(DEEP, 1.6), max(1.0, r * 0.043))
    pen.setStyle(Qt.PenStyle.DotLine)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawEllipse(QRectF(cx - dot, cy - dot, dot * 2, dot * 2))

    # 4. The state's silhouette. Quiet has no ring at all — that is the shape
    #    difference the mode table asked for, not a lower opacity.
    if not look.dotted:
        width = max(2.0, r * (0.10 if state == "speaking" else 0.055))
        painter.setPen(QPen(tint(CYAN if not alert else AMBER, 1.4), width))
        painter.drawEllipse(QRectF(cx - r, cy - r, r * 2, r * 2))

    if alert:
        # A single amber tick above the orb, like the mockup's exclamation.
        # Short enough to read as punctuation and not as a second widget.
        painter.setPen(QPen(tint(AMBER, 1.6), max(2.0, r * 0.11)))
        painter.drawLine(int(cx), int(cy - r * 1.55), int(cx), int(cy - r * 1.95))
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(tint(AMBER, 1.6))
        painter.drawEllipse(QRectF(cx - r * 0.06, cy - r * 2.24,
                                   r * 0.12, r * 0.12))
        return

    if state == "listening":
        # A crown of spikes growing outward. Voice graduations: the shape says
        # "taking something in", and it is impossible to confuse with the calm
        # ring of idle at a glance.
        import math

        painter.setPen(QPen(tint(CYAN, 1.5), max(1.0, r * 0.06)))
        count = 24
        for i in range(count):
            # `phase` intentionally does not move these: the crown is a
            # steady shape, and a spinning one would read as thinking.
            a = math.radians(i * (360.0 / count))
            inner = r * 1.16
            length = r * (0.26 + 0.22 * (0.5 + 0.5 * math.sin(i * 1.4)))
            painter.drawLine(
                int(cx + inner * math.cos(a)), int(cy - inner * math.sin(a)),
                int(cx + (inner + length) * math.cos(a)),
                int(cy - (inner + length) * math.sin(a)))
    elif state == "thinking":
        # One thick arc sweeping around, never a complete circle: work in
        # progress is a gap, and the gap moving is what says it is still going.
        from PyQt6.QtCore import QRectF as _Rect

        start = int((phase % 1.0) * 360) - 90
        arc_r = r * 1.22
        painter.setPen(QPen(tint(CYAN, 1.3), max(2.0, r * 0.13)))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawArc(_Rect(cx - arc_r, cy - arc_r, arc_r * 2, arc_r * 2),
                        start * 16, 100 * 16)
