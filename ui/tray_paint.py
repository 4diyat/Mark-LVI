"""What the tray panel DRAWS, given a snapshot. No state, no decisions.

WHY THIS IS A THIRD FILE ABOUT ONE PANEL
    `ui/tray_panel.py` is lifecycle and dispatch, `ui/tray_pages.py` is geometry
    and palettes, and this is the step between them: take one immutable
    `Snapshot` and write it onto widgets that already exist. The split is not
    taste. The panel crossed the 600-line ceiling twice — once when the theme
    control was added, once before — and both times the right answer was that
    "draw" and "open/close/dispatch" are different jobs sharing a file.

WHAT MAKES THIS SAFE TO MOVE
    Every function takes `panel` and touches only `panel._labels`,
    `panel._buttons`, `panel._theme`, `panel._requested` and `panel._page`.
    Nothing here reads the world: `snapshot()` in the model module does that,
    once, before any of this runs. So the panel cannot half-paint itself from
    live state — the failure mode where the mode has changed but the label has
    not.

WHAT A CALLER MUST HAVE
    `labels` and `buttons` filled by the builders in `ui/tray_pages.py`. These
    functions assume the keys exist and let a KeyError through: a missing key is
    a bug in the builder, and a painter that silently skipped it would leave a
    widget saying whatever it said at build time — which is the exact class of
    lie this panel was built to avoid.
"""
from __future__ import annotations

import dataclasses

from ui.tray_pages import GEOMETRY, PALETTES
from ui.tray_theme import _rgba
from ui.tray_panel_model import (ALL_QUICK_KEYS, MODE_ORDER, NAV_ORDER,
                                 NAV_PAGES, PERMISSIONS, _t,
                                 quick_actions_for)
# `quota_note` is called THROUGH the module, not imported by name: the tests
# patch it on `tray_panel_model`, and a by-name import would make that patch
# invisible here — the seam would look tested and paint a stale answer.
from ui import tray_panel_model


def paint(panel, snap) -> None:
    """Put one snapshot on the widgets. Never raises."""
    labels = panel._labels

    # THE PAGE DECIDES THE TWO LINES ABOVE EVERY PAGE, so the snapshot has to
    # know which page it was taken for. Repainting from a snapshot taken at open
    # time would put "JARVIS" back over the privacy page the first time the user
    # clicked a switch — which is exactly how the title bug survived: nothing
    # ever took a second snapshot.
    title_page = getattr(panel, "_page", "main")
    if getattr(snap, "page", "main") != title_page:
        snap = dataclasses.replace(snap, page=title_page)
    labels["title"].setText(snap.title)
    labels["subtitle"].setText(snap.subtitle)
    labels["quota"].setText(snap.quota_line)
    # Empty in every mode but Fokus — `quota_note()` decides, because it is the
    # only thing that knows whether anything is actually being held.
    labels["quota_held"].setText(tray_panel_model.quota_note())
    paint_theme(panel)
    if hasattr(panel, "_render_conversation"):
        panel._render_conversation()
    labels["suggestion"].setText(
        snap.suggestion or _t("ui.panel.suggestion.empty"))

    for mode in MODE_ORDER:
        panel._buttons[f"mode:{mode}"].setChecked(mode == snap.mode)
    mark_segments(panel, snap)
    mark_nav(panel)

    paint_quick(panel, snap)

    # Board 05a's strip: only in Fokus, because only Fokus holds anything.
    held = labels["held"]
    if snap.mode == "focus" and getattr(panel, "_page", "main") == "main":
        # NO DEADLINE LINE. It used to read "Fokus aktif sampai 17.00" with 17.00
        # HARDCODED here — there is no focus duration anywhere in the build, so
        # the panel was stating a time nobody computed. The owner chose the
        # honest sentence: what Fokus does, and how much is waiting.
        held.setText("\n".join((_t("ui.panel.focus.title"),
                                 _t("ui.panel.focus.held"),
                                 snap.held_line)))
        held.show()
    else:
        held.hide()

    for key, name_key, _sub in PERMISSIONS[:3]:
        button = panel._buttons[f"perm:{key}"]
        state = snap.permissions.get(key, {})
        fixed = state.get("fixed", True)
        button.setCheckable(not fixed)
        button.setChecked(bool(state.get("on")) and not fixed)
        button.setEnabled(not fixed)
        button.setText(f"{_t(name_key)}\n{_permission_status(key, state)}")
        _paint_dot(panel, key, state)

    paint_history(panel, snap)
    paint_permissions(panel, snap)
    paint_board_pages(panel, snap)


