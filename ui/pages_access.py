"""Board 15, the accessibility page — split off `pages_admin` at the ceiling.

WHY IT IS ITS OWN FILE
    `pages_admin` held five board builders and reached 608 lines against the
    600-line ceiling for the third time in this round. The split is not
    "whatever fits": board 15 is the only admin page that is about the PERSON
    rather than the machine — language, reading size, motion, gestures — and it
    is the only one that reads `core.i18n` and the gesture table. Everything it
    touches is either `page_kit` geometry or its own small store, so it has no
    reason to live beside the plugin and installer pages.

LIMITATIONS
    Language and panel contrast work. Text scaling, reduced motion and custom
    gesture bindings are unavailable until their renderers/controllers consume
    the stored preferences; their controls must not claim otherwise.

"""
from __future__ import annotations

from PyQt6.QtWidgets import QLabel, QPushButton

from ui.board_geometry import BOARDS
from ui.page_kit import at, text_box
from ui.tray_pages import _at
from ui.tray_panel_model import _t

# The language list is the CATALOGUE's, which `pages_admin` already reads for
# board 16 and the header. Imported rather than re-derived: two functions that
# answer "which languages exist" would eventually disagree, and the panel would
# offer a language it cannot draw in.
from ui.pages_admin import languages

# Board 15's left-to-right order, from `b15()`: Indonesia, English, then the
# slot that says "Campur" is not available. `languages()` says which catalogues
# EXIST; this says where the drawing puts them.
LANGUAGE_ORDER = ("id", "en")


def language_slots() -> list[str]:
    """The slots the page draws: the drawing's order, minus what does not exist.

    BOTH INPUTS ARE NEEDED. Taking only the drawing's order would draw a button
    for a catalogue that is not installed, and the panel would call
    `set_language("id")` on a build without `id.json`. Taking only
    `i18n.available()` is what reversed the row. This intersects them, keeping
    the artboard's order.
    """
    return [code for code in LANGUAGE_ORDER if code in languages()]


