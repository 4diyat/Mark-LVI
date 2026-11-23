"""The three pages of the tray panel, and the two palettes they are drawn in.

WHY THIS IS A SECOND MODULE
    Boards 5, 23, 26, 27 and 28 are five artboards of ONE 460x660 panel. The
    widget that owns it (`ui/tray_panel.py`) is about lifecycle, dispatch and
    truth; the widgets below are about geometry — a dozen fixed coordinates per
    page, transcribed from the artboard and nowhere else. Splitting them is not
    tidiness: the module ceiling for `ui/` is 600 lines and the panel crossed
    it, which is the rule doing its job.

    It is also the split that makes the palette honest. Board 17a is the SAME
    panel in light colours, so the colours are a table here and the pages read
    it by name. A second widget for the light theme — the obvious way to build
    it — would be two panels to keep in step forever.

WHAT IS IN HERE
    `PALETTES`          dark (boards 5/23/27) and light (board 17a), taken from
                        `docs/mockups/build.py` rather than retyped by eye.
    `build_main()`      boards 5 and 05a: four quick actions, the quota line,
                        three switches and the command field. The segments and
                        the hold strip live on the panel itself, because both
                        are shared with the other pages' header.
    `build_history()`   board 08a: four undoable rows, the audit tail, and the
                        two buttons at the bottom.
    `build_permissions()` board 6: IZIN AKSES over four switches at the
                        artboard's 72 px pitch, the activity log, and the
                        two buttons beneath it.

    Every function takes `(panel, page)` and fills `panel._labels` and
    `panel._buttons`. They are functions rather than methods because they hold
    no state of their own — if one of them ever needs some, that is a sign the
    value belongs on the panel.
"""
from __future__ import annotations

from ui.tray_panel_model import (ALL_QUICK_KEYS, PERMISSIONS,
                                QUICK_ACTIONS, _t)  # noqa: F401 — used below

# The artboard size. Defined here because this is the module that owns
# geometry; the panel imports it so the two cannot disagree.
PANEL_W, PANEL_H = 460, 660