# WHICH PAINTER RUNS, AND WHY IT IS A TABLE
#
# Every page has a painter, and every open page is repainted on every refresh —
# board 9's count must change when a fact is deleted while the list is on
# screen. Painting ALL of them would read thirteen stores on every keystroke in
# the panel's command field; painting none of them would leave a page showing
# whatever it said when it was built, which is the class of lie this panel was
# built to avoid. So: one table, looked up by the open page, `only`.
#
# The core three pages are painted unconditionally above, as they always were:
# their painters are cheap and `paint_quick`/`paint_history` already run on both
# of them. This table is only the board pages.
_PAGE_PAINTERS = {
    "memory": "paint_memory",
    "memory_one": "paint_memory_one",
    "more": None,                     # its labels are constants; see below
    "routines": "paint_routines",
    "tools": "paint_tools",
    "gestures": "paint_gestures",
    "consent": "paint_consent",
    "help": "paint_help",
    "security": "paint_security",
    "access": "paint_access",
    "plugins": "paint_plugins",
    "light": "paint_light",
    "brand": "paint_brand",
    "installer": "paint_installer",
}


def paint_board_pages(panel, snap) -> None:
    """Paint the open board page, and only it.

    THE MORE-LIST IS PAINTED TOO, and it is the reason this function takes the
    palette seriously: its rows are buttons whose TEXT is a constant, set at
    build time, but the page's own title pair changes with the locale, so it is
    repainted on every locale switch like the rest.
    """
    from ui import pages_paint

    name = getattr(panel, "_page", "main")
    if name == "more":
        _paint_more(panel)
        return
    attr = _PAGE_PAINTERS.get(name)
    if not attr:
        return
    painter = getattr(pages_paint, attr, None)
    if painter is None:
        panel._note(f"no painter for page {name!r}")
        return
    try:
        painter(panel, snap)
    except KeyError as e:
        # A MISSING WIDGET IS A BUILDER BUG and is reported, not swallowed:
        # a painter that skipped a key would leave that widget saying whatever
        # it said at build time.
        panel._note(f"page {name!r} is missing widget {e}")
    except Exception as e:                       # noqa: BLE001
        panel._note(f"page {name!r} would not paint — {type(e).__name__}: {e}")


def _paint_more(panel) -> None:
    """The list of pages: one name and one board number per cell."""
    from ui.page_registry import PAGE_BOARD, PAGE_LABEL, PAGES

    labels = panel._labels
    labels["more_head"].setText(_t("ui.page.more.title"))
    labels["more_sub"].setText(_t("ui.page.more.subtitle", count=len(PAGES)))
    for key, label_key, _title, board in PAGES:
        name = labels.get(f"more_name:{key}")
        if name is not None:
            name.setText(_t(PAGE_LABEL[key]))
            name.setStyleSheet(f"color:{PALETTES[panel._theme]['text']};")
        number = labels.get(f"more_board:{key}")
        if number is not None:
            number.setText(f"BOARD {PAGE_BOARD[key]:02d}")
            number.setStyleSheet(f"color:{PALETTES[panel._theme]['muted']};")
        button = panel._buttons.get(f"more:{key}")
        if button is not None:
            button.setText("")
            button.setAccessibleName(_t(PAGE_LABEL[key]))
    panel._buttons["more_back"].setText(_t("ui.page.more.back"))



