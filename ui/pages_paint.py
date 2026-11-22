"""What the board pages DRAW. Split off `tray_paint` at the 600-line ceiling.

THE SAME BOUNDARY, ONE LEVEL DOWN. `tray_paint` already holds the rule for its
own three pages: read nothing, decide nothing, write one snapshot onto widgets
that exist. Thirteen more pages would have put it past the ceiling and, worse,
would have put thirteen different stores inside the one function that runs on
every refresh. Each painter here is called only when ITS page is the open one,
so a page that is slow cannot make the main page slow.

WHAT A PAINTER MAY READ. The stores are read here and not in the model, because
the model's `Snapshot` is built once per open and these pages must be current
while they are on screen — board 9's count is of what is in memory NOW, and a
user who deletes a fact while looking at the list must see it leave. This is the
same decision `paint_permissions` already documents for the activity log.

NOTHING HERE RAISES. A page whose store is missing draws its empty state; a
panel that dies because `memory_manager` is mid-write is a tray icon that opens
nothing.
"""
from __future__ import annotations

from ui.tray_panel_model import _t


def _labels(panel):
    return panel._labels


def paint_memory(panel, snap) -> None:
    """Board 9: the count, the rows that fit, and the remainder."""
    from ui import pages_memory

    labels = _labels(panel)
    rows = pages_memory.entries()
    shown = pages_memory.LIST_ROWS

    labels["mem_head"].setText(_t("ui.page.memory.title"))
    labels["mem_count"].setText(
        _t("ui.page.memory.count", count=len(rows)) if rows
        else _t("ui.page.memory.empty"))
    labels["mem_section"].setText(_t("ui.page.memory.section"))

    for index in range(shown):
        row = rows[index] if index < len(rows) else None
        if row is None:
            labels[f"mem_card:{index}"].hide()
            labels[f"mem_key:{index}"].setText("")
            labels[f"mem_val:{index}"].setText("")
            panel._buttons[f"mem_open:{index}"].hide()
            continue
        labels[f"mem_card:{index}"].show()
        labels[f"mem_key:{index}"].setText(str(row.get("key") or ""))
        labels[f"mem_val:{index}"].setText(str(row.get("value") or ""))
        button = panel._buttons[f"mem_open:{index}"]
        button.show()
        button.setText(_t("ui.page.memory.open"))

    # THE REMAINDER IS STATED, NOT HIDDEN. The header counts the store; the list
    # counts the widgets. A page that showed eight of twelve and said nothing
    # would be claiming the panel holds everything.
    rest = max(0, len(rows) - shown)
    labels["mem_more"].setText(_t("ui.page.memory.more", count=rest) if rest else "")
    panel._buttons["mem_add"].setText(_t("ui.page.memory.add"))
    panel._buttons["mem_clear"].setText(_t("ui.page.memory.clear"))


def paint_memory_one(panel, snap) -> None:
    """Board 10: one memory, and the three fields this store does not keep."""
    from ui import pages_memory

    labels = _labels(panel)
    labels["m1_head"].setText(_t("ui.page.memory_one.title"))

    target = panel.target_memory()
    row = pages_memory.find(*target) if target else None
    if row is None:
        labels["m1_sub"].setText(_t("ui.page.memory.gone"))
        for index in range(3):
            labels[f"m1_label:{index}"].setText("")
            labels[f"m1_value:{index}"].setText("")
            labels[f"m1_note:{index}"].setText("")
        labels["m1_absent"].setText("")
        panel._buttons["m1_forget"].hide()
        return

    labels["m1_sub"].setText(str(row.get("category") or ""))
    fields = [
        (_t("ui.page.memory.field.category"), str(row.get("category") or "")),
        (_t("ui.page.memory.field.key"), str(row.get("key") or "")),
        (_t("ui.page.memory.field.value"), str(row.get("value") or "")),
    ]
    for index, (name, value) in enumerate(fields):
        labels[f"m1_label:{index}"].setText(name)
        labels[f"m1_value:{index}"].setText(value)
        labels[f"m1_note:{index}"].setText("")

    # The honest line. It is drawn on every memory, not only when something is
    # missing, because what is missing is missing from ALL of them.
    labels["m1_absent"].setText(_t("ui.page.memory.absent"))
    panel._buttons["m1_forget"].show()
    panel._buttons["m1_forget"].setText(_t("ui.page.memory.forget"))
    panel._buttons["m1_back"].setText(_t("ui.page.memory.back"))


