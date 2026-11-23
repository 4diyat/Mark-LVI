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

from ui.tray_pages import PALETTES
from ui.tray_panel_model import _t


def _labels(panel):
    return panel._labels


def paint_memory(panel, snap) -> None:
    """Board 9: the count, the rows that fit, and the remainder."""
    from ui import pages_memory

    labels = _labels(panel)
    rows = pages_memory.entries()
    shown = pages_memory.LIST_ROWS

    # THE COUNT IS THE HEADER'S, NOT THIS PAGE'S. `b09()` passes it to
    # `panel_head()`, so it renders in the shared subtitle at (24,54) — the
    # page's own second line was a duplicate of it 8 px lower.
    labels["mem_section"].setText(_t("ui.page.memory.section"))

    # THE CARDS STAY ON SCREEN EVEN WHEN THE STORE IS EMPTY. `b09()` draws six
    # of them and hiding every one left the page as a section header over blank
    # space with the key/value labels still visible underneath — the cards were
    # exactly where the artboard puts them and nobody could see them. An empty
    # list is a fact; an empty PAGE is a bug. The first card carries the
    # sentence that says there is nothing yet.
    for index in range(shown):
        row = rows[index] if index < len(rows) else None
        if row is None:
            labels[f"mem_card:{index}"].show()
            labels[f"mem_key:{index}"].setText(
                _t("ui.page.memory.empty_row") if index == 0 and not rows else "")
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
    """Board 10: one memory, and four bands the store cannot fill.

    THREE OF THE ARTBOARD'S BANDS HAVE NO DATA BEHIND THEM. `b10()` draws
    SUMBER (a Otomatis/Manual control), MASA BERLAKU (30 hari / 1 tahun /
    Selamanya) and KEYAKINAN (a slider at 86%) plus DIPAKAI OLEH (three chips).
    `all_entries_for_ui()` returns category, key, value and `updated` — there
    is no source, no lifetime, no confidence and no usage tracking anywhere in
    the store. Each band is drawn at the artboard's coordinates and says in
    that place that the value is not recorded. NO PERCENTAGE IS DRAWN.
    """
    from ui import pages_memory

    labels = _labels(panel)

    target = panel.target_memory()
    row = pages_memory.find(*target) if target else None

    # BOARD 10 HAS NO `panel_head()`, so this is the one board page that draws
    # its own title line — at (58, 56), beside the back chevron the artboard
    # puts at (42, 54).
    labels["m1_title"].setText(_t("ui.page.memory_one.title"))

    labels["m1_isi_header"].setText(_t("ui.page.memory_one.isi"))
    if row is None:
        labels["m1_isi_label"].setText("")
        labels["m1_isi_value"].setText(_t("ui.page.memory.gone"))
    else:
        labels["m1_isi_label"].setText(str(row.get("key") or ""))
        labels["m1_isi_value"].setText(str(row.get("value") or ""))

    # The four bands, each stating its own absence where the control would be.
    labels["m1_source_header"].setText(_t("ui.page.memory_one.source"))
    labels["m1_source"].setText(_t("ui.page.memory_one.source_absent"))
    labels["m1_life_header"].setText(_t("ui.page.memory_one.life"))
    labels["m1_life"].setText(_t("ui.page.memory_one.life_absent"))
    labels["m1_conf_header"].setText(_t("ui.page.memory_one.confidence"))
    labels["m1_conf_track"].setStyleSheet(
        f"background:{PALETTES[panel._theme]['line']};border-radius:1px;")
    labels["m1_conf_note"].setText(_t("ui.page.memory_one.confidence_absent"))
    labels["m1_used_header"].setText(_t("ui.page.memory_one.used"))
    labels["m1_used"].setText(_t("ui.page.memory_one.used_absent"))

    # The two pills. There is no "Simpan": see `build_memory_one`.
    panel._buttons["m1_forget"].setText(_t("ui.page.memory_one.forget"))
    panel._buttons["m1_export"].setText(_t("ui.page.memory_one.export"))
    if row is None:
        panel._buttons["m1_forget"].hide()
    else:
        panel._buttons["m1_forget"].show()


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

    # ONE ROUTINE IS DRAWN, in the first card's geometry. There is no routine
    # store; `routines()` answers with the single real one, and the sentence in
    # the band the other two cards would occupy says why.
    row = rows[0] if rows else None
    if row is None:
        labels["rt_name:0"].setText(_t("ui.page.routines.count", count=0))
        labels["rt_when:0"].setText("")
        labels["rt_what:0"].setText("")
    else:
        labels["rt_name:0"].setText(_t(row["name"]))
        labels["rt_when:0"].setText(_t(row["when"]))
        labels["rt_what:0"].setText(_t(row["what"]))
    labels["rt_absent"].setText(_t("ui.page.routines.no_engine"))

    labels["rt_suggest_header"].setText(_t("ui.page.routines.suggest"))
    labels["rt_suggest_note"].setText(
        _t("ui.page.routines.paused") if pages_people.suggestion_paused()
        else _t("ui.page.routines.no_engine"))
    labels["rt_footnote"].setText(_t("ui.page.routines.footnote"))
    button = panel._buttons["rt_pause"]
    button.setText(_t("ui.page.routines.resume" if pages_people.suggestion_paused()
                      else "ui.page.routines.pause"))