# ── board 5's geometry, as numbers you can check ───────────────────────────
#
# WHY A TABLE AND NOT THE SAME NUMBERS INSIDE THE BUILDER
#     Every value below is read off `docs/mockups/build.py: n05()` and nothing
#     else. Written inline in `build_main()` they were unverifiable: four of
#     them had drifted from the artboard (the suggestion card was never drawn,
#     its two lines sat 8 px high, and the whole IZIN block sat 18-26 px high
#     with no toggle column), and no test could tell, because a call to
#     `setGeometry` is not a fact anyone can assert against a drawing.
#
#     As a dict, `tests/test_tray_geometry.py` can compare it with `build.py`
#     itself — so the next drift fails a test instead of surviving a review.
#
# THE ONE DELIBERATE DIFFERENCE
#     `PANEL_H` is 660 and the artboard is 640. That is not drift and it is not
#     in this table: `DESIGN-ambient.md` records the decision ("tiga baris izin
#     + input butuh 20 px ekstra"), and the values below already sit in the
#     taller panel — which is why the input is at y=596 rather than 576.
GEOMETRY = {
    # section headers: (x, y, w, h)
    "quick_header":      (24, 140, 200, 16),
    "suggestion_header": (24, 366, 200, 16),
    "perm_header":       (24, 478, 200, 16),
    # the four quick rows: first y, height, pitch
    "quick_row_y": 154, "quick_row_h": 40, "quick_pitch": 48,
    # the suggestion card the artboard draws and this panel did not
    "suggestion_card":     (24, 380, 412, 62),
    "suggestion_bar":      (24, 392, 3, 38),
    "suggestion_title":    (44, 396, 372, 20),
    "suggestion_quota":    (44, 416, 372, 18),
    # BOARD 23'S SECOND QUOTA SENTENCE. The artboard draws it INSIDE the card, at
    # y=548 of a layout whose card sits at 504. This panel's card sits at 380 and
    # is 62 px tall — board 5's, pinned by `tests/test_tray_geometry.py` — and a
    # third line does not fit in 62 px without changing the card the other board
    # is measured against. So it sits directly BENEATH the card: same column,
    # same type, 4 px of air. The line is blank outside Fokus, where nothing is
    # being held and the sentence would be false.
    "quota_held":          (44, 446, 372, 18),
    # the three permission rows: text at x=24, toggle at x=396, pitch 30
    "perm_row_y": 492, "perm_pitch": 30, "perm_row_h": 26, "perm_toggle_x": 396,
    # the command line, and the send disc the artboard draws at cx=404
    "field": (24, 596, 340, 40),
    # A 36 px box whose CENTRE is the artboard's circle centre (404, 616):
    # the circle is drawn by centre, a QPushButton by its corner, and 596 put
    # the disc two pixels high of the drawing.
    "send":  (386, 598, 36, 36),

    # ── BOARD 6'S PAGE ────────────────────────────────────────────────────
    # The artboard is 460x640 and the panel is 460x660, so the extra 20 px sits
    # BETWEEN the last permission row and the activity log: rows 1-4 keep the
    # artboard's y exactly (106 + i*72), and everything from the log down is
    # shifted +20. Nothing above the log moves, which is what makes this a fit
    # rather than a re-layout. `tests/test_tray_geometry.py` compares this
    # table with `build.py: b06()`.
    "p6_head":        (24, 34, 412, 22),      # "Izin & privatisasi"
    "p6_sub":         (24, 54, 412, 18),      # "Semua proses di perangkat"
    "p6_perm_header": (24, 92, 240, 16),      # "IZIN AKSES"
    "p6_row_y": 106, "p6_pitch": 72,          # card tops
    "p6_card": (24, 62, 412),                 # x, height, width
    "p6_name": (44, 26),                      # name inside the card
    "p6_sub_off": (44, 45),                   # subtitle inside the card
    "p6_toggle_x": 378, "p6_toggle_dy": 20,
    "p6_log_header": (24, 432, 240, 16),      # "LOG AKTIVITAS" (412 + 20)
    "p6_log_card": (24, 446, 412, 118),
    "p6_log_row_y": 468, "p6_log_pitch": 32,  # 448 + 20, same 32 px pitch
    "p6_log_time_x": 40, "p6_log_text_x": 92,
    "p6_divider": (24, 576, 412, 1),          # 556 + 20
    "p6_clear":  (24, 594, 200, 40),          # 574 + 20
    "p6_export": (236, 594, 200, 40),

    # ── boards 9 and 10: memory ──────────────────────────────────────────
    # Board 9's own header carries a COUNT of what is stored, which is why it
    # is a separate line from the title: the title is the artboard's, the count
    # is the store's, and a page that merged them would have to choose which
    # one to keep when they disagree.
    "mem_head":    (24, 30, 412, 24),         # "Memori personal"
    "mem_section": (24, 86, 240, 16),         # "FAKTA TENTANG ANDA"
    "mem_more":    (24, 640, 412, 16),        # "dan 4 lagi"
    "mem_add":     (24, 600, 200, 36),
    "mem_clear":   (236, 600, 200, 36),

    # Board 10 packs three fields into the space board 9 gives one row, so its
    # pitch is 74 and not 72. The artboard is tighter here on purpose: this page
    # shows ONE memory, and the detail is the point.
    "m1_head":   (24, 30, 412, 24),
    "m1_back":   (24, 596, 130, 36),
    "m1_forget": (306, 596, 130, 36),

    # ── the list that reaches every board page ───────────────────────────
    "more_head": (24, 30, 412, 24),
    "more_sub":  (24, 54, 412, 18),
    "more_back": (24, 604, 140, 36),

    # ── boards 11 and 12: routines, quick tools ──────────────────────────
    "rt_head":    (24, 30, 412, 24),
    "rt_count":   (24, 54, 412, 18),
    "rt_section": (24, 86, 240, 16),
    "rt_absent":  (24, 168, 412, 44),     # "tidak ada rutinitas terjadwal"
    "rt_suggest": (24, 226, 240, 16),
    "rt_suggest_note": (24, 248, 412, 40),
    "rt_pause":   (24, 600, 220, 36),

    "tl_head":        (24, 30, 412, 24),
    "tl_clip_header": (24, 70, 240, 16),
    "tl_clip":        (24, 94, 412, 40),
    "tl_kind":        (24, 138, 412, 18),
    "tl_btns_y": 166,
    "tl_find_header": (24, 214, 300, 16),
    "tl_find_field":  (24, 236, 412, 34),
    "tl_hits_y": 282,
    "tl_snap_header": (24, 366, 240, 16),
    "tl_snap_absent": (24, 388, 412, 40),

    # ── boards 19, 7, 13 ─────────────────────────────────────────────────
    "gs_head":   (24, 30, 412, 24),
    "gs_absent": (24, 404, 412, 20),
    "gs_note":   (24, 432, 412, 44),

    "cn_head":  (24, 30, 412, 24),
    "cn_step":  (24, 54, 412, 18),
    "cn_name":  (24, 96, 412, 26),
    "cn_why":   (24, 130, 412, 40),
    "cn_when":  (24, 178, 412, 20),
    "cn_done":  (24, 230, 412, 40),
    "cn_allow": (24, 600, 200, 40),
    "cn_deny":  (236, 600, 200, 40),

    "hp_head":       (24, 30, 412, 24),
    "hp_dictate_h":  (24, 78, 240, 16),
    "hp_dictate":    (24, 100, 412, 44),
    "hp_read_h":     (24, 176, 240, 16),
    "hp_read":       (24, 198, 412, 44),
    "hp_form_h":     (24, 274, 240, 16),
    "hp_form_absent": (24, 296, 412, 44),

    # ── boards 14, 15, 16, 18, 21, 22 ────────────────────────────────────
    "sec_head":    (24, 30, 412, 24),
    "sec_levels":  (24, 78, 240, 16),
    "sec_rows_y": 92, "sec_pitch": 66,
    "sec_guest_h": (24, 300, 240, 16),
    "sec_guest":   (24, 322, 412, 40),
    "sec_os_h":    (24, 386, 240, 16),
    "sec_os":      (24, 408, 412, 40),

    "ac_head":     (24, 30, 412, 24),
    "ac_lang_h":   (24, 78, 240, 16),
    "ac_lang_y": 100,
    "ac_size_h":   (24, 164, 240, 16),
    "ac_size_note": (24, 186, 412, 18),
    "ac_size_y": 212,
    "ac_motion_h": (24, 272, 240, 16),
    "ac_motion":   (24, 294, 220, 36),
    "ac_gest_h":   (24, 356, 240, 16),
    "ac_gest":     (24, 378, 412, 40),

    "pl_head":     (24, 30, 412, 24),
    "pl_count":    (24, 54, 412, 18),
    "pl_section":  (24, 84, 240, 16),
    "pl_rows_y": 104, "pl_pitch": 56,
    "pl_phone_h":  (24, 470, 240, 16),
    "pl_phone":    (24, 492, 412, 24),
    "pl_phone2":   (24, 518, 412, 40),

    "l18_head":    (24, 30, 412, 24),
    "l18_sub":     (24, 54, 412, 18),
    "l18_perm_h":  (24, 90, 240, 16),
    "l18_log_h":   (24, 432, 240, 16),
    "l18_log_y": 452,
    "l18_note":    (24, 560, 412, 40),

    "br_head":     (24, 30, 412, 24),
    "br_icons_h":  (24, 272, 240, 16),
    "br_app":      (24, 372, 412, 20),
    "br_spec":     (24, 404, 412, 40),

    "in_head":     (24, 30, 412, 24),
    "in_sub":      (24, 54, 412, 18),
    "in_rows_y": 92,

}