__all__ = ["paint_memory", "paint_memory_one"]


# ── boards 11, 12, 13, 7, 19 ─────────────────────────────────────────────────

def _keyed(labels, prefix, count, text_key) -> None:
    """Write `text` into `prefix:0..count-1`, reading each label's own i18n key.

    Board 19's gestures and board 22's modes are drawn from a table and carry a
    key per row rather than a fixed string, so the painter does not have to know
    which row says what — the builder stamped the key on the label.
    """
    for index in range(count):
        widget = labels.get(f"{prefix}:{index}")
        if widget is None:
            continue
        key = getattr(widget, "_key", "") or text_key
        widget.setText(_t(key))


def paint_routines(panel, snap) -> None:
    from ui import pages_people

    labels = _labels(panel)
    rows = pages_people.routines()
    labels["rt_head"].setText(_t("ui.page.routines.title"))
    labels["rt_count"].setText(
        _t("ui.page.routines.count", count=len(rows)))
    labels["rt_section"].setText(_t("ui.page.routines.section"))
    for index, row in enumerate(rows):
        labels[f"rt_name:{index}"].setText(_t(row["name"]))
        labels[f"rt_when:{index}"].setText(_t(row["when"]))
        labels[f"rt_what:{index}"].setText(_t(row["what"]))
    # THE ABSENCE IS STATED WHERE THE READER LOOKS FOR ROUTINES, not only in a
    # doc: the artboard draws three and this build runs one.
    labels["rt_absent"].setText(_t("ui.page.routines.no_engine"))
    labels["rt_suggest_header"].setText(_t("ui.page.routines.suggest"))
    labels["rt_suggest_note"].setText(
        _t("ui.page.routines.paused") if pages_people.suggestion_paused()
        else _t("ui.page.routines.no_engine"))
    button = panel._buttons["rt_pause"]
    button.setText(_t("ui.page.routines.resume" if pages_people.suggestion_paused()
                      else "ui.page.routines.pause"))


def paint_tools(panel, snap) -> None:
    from ui import pages_people

    labels = _labels(panel)
    labels["tl_head"].setText(_t("ui.page.tools.title"))
    labels["tl_clip_header"].setText(_t("ui.page.tools.clipboard"))
    text = pages_people.clipboard_text()
    # THE MARK BELONGS TO THE TEXT, NOT TO THE PAGE. "Marked safe" was a decision
    # about ONE clipboard, and carrying it to the next one would silently clear a
    # secret the user never looked at. New text, new question.
    if text != getattr(panel, "_marked_text", ""):
        panel._marked_text = text
        panel._marked_safe = False
    labels["tl_clip"].setText(text or _t("ui.page.tools.empty_clip"))
    # "TANDAI AMAN" HAS TO CHANGE WHAT THIS LINE SAYS, or the button is a
    # button that does nothing — the exact class of control this build keeps
    # removing. It is a DISPLAY decision and lasts the session: there is no
    # secret scanner, and this program will not vouch for text it never read.
    kind = "" if getattr(panel, "_marked_safe", False) \
        else pages_people.sensitive_kind(text)
    labels["tl_kind"].setText(
        _t("ui.page.tools.sensitive", what=_t(kind)) if kind
        else (_t("ui.page.tools.marked_safe")
              if getattr(panel, "_marked_safe", False)
              else _t("ui.page.tools.not_sensitive")))
    for name, label_key in (("copy", "ui.page.tools.copy"),
                            ("safe", "ui.page.tools.mark_safe"),
                            ("clear", "ui.page.tools.clear")):
        panel._buttons[f"tl_{name}"].setText(_t(label_key))
    labels["tl_find_header"].setText(_t("ui.page.tools.find"))
    # `hits` is a PROPERTY on the panel, not a method: `hasattr` alone would not
    # catch the difference, and calling a tuple is a TypeError at paint time —
    # which is exactly how this line failed the first time it ran.
    hits = tuple(getattr(panel, "hits", ()) or ())
    for index in range(3):
        label = labels[f"tl_hit:{index}"]
        label.setText(str(hits[index]) if index < len(hits)
                      else (_t("ui.page.tools.find_none") if index == 0 else ""))
    labels["tl_snap_header"].setText(_t("ui.page.tools.snap"))
    labels["tl_snap_absent"].setText(_t("ui.page.tools.snap_absent"))


