"""Boards 9 and 10 — Memori personal, and one memory in detail.

BOARD 9 DRAWS WHAT JARVIS REMEMBERS, and counts it: "12 hal yang JARVIS ingat".
That number is not decoration, it is a claim about the store, so the header here
reads it from `memory_manager.all_entries_for_ui()` on every paint rather than
counting the rows it happened to draw. The panel holds eight; the header says
twelve and the list says "dan 4 lagi", because a count that matches the visible
rows would be a count of the WIDGETS and not of the memory.

BOARD 10 DRAWS ONE MEMORY: source, confidence, used-by. THE STORE HAS NONE OF
THE THREE. `all_entries_for_ui()` returns category, key, value and `updated` —
faithfully, because those are the only things `update_memory()` writes. The
owner's ruling is that an artboard may only draw what is real, so this page
shows the three fields it has and says, in the place the other three would go,
that they are not recorded. It does not draw "92%" beside anything.

WHY THE DETAIL PAGE TAKES A KEY RATHER THAN AN INDEX
    An index is a position in a list that is re-sorted newest-first on every
    read: delete one memory and every row under it becomes a different memory.
    Clicking the third row and deleting the second would then show — and the
    next click would delete — something the user never chose. The page holds
    `(category, key)`, which survives the resort.
"""
from __future__ import annotations

from ui.tray_pages import GEOMETRY, PALETTES, _at

from ui.page_kit import (BODY_TOP, CARD_H, CONTENT_W, MARGIN, ROW_PITCH, at,
                         visible_count)
from ui.page_registry import PAGE_TITLE

# How many rows the list page shows before it counts the rest.
LIST_ROWS = visible_count(99)          # measured against the panel, not guessed


def _store():
    """The memory module, or None. A page must open even if the store cannot."""
    try:
        from memory import memory_manager

        return memory_manager
    except Exception as e:                       # noqa: BLE001
        print(f"[JARVIS] Memori tidak terbaca — {type(e).__name__}: {e}")
        return None


def entries() -> list[dict]:
    """Every remembered fact, newest first. Never raises."""
    module = _store()
    if module is None:
        return []
    try:
        return list(module.all_entries_for_ui() or [])
    except Exception as e:                       # noqa: BLE001
        print(f"[JARVIS] Memori tidak terbaca — {type(e).__name__}: {e}")
        return []


def count() -> int:
    """How many facts are stored. The header's number, from the store."""
    return len(entries())


def find(category: str, key: str) -> dict | None:
    """One entry by its identity, or None when it is gone.

    Returns None rather than an empty dict: a page showing a memory that no
    longer exists must be able to say "sudah dihapus", and `{}` would paint a
    card with three blank lines and look like a memory with no value.
    """
    for row in entries():
        if row.get("category") == category and row.get("key") == key:
            return row
    return None


def forget(category: str, key: str) -> tuple[bool, str]:
    """Delete one memory. Returns (did it, the sentence to show).

    THE RETURN IS A PAIR BECAUSE BOTH HALVES MATTER. `forget()` answers with a
    sentence either way, and "Not found: …" is not a success — a page that
    treated any string as success would report deleting something that was
    already gone.
    """
    module = _store()
    if module is None:
        return False, "Memori tidak tersedia"
    try:
        message = str(module.forget(key, category) or "")
    except Exception as e:                       # noqa: BLE001
        return False, f"Gagal menghapus — {type(e).__name__}: {e}"
    return (not message.lower().startswith("not found")), message


def details(category: str, key: str) -> list[tuple[str, str, str]]:
    """Board 10's field list as (label key, value key, the value).

    THE THREE THE STORE DOES NOT HAVE ARE PRESENT AND EMPTY-ON-PURPOSE, so the
    page can draw the label and the sentence that explains the absence. Leaving
    them out would make the page look like the artboard minus three rows, which
    reads as an incomplete page rather than an honest one.
    """
    return [
        ("ui.page.memory.field.category", "ui.page.memory.field.category.note",
         str(category)),
        ("ui.page.memory.field.key", "ui.page.memory.field.key.note", str(key)),
        ("ui.page.memory.field.value", "ui.page.memory.field.value.note", ""),
    ]