# Which page the panel is showing. Board 08a and 27 are pages, not other
# windows: a tray panel that spawns three windows is three things to close.
PAGE_MAIN, PAGE_HISTORY, PAGE_PRIVACY = "main", "history", "privacy"

# THE FULL SET, from the registry rather than a second list. `more` is the list
# that reaches the board pages, so it belongs with them and not with the three
# the panel has always had.
from ui.page_registry import ALL_PAGES as _PAGES  # noqa: E402  (after the constants)

PAGES = _PAGES


# Boards 5/23/27 (dark) and 28 (light), transcribed from `docs/mockups/build.py`
# so the two cannot disagree without a test failing. The keys are what the
# stylesheet below reads, not what Qt calls them.
PALETTES = {
    "dark": {
        "base": "#04080D", "panel": "#0A1722", "card": "#081520",
        "line": "#17323F", "line_accent": "#2A6477",
        "text": "#E6F4F8", "muted": "#8FA9B5",
        "accent": "#4FD8F0", "amber": "#F5A524", "on_accent": "#04080D",
    },
    "light": {
        "base": "#F6F9FB", "panel": "#FFFFFF", "card": "#FFFFFF",
        "line": "#D8E3E9", "line_accent": "#0A7A93",
        "text": "#0B1A24", "muted": "#5B7480",
        "accent": "#0A7A93", "amber": "#9A5B00", "on_accent": "#FFFFFF",
    },
}


