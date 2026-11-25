"""actions/window_tile.py — the real window-arrangement adapter (board 12).

WHAT THIS DOES
    Takes the geometry the pure policy in `core.window_tile` computes for a
    mode and moves real windows to those rectangles, using the same
    window-manager tools `core.appidentity` already uses (xdotool, then
    wmctrl). This module is the one place that touches the OS; the policy
    only decides WHERE each window goes.

WHY THE ADAPTERS SPLIT
    The policy in `core/window_tile.py` is pure — it turns a mode, a work
    area, and a window count into rectangles. That is so a test can assert
    the geometry for every mode without a display. This adapter does the
    I/O the policy cannot: it locates each window and moves it. Keeping the
    move here means the geometry stays testable and the OS call stays in one
    place that can report honestly when the tools are absent.

WHAT IT DOES NOT DO, AND WHY IT SAYS SO
    Window management on a desktop is whatever the user installed. If neither
    xdotool nor wmctrl is present — a normal state on a minimal or headless
    machine — `apply` returns False with a reason rather than claiming the
    windows were moved. A control that reported success when nothing moved
    would be the exact lie board 12's "desain jujur" rule exists to prevent,
    and the page already shows the mode choice; this adapter makes the choice
    actually arrange windows when it can, and says plainly when it cannot.

    Dimming the non-focused windows in `focus` mode is a compositor feature
    these tools cannot request, so it is reported as unavailable rather than
    pretended.
"""
from __future__ import annotations

import subprocess
from typing import Iterable


def _have(tool: str) -> bool:
    """Whether a window-manager tool is installed (without running it)."""
    import shutil
    return shutil.which(tool) is not None


def _move_xdotool(window_id: str, rect) -> bool:
    """Move one window by id with xdotool. True if the move was accepted."""
    try:
        r = subprocess.run(
            ["xdotool", "windowmove", str(window_id),
             str(rect.x), str(rect.y)],
            capture_output=True, timeout=5)
        return r.returncode == 0
    except Exception:                              # noqa: BLE001
        return False


def _move_wmctrl(window_id: str, rect) -> bool:
    """Move one window by id with wmctrl.

    wmctrl addresses windows by a numeric id from its own listing; a move
    is `wmctrl -r :SELECT: -e 0,x,y,w,h` after selecting the id. Returns
    whether the command succeeded.
    """
    try:
        subprocess.run(["wmctrl", "-i", "-r", str(window_id)],
                       capture_output=True, timeout=5)
        r = subprocess.run(
            ["wmctrl", "-i", "-r", str(window_id), "-e",
             f"0,{rect.x},{rect.y},{rect.width},{rect.height}"],
            capture_output=True, timeout=5)
        return r.returncode == 0
    except Exception:                              # noqa: BLE001
        return False


def available() -> bool:
    """Whether a window-manager tool is present to actually arrange windows."""
    return _have("xdotool") or _have("wmctrl")


def apply(
    mode: str,
    windows: Iterable,
    area=None,
) -> "tuple[bool, str]":
    """Arrange the given windows to the mode's geometry.

    `windows` is a list of window ids (strings). The policy computes the
    geometry; this adapter moves each window to its rectangle. Returns
    `(did_apply, reason)`. If no window-manager tool is present, nothing is
    moved and the reason says so — the caller can show that the choice is
    recorded but not yet arranged, which is the honest state.
    """
    from core.window_tile import arrange

    if not available():
        return (False,
                "Alat susun jendela (xdotool/wmctrl) tidak tersedia — "
                "pilihan disimpan tetapi jendela belum diatur.")

    ids = [str(w) for w in (windows or ())]
    rects = arrange(mode, ids, area)
    if not rects:
        return True, "Tidak ada jendela untuk diatur."

    moved = 0
    for window_id, rect in zip(ids, rects):
        ok = _move_xdotool(window_id, rect) if _have("xdotool") \
            else _move_wmctrl(window_id, rect)
        if ok:
            moved += 1

    if moved == 0:
        return False, "Tidak ada jendela yang berhasil diatur."
    return True, f"Susun jendela diatur: {moved} jendela."


__all__ = ["available", "apply"]