# ── Qt ───────────────────────────────────────────────────────────────────────
#
# Everything above this line is readable without Qt and is what the tests
# exercise. Below it, widgets are placed and wired; no decision is taken here
# that the functions above do not already answer.

def build_memory(panel, page) -> None:
    """Board 9: FAKTA TENTANG ANDA over a list, plus the two buttons."""
    from PyQt6.QtWidgets import QLabel, QPushButton

    from ui.tray_pages import _at

    page.hide()
    panel._pages["memory"] = page
    g = GEOMETRY
    panel._labels["mem_head"] = at(page, QLabel, g["mem_head"], PAGE_TITLE["memory"])
    panel._labels["mem_count"] = at(page, QLabel, g["mem_count"], "")
    panel._labels["mem_section"] = at(page, QLabel, g["mem_section"], "")

    for index in range(LIST_ROWS):
        y = BODY_TOP + index * ROW_PITCH
        card = _at(page, QLabel, MARGIN, y, CONTENT_W, CARD_H, "")
        card.setStyleSheet(f"background:{PALETTES['dark']['card']};"
                           f"border-radius:12px;")
        panel._labels[f"mem_card:{index}"] = card
        panel._labels[f"mem_key:{index}"] = _at(page, QLabel, MARGIN + 18,
                                                y + 10, 250, 18, "")
        panel._labels[f"mem_val:{index}"] = _at(page, QLabel, MARGIN + 18,
                                                y + 32, 250, 20, "")
        # One button per row, labelled with what it does to THAT row.
        button = QPushButton("", page)
        button.setGeometry(MARGIN + 300, y + 18, 96, 26)
        button.clicked.connect(
            lambda _checked=False, i=index: panel._call("memory_open", i))
        panel._buttons[f"mem_open:{index}"] = button

    panel._labels["mem_more"] = at(page, QLabel, g["mem_more"], "")
    panel._buttons["mem_add"] = QPushButton("", page)
    panel._buttons["mem_add"].setGeometry(*g["mem_add"])
    panel._buttons["mem_add"].clicked.connect(lambda: panel._call("memory_add"))
    panel._buttons["mem_clear"] = QPushButton("", page)
    panel._buttons["mem_clear"].setGeometry(*g["mem_clear"])
    panel._buttons["mem_clear"].clicked.connect(
        lambda: panel._call("memory_clear"))


def build_memory_one(panel, page) -> None:
    """Board 10: one memory's detail, with an honest line where data is missing."""
    from PyQt6.QtWidgets import QLabel, QPushButton


    page.hide()
    panel._pages["memory_one"] = page
    g = GEOMETRY
    panel._labels["m1_head"] = at(page, QLabel, g["m1_head"], PAGE_TITLE["memory_one"])
    panel._labels["m1_sub"] = at(page, QLabel, g["m1_sub"], "")

    for index in range(3):
        y = 118 + index * 74
        panel._labels[f"m1_label:{index}"] = _at(page, QLabel, MARGIN, y,
                                                 160, 16, "")
        panel._labels[f"m1_value:{index}"] = _at(page, QLabel, MARGIN, y + 20,
                                                 412, 20, "")
        panel._labels[f"m1_note:{index}"] = _at(page, QLabel, MARGIN, y + 42,
                                                412, 16, "")

    panel._labels["m1_absent"] = at(page, QLabel, g["m1_absent"], "")
    panel._buttons["m1_back"] = QPushButton("", page)
    panel._buttons["m1_back"].setGeometry(*g["m1_back"])
    panel._buttons["m1_back"].clicked.connect(lambda: panel._call("page", "memory"))
    panel._buttons["m1_forget"] = QPushButton("", page)
    panel._buttons["m1_forget"].setGeometry(*g["m1_forget"])
    panel._buttons["m1_forget"].clicked.connect(
        lambda: panel._call("memory_forget"))


__all__ = ["LIST_ROWS", "build_memory", "build_memory_one", "count", "details",
           "entries", "find", "forget"]
