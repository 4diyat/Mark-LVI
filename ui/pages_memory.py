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

from ui.tray_pages import PALETTES, _at

from ui.board_geometry import BOARDS
from ui.page_kit import at, text_box

# HOW MANY ROWS THE ARTBOARD DRAWS, not how many happen to fit. b09 draws six
# 62 px cards from y=106 to y=528 and a divider at 556: six is the design, and a
# seventh would land on the divider. Read from the table so the two agree.
LIST_ROWS = len([r for r in BOARDS["memory"]["rects"] if r[3] == 62])


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
    """Board 9, transcribed: six 412x62 cards from y=106 at pitch 72.

    THE NUMBERS ARE THE DRAWING'S. `ui/board_geometry.BOARDS["memory"]` is
    generated from `build.py: b09()`, and `tests/test_board_conformance.py`
    compares this page against it. The first version of this function placed
    the list at y=62 — the top of the panel — so the section header printed
    over the first card and the last two rows fell past the artboard's own
    divider. Nothing failed, because the only thing checking this page was
    about to be written.

    NO TITLE IS DRAWN HERE. The panel's shared header already carries the
    page's name and subtitle from `n05`'s (24,34)/(24,54); this page used to
    add a second copy eight pixels below it.
    """
    from PyQt6.QtWidgets import QLabel, QPushButton

    from ui.tray_pages import _at

    page.hide()
    panel._pages["memory"] = page
    card = BOARDS["memory"]
    first = card["rects"][0]                    # (24, 106, 412, 62, 12)
    pitch = card["rects"][1][1] - first[1]      # 72, read not assumed

    panel._labels["mem_section"] = at(
        page, QLabel, text_box(24, 92, 10, width=240), "")

    for index in range(LIST_ROWS):
        y = first[1] + index * pitch
        box = _at(page, QLabel, first[0], y, first[2], first[3], "")
        box.setStyleSheet(f"background:{PALETTES['dark']['card']};"
                          f"border-radius:{first[4]}px;")
        panel._labels[f"mem_card:{index}"] = box
        # The artboard's own offsets: label at +24, value at +46, both x+20.
        panel._labels[f"mem_key:{index}"] = _at(
            page, QLabel, first[0] + 20, y + 16, 300, 16, "")
        panel._labels[f"mem_val:{index}"] = _at(
            page, QLabel, first[0] + 20, y + 36, 300, 20, "")
        # The row's own affordance is the small cross the artboard draws at
        # x=400 (a `path`, so it is not in the rect table) — a 24 px target on
        # the card's right edge. Its label is the row's key, so a screen reader
        # says which fact it forgets.
        forget = QPushButton("", page)
        forget.setGeometry(392, y + 18, 32, 28)
        forget.clicked.connect(
            lambda _checked=False, i=index: panel._call("memory_open", i))
        panel._buttons[f"mem_open:{index}"] = forget
        # THE CHEVRON the artboard draws at (400, y+22): a double arrow
        # (M400 {y+22} l8 8 M408 {y+22} l-8 8) marking the row as openable.
        # The button above is the click target; this label is its visual
        # glyph, drawn at the artboard's coordinate and in the muted token.
        chev = QLabel(page)
        chev.setGeometry(398, y + 20, 18, 18)
        chev.setStyleSheet(
            f"color:{PALETTES['dark']['muted']};background:transparent;"
            f"font-size:14px;")
        chev.setText("Â»")
        panel._labels[f"mem_chev:{index}"] = chev

    # The artboard's "dan N lagi" line sits between the last card and the
    # divider: 466+62 = 528, divider 556, so 530..554 is the only free band.
    panel._labels["mem_more"] = _at(page, QLabel, 24, 532, 412, 16, "")

    # The divider and the two 200 px pills, exactly where b09 draws them.
    rule = QLabel(page)
    rule.setGeometry(24, 556, 412, 1)
    rule.setStyleSheet(f"background:{PALETTES['dark']['line']};")
    panel._labels["mem_rule"] = rule

    panel._buttons["mem_add"] = QPushButton("", page)
    panel._buttons["mem_add"].setGeometry(24, 574, 200, 40)
    panel._buttons["mem_add"].clicked.connect(lambda: panel._call("memory_add"))
    panel._buttons["mem_clear"] = QPushButton("", page)
    panel._buttons["mem_clear"].setGeometry(236, 574, 200, 40)
    panel._buttons["mem_clear"].clicked.connect(
        lambda: panel._call("memory_clear"))