def paint_quick(panel, snap) -> None:
    """Board 5's four rows in Aktif/Senyap, board 05a's three in Fokus.

    THE ROWS ARE SET HERE AND NOT AT BUILD TIME, because the list depends on the
    mode and the mode changes while the panel is open. Each widget is looked up
    by ACTION KEY from the union of both lists, so a row that does not exist in
    this mode is hidden rather than emptied — an empty 40 px button is a hole a
    user will click.
    """
    rows = quick_actions_for(snap.mode)
    live = {key for key, _n, _c in rows}
    for key in ALL_QUICK_KEYS:
        button = panel._buttons.get(f"quick:{key}")
        if button is None:
            continue
        if key not in live:
            button.hide()
            continue
        name, chord = "", ""
        for row_key, row_name, row_chord in rows:
            if row_key == key:
                name = _t(row_name)
                chord = (_t(row_chord) if row_chord.startswith("ui.")
                         else snap.quick_chord(row_chord))
                break
        # Cards use a label and description; focus actions use their count.
        button.setText(f"{name}\n{chord}" if chord else name)
        index = next(i for i, row in enumerate(rows) if row[0] == key)
        g = GEOMETRY
        button.setGeometry(g["quick_x"] + (index % 2) * g["quick_column_pitch"],
                           g["quick_row_y"] + (index // 2) * g["quick_pitch"],
                           g["quick_width"], g["quick_row_h"])
        button.show()


def _permission_status(key: str, state: dict) -> str:
    """A capability hint is not proof that OS permission was granted."""
    if not state:
        status = "unknown"
    elif state.get("note") == "unavailable":
        status = "not_available"
    elif key == "screen":
        status = "on_request"
    elif key == "microphone":
        # input_available() is a hint: True includes enumeration failures.
        status = "unknown" if state.get("on") else "not_detected"
    else:
        status = "on" if state.get("on") else "off"
    return _t("ui.panel.chat.status." + status)


def _paint_dot(panel, key: str, state: dict) -> None:
    """The 40x22 track at x=396: cyan with the knob to the right when on.

    IT IS A READOUT, NOT A CONTROL — the row's label is the click target, and
    a second control for one boolean would be two places to disagree. But an
    unlit dot that never moves would be a lie of a worse kind: it would show
    "off" for a permission that is on, which is the exact failure the panel
    was built to avoid. `fixed` (a Microphone that does not exist) draws
    muted, because there is nothing behind the switch to permit.
    """
    dot = panel._labels.get(f"perm_dot:{key}")
    if dot is None:
        return
    pal = PALETTES[panel._theme]
    if state.get("fixed"):
        track, border = pal["card"], pal["line"]
    elif state.get("on"):
        track, border = pal["accent"], pal["accent"]
    else:
        track, border = pal["card"], pal["line"]
    try:
        dot.setStyleSheet(
            f"background:{track};border:1px solid {border};border-radius:11px;")
    except Exception as e:                       # noqa: BLE001
        panel._note(f"permission dot {key!r} refused — {type(e).__name__}: {e}")


def paint_theme(panel) -> None:
    """The header control says which SETTING is on, never which palette.

    "auto" on the button is the truth the user set; the palette it resolved
    to is what they see. A button reading "light" because `auto` happened to
    resolve light is a button that cannot be set back to auto.
    """
    button = panel._buttons.get("theme")
    if button is None:
        return
    mark = {"auto": "A", "dark": "D", "light": "L"}.get(panel._requested, "A")
    try:
        button.setText(mark)
        button.setStyleSheet(
            f"background:transparent;color:{PALETTES[panel._theme]['muted']};"
            f"border:1px solid {PALETTES[panel._theme]['line']};"
            f"border-radius:6px;padding:0;")
    except Exception as e:                       # noqa: BLE001
        panel._note(f"theme control not painted — {type(e).__name__}: {e}")



def mark_segments(panel, snap) -> None:
    """The lit segment is filled; the others are outlines.

    Colour alone is not enough — the active segment also carries the
    heavier weight, so the difference survives a grey-scale screenshot and
    the checked state survives a reader who cannot see the fill.
    """
    pal = PALETTES[panel._theme]
    for mode in MODE_ORDER:
        button = panel._buttons[f"mode:{mode}"]
        if mode == snap.mode:
            button.setStyleSheet(
                f"background:{pal['accent']};color:{pal['on_accent']};"
                f"border:none;border-radius:9px;font-weight:600;")
        else:
            button.setStyleSheet(
                f"background:transparent;color:{pal['muted']};"
                f"border:1px solid {pal['line']};border-radius:9px;")


def mark_nav(panel) -> None:
    """Lit the navigation segment that matches the page on screen.

    Board 5's header carries two segmented controls: the mode selector above
    and the page navigator below. The mode one is filled from the snapshot
    (`mark_segments`); this one is filled from `panel._page`, because the page
    is a panel-owned fact, not a snapshot fact — a navigation click changes the
    page without taking a new snapshot, so the active segment has to follow the
    page itself. Same fill-plus-weight convention, so the difference survives a
    grey-scale screenshot the same way the mode segments do.
    """
    pal = PALETTES[panel._theme]
    current = getattr(panel, "_page", "")
    for key in NAV_ORDER:
        try:
            button = panel._buttons[f"nav:{key}"]
        except KeyError:
            continue
        if NAV_PAGES.get(key) == current:
            button.setStyleSheet(
                f"background:{pal['accent']};color:{pal['on_accent']};"
                f"border:none;border-radius:9px;font-weight:600;")
        else:
            button.setStyleSheet(
                f"background:transparent;color:{pal['muted']};"
                f"border:1px solid {pal['line']};border-radius:9px;")


def paint_history(panel, snap) -> None:
    from ui.history_panel import paint_history as paint
    paint(panel, snap)



def paint_permissions(panel, snap) -> None:
    """Board 6's page: the heading, the four switches, and the activity log.

    THE LOG IS READ HERE RATHER THAN AT BUILD TIME. `core.audit_log` grows while
    the panel is open — an action completes, a permission is refused — and a log
    captured when the page was built would be a screenshot of the past. Three
    rows, newest first, which is what the artboard draws and what
    `core.audit_log.entries()` already returns.
    """
    labels = panel._labels
    # b06's own heading and subtitle, not 06a's: the artboard says
    # "Izin & privatisasi / Semua proses di perangkat", where 06a says
    # "Izin & Privasi / Semua data diproses lokal secara default". Two
    # artboards, two sentences; using one pair for both would draw one of them
    # wrong.
    labels["p6_head"].setText(_t("ui.panel.perm.title"))
    labels["p6_sub"].setText(_t("ui.panel.perm.subtitle"))

    pal = PALETTES[panel._theme]
    for key in ("p6_log_card", *(f"p6_card:{k}" for k, _, _ in PERMISSIONS)):
        labels[key].setStyleSheet(
            f"background:{pal['card']};border:1px solid {pal['line']};border-radius:12px;")
    labels["p6_divider"].setStyleSheet(f"background:{pal['line']};")

    for key, name, sub in PERMISSIONS:
        state = snap.permissions.get(key, {})
        fixed = state.get("fixed", True)
        button = panel._buttons[f"p6:{key}"]
        button.setText(_t(name))
        button.setCheckable(not fixed)
        button.setChecked(bool(state.get("on")) and not fixed)
        button.setEnabled(not fixed)
        button.setStyleSheet(
            f"QPushButton {{background:transparent;color:{pal['text']};border:none;"
            "text-align:left;padding-left:20px;padding-bottom:20px;}"
            f"QPushButton:disabled {{color:{pal['text']};}}"
            f"QPushButton:focus {{border:1px solid {pal['accent']};border-radius:12px;}}")
        labels[f"p6_sub:{key}"].setText(_t(sub))
        labels[f"p6_sub:{key}"].setStyleSheet(f"color:{pal['muted']};")
        status = _permission_status(key, state)
        labels[f"p6_status:{key}"].setText(status)
        labels[f"p6_status:{key}"].setStyleSheet(f"color:{pal['muted']};")
        button.setAccessibleDescription(status)
        _paint_dot(panel, key, state)
        track = labels[f"perm_dot:{key}"]
        track.setVisible(not fixed)
        if not fixed:
            colour = pal['on_accent'] if state.get("on") else pal['muted']
            track.setText("●")
            track.setStyleSheet(
                f"background:{pal['accent'] if state.get('on') else pal['card']};"
                f"border:1px solid {pal['line']};border-radius:11px;color:{colour};")

    lines = _activity_lines()
    for index in range(3):
        when, what = lines[index] if index < len(lines) else ("", "")
        labels[f"p6_log_time:{index}"].setText(when)
        labels[f"p6_log_text:{index}"].setText(
            what or (_t("ui.panel.activity.empty") if index == 0 else ""))


def _activity_lines() -> list[tuple[str, str]]:
    """The newest three audit entries as (time, what), or an empty list.

    `entries()` returns dicts, newest last. The artboard puts the newest at the
    TOP of its little table, so the order is reversed once, here — the same
    convention `tray_panel_model._audit()` uses for board 08a, written twice on
    purpose: the two pages can be drawn in different states and a shared helper
    would have to know which one is asking.
    """
    try:
        from core import audit_log

        entries = audit_log.shared().entries(3) or ()
    except Exception as e:                       # noqa: BLE001
        panel_note = f"activity log unavailable — {type(e).__name__}"
        print(f"[JARVIS] {panel_note}")
        return []
    lines = []
    for item in entries:
        when = str(item.get("at") or item.get("time") or "")[11:19]
        what = " · ".join(str(item.get(k) or "") for k in ("tool", "outcome")
                          if item.get(k))
        detail = str(item.get("detail") or "")
        lines.append((when, f"{what} — {detail}" if detail else what))
    return list(reversed(lines))


def show_page(panel) -> None:
    for name, page in panel._pages.items():
        try:
            page.show() if name == panel._page else page.hide()
        except Exception as e:                   # noqa: BLE001
            panel._note(f"page {name!r} would not switch — {type(e).__name__}: {e}")
    # The full-size page is above the window's shared header in Qt's stacking
    # order. Raise the main controls explicitly; other pages have their own
    # headers and only need a back/close control above them.
    main = getattr(panel, "_page", "") == "main"
    for key in ("title", "subtitle"):
        widget = panel._labels[key]
        visible = (main or panel._page in ("memory", "tools", "access", "routines", "plugins", "help")
                   or (key == "title" and panel._page == "history"))
        widget.setVisible(visible)
        if visible:
            widget.raise_()
    for key in ("theme", *(f"mode:{m}" for m in MODE_ORDER),
                *(f"nav:{n}" for n in NAV_ORDER)):
        widget = panel._buttons[key]
        widget.setVisible(main)
        if main:
            widget.raise_()
    if main:
        panel._labels["held"].raise_()
    back = panel._buttons.get("panel_back")
    close = panel._buttons.get("panel_close")
    if back is not None:
        back.setVisible(panel._page != "main")
        back.raise_()
    if close is not None:
        close.raise_()
    # The active nav segment follows the page, so it is re-marked here as well:
    # a navigation click calls `set_page` → `_show_page`, and `paint` is not
    # guaranteed to run on that path.
    mark_nav(panel)



def apply_style(panel) -> None:
    """One stylesheet for the whole panel, rebuilt when the palette changes.

    Set on the window rather than per widget, so board 17a is a palette swap
    and not a second set of colours in twelve places.
    """
    window = panel._window
    if window is None:
        return
    pal = PALETTES[panel._theme]
    try:
        window.setStyleSheet(f"""
            QWidget {{ background:{pal['panel']};color:{pal['text']}; }}
            QLabel {{ background:transparent;color:{pal['text']}; }}
            QPushButton {{ background:{pal['card']};color:{pal['text']};
                          border:1px solid {pal['line']};border-radius:10px;
                          text-align:left;padding-left:14px; }}
            QPushButton:checked {{ border:1px solid {pal['accent']};
                                  background:{_rgba(pal['accent'], 0.12)}; }}
            QPushButton:disabled {{ color:{pal['muted']}; }}
            QTextEdit {{ background:{pal['card']};color:{pal['text']};
                        border:1px solid {pal['line']};border-radius:10px;
                        padding:8px; }}
            QLineEdit {{ background:{pal['card']};color:{pal['text']};
                        border:1px solid {pal['line']};border-radius:20px;
                        padding-left:18px; }}
        """)
    except Exception as e:                       # noqa: BLE001
        panel._note(f"stylesheet refused — {type(e).__name__}: {e}")