def paint_tools(panel, snap) -> None:
    from ui import pages_people

    labels = _labels(panel)
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
    # The card, its three thumbnails and the sentence all say the same thing:
    # this tool is drawn because the artboard draws it, and there is no window
    # manager behind it.
    for index in range(3):
        labels[f"tl_snap_thumb:{index}"].setText(
            _t(f"ui.page.tools.snap_thumb{index + 1}"))
    labels["tl_snap_absent"].setText(_t("ui.page.tools.snap_absent"))


def paint_gestures(panel, snap) -> None:
    labels = _labels(panel)
    _keyed(labels, "gs_name", 6, "ui.page.gestures.g1")
    _keyed(labels, "gs_note", 6, "ui.page.gestures.g1.note")
    labels["gs_absent"].setText(_t("ui.page.gestures.absent"))
    labels["gs_note"].setText(_t("ui.page.gestures.note"))


def paint_consent(panel, snap) -> None:
    """Board 7: one microphone question, and the segments that say so."""
    from ui import pages_people

    labels = _labels(panel)
    given = pages_people.consent_given()
    labels["cn_name"].setText(_t("ui.page.consent.mic"))
    labels["cn_why"].setText(_t("ui.page.consent.mic.why"))
    labels["cn_when"].setText(_t("ui.page.consent.mic.when"))
    labels["cn_what_header"].setText(_t("ui.page.consent.what"))

    # THE FOUR SEGMENTS ARE THE FOUR-STEP FLOW THE ARTBOARD DRAWS. There is one
    # step, so ONE is lit and the rest are the artboard's unfilled track. Two
    # lit segments would claim a second step nobody will be shown.
    accent = PALETTES[panel._theme]["accent"]
    idle = PALETTES[panel._theme]["line"]
    for index in range(4):
        labels[f"cn_step:{index}"].setStyleSheet(
            f"background:{accent if index == 0 else idle};border-radius:2px;")

    for index in range(3):
        labels[f"cn_point:{index}"].setText(
            _t(f"ui.page.consent.point{index + 1}"))
    labels["cn_ack"].setText(_t("ui.page.consent.ack"))
    # "Saya mengerti" is true only once the consent is recorded; the toggle is
    # a READOUT of that, not a second control that could disagree with it.
    toggle = panel._buttons["cn_toggle"]
    toggle.setText("")
    toggle.setChecked(given)
    labels["cn_card"].setStyleSheet(
        f"background:{PALETTES[panel._theme]['card']};border-radius:12px;")
    panel._buttons["cn_allow"].setText(
        _t("ui.page.consent.done") if given else _t("ui.page.consent.allow"))
    panel._buttons["cn_deny"].setText(_t("ui.page.consent.deny"))


