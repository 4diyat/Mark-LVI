"""The list that reaches every board page: "Lainnya".

WHY A LIST AND NOT A ROW OF TABS
    Thirteen pages cannot sit in a 460 px tab strip — the labels would collide at
    about the sixth. A list is what the panel already draws (board 5's quick
    actions, board 6's permission rows), so this page invents no new shape: it is
    the same 72 px row, one per page, with the board's own name on it.

WHY A PAGE AND NOT THE ORB MENU
    The orb's menu is board 4's "menu cepat" and is deliberately short — the
    three presence modes, the two existing pages, Quit. Thirteen more items would
    make it a menu of fifteen, which is not quick and is not what that artboard
    draws. The panel holds the long list instead.

TWO COLUMNS, SIX ROWS. Thirteen pages do not fit one column of eight, and a
scroll inside a 660 px popup is a scroll nobody performs — the same reason the
history page draws four rows rather than a scroll area. Two columns of seven
with the last cell left empty fits thirteen exactly and reads top-down, then
across.
"""
from __future__ import annotations

from ui.tray_pages import GEOMETRY, PALETTES, _at

from ui.page_kit import BODY_TOP, CARD_H, MARGIN, ROW_PITCH, at
from ui.page_registry import PAGES

# Two columns of seven: 13 pages, one cell spare.
COLUMNS = 2
PER_COLUMN = 7
COL_W = 198                     # (412 − 16) / 2
COL_GAP = 16


def cells() -> list[tuple[int, int, int, int]]:
    """(x, y, w, h) for every page cell, in reading order.

    Column-major: the first seven pages fill the left column, the rest the right.
    Row-major was tried and read badly — board 5's list is a single column, so a
    user scanning for a name goes DOWN first, and a row-major grid put every
    other page one step to the right of the name they were reading.
    """
    out = []
    for index in range(len(PAGES)):
        column, row = divmod(index, PER_COLUMN)
        x = MARGIN + column * (COL_W + COL_GAP)
        y = BODY_TOP + row * ROW_PITCH
        out.append((int(x), int(y), int(COL_W), int(CARD_H)))
    return out


def build_more(panel, page) -> None:
    """The page that lists the pages."""
    from PyQt6.QtWidgets import QLabel, QPushButton


    page.hide()
    panel._pages["more"] = page
    g = GEOMETRY

    panel._labels["more_head"] = at(page, QLabel, g["more_head"], "")
    panel._labels["more_sub"] = at(page, QLabel, g["more_sub"], "")

    for (key, label_key, _title, board), rect in zip(PAGES, cells()):
        button = QPushButton("", page)
        button.setGeometry(*rect)
        # The page's own name, and its artboard number: this list is also how a
        # reader checks a page against the sheet, so the number belongs on it.
        panel._labels[f"more_board:{key}"] = _at(
            page, QLabel, rect[0] + 14, rect[1] + 10, rect[2] - 28, 16, "")
        panel._labels[f"more_name:{key}"] = _at(
            page, QLabel, rect[0] + 14, rect[1] + 30, rect[2] - 28, 22, "")
        panel._labels[f"more_name:{key}"].setStyleSheet(
            f"color:{PALETTES['dark']['text']};")
        panel._labels[f"more_board:{key}"].setStyleSheet(
            f"color:{PALETTES['dark']['muted']};")
        button.clicked.connect(
            lambda _checked=False, k=key: panel._call("page", k))
        panel._buttons[f"more:{key}"] = button

    back = QPushButton("", page)
    back.setGeometry(*g["more_back"])
    back.clicked.connect(lambda: panel._call("page", "main"))
    panel._buttons["more_back"] = back


__all__ = ["COLUMNS", "PER_COLUMN", "build_more", "cells"]