def panel_position(screen, size=(PANEL_W, PANEL_H), point=None) -> tuple[int, int]:
    """Where the panel goes, given the screen's available rectangle.

    Pure, and that is the point: the interesting part of a tray panel is not
    its paint, it is that it opens INSIDE the screen no matter where the
    taskbar is. A panel that opens off the bottom edge is the classic tray bug,
    and it is a two-line bug that a screenshot review never catches.

    `point` is the tray icon's position when the platform reports one. Without
    it the panel goes bottom-right, which is where a Windows tray lives; the
    clamp below is what keeps it on screen when it does not.
    """
    left, top = int(screen.x()), int(screen.y())
    width, height = int(screen.width()), int(screen.height())
    w, h = int(size[0]), int(size[1])

    if point is None:
        x = left + width - w - 12
        y = top + height - h - 12
    else:
        px, py = int(point[0]), int(point[1])
        # Above the icon and right-aligned to it, which is where a tray menu
        # opens on Windows and macOS alike.
        x = px - w + 24
        y = py - h - 8
    x = max(left, min(x, left + width - w))
    y = max(top, min(y, top + height - h))
    return x, y


def build_main(panel, page) -> None:
    """Board 5, built from `GEOMETRY` — see the table's own note on why.

    The permission rows are a text label plus a DOT TOGGLE at x=396, not one
    wide button. That is the artboard's shape: a 40x22 track with a knob on
    the left when off and on the right when on. A full-width pill was the
    earlier version and it read as a menu row, not a switch.
    """
    from PyQt6.QtWidgets import QLabel, QLineEdit, QPushButton

    panel._pages = {PAGE_MAIN: page}
    g = GEOMETRY

    panel._labels["quick_header"] = _at(
        page, QLabel, *g["quick_header"], _t("ui.panel.section.quick"))
    # FOUR ROWS ARE BUILT FOR THE LONGEST LIST AND REUSED, because the panel is
    # 460 px and the artboard gives the block exactly four rows. Building them
    # per mode would rebuild the page on a mode change; three keys in Fokus and
    # four in Aktif would then need the fourth widget to disappear, which moves
    # every section under it.
    #
    # So: one button per ROW INDEX, and `paint_quick` decides what each row says
    # and which action it runs for the mode in force. The widget count is the
    # layout's, not the mode's.
    # ONE WIDGET PER ACTION, and the two modes' lists share this block. Fokus
    # draws three rows where Aktif draws four, so the fourth keeps its geometry
    # and is hidden in Fokus — a hidden widget, not a rebuilt page, because
    # rebuilding on a mode change moves every section below it by 48 px.
    for index, key in enumerate(ALL_QUICK_KEYS):
        y = g["quick_row_y"] + index * g["quick_pitch"]
        button = QPushButton("", page)
        button.setGeometry(24, y, 412, g["quick_row_h"])
        button.clicked.connect(lambda _checked=False, k=key: panel.press_quick(k))
        button.hide()                       # `paint_quick` shows the live ones
        panel._buttons[f"quick:{key}"] = button

    # THE SUGGESTION CARD. The artboard draws a 412x62 card with an amber bar
    # down its left edge — amber because a suggestion is the one thing on this
    # page the user did not ask for. Neither existed before: the text floated
    # on the panel background and the card was simply missing.
    panel._labels["suggestion_header"] = _at(
        page, QLabel, *g["suggestion_header"], _t("ui.panel.section.suggestion"))
    panel._labels["suggestion_card"] = _at(
        page, QLabel, *g["suggestion_card"], "")
    panel._labels["suggestion_card"].setStyleSheet(
        f"background:{PALETTES['dark']['card']};"
        f"border:1px solid {PALETTES['dark']['line']};border-radius:12px;")
    panel._labels["suggestion_bar"] = _at(
        page, QLabel, *g["suggestion_bar"], "")
    panel._labels["suggestion_bar"].setStyleSheet(
        f"background:{PALETTES['dark']['amber']};border-radius:1.5px;")
    panel._labels["suggestion"] = _at(
        page, QLabel, *g["suggestion_title"], "")
    panel._labels["quota"] = _at(page, QLabel, *g["suggestion_quota"], "")
    panel._labels["quota_held"] = _at(page, QLabel, *g["quota_held"], "")

    panel._labels["perm_header"] = _at(
        page, QLabel, *g["perm_header"], _t("ui.panel.section.permissions"))
    for index, (key, name, _sub) in enumerate(PERMISSIONS[:3]):
        y = g["perm_row_y"] + index * g["perm_pitch"]
        # The label is the switch: clicking the word "Mikrofon" toggles it.
        # A 26 px row with a separate 40 px dot is below the 44 px touch
        # target, so the row has to be the target — the dot is the readout.
        button = QPushButton(_t(name), page)
        button.setCheckable(True)
        button.setGeometry(24, y, 360, g["perm_row_h"])
        button.setStyleSheet("text-align:left;padding-left:0;border:none;")
        button.clicked.connect(
            lambda checked=False, k=key: panel.press_permission(k, checked))
        panel._buttons[f"perm:{key}"] = button
        dot = _at(page, QLabel, g["perm_toggle_x"], y + 4, 40, 22, "")
        dot.setStyleSheet(
            f"background:{PALETTES['dark']['card']};"
            f"border:1px solid {PALETTES['dark']['line']};border-radius:11px;")
        panel._labels[f"perm_dot:{key}"] = dot

    field = QLineEdit(page)
    field.setPlaceholderText(_t("ui.panel.command.placeholder"))
    field.setGeometry(*g["field"])
    field.returnPressed.connect(panel.submit_command)
    panel._field = field
    # The send control is a 36 px disc at the same place the artboard puts its
    # 18 px-radius circle, rather than the 50x40 rectangle it was.
    send = QPushButton(_t("ui.panel.command.send"), page)
    send.setGeometry(*g["send"])
    send.setStyleSheet("border-radius:18px;padding:0;")
    send.clicked.connect(panel.submit_command)
    panel._buttons["send"] = send