def paint_gestures(panel, snap) -> None:
    labels = _labels(panel)
    labels["gs_head"].setText(_t("ui.page.gestures.title"))
    _keyed(labels, "gs_name", 6, "ui.page.gestures.g1")
    _keyed(labels, "gs_note", 6, "ui.page.gestures.g1.note")
    labels["gs_absent"].setText(_t("ui.page.gestures.absent"))
    labels["gs_note"].setText(_t("ui.page.gestures.note"))


def paint_consent(panel, snap) -> None:
    from ui import pages_people

    labels = _labels(panel)
    labels["cn_head"].setText(_t("ui.page.consent.title"))
    labels["cn_step"].setText(_t("ui.page.consent.step"))
    labels["cn_name"].setText(_t("ui.page.consent.mic"))
    labels["cn_why"].setText(_t("ui.page.consent.mic.why"))
    labels["cn_when"].setText(_t("ui.page.consent.mic.when"))
    labels["cn_done"].setText(
        _t("ui.page.consent.done") if pages_people.consent_given()
        else _t("ui.page.consent.why_one_step"))
    panel._buttons["cn_allow"].setText(_t("ui.page.consent.allow"))
    panel._buttons["cn_deny"].setText(_t("ui.page.consent.deny"))


def paint_help(panel, snap) -> None:
    labels = _labels(panel)
    labels["hp_head"].setText(_t("ui.page.help.title"))
    labels["hp_dictate_header"].setText(_t("ui.page.help.dictate"))
    labels["hp_dictate"].setText(_t("ui.page.help.dictate.note"))
    labels["hp_read_header"].setText(_t("ui.page.help.read"))
    labels["hp_read"].setText(_t("ui.page.help.read.note"))
    labels["hp_form_header"].setText(_t("ui.page.help.form"))
    labels["hp_form_absent"].setText(_t("ui.page.help.form_absent"))


# ── boards 14, 15, 16, 18, 21, 22 ────────────────────────────────────────────

def paint_security(panel, snap) -> None:
    from ui import pages_admin

    labels = _labels(panel)
    labels["sec_head"].setText(_t("ui.page.security.title"))
    labels["sec_levels_header"].setText(_t("ui.page.security.levels"))
    counts = pages_admin.level_counts()
    for index, (level, name_key, note_key) in enumerate(pages_admin.levels()):
        labels[f"sec_name:{index}"].setText(_t(name_key))
        labels[f"sec_note:{index}"].setText(_t(note_key))
        labels[f"sec_count:{index}"].setText(str(counts.get(level, 0)))
    # TWO THINGS BOARD 14 DRAWS THAT ARE NOT BUILT — and one of them may not be
    # drawn at all. The artboard has a MODE TAMU card; the owner's ruling deleted
    # guest mode, and `tests/test_privacy_board27.py` enforces the SHAPE of that
    # ruling: not even a disabled switch, because a disabled switch says "this
    # exists and you may not use it yet". So both absences are stated in one
    # sentence under the OS-control heading, and no widget carries the word.
    labels["sec_os_header"].setText(_t("ui.page.security.os"))
    labels["sec_os"].setText(_t("ui.page.security.os_and_guest_absent"))


def paint_access(panel, snap) -> None:
    from ui import pages_admin

    labels = _labels(panel)
    labels["ac_head"].setText(_t("ui.page.access.title"))
    labels["ac_lang_header"].setText(_t("ui.page.access.language"))
    active = pages_admin.active_language()
    for code in ("en", "id"):
        button = panel._buttons.get(f"ac_lang:{code}")
        if button is not None:
            button.setChecked(code == active)
    labels["ac_size_header"].setText(_t("ui.page.access.size"))
    labels["ac_size_note"].setText(_t("ui.page.access.size.note"))
    scale = pages_admin.text_scale()
    for index, value in enumerate(pages_admin.TEXT_SCALES):
        button = panel._buttons.get(f"ac_scale:{index}")
        if button is not None:
            button.setText(f"{int(round(value * 100))}%")
            button.setChecked(abs(value - scale) < 1e-6)
    labels["ac_motion_header"].setText(_t("ui.page.access.motion"))
    panel._buttons["ac_motion"].setText(
        _t("ui.page.access.motion.off") if pages_admin.reduced_motion()
        else _t("ui.page.access.motion.on"))
    labels["ac_gestures_header"].setText(_t("ui.page.access.gestures"))
    labels["ac_gestures"].setText(_t("ui.page.access.gestures_absent"))


