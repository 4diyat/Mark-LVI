"""Which pages the panel has, and what each one is for. No Qt.

WHY THIS IS A MODULE AND NOT THREE LINES IN `tray_pages`
    Thirteen artboards became pages in one round. Written the obvious way, each
    one would be a constant in `tray_pages`, a branch in the builder, a branch
    in the painter and a line in the quick menu — four places to forget. The
    registry below is the ONE list: adding a page means adding a row here, and
    the tests that check the panel can reach every page read this list rather
    than a copy of it.

ORDER IS THE ORDER THE MENU SHOWS, and it is deliberate: what a user changes
most (memory, routines) before what they change once (language, plugins) before
the pages that only describe (brand, gesture map).
"""
from __future__ import annotations

# key, i18n key for the menu label, i18n key for the page title, board number
#
# THE BOARD IS PART OF THE ROW. Every page is an artboard, and `NOT-IN-MOCKUP.md`
# is generated against board numbers; a page that lost its number would be a page
# nobody could check against the sheet.
PAGES = (
    ("memory",      "ui.page.memory.name",      "ui.page.memory.title",      9),
    ("memory_one",  "ui.page.memory_one.name",  "ui.page.memory_one.title",  10),
    ("routines",    "ui.page.routines.name",    "ui.page.routines.title",    11),
    ("tools",       "ui.page.tools.name",       "ui.page.tools.title",       12),
    ("security",    "ui.page.security.name",    "ui.page.security.title",    14),
    ("access",      "ui.page.access.name",      "ui.page.access.title",      15),
    ("plugins",     "ui.page.plugins.name",     "ui.page.plugins.title",     16),
    ("light",       "ui.page.light.name",       "ui.page.light.title",       18),
    ("gestures",    "ui.page.gestures.name",    "ui.page.gestures.title",    19),
    ("brand",       "ui.page.brand.name",       "ui.page.brand.title",       21),
    ("installer",   "ui.page.installer.name",   "ui.page.installer.title",   22),
    ("consent",     "ui.page.consent.name",     "ui.page.consent.title",      7),
    ("help",        "ui.page.help.name",        "ui.page.help.title",        13),
)

PAGE_KEYS = tuple(row[0] for row in PAGES)
PAGE_BOARD = {row[0]: row[3] for row in PAGES}
PAGE_LABEL = {row[0]: row[1] for row in PAGES}
PAGE_TITLE = {row[0]: row[2] for row in PAGES}

# The three pages that existed before this registry, kept out of it on purpose:
# they are the panel's own front door, not entries in the more-list.
CORE_PAGES = ("main", "history", "privacy")

# `more` is the list itself. It is a page and `set_page` must accept it, but it
# is not an ENTRY in its own list — a row that opens the page you are on is a
# row that does nothing.
ALL_PAGES = CORE_PAGES + ("more",) + PAGE_KEYS


def board_page(board: int) -> str:
    """The page that implements one artboard, or "" when none does.

    Used by the docs test: every board in `NOT-IN-MOCKUP.md`'s built table must
    name a page that exists here, so a deleted page cannot leave a built claim
    behind.
    """
    for page, num in PAGE_BOARD.items():
        if num == int(board):
            return page
    return ""


__all__ = ["ALL_PAGES", "CORE_PAGES", "PAGES", "PAGE_BOARD", "PAGE_KEYS",
           "PAGE_LABEL", "PAGE_TITLE", "board_page"]