def build_access(panel, page) -> None:
    """Board 15, transcribed from `b15()`: three languages, a slider, three cards.

    THE LANGUAGE ROW DRAWS THREE AND THE STORE HAS TWO. `b15()` draws
    Indonesia · English · Campur as one 412 px segmented control; `core.i18n`
    ships en and id and has no mixed mode. The third slot is drawn because the
    artboard's layout is the layout — and it says in place that mixed language
    is not available, rather than being dropped (which would silently change the
    design) or wired to nothing (which is a button that lies). That is the
    owner's ruling for every artboard that draws data this build does not have.
    """

    page.hide()
    panel._pages["access"] = page
    geo = BOARDS["access"]

    # ── BAHASA UI at y=92, the 412x38 segmented control at 106 ─────────────
    panel._labels["ac_lang_header"] = at(page, QLabel, text_box(24, 92, 10, width=240), "")
    seg = [r for r in geo["rects"] if r[3] == 38 and r[2] == 412][0]   # (24,106,412,38)
    # The track itself, so the control is a 412x38 pill at the artboard's
    # coordinates even before the three slots are drawn on top of it.
    panel._labels["ac_lang_track"] = _at(page, QLabel, seg[0], seg[1], seg[2], seg[3], "")
    share = seg[2] / 3
    # THE SLOT SAYS THE LANGUAGE'S NAME, NOT ITS CODE. `b15()` draws
    # "Indonesia", "English", "Campur"; the first version drew "ID" and "EN",
    # which is a different word in the same 137 px slot. Each name is its own
    # key, so the Indonesian catalogue says "Indonesia" — the artboard's exact
    # word — while the English catalogue says "Indonesian", the same way the
    # third slot already says "Mixed" rather than "Campur".
    # THE ORDER IS THE ARTBOARD'S, NOT THE CATALOGUE'S. `b15()` draws
    # Indonesia · English · Campur, left to right; `i18n.available()` returns
    # ["en", "id"] because that is how the files sort. Iterating the store put
    # English in the slot the drawing gives Indonesia — the right words in the
    # wrong places. `language_slots()` intersects the drawing with what ships.
    for index, code in enumerate(language_slots()):
        button = QPushButton(_t(f"ui.page.access.language.{code}"), page)
        button.setGeometry(round(seg[0] + index * share + 3), seg[1] + 3,
                           round(share) - 6, seg[3] - 6)
        button.clicked.connect(
            lambda _checked=False, c=code: panel._call("language", c))
        panel._buttons[f"ac_lang:{code}"] = button
    # The third slot: present, disabled, and honest in its own label.
    mixed = QPushButton("", page)
    mixed.setGeometry(round(seg[0] + 2 * share + 3), seg[1] + 3,
                      round(share) - 6, seg[3] - 6)
    mixed.setEnabled(False)
    panel._buttons["ac_lang:mixed"] = mixed

    # ── UKURAN TEKS at 172, the 380 px slider at 194, the note at 222 ──────
    panel._labels["ac_size_header"] = at(page, QLabel, text_box(24, 172, 10, width=240), "")
    # THE SLIDER IS THE CONTROL, and it is THREE targets rather than a drag
    # handle. `b15()` draws a 380x3 track at (24,194) with a knob at 50% and the
    # line "Sedang · 14 px" under it — the artboard's only text-size control.
    # A row of 130 px buttons was invented on top of it at y=240, where the
    # sheet draws nothing, and it pushed into the KONTRAS control at 278.
    panel._labels["ac_size_track"] = _at(page, QLabel, 24, 194, 380, 3, "")
    panel._labels["ac_size_fill"] = _at(page, QLabel, 24, 194, 190, 3, "")
    panel._labels["ac_size_knob"] = _at(page, QLabel, 194, 187, 14, 14, "")
    panel._labels["ac_size_note"] = at(page, QLabel, text_box(24, 222, 10.5, width=412), "")
    # ONE HIT TARGET, THE WHOLE TRACK. The artboard draws a slider, and a
    # slider means drag; this panel has no drag handling and a 3 px track is no
    # target at all. Three invisible thirds were tried first and were WORSE:
    # `apply_style` gives every QPushButton a card background and a border, so
    # they painted as three boxes on top of the drawing. So there is one 380x24
    # button over the track, made transparent here, and pressing it cycles the
    # three scales — the knob and the "Sedang · 14 px" line then show which one
    # is on. `tests/test_board_pages.py` presses it and checks the store.
    button = QPushButton("", page)
    button.setGeometry(24, 184, 380, 24)
    button.setStyleSheet("background:transparent;border:none;")
    button.clicked.connect(lambda: panel._call("text_scale", "next"))
    panel._buttons["ac_scale"] = button

    # ── KONTRAS at 264: a 412x38 segmented control, two slots (Standar/Tinggi).
    # The artboard draws the track at (24,278) with a 200 px slot each; b15
    # names the two levels at x=127 and x=333. The first version wrote a
    # sentence saying high contrast does not exist; the owner chose to build
    # it, so the control is now real and the two slots are live buttons.
    panel._labels["ac_contrast_header"] = at(page, QLabel, text_box(24, 264, 10, width=240), "")
    panel._labels["ac_contrast_track"] = _at(page, QLabel, 24, 278, 412, 38, "")
    panel._labels["ac_contrast_note"] = at(page, QLabel, text_box(24, 324, 10.5, width=412), "")
    # Two equal 200 px slots, matching the artboard's (27,281,200,32) and its
    # mirror at x=225. Both are buttons: the checked one is the active level.
    for index, (label_key, level) in enumerate((("standard", "standard"),
                                                 ("high", "high"))):
        button = QPushButton("", page)
        button.setGeometry(24 + index * 200, 278, 200, 38)
        button.setObjectName(f"ac_contrast:{level}")
        button.clicked.connect(
            lambda _checked=False, lv=level: panel._call("contrast_set", lv))
        panel._buttons[f"ac_contrast:{level}"] = button

    # ── GERAK at 344: the 412x64 card, the toggle at (378, 380) ────────────
    panel._labels["ac_motion_header"] = at(page, QLabel, text_box(24, 344, 10, width=240), "")
    panel._labels["ac_motion_card"] = _at(page, QLabel, 24, 358, 412, 64, "")
    panel._labels["ac_motion_name"] = _at(page, QLabel, 44, 368, 300, 20, "")
    panel._labels["ac_motion_note"] = _at(page, QLabel, 44, 390, 320, 18, "")
    panel._buttons["ac_motion"] = QPushButton("", page)
    panel._buttons["ac_motion"].setGeometry(378, 380, 40, 22)
    panel._buttons["ac_motion"].clicked.connect(lambda: panel._call("motion_toggle"))

    # ── GESTUR KUSTOM at 450: three 412x38 cards at pitch 46 ───────────────
    panel._labels["ac_gestures_header"] = at(page, QLabel, text_box(24, 450, 10, width=240), "")
    for index in range(3):
        y = 464 + index * 46
        panel._labels[f"ac_gest_card:{index}"] = _at(page, QLabel, 24, y, 412, 38, "")
        panel._labels[f"ac_gest_name:{index}"] = _at(page, QLabel, 44, y + 8, 190, 18, "")
        # The three columns `b15()` draws: name at 44, action at 250 in cyan,
        # "ubah" right-aligned at 416. The action cell starts at 250, not 240 —
        # 240 was a guess that put it 10 px left of the artboard's column.
        panel._labels[f"ac_gest_act:{index}"] = _at(page, QLabel, 250, y + 8, 130, 18, "")
        # The artboard's "ubah" is anchored END at x=416. A QLabel has no
        # anchor, so the cell is 96 px wide ending at 416 and the text is
        # aligned right inside it — the same result, and it stops "ubah"
        # spilling out of a 32 px box. The cell is a BUTTON now: rebinding is
        # real (core.gesture_binding + actions.gesture_binding), so "ubah"
        # walks the action cycle for this gesture rather than stating "fixed".
        edit = QPushButton("", page)
        edit.setGeometry(320, y + 8, 96, 18)
        edit.setObjectName(f"ac_gest_edit:{index}")
        edit.setStyleSheet("background:transparent;border:none;color:inherit;")
        edit.clicked.connect(lambda _checked=False, i=index:
                             panel._call("gesture_rebind", i))
        panel._buttons[f"ac_gest_edit:{index}"] = edit
    panel._labels["ac_footnote"] = at(page, QLabel, text_box(24, 616, 10, width=412), "")