def paint_help(panel, snap) -> None:
    """Board 13: three panels, and the form strip that says nothing is applied."""
    labels = _labels(panel)
    labels["hp_dictate_header"].setText(_t("ui.page.help.dictate"))
    labels["hp_dictate"].setText(_t("ui.page.help.dictate.note"))
    labels["hp_read_header"].setText(_t("ui.page.help.read"))
    labels["hp_read"].setText(_t("ui.page.help.read.note"))
    panel._buttons["hp_read"].setText(_t("ui.page.help.read.act"))
    labels["hp_form_header"].setText(_t("ui.page.help.form"))
    # THE THREE FIELD ROWS KEEP THE ARTBOARD'S GEOMETRY AND CARRY NO VALUES.
    # The artboard fills them with "PT Sinar Abadi", "FB-2026-0912" and
    # "Rp 12.400.000"; there is no form-filling engine, so each row shows its
    # label and the sentence that there is nothing to propose.
    for index in range(3):
        labels[f"hp_form_label:{index}"].setText(
            _t(f"ui.page.help.form_field{index + 1}"))
        labels[f"hp_form_field:{index}"].setText(_t("ui.page.help.form_absent"))
    labels["hp_preview"].setText(_t("ui.page.help.preview"))


# ── boards 14, 15, 16, 18, 21, 22 ────────────────────────────────────────────

def paint_security(panel, snap) -> None:
    from ui import pages_admin

    labels = _labels(panel)
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
    labels["ac_lang_header"].setText(_t("ui.page.access.language"))
    active = pages_admin.active_language()
    for code in ("en", "id"):
        button = panel._buttons.get(f"ac_lang:{code}")
        if button is not None:
            button.setText(code.upper())
            button.setChecked(code == active)
    # THE THIRD SLOT IS DRAWN AND SAYS IT IS NOT AVAILABLE. `core.i18n` ships
    # two catalogues and there is no mixed mode; the artboard draws three
    # segments, so the third exists as a disabled label rather than as a gap
    # where the design has a button.
    mixed = panel._buttons.get("ac_lang:mixed")
    if mixed is not None:
        mixed.setText(_t("ui.page.access.language.mixed_absent"))
    labels["ac_size_header"].setText(_t("ui.page.access.size"))
    scale = pages_admin.text_scale()
    labels["ac_size_note"].setText(_t("ui.page.access.size.value",
                                      percent=int(round(scale * 100))))
    # THE SLIDER IS DRAWN THE WAY b15 DRAWS IT: a 380 px track with a cyan fill
    # whose width IS the setting. It is not a drag target — the three buttons
    # below it are how the value changes — and drawing it as a static bar keeps
    # the artboard's proportions without inventing a control the panel has no
    # room to handle.
    low, high = pages_admin.TEXT_SCALES[0], pages_admin.TEXT_SCALES[-1]
    fraction = 0.0 if high == low else (scale - low) / (high - low)
    labels["ac_size_track"].setStyleSheet(
        f"background:{PALETTES[panel._theme]['line']};border-radius:1px;")
    labels["ac_size_fill"].setStyleSheet(
        f"background:{PALETTES[panel._theme]['accent']};border-radius:1px;")
    labels["ac_size_fill"].setGeometry(24, 194, max(2, round(380 * fraction)), 3)
    for index, value in enumerate(pages_admin.TEXT_SCALES):
        button = panel._buttons.get(f"ac_scale:{index}")
        if button is not None:
            button.setText(f"{int(round(value * 100))}%")
            button.setChecked(abs(value - scale) < 1e-6)
    labels["ac_contrast_header"].setText(_t("ui.page.access.contrast"))
    labels["ac_contrast"].setText(_t("ui.page.access.contrast_absent"))
    labels["ac_motion_header"].setText(_t("ui.page.access.motion"))
    labels["ac_motion_card"].setStyleSheet(
        f"background:{PALETTES[panel._theme]['card']};border-radius:12px;")
    labels["ac_motion_name"].setText(_t("ui.page.access.motion.name"))
    labels["ac_motion_note"].setText(_t("ui.page.access.motion.note"))
    panel._buttons["ac_motion"].setText(
        _t("ui.page.access.motion.off") if pages_admin.reduced_motion()
        else _t("ui.page.access.motion.on"))
    labels["ac_gestures_header"].setText(_t("ui.page.access.gestures"))
    # The artboard draws three gesture rows with a "ubah" affordance on each.
    # `core.gesture_os` knows the gestures but offers no rebinding, so the rows
    # are drawn from it and the third column says what is missing.
    from ui import pages_people

    for index, (name_key, _note_key) in enumerate(pages_people.gesture_rows()[:3]):
        labels[f"ac_gest_card:{index}"].setStyleSheet(
            f"background:{PALETTES[panel._theme]['card']};border-radius:12px;")
        labels[f"ac_gest_name:{index}"].setText(_t(name_key))
        labels[f"ac_gest_act:{index}"].setText(_t("ui.page.access.gestures_rebind_absent"))
    labels["ac_footnote"].setText(_t("ui.page.access.footnote"))


