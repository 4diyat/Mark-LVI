"""The two rows that give the assistant reach BEYOND this program.

WHY THEY ARE BUILT TOGETHER
    `ui/file_access_row.py` lets it work in folders you name; `ui/camera_row.py`
    lets it look at the room. Different features, one category: each is a
    permission the user grants, each is off by default, and neither can be
    granted by the assistant itself. Building them from one place is what keeps
    them adjacent in the drawer — a reader scrolling past one reads the other,
    which is the point of putting the two questions side by side.

WHY A SEPARATE MODULE FOR ONE FUNCTION
    `ui/window.py` has a hard ceiling (`tests/test_ui_split.py`) and it is at
    it. Two imports and two assignments there is +4 lines the file does not
    have; this is +2, and the next permission row costs zero.
"""
from __future__ import annotations

from ui.camera_row import build_camera_button
from ui.file_access_row import build_file_access_button


def build_permission_rows(layout, row_factory):
    """Add both rows to `layout`. Returns (file_access_button, camera_button)."""
    return (build_file_access_button(layout, row_factory),
            build_camera_button(layout, row_factory))


__all__ = ["build_permission_rows"]
