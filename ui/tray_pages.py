"""The three pages of the tray panel, and the two palettes they are drawn in.

WHY THIS IS A SECOND MODULE
    Boards 5, 23, 26, 27 and 28 are five artboards of ONE 460x660 panel. The
    widget that owns it (`ui/tray_panel.py`) is about lifecycle, dispatch and
    truth; the widgets below are about geometry — a dozen fixed coordinates per
    page, transcribed from the artboard and nowhere else. Splitting them is not
    tidiness: the module ceiling for `ui/` is 600 lines and the panel crossed
    it, which is the rule doing its job.

    It is also the split that makes the palette honest. Board 28 is the SAME
    panel in light colours, so the colours are a table here and the pages read
    it by name. A second widget for the light theme — the obvious way to build
    it — would be two panels to keep in step forever.

WHAT IS IN HERE
    `PALETTES`          dark (boards 5/23/27) and light (board 28), taken from
                        `docs/mockups/build.py` rather than retyped by eye.
    `build_main()`      boards 5 and 23: four quick actions, the quota line,
                        three switches and the command field. The segments and
                        the hold strip live on the panel itself, because both
                        are shared with the other pages' header.
    `build_history()`   board 26: four undoable rows, the audit tail, and the
                        two buttons at the bottom.
    `build_privacy()`   board 27: three indicators, four explicit switches,
                        guest mode, the erase button.

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

    # ── BOARD 27'S PAGE ──────────────────────────────────────────────────
    # Its own keys, because the block above is board 5's main page and is
    # pinned by `tests/test_tray_geometry.py`. Sharing names between two
    # pages is how one of them gets measured against the other's drawing.
    #
    # The artboard gives each of these a card. Without them the three
    # indicator words float loose and the four permissions read as one
    # paragraph instead of four separate decisions.
    "indicator_card":   (24, 102, 132, 62),
    "indicator_pitch":  140,
    "permx_card":       (24, 208, 412, 56),
    "permx_pitch":      66,
}

# Which page the panel is showing. Board 26 and 27 are pages, not other
# windows: a tray panel that spawns three windows is three things to close.
PAGE_MAIN, PAGE_HISTORY, PAGE_PRIVACY = "main", "history", "privacy"
PAGES = (PAGE_MAIN, PAGE_HISTORY, PAGE_PRIVACY)


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
    # Four rows at board 26's pitch, each with its own label and its own
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


def build_privacy(panel, page) -> None:
    from PyQt6.QtWidgets import QLabel, QPushButton
    page.hide()
    panel._pages[PAGE_PRIVACY] = page

    panel._labels["indicator_header"] = _at(
        page, QLabel, 24, 78, 240, 16, _t("ui.panel.section.indicators"))
    g = GEOMETRY
    for index, (key, name, _sub) in enumerate(PERMISSIONS[:3]):
        x = g["indicator_card"][0] + index * g["indicator_pitch"]
        # The card is a label with a border, like the suggestion card on the
        # main page: a QFrame would be a second widget class for the same job.
        card = _at(page, QLabel, *g["indicator_card"], "")
        card.setGeometry(x, g["indicator_card"][1],
                         g["indicator_card"][2], g["indicator_card"][3])
        card.setStyleSheet(
            f"background:{PALETTES['dark']['card']};"
            f"border:1px solid {PALETTES['dark']['line']};border-radius:12px;")
        panel._labels[f"indicator_card:{key}"] = card
        panel._labels[f"indicator:{key}"] = _at(
            page, QLabel, x + 12, 108, 110, 18, _t(name))
        panel._labels[f"indicator_state:{key}"] = _at(
            page, QLabel, x + 12, 138, 110, 18, "")

    panel._labels["permx_header"] = _at(
        page, QLabel, 24, 184, 240, 16, _t("ui.panel.section.explicit"))
    for index, (key, name, sub) in enumerate(PERMISSIONS):
        y = g["permx_card"][1] + index * g["permx_pitch"]
        card = _at(page, QLabel, *g["permx_card"], "")
        card.setGeometry(g["permx_card"][0], y,
                         g["permx_card"][2], g["permx_card"][3])
        card.setStyleSheet(
            f"background:{PALETTES['dark']['card']};"
            f"border:1px solid {PALETTES['dark']['line']};border-radius:12px;")
        panel._labels[f"permx_card:{key}"] = card
        panel._labels[f"permx:{key}"] = _at(
            page, QLabel, 44, y + 10, 300, 20, _t(name))
        panel._labels[f"permx_sub:{key}"] = _at(
            page, QLabel, 44, y + 30, 300, 18, _t(sub))
        button = QPushButton("", page)
        button.setCheckable(True)
        button.setGeometry(378, y + 17, 42, 22)
        button.clicked.connect(
            lambda checked=False, k=key: panel.press_permission(k, checked))
        panel._buttons[f"permx:{key}"] = button

    # MODE TAMU IS NOT DRAWN, AND THAT IS A RULING RATHER THAN AN OVERSIGHT.
    #
    # The artboard draws a "MODE TAMU — Sembunyikan memori & riwayat" switch
    # here. Guest mode needs every surface to stop reading memory and history,
    # and nothing in this tree does that: clicking the switch printed "mode tamu
    # belum ada" and returned False, and the next paint put it back.
    #
    # It is also not drawn DISABLED. A disabled switch still says "this exists
    # and you are not allowed yet", which is a promise about a feature that does
    # not exist. With `screen` and `microphone` the promise is true — the
    # capability is real and the machine decides — so those stay and explain
    # themselves. This one has nothing behind it at all.
    panel._labels["camera_note"] = _at(
        page, QLabel, 24, 566, 412, 18, _t("ui.panel.camera.note"))
    erase = QPushButton(_t("ui.panel.erase"), page)
    erase.setGeometry(24, 590, 412, 38)
    erase.clicked.connect(lambda: panel._call("erase"))
    panel._buttons["erase"] = erase


def _at(parent, cls, x: int, y: int, w: int, h: int, text: str):
    """One positioned label. Six arguments, six copies of `setGeometry` saved."""
    label = cls(parent)
    label.setGeometry(x, y, w, h)
    label.setText(text)
    return label


__all__ = [
    "PAGE_HISTORY", "PAGE_MAIN", "PAGE_PRIVACY", "PAGES", "PALETTES",
    "PANEL_H", "PANEL_W", "build_history", "build_main", "build_privacy",
]
