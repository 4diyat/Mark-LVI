"""Where a dropped orb comes to rest — board 4's "menempel ke tepi".

WHY THIS IS A MODULE AND NOT THREE LINES IN THE CANVAS
    A snap is arithmetic about a screen and a window: given the available
    rectangle, where the pointer let go, and how big the window is, decide
    whether an edge is close enough to belong to. That is answerable with four
    numbers and no display, which is the only kind of drag question this repo
    can test. The canvas keeps the pointer, this keeps the rule.

WHAT THE RULE IS, AND WHY IT IS THIS ONE
    `n04()` draws the orb at two more positions, both against an edge, labelled
    "posisi lain · disimpan antar sesi". It does not draw an orb mid-desktop. So:

      - within `EDGE_PX` of a side  -> sit ON that side, at `MARGIN`;
      - otherwise                    -> stay exactly where it was let go.

    The second half matters as much as the first. A snap that fires from the
    middle of the screen makes the drag feel like it is fighting the hand, and
    the user cannot place the orb where they want it at all.

    Off-screen is NOT a special case with its own rule: a drop past the right
    edge is "within EDGE_PX of the right edge" by any measure, so it snaps back
    on. That is why there is no clamp here — a clamp would preserve the mistake,
    parking the orb half outside the screen.

WHAT IT DOES NOT DO
    It does not save anything, move anything, or know about Qt. `orb_place`
    writes the position and `orb_overlay` calls this on release.
"""
from __future__ import annotations

# Board 1's corner margin, reused rather than re-invented: two margins for one
# widget is how the orb lands 24 px from one edge and 12 from another.
MARGIN = 24

# How near an edge a drop has to land to belong to it. 64 px is roughly a
# fingertip at arm's length: close enough to hit on purpose, far enough that the
# middle half of a 1920 px desktop is still the middle.
EDGE_PX = 64


def snap_to_edge(area, x: int, y: int, size: int,
                 edge_px: int = EDGE_PX, margin: int = MARGIN) -> tuple[int, int]:
    """The corner a window of `size` settles at when dropped at (x, y).

    `area` is a screen's available geometry — x()/y()/width()/height(), the same
    shape `corner_anchor` takes. Each AXIS is decided on its own, so a drop near
    the bottom but in the middle does not move sideways.
    """
    left, top = int(area.x()), int(area.y())
    right = left + int(area.width()) - int(size)
    bottom = top + int(area.height()) - int(size)
    near = max(0, int(edge_px))

    out_x = int(x)
    if out_x >= right - near:            # includes every drop past the edge
        out_x = right - margin
    elif out_x <= left + near:
        out_x = left + margin

    out_y = int(y)
    if out_y >= bottom - near:
        out_y = bottom - margin
    elif out_y <= top + near:
        out_y = top + margin

    # NO CLAMP AT THE END, and that is a finding rather than an omission. A
    # clamp was written here first and a mutation test proved it could never
    # change the result: every branch above already lands inside the available
    # rectangle (`right - margin`, `left + margin`, or the drop itself). A line
    # that cannot alter the output is a line no test can fail on, so it is gone
    # rather than kept as reassurance.
    #
    # The one case the branches do NOT cover is a screen smaller than the window
    # plus twice the margin — a 150 px screen — and neither behaviour is right
    # there. `orb_place` only restores a position whose CENTRE is on the screen,
    # so such a position is refused on the next launch either way.
    return (out_x, out_y)


__all__ = ["EDGE_PX", "MARGIN", "snap_to_edge"]
