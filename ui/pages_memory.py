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
    """The memory list: a section marker and a COLUMN THAT SCROLLS.

    WHAT CHANGED FROM THE ARTBOARD BUILD, AND WHY
        The previous version drew `LIST_ROWS` (six) fixed cards at the
        artboard's pitch 72 and put "dan N lagi" in the band above the divider.
        Both numbers came from `b09()`, and both were wrong for the same
        reason: they describe a PAGE, not a list. A memory store has no upper
        bound. Six rows and a counter mean that with twelve memories the panel
        shows half and mentions the rest; with twelve hundred it mentions
        ~1,194.

        `docs/design/00-principles.md` rule 2 says everything that grows
        scrolls. So the list is a `components.scroll_list` and the counter is
        gone — not because counting is wrong, but because counting was
        compensation for a container that could not scroll.

    WHAT STAYED
        The section marker above the list, the two pills below it, and the
        order of the cards: newest first, key over value, the cross on the
        right. Those are the design; the scroll is how it survives contact
        with a real store.

    THE HEADER STILL CARRIES THE COUNT. `b09()` passes "12 hal yang JARVIS
    ingat" to `panel_head()`, and the shared header formats that from the
    store at paint time. This page does not repeat it: one count, one place.
    """
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QLabel, QPushButton

    from ui import components, tokens
    from ui.page_kit import at, text_box

    page.hide()
    panel._pages["memory"] = page
    palette = PALETTES["dark"]

    panel._labels["mem_section"] = at(
        page, QLabel, text_box(tokens.S5, tokens.HEAD_H, tokens.LABEL, width=240), "")

    # The column starts under the section marker and ends above the actions.
    list_top = tokens.HEAD_H + tokens.S6
    list_height = tokens.PANEL_H - tokens.ACTION_H - list_top
    viewport, column = components.scroll_list(
        page, x=tokens.S5, y=list_top,
        width=tokens.CONTENT_W, height=list_height)
    panel._labels["mem_list"] = viewport

    # The action band: the divider, then two pills. Sizes from tokens, so the
    # pill height and the divider's inset cannot drift from the rest of the app.
    rule = QLabel(page)
    rule.setGeometry(tokens.S5, tokens.PANEL_H - tokens.ACTION_H,
                     tokens.CONTENT_W, 1)
    rule.setStyleSheet(f"background:{palette['line']};")
    panel._labels["mem_rule"] = rule

    pill_w = (tokens.CONTENT_W - tokens.S3) // 2      # 200 each, 12 apart
    add = QPushButton("", page)
    add.setGeometry(tokens.S5, tokens.PANEL_H - tokens.ACTION_H + tokens.S2,
                    pill_w, tokens.PILL_H_SMALL)
    add.setStyleSheet(components.pill_style(palette, primary=False))
    add.clicked.connect(lambda: panel._call("memory_add"))
    panel._buttons["mem_add"] = add

    clear = QPushButton("", page)
    clear.setGeometry(tokens.S5 + pill_w + tokens.S3,
                      tokens.PANEL_H - tokens.ACTION_H + tokens.S2,
                      pill_w, tokens.PILL_H_SMALL)
    clear.setStyleSheet(components.pill_style(palette, primary=False))
    clear.clicked.connect(lambda: panel._call("memory_clear"))
    panel._buttons["mem_clear"] = clear

    # THE ROWS ARE BUILT BY THE PAINTER, not here. A card's text comes from the
    # store, and the store must be read when the page is DRAWN: a memory added
    # while the panel is open has to appear without rebuilding the page. The
    # builder's job is the frame; `populate_memory` fills it.
    panel._memory_column = column
    _ = Qt


def populate_memory(panel) -> None:
    """Rebuild the memory rows from the store. Called on every paint.

    WHY IT REBUILDS RATHER THAN UPDATES. `entries()` returns a list that is
    re-sorted newest-first on every read, so row 3 is a different memory after
    one deletion. Updating text in place would leave the crosses wired to the
    order they were built in — and a click would delete something the user
    never pointed at. Rebuilding from the current list is the only version that
    cannot do that.

    IT IS ALSO WHY THE LIST CAN BE ANY LENGTH. There is no `LIST_ROWS` here:
    every entry gets a card, and the column scrolls. Six is how many are
    visible; it is not how many exist.
    """
    from PyQt6.QtWidgets import (QHBoxLayout, QLabel, QPushButton,
                                 QVBoxLayout, QWidget)

    from ui import components, tokens
    from ui.tray_panel_model import _t

    column = getattr(panel, "_memory_column", None)
    if column is None:                       # page never built: nothing to fill
        return

    # Clear what the last paint put here. The stretch spacer is re-added at the
    # end so the cards stay top-aligned instead of spreading down the column.
    while column.count():
        item = column.takeAt(0)
        widget = item.widget() if item is not None else None
        if widget is not None:
            widget.setParent(None)
            widget.deleteLater()

    palette = PALETTES[getattr(panel, "_theme", "dark")]
    rows = entries()

    if not rows:
        # AN EMPTY STORE GETS A CARD, NOT A BLANK PAGE. The artboard draws six
        # cards whether or not there is anything in them; an empty list is a
        # fact to state, not a reason to render an empty section.
        empty = QLabel(_t("ui.page.memory.empty_row"))
        empty.setStyleSheet(
            f"color:{palette['muted']};font-size:{tokens.META}px;"
            f"background:{palette['card']};border-radius:{tokens.R_CARD}px;"
            f"border:1px solid {palette['line']};padding:{tokens.S4}px;")
        empty.setWordWrap(True)
        empty.setMinimumHeight(tokens.CARD_H_2LINE)
        column.addWidget(empty)
        column.addStretch(1)
        return

    for index, row in enumerate(rows):
        card = QWidget()
        card.setStyleSheet(components.card_style(palette))
        card.setMinimumHeight(components.card_height(2))
        card_layout = QHBoxLayout(card)
        card_layout.setContentsMargins(tokens.CARD_PAD, 0, tokens.S4, 0)
        card_layout.setSpacing(tokens.S2)

        text = QWidget(card)
        text_column = QVBoxLayout(text)
        text_column.setContentsMargins(0, 0, 0, 0)
        text_column.setSpacing(tokens.S1)

        key = QLabel(str(row.get("key") or ""))
        key.setStyleSheet(f"color:{palette['muted']};"
                          f"font-size:{tokens.META}px;")
        value = QLabel(str(row.get("value") or ""))
        value.setStyleSheet(f"color:{palette['text']};"
                            f"font-size:{tokens.CARD_TITLE}px;"
                            f"font-weight:{tokens.WEIGHT_LABEL};")
        value.setWordWrap(True)
        text_column.addWidget(key)
        text_column.addWidget(value)
        card_layout.addWidget(text, 1)

        # The cross keeps the row's IDENTITY, not its index: `i=index` would
        # bind to the position, and the list re-sorts on every read.
        forget = QPushButton(_t("ui.page.memory.open"))
        forget.setFixedSize(tokens.S7, tokens.S6)
        forget.setStyleSheet(f"QPushButton{{background:transparent;"
                             f"border:none;color:{palette['muted']};"
                             f"font-size:{tokens.META}px;}}")
        forget.clicked.connect(
            lambda _checked=False, r=dict(row): panel._call(
                "memory_open_id", r.get("category", ""), r.get("key", "")))
        card_layout.addWidget(forget, 0)

        column.addWidget(card)

    column.addStretch(1)

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