def build_history(panel, page) -> None:
    from PyQt6.QtWidgets import QLabel, QPushButton
    page.hide()
    panel._pages[PAGE_HISTORY] = page

    panel._labels["history_count"] = _at(page, QLabel, 24, 46, 412, 20, "")
    # Four rows at board 08a's pitch, each with its own label and its own
    # Urungkan button. Four, not a scroll area: the panel is a glance, and
    # a scroll inside a 660 px popup is a scroll nobody performs.
    for index in range(4):
        y = 80 + index * 96
        panel._labels[f"history:{index}"] = _at(page, QLabel, 60, y + 12, 240, 22, "")
        panel._labels[f"history_meta:{index}"] = _at(
            page, QLabel, 60, y + 40, 240, 18, "")
        button = QPushButton(_t("ui.panel.undo"), page)
        button.setGeometry(300, y + 48, 120, 26)
        button.clicked.connect(panel.press_undo)
        button.hide()
        panel._buttons[f"undo:{index}"] = button

    panel._labels["audit_header"] = _at(
        page, QLabel, 24, 486, 200, 16, _t("ui.panel.section.audit"))
    panel._labels["audit"] = _at(page, QLabel, 40, 506, 396, 84, "")

    export = QPushButton(_t("ui.panel.history.export"), page)
    export.setGeometry(24, 612, 200, 36)
    export.clicked.connect(lambda: panel._call("history_export"))
    panel._buttons["export"] = export
    clear = QPushButton(_t("ui.panel.history.clear"), page)
    clear.setGeometry(236, 612, 200, 36)
    clear.clicked.connect(lambda: panel._call("history_clear"))
    panel._buttons["clear"] = clear