def paint_plugins(panel, snap) -> None:
    from ui import pages_admin

    labels = _labels(panel)
    rows = pages_admin.plugin_rows()
    labels["pl_head"].setText(_t("ui.page.plugins.title"))
    labels["pl_count"].setText(_t("ui.page.plugins.count",
                                  count=sum(1 for r in rows if r["on"]),
                                  total=len(rows)))
    labels["pl_section"].setText(_t("ui.page.plugins.section"))
    drawn = 0
    for index, row in enumerate(rows):
        if f"pl_name:{index}" not in labels:
            continue
        drawn += 1
        labels[f"pl_name:{index}"].setText(row["name"])
        labels[f"pl_desc:{index}"].setText(row["description"])
        button = panel._buttons[f"pl_toggle:{index}"]
        button.setText("ON" if row["on"] else "OFF")
        button.setChecked(bool(row["on"]))
    labels["pl_phone_header"].setText(_t("ui.page.plugins.phone"))
    labels["pl_phone"].setText(_t("ui.page.plugins.phone_absent"))
    labels["pl_phone2"].setText(_t("ui.page.plugins.phone_absent2"))
    if drawn == 0:
        labels["pl_section"].setText(_t("ui.page.plugins.section") + " — 0")


def paint_light(panel, snap) -> None:
    """Board 18: board 6's content in whatever palette is on screen.

    IT READS THE PALETTE THROUGH `panel._theme`, so opening board 18 while the
    light theme is on shows exactly board 6 in light — which is what the
    artboard is: the same page, the same words, different tokens. Opening it in
    dark shows board 6 in dark, and the page says which palette it drew.
    """
    from ui.tray_panel_model import PERMISSIONS

    labels = _labels(panel)
    labels["l18_head"].setText(_t("ui.page.light.title"))
    labels["l18_sub"].setText(_t("ui.page.light.subtitle"))
    labels["l18_perm_header"].setText(_t("ui.panel.section.access"))
    for index, (key, name_key, sub_key) in enumerate(PERMISSIONS):
        state = getattr(snap, "permissions", {}).get(key, {})
        labels[f"l18_name:{index}"].setText(_t(name_key))
        labels[f"l18_sub_name:{index}"].setText(_t(sub_key))
        labels[f"l18_state:{index}"].setText("ON" if state.get("on") else "OFF")
    labels["l18_log_header"].setText(_t("ui.panel.section.activity"))
    from ui.tray_paint import _activity_lines

    lines = _activity_lines()
    for index in range(3):
        when, what = lines[index] if index < len(lines) else ("", "")
        labels[f"l18_log:{index}"].setText(f"{when}  {what}".strip())
    # WHICH PALETTE IS ON SCREEN IS A FACT WORTH STATING. Board 18 is the light
    # permission page; opened while the dark theme is active it is the same
    # content in dark, and a page that said nothing would let a reader believe
    # they were looking at the light design.
    palette_name = "light" if getattr(panel, "_theme", "dark") == "light" else "dark"
    labels["l18_note"].setText(
        _t("ui.page.light.drawn_light") if palette_name == "light"
        else _t("ui.page.light.drawn_dark"))


def paint_brand(panel, snap) -> None:
    from ui import pages_admin

    labels = _labels(panel)
    labels["br_head"].setText(_t("ui.page.brand.title_line"))
    for index, (_key, colour) in enumerate(pages_admin.palette_swatches()):
        labels[f"br_hex:{index}"].setText(colour)
    labels["br_icons_header"].setText(_t("ui.page.brand.icons"))
    _keyed(labels, "br_state_name", 4, "ui.page.brand.state.idle")
    labels["br_app_note"].setText(_t("ui.page.brand.app_note"))
    labels["br_spec"].setText(_t("ui.page.brand.spec"))


def paint_installer(panel, snap) -> None:
    from ui import pages_admin

    labels = _labels(panel)
    labels["in_head"].setText(_t("ui.page.installer.name"))
    labels["in_sub"].setText(_t("ui.page.installer.subtitle"))
    _keyed(labels, "in_name", 3, "ui.page.installer.ambient")
    _keyed(labels, "in_note", 3, "ui.page.installer.ambient.note")
    current = str(getattr(snap, "mode", ""))
    for index, (mode, _n, _d) in enumerate(pages_admin.modes()):
        button = panel._buttons.get(f"in_pick:{index}")
        if button is not None:
            button.setChecked(mode == current)
            button.setText(_t("ui.page.installer.apply"))