def build_memory_one(panel, page) -> None:
    """Board 10, transcribed from `b10()` — seven bands, three buttons.

    THE ARTBOARD IS RICHER THAN THE FIRST VERSION OF THIS PAGE. It draws a
    header-less layout with a back chevron at (42,54), an ISI MEMORI card at
    130, a SUMBER segmented control at 236, a MASA BERLAKU control at 320, a
    KEYAKINAN slider at 412, a chip row at 500, a divider at 556 and three
    pills at 574. The built page had three generic label/value pairs from
    y=118 and two buttons.

    ONLY THE ISI MEMORI CARD CARRIES REAL DATA. `all_entries_for_ui()` returns
    category, key, value and `updated`; there is no source, no lifetime and no
    confidence anywhere in the store. So those three bands are drawn at the
    artboard's coordinates with the artboard's controls in place, and the words
    in them say the value is not recorded — the owner's ruling for every
    artboard that draws data this build does not have. No percentage is shown.
    """
    from PyQt6.QtWidgets import QLabel, QPushButton

    page.hide()
    panel._pages["memory_one"] = page

    # The back chevron and the "Detail memori" line are the artboard's own
    # header, so this page is the one board page that draws a title — b10 has
    # no `panel_head()` and the shared header must be hidden for it.
    panel._labels["m1_title"] = _at(page, QLabel, 58, 56, 300, 22, "")
    panel._buttons["m1_back"] = QPushButton("", page)
    panel._buttons["m1_back"].setGeometry(30, 44, 32, 32)
    panel._buttons["m1_back"].clicked.connect(lambda: panel._call("page", "memory"))

    # ── ISI MEMORI: the one band with real data ────────────────────────────
    panel._labels["m1_isi_header"] = at(page, QLabel, text_box(24, 116, 10, width=240), "")
    panel._labels["m1_isi_card"] = _at(page, QLabel, 24, 130, 412, 62, "")
    panel._labels["m1_isi_label"] = _at(page, QLabel, 44, 140, 240, 18, "")
    panel._labels["m1_isi_value"] = _at(page, QLabel, 44, 162, 372, 22, "")

    # ── SUMBER at 222, the 412x36 control at 236 ───────────────────────────
    panel._labels["m1_source_header"] = at(page, QLabel, text_box(24, 222, 10, width=240), "")
    panel._labels["m1_source"] = _at(page, QLabel, 24, 236, 412, 36, "")

    # ── MASA BERLAKU at 306, the 412x36 control at 320 ─────────────────────
    panel._labels["m1_life_header"] = at(page, QLabel, text_box(24, 306, 10, width=240), "")
    panel._labels["m1_life"] = _at(page, QLabel, 24, 320, 412, 36, "")

    # ── KEYAKINAN at 392: the slider is drawn, and the note says what is not
    panel._labels["m1_conf_header"] = at(page, QLabel, text_box(24, 392, 10, width=240), "")
    panel._labels["m1_conf_track"] = _at(page, QLabel, 24, 412, 380, 3, "")
    panel._labels["m1_conf_note"] = at(page, QLabel, text_box(24, 440, 10.5, width=412), "")

    # ── DIPAKAI OLEH at 486: three chips, drawn as the artboard chips them ─
    panel._labels["m1_used_header"] = at(page, QLabel, text_box(24, 486, 10, width=240), "")
    panel._labels["m1_used"] = _at(page, QLabel, 24, 500, 412, 22, "")

    # ── the divider and the three pills: 130 + 130 + 128 at y=574 ──────────
    rule = QLabel(page)
    rule.setGeometry(24, 556, 412, 1)
    rule.setStyleSheet(f"background:{PALETTES['dark']['line']};")
    panel._labels["m1_rule"] = rule

    # b10 DRAWS THREE PILLS AND THIS PAGE HAS TWO THINGS TO DO WITH A MEMORY.
    # "Simpan" edits a memory's source, lifetime and confidence — none of which
    # this store keeps, so there is nothing to save and no control to save it
    # from. It is not drawn at all rather than drawn disabled: the two absences
    # are already stated band by band above, and a third disabled control in
    # the action row would suggest the page is one bug away from working.
    # "Ekspor" is real and it is the panel's existing audit export.
    panel._buttons["m1_forget"] = QPushButton("", page)
    panel._buttons["m1_forget"].setGeometry(24, 574, 130, 40)
    panel._buttons["m1_forget"].clicked.connect(
        lambda: panel._call("memory_forget"))
    panel._buttons["m1_export"] = QPushButton("", page)
    panel._buttons["m1_export"].setGeometry(166, 574, 130, 40)
    panel._buttons["m1_export"].clicked.connect(
        lambda: panel._call("history_export"))


__all__ = ["LIST_ROWS", "build_memory", "build_memory_one", "count", "details",
           "entries", "find", "forget"]