def paint_plugins(panel, snap) -> None:
    from ui import pages_admin

    labels = _labels(panel)
    rows = pages_admin.plugin_rows()
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
    pal = PALETTES[getattr(panel, "_theme", "dark")]
    for index, row in enumerate(rows[:3]):
        if f"pl_card:{index}" in labels:
            labels[f"pl_card:{index}"].setStyleSheet(
                f"background:{pal['card']};border-radius:12px;")
    labels["pl_phone_header"].setText(_t("ui.page.plugins.phone"))
    labels["pl_phone_card"].setStyleSheet(
        f"background:{pal['card']};border-radius:12px;")
    labels["pl_phone_shape"].setStyleSheet(
        f"background:{pal['panel']};border-radius:10px;"
        f"border:1px solid {pal['line']};")
    labels["pl_phone"].setText(_t("ui.page.plugins.phone_absent"))
    labels["pl_phone2"].setText(_t("ui.page.plugins.phone_absent2"))
    labels["pl_code_header"].setText(_t("ui.page.plugins.code"))
    # THE PAIRING CODE IS NOT DRAWN. `b16()` prints "4 7 9 2 1 5"; a code this
    # build never issued is exactly the kind of plausible fake the owner's
    # ruling forbids, so the box says where a code would come from.
    labels["pl_code_box"].setStyleSheet(
        f"background:{pal['card']};border-radius:10px;"
        f"border:1px solid {pal['line']};")
    labels["pl_code_box"].setText(_t("ui.page.plugins.code_absent"))
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
    labels["l18_perm_header"].setText(_t("ui.panel.section.access"))
    # THE CARDS, THE DOT AND THE LOG BOX ARE COLOURED FROM THE LIVE PALETTE.
    # `b18()` is board 6 in light tokens, so the page reads whichever palette
    # is on screen and never carries a colour of its own.
    pal = PALETTES[getattr(panel, "_theme", "dark")]
    for index in range(4):
        labels[f"l18_card:{index}"].setStyleSheet(
            f"background:{pal['card']};border-radius:12px;")
    labels["l18_log_box"].setStyleSheet(
        f"background:{pal['card']};border-radius:12px;")
    for index in range(3):
        labels[f"l18_state:{index}"].setStyleSheet(
            f"background:{pal['card']};border:1px solid {pal['line']};"
            f"border-radius:11px;")
    panel._buttons["l18_clear"].setText(_t("ui.panel.history.clear"))
    panel._buttons["l18_export"].setText(_t("ui.panel.history.export"))
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
    for index, (_key, colour) in enumerate(pages_admin.palette_swatches()):
        labels[f"br_hex:{index}"].setText(colour)
    labels["br_icons_header"].setText(_t("ui.page.brand.icons"))
    _keyed(labels, "br_state_name", 4, "ui.page.brand.state.idle")
    labels["br_app_note"].setText(_t("ui.page.brand.app_note"))
    labels["br_spec"].setText(_t("ui.page.brand.spec"))


def paint_installer(panel, snap) -> None:
    from ui import pages_admin

    labels = _labels(panel)
    labels["in_sub"].setText(_t("ui.page.installer.subtitle"))
    _keyed(labels, "in_name", 3, "ui.page.installer.ambient")
    _keyed(labels, "in_note", 3, "ui.page.installer.ambient.note")
    current = str(getattr(snap, "mode", ""))
    for index, (mode, _n, _d) in enumerate(pages_admin.modes()):
        button = panel._buttons.get(f"in_pick:{index}")
        if button is not None:
            button.setChecked(mode == current)
            button.setText(_t("ui.page.installer.apply"))