def build_permissions(panel, page) -> None:
    """Board 6: IZIN AKSES, the activity log, and the two buttons under it.

    WHY THIS REPLACED `build_privacy()`, BY OWNER RULING (2026-11-22)
        Two artboards draw "the permissions page" and they are almost disjoint.
        `b06` has `IZIN AKSES`, a 72 px row pitch, a `LOG AKTIVITAS` card and
        `Ekspor log` / `Hapus riwayat`. `n11` (board 06a) has `INDIKATOR
        PRIVASI`, `IZIN EKSPLISIT`, a `MODE TAMU` card and `Hapus semua data
        lokal`.

        `n11` can never be drawn faithfully, and that is why it lost: its MODE
        TAMU card was already deleted by an earlier ruling — guest mode needs
        every surface to stop reading memory and history, and nothing does that
        — so the artboard requires a control this build may not draw. `b06`
        asks for nothing that contradicts a ruling.

    The four permissions are the SAME `PERMISSIONS` rows as board 5, so a switch
    means the same thing on every page.
    """
    from PyQt6.QtWidgets import QLabel, QPushButton
    page.hide()
    panel._pages[PAGE_PRIVACY] = page
    g = GEOMETRY

    panel._labels["p6_head"] = _at(page, QLabel, *g["p6_head"], "")
    panel._labels["p6_sub"] = _at(page, QLabel, *g["p6_sub"], "")
    panel._labels["p6_perm_header"] = _at(
        page, QLabel, *g["p6_perm_header"], _t("ui.panel.section.access"))

    card_x, card_h, card_w = g["p6_card"]
    for index, (key, name, sub) in enumerate(PERMISSIONS):
        y = g["p6_row_y"] + index * g["p6_pitch"]
        card = _at(page, QLabel, card_x, y, card_w, card_h, "")
        card.setStyleSheet(
            f"background:{PALETTES['dark']['card']};"
            f"border:1px solid {PALETTES['dark']['line']};border-radius:12px;")
        panel._labels[f"p6_card:{key}"] = card
        # The ROW is the click target (a 40 px switch is under the 44 px touch
        # target), and the track at x=378 is the readout — the same split board
        # 5 uses, so a permission is toggled the same way on both pages.
        button = QPushButton(_t(name), page)
        button.setCheckable(True)
        button.setGeometry(card_x + 20, y,
                           g["p6_toggle_x"] - card_x - 20, card_h)
        button.setStyleSheet("text-align:left;padding-left:24px;border:none;")
        button.clicked.connect(
            lambda checked=False, k=key: panel.press_permission(k, checked))
        panel._buttons[f"p6:{key}"] = button
        panel._labels[f"p6_sub:{key}"] = _at(
            page, QLabel, g["p6_name"][0], y + g["p6_sub_off"][1], 300, 18, _t(sub))
        track = _at(page, QLabel, g["p6_toggle_x"], y + g["p6_toggle_dy"], 40, 22, "")
        track.setStyleSheet(
            f"background:{PALETTES['dark']['card']};"
            f"border:1px solid {PALETTES['dark']['line']};border-radius:11px;")
        panel._labels[f"perm_dot:{key}"] = track

    panel._labels["p6_log_header"] = _at(
        page, QLabel, *g["p6_log_header"], _t("ui.panel.section.activity"))
    log_card = _at(page, QLabel, *g["p6_log_card"], "")
    log_card.setStyleSheet(
        f"background:{PALETTES['dark']['card']};"
        f"border:1px solid {PALETTES['dark']['line']};border-radius:12px;")
    panel._labels["p6_log_card"] = log_card
    for index in range(3):
        y = g["p6_log_row_y"] + index * g["p6_log_pitch"]
        panel._labels[f"p6_log_time:{index}"] = _at(
            page, QLabel, g["p6_log_time_x"], y - 12, 48, 16, "")
        panel._labels[f"p6_log_text:{index}"] = _at(
            page, QLabel, g["p6_log_text_x"], y - 12, 330, 16, "")

    divider = _at(page, QLabel, *g["p6_divider"], "")
    divider.setStyleSheet(f"background:{PALETTES['dark']['line']};")
    panel._labels["p6_divider"] = divider

    # THE TWO BUTTONS UNDER THE ACTIVITY LOG ACT ON THE ACTIVITY LOG.
    #
    # The artboard labels them "Hapus riwayat" and "Ekspor log", and the same
    # two labels on the HISTORY page mean the undo stack — `clear_history`'s own
    # docstring says it does not erase the audit log, and `export_history` writes
    # `undo.history()`. Wiring board 6's buttons to those handlers would put a
    # button under an activity log that clears a different store, which is the
    # class of lie this build keeps removing.
    #
    # So: same words, the store the card above them shows. The action keys are
    # distinct (`erase` / `export_audit`) so the two pages cannot be confused.
    clear = QPushButton(_t("ui.panel.history.clear"), page)
    clear.setGeometry(*g["p6_clear"])
    clear.clicked.connect(lambda: panel._call("erase"))
    panel._buttons["p6_clear"] = clear
    export = QPushButton(_t("ui.panel.history.export"), page)
    export.setGeometry(*g["p6_export"])
    export.clicked.connect(lambda: panel._call("export_audit"))
    panel._buttons["p6_export"] = export


def _at(parent, cls, x: int, y: int, w: int, h: int, text: str):
    """One positioned label. Six arguments, six copies of `setGeometry` saved."""
    label = cls(parent)
    label.setGeometry(x, y, w, h)
    label.setText(text)
    return label


__all__ = [
    "PAGE_HISTORY", "PAGE_MAIN", "PAGE_PRIVACY", "PAGES", "PALETTES",
    "PANEL_H", "PANEL_W", "build_history", "build_main", "build_permissions",
]
