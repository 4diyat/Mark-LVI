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
from ui.pages_paint_util import (
    _keyed,
    _paint_install_status,
)

def _labels(panel):
    return panel._labels

def paint_memory(panel, snap) -> None:
    """Memori: the section marker, the actions, and the rows the store holds.

    WHAT THIS NO LONGER DOES
        It used to draw exactly `pages_memory.LIST_ROWS` cards, hide the rest,
        and put "dan N lagi" in the band above the divider. That was a truthful
        workaround for a container that could not scroll — and a workaround
        that gets worse as the store grows, because with twelve memories the
        panel showed half and with twelve hundred it would say "dan 1.194 lagi".

        The list is now a scrolling column (`components.scroll_list`) and every
        entry gets a card. `populate_memory` rebuilds it on each paint, because
        `entries()` re-sorts newest-first on every read and a rebuilt list is
        the only version that cannot wire a cross to the wrong memory.

    WHAT THIS STILL DOES
        The section marker, the two pills' labels, and nothing else. The header
        above already carries the count (`b09()` passes "12 hal yang JARVIS
        ingat" to `panel_head`), formatted from the store at snapshot time —
        one count, one place.
    """
    from ui import pages_memory

    labels = _labels(panel)

    # THE COUNT IS THE HEADER'S, NOT THIS PAGE'S: `b09()` passes it to
    # `panel_head()`, rendered in the shared subtitle at (24,54).
    labels["mem_section"].setText(_t("ui.page.memory.section"))

    # THE LIST IS REBUILT FROM THE STORE ON EVERY PAINT. The section marker
    # and the two pills are this page's own frame; the rows are the store's.
    # `populate_memory` clears the column and adds one card per entry (plus a
    # card that states an empty store), because `entries()` re-sorts newest
    # first on every read and a card already carries its own (category, key)
    # pair — so a row can never be wired to a memory the user did not point
    # at, and the list cannot clip: it scrolls.
    pages_memory.populate_memory(panel)

    panel._buttons["mem_add"].setText(_t("ui.page.memory.add"))
    panel._buttons["mem_clear"].setText(_t("ui.page.memory.clear"))

def paint_memory_one(panel, snap) -> None:
    """Board 10: one memory, and four bands the store cannot fill."""
    from ui import pages_memory

    labels = _labels(panel)

    target = panel.target_memory()
    row = pages_memory.find(*target) if target else None

    # BOARD 10 HAS NO `panel_head()`, so it draws its own title at (58,56).
    labels["m1_title"].setText(_t("ui.page.memory_one.title"))

    labels["m1_isi_header"].setText(_t("ui.page.memory_one.isi"))
    if row is None:
        labels["m1_isi_label"].setText("")
        labels["m1_isi_value"].setText(_t("ui.page.memory.gone"))
    else:
        labels["m1_isi_label"].setText(str(row.get("key") or ""))
        labels["m1_isi_value"].setText(str(row.get("value") or ""))

    # The four bands each state their own absence where the control would be.
    for key in ("source", "life"):
        labels[f"m1_{key}_header"].setText(_t(f"ui.page.memory_one.{key}"))
        labels[f"m1_{key}"].setText(_t(f"ui.page.memory_one.{key}_absent"))
    labels["m1_conf_header"].setText(_t("ui.page.memory_one.confidence"))
    labels["m1_conf_track"].setStyleSheet(
        f"background:{PALETTES[panel._theme]['line']};border-radius:1px;")
    labels["m1_conf_note"].setText(_t("ui.page.memory_one.confidence_absent"))
    labels["m1_used_header"].setText(_t("ui.page.memory_one.used"))
    labels["m1_used"].setText(_t("ui.page.memory_one.used_absent"))

    # The two pills. There is no "Simpan": see `build_memory_one`.
    for btn, key in (("m1_forget", "forget"), ("m1_export", "export")):
        panel._buttons[btn].setText(_t(f"ui.page.memory_one.{key}"))
    panel._buttons["m1_forget"].setVisible(row is not None)


__all__ = ["paint_memory", "paint_memory_one"]


# ── boards 11, 12, 13, 7, 19 ─────────────────────────────────────────────────

def paint_routines(panel, snap) -> None:
    from ui import pages_people

    labels = _labels(panel)
    stored = pages_people.routines()
    unavailable = stored is None
    rows = stored or []
    total_pages = max(1, (len(rows) + 2) // 3)
    page = max(0, min(getattr(panel, "_routine_page", 0), total_pages - 1))
    panel._routine_page = page
    visible_rows = rows[page * 3:page * 3 + 3]
    panel._routine_ids = [str(row.get("key") or "") for row in visible_rows]
    pal = PALETTES[getattr(panel, "_theme", "dark")]
    paused = pages_people.suggestion_paused()

    # UP TO THREE ROUTINE CARDS from the store; a card past the store's length
    # says so and disables its controls, matching the artboard's three slots.
    for index in range(3):
        row = visible_rows[index] if index < len(visible_rows) else None
        labels[f"rt_card:{index}"].setStyleSheet(
            f"background:{pal['card']};border-radius:12px;")
        toggle = panel._buttons.get(f"rt_toggle:{index}")
        delete = panel._buttons.get(f"rt_delete:{index}")
        show = row is not None or (not rows and index == 0)
        for part in ("card", "name", "when", "what"):
            labels[f"rt_{part}:{index}"].setVisible(show)
        for ctrl in (toggle, delete):
            if ctrl is not None:
                ctrl.setVisible(row is not None)
        if row is None:
            labels[f"rt_name:{index}"].setText(_t(
                "ui.page.routines.unavailable" if unavailable else "ui.page.routines.empty"))
            labels[f"rt_when:{index}"].setText("")
            labels[f"rt_what:{index}"].setText("")
            for ctrl in (toggle, delete):
                if ctrl is not None:
                    ctrl.setEnabled(False)
        else:
            labels[f"rt_name:{index}"].setText(str(row["name"]))
            labels[f"rt_when:{index}"].setText(str(row["when"]))
            labels[f"rt_what:{index}"].setText(str(row["what"]) or _t("ui.page.routines.no_command"))
            if toggle is not None:
                toggle.setEnabled(bool(row.get("key")))
                toggle.setCheckable(True)
                toggle.setChecked(bool(row["on"]))
                toggle.setText("✓" if row["on"] else "—")
                toggle.setToolTip(_t("ui.page.routines.pause_one") if row["on"]
                                  else _t("ui.page.routines.resume_one"))
                toggle.setAccessibleName(f"{row['name']}: {toggle.toolTip()}")
            if delete is not None:
                delete.setEnabled(bool(row.get("key")))
                delete.setText("×")
                delete.setToolTip(_t("ui.page.routines.delete"))
                delete.setAccessibleName(f"{_t('ui.page.routines.delete')}: {row['name']}")

    # THE BUILDER: one line for the schedule phrase.
    labels["rt_builder_label"].setText(_t("ui.page.routines.daily"))
    labels["rt_builder_note"].setText(_t("ui.page.routines.builder_note"))
    panel._inputs["rt_builder_edit"].setPlaceholderText(_t("ui.page.routines.time_hint"))
    panel._inputs["rt_builder_command"].setPlaceholderText(_t("ui.page.routines.command_hint"))
    create = panel._buttons["rt_builder_create"]
    create.setText(_t("ui.page.routines.create"))
    create.setEnabled(not unavailable)
    labels["rt_suggest_header"].setText(_t("ui.page.routines.suggest"))
    labels["rt_suggest_note"].setText(
        _t("ui.page.routines.no_engine"))
    labels["rt_more"].setText(_t("ui.page.routines.page", page=page + 1,
                                      total=total_pages, count=len(rows))
                              if not unavailable else "")
    for key, enabled in (("prev", page > 0), ("next", page + 1 < total_pages)):
        button = panel._buttons[f"rt_{key}"]
        label = _t(f"ui.page.routines.{key}")
        button.setText("‹" if key == "prev" else "›")
        button.setToolTip(label)
        button.setAccessibleName(label)
        button.setEnabled(enabled and not unavailable)
    labels["rt_footnote"].setText(_t("ui.page.routines.footnote"))
    if (button := panel._buttons.get("rt_pause")) is not None:
        button.setText(_t("ui.page.routines.resume" if paused else "ui.page.routines.pause"))

def paint_tools(panel, snap) -> None:
    from ui import pages_people

    labels = _labels(panel)
    labels["tl_clip_header"].setText(_t("ui.page.tools.clipboard"))
    from ui.clipboard_view import paint_clipboard
    paint_clipboard(panel, pages_people.clipboard_text())
    pal = PALETTES[panel._theme]
    for key in ("tl_clip_card", "tl_find_card", "tl_snap_card"):
        labels[key].setStyleSheet(
            f"background:{pal['card']};border:1px solid {pal['line']};border-radius:12px;")
    labels["tl_clip_box"].setStyleSheet(
        f"background:{pal['panel']};border:1px solid {pal['line']};border-radius:8px;")
    panel._fields["tl_find"].setPlaceholderText(_t("ui.page.tools.find_hint"))
    for key in ("screenshot", "dictate"):
        panel._buttons[f"tl_quick:{key}"].setText(_t(f"ui.panel.quick.{key}"))
    labels["tl_find_header"].setText(_t("ui.page.tools.find"))
    # `hits` is a PROPERTY (a tuple), not a method.
    hits = tuple(getattr(panel, "hits", ()) or ())
    status = getattr(panel, "search_status", "idle")
    status_key = {"idle": "find_idle", "invalid": "find_invalid",
                  "searching": "find_searching", "error": "find_error",
                  "done": "find_none"}.get(status, "find_error")
    for index in range(3):
        label = labels[f"tl_hit:{index}"]
        label.setText(str(hits[index]) if index < len(hits)
                      else (_t(f"ui.page.tools.{status_key}")
                            if index == 0 and not hits else ""))
    labels["tl_snap_header"].setText(_t("ui.page.tools.snap"))
    # The three thumbnails are clickable buttons; the chosen one is checked.
    from actions.window_layout import read_state
    active = read_state()
    for index, mode in enumerate(("columns2", "columns3", "focus")):
        button = panel._buttons[f"tl_snap_thumb:{index}"]
        button.setText(_t(f"ui.page.tools.snap_thumb{index + 1}"))
        button.setCheckable(True)
        button.setChecked(mode == active)
    # The note states the current arrangement, so the card reads as a real
    # choice rather than three unconnected thumbnails.
    labels["tl_snap_note"].setText(_t("ui.page.tools.snap_note",
                                      mode=_t(f"ui.page.tools.snap_{active}")))

def paint_gestures(panel, snap) -> None:
    labels = _labels(panel)
    _keyed(labels, "gs_name", 6, "ui.page.gestures.g1")
    _keyed(labels, "gs_note", 6, "ui.page.gestures.g1.note")
    labels["gs_absent"].setText(_t("ui.page.gestures.absent"))
    labels["gs_note"].setText(_t("ui.page.gestures.note"))

def paint_consent(panel, snap) -> None:
    """Board 7: the four-step onboarding ladder, painted from the panel's flow."""
    from core.onboarding import MIC, PRESENCE, WELCOME, Onboarding

    labels = _labels(panel)
    flow = getattr(panel, "_onboarding", None) or Onboarding.start()
    step = flow.current
    index = flow.current_index

    labels["cn_name"].setText(_t(f"ui.page.consent.{step}.name"))
    labels["cn_body"].setText(_t(f"ui.page.consent.{step}.body"))
    # THE STEP LINE STATES THE ACTUAL LADDER: "Langkah 1 dari 4", not a static
    labels["subtitle"].setText(_t("ui.page.consent.step.of",
                                  n=index + 1, total=flow.total))

    # THE FOUR SEGMENTS ARE THE ARTBOARD'S FOUR-STEP FLOW: each decided step
    accent = PALETTES[panel._theme]["accent"]
    idle = PALETTES[panel._theme]["line"]
    for seg in range(4):
        lit = seg < index or seg == index
        labels[f"cn_step:{seg}"].setStyleSheet(
            f"background:{accent if lit else idle};border-radius:2px;")

    if step == MIC:
        labels["cn_when"].setText(_t("ui.page.consent.mic.when"))
        labels["cn_what_header"].setText(_t("ui.page.consent.what"))
        for i in range(3):
            labels[f"cn_point:{i}"].setText(_t(f"ui.page.consent.point{i + 1}"))
        labels["cn_ack"].setText(_t("ui.page.consent.ack"))
        given = flow.is_done(MIC)
        panel._buttons["cn_toggle"].setChecked(given)
        panel._buttons["cn_allow"].setText(
            _t("ui.page.consent.allow") if not given else _t("ui.page.consent.done"))
        panel._buttons["cn_deny"].setText(_t("ui.page.consent.deny"))
    elif step == PRESENCE:
        labels["cn_when"].setText(_t("ui.page.consent.presence.body"))
        labels["cn_what_header"].setText("")
        for i in range(3):
            labels[f"cn_point:{i}"].setText("")
        picked = getattr(panel, "_onboarding_picked", None)
        mode_key = picked or ""
        labels["cn_ack"].setText(
            _t("ui.page.consent.presence.selected", mode=_t(
                f"ui.page.consent.presence.{mode_key}" if mode_key else "active")))
        panel._buttons["cn_allow"].setText(_t("ui.page.consent.next"))
        panel._buttons["cn_deny"].setText(_t("ui.page.consent.back"))
    elif step == WELCOME:
        for i in range(3):
            labels[f"cn_point:{i}"].setText("")
        labels["cn_when"].setText("")
        labels["cn_what_header"].setText("")
        labels["cn_ack"].setText("")
        panel._buttons["cn_allow"].setText(_t("ui.page.consent.next"))
        panel._buttons["cn_deny"].setText(_t("ui.page.consent.skip"))
    else:  # done: the summary reads the record back.
        labels["cn_when"].setText("")
        labels["cn_what_header"].setText(_t("ui.page.consent.done.name"))
        lines = flow.summary_lines()
        for i in range(3):
            labels[f"cn_point:{i}"].setText(lines[i] if i < len(lines) else "")
        labels["cn_ack"].setText("")
        panel._buttons["cn_allow"].setText(_t("ui.page.consent.finish"))
        panel._buttons["cn_deny"].setText(_t("ui.page.consent.back"))

    labels["cn_card"].setStyleSheet(f"background:{PALETTES[panel._theme]['card']};border-radius:12px;")

def paint_help(panel, snap) -> None:
    """Board 13: three panels, and the form strip that reports review status."""
    labels = _labels(panel)
    labels["hp_dictate_header"].setText(_t("ui.page.help.dictate"))
    labels["hp_dictate"].setText(_t("ui.page.help.dictate.note"))
    labels["hp_read_header"].setText(_t("ui.page.help.read"))
    labels["hp_read"].setText(_t("ui.page.help.read.note"))
    panel._buttons["hp_read"].setText(_t("ui.page.help.read.act"))
    labels["hp_form_header"].setText(_t("ui.page.help.form"))
    for index in range(3):
        labels[f"hp_form_label:{index}"].setText(_t(f"ui.page.help.form_field{index + 1}"))
    labels["hp_form_url_label"].setText(_t("ui.page.help.form_url"))
    panel._buttons["hp_form_apply"].setText(_t("ui.page.help.form_apply"))
    labels["hp_preview"].setText(_form_fill_preview(panel))

def _form_fill_preview(panel) -> str:
    """The preview strip's sentence, driven by the form-fill state."""
    state = getattr(panel, "_form_fill", {})
    status = state.get("status")
    if status == "applied":
        return _t("ui.page.help.form_applied")
    if status == "failed":
        return _t("ui.page.help.form_failed", detail=state.get("detail", ""))
    return _t("ui.page.help.form_reviewed" if status == "reviewed"
              else "ui.page.help.preview")


# ── boards 14, 15, 16, 18, 21, 22 ────────────────────────────────────────────

def paint_security(panel, snap) -> None:
    from ui import pages_admin

    labels = _labels(panel)
    labels["sec_levels_header"].setText(_t("ui.page.security.levels"))
    counts = pages_admin.level_counts()
    # THE GLYPH each level card draws at its right edge (b14): a tick for
    # Aman, an undo arrow for Sedang, an exclamation for Berisiko, in the
    # level's own colour. The cards had the name, note and count but not
    # the marker that says which policy the row carries.
    pal = PALETTES[getattr(panel, "_theme", "dark")]
    glyphs = {"safe": ("✓", pal["accent"]),
              "medium": ("↶", pal["amber"]),
              "risky": ("!", "#f44a42")}
    for index, (level, name_key, note_key) in enumerate(pages_admin.levels()):
        labels[f"sec_name:{index}"].setText(_t(name_key))
        labels[f"sec_note:{index}"].setText(_t(note_key))
        labels[f"sec_count:{index}"].setText(str(counts.get(level, 0)))
        glyph_text, glyph_colour = glyphs.get(level, ("", pal["muted"]))
        glyph = labels.get(f"sec_glyph:{index}")
        if glyph is not None:
            glyph.setText(glyph_text)
            glyph.setStyleSheet(
                f"color:{glyph_colour};background:transparent;"
                f"font-size:16px;font-weight:700;")
    state = getattr(panel, "_os_control", None)  # OS-control state from the panel
    if state is None:
        from actions.os_control import read_state
        enabled = read_state()
        labels["sec_os"].setText(_t("ui.page.security.os_off"))
    else:
        enabled = state.get("enabled", False)
        labels["sec_os"].setText(_t("ui.page.security.os_on") if enabled
                                 else _t("ui.page.security.os_off"))
    os_toggle = panel._buttons.get("sec_os_toggle")
    if os_toggle is not None:
        os_toggle.setChecked(bool(enabled))
        os_toggle.setToolTip(_t("ui.page.security.os.toggle"))
    os_confirm = panel._buttons.get("sec_os_confirm")
    if os_confirm is not None:
        need_confirm = not enabled
        os_confirm.setVisible(need_confirm)
        os_confirm.setText(_t("ui.page.security.os.confirm"))
        os_confirm.setToolTip(
            _t("ui.page.security.os.confirm.tip") if need_confirm else "")

    # VERIFIKASI SUARA: the deleted guest-mode card now carries the voice gate.
    labels["va_header"].setText(_t("ui.page.security.voice_auth"))
    va = str(getattr(snap, "voice_auth", "off") or "off")
    labels["va_status"].setText(_t(f"ui.page.security.voice_auth.{va}"))
    toggle = panel._buttons.get("va_toggle")
    if toggle is not None:
        # Reflects the STORED setting, not the live state (locked is still "on").
        from memory.config_manager import get_voice_auth_enabled
        try:
            toggle.setChecked(bool(get_voice_auth_enabled()))
        except Exception:
            toggle.setChecked(False)
        toggle.setToolTip(_t("ui.page.security.voice_auth.toggle"))
    enroll = panel._buttons.get("va_enroll")
    if enroll is not None:
        enroll.setText(_t("ui.page.security.voice_auth.enroll"))
    delete = panel._buttons.get("va_delete")
    if delete is not None:
        delete.setText(_t("ui.page.security.voice_auth.delete"))
    labels["va_card"].setStyleSheet(
        f"background:{PALETTES[panel._theme]['panel']};border-radius:12px;"
        f"border:1px solid {PALETTES[panel._theme]['amber']};")
    labels["sec_os"].setStyleSheet(
        f"background:{PALETTES[panel._theme]['panel']};border-radius:12px;"
        f"border:1px solid {PALETTES[panel._theme]['panel']};")

def paint_access(panel, snap) -> None:
    from ui import pages_admin

    labels = _labels(panel)
    labels["ac_lang_header"].setText(_t("ui.page.access.language"))
    pal = PALETTES[getattr(panel, "_theme", "dark")]
    labels["ac_lang_track"].setStyleSheet(
        f"background:{pal['panel']};border-radius:19px;border:1px solid {pal['line']};")
    active = pages_admin.active_language()
    from ui.pages_access import language_slots

    for code in language_slots():  # the builder's own order, never reversed
        button = panel._buttons.get(f"ac_lang:{code}")
        if button is not None:
            # THE NAME, NOT THE CODE. `b15()` draws "Indonesia" and "English" in
            button.setText(_t(f"ui.page.access.language.{code}"))
            button.setCheckable(True)
            button.setChecked(code == active)
    # The third slot exists as a disabled label — i18n has no mixed mode.
    mixed = panel._buttons.get("ac_lang:mixed")
    if mixed is not None:
        mixed.setText(_t("ui.page.access.language.mixed_absent"))
    labels["ac_size_header"].setText(_t("ui.page.access.size"))
    # The preference has no renderer: do not claim that text size changed.
    labels["ac_size_note"].setText(_t("ui.page.access.size.unavailable"))
    for key in ("ac_size_track", "ac_size_fill", "ac_size_knob"):
        labels[key].hide()
    panel._buttons["ac_scale"].setEnabled(False)
    labels["ac_contrast_header"].setText(_t("ui.page.access.contrast"))
    pal_c = PALETTES[panel._theme]
    labels["ac_contrast_track"].setStyleSheet(
        f"background:{pal_c['panel']};border-radius:19px;border:1px solid {pal_c['line']};")
    high = bool(getattr(panel, "_high_contrast", False))
    for level in ("standard", "high"):
        button = panel._buttons.get(f"ac_contrast:{level}")
        if button is not None:
            button.setText(_t(f"ui.page.access.contrast.{level}"))
            button.setCheckable(True)
            button.setChecked(high == (level == "high"))
    labels["ac_contrast_note"].setText(
        _t("ui.page.access.contrast.high_note") if high
        else _t("ui.page.access.contrast.standard_note"))
    labels["ac_motion_header"].setText(_t("ui.page.access.motion"))
    labels["ac_motion_card"].setStyleSheet(
        f"background:{PALETTES[panel._theme]['card']};border-radius:12px;")
    labels["ac_motion_name"].setText(_t("ui.page.access.motion.name"))
    labels["ac_motion_note"].setText(_t("ui.page.access.motion.unavailable"))
    motion = panel._buttons["ac_motion"]
    motion.setText("—")
    motion.setEnabled(False)
    labels["ac_gestures_header"].setText(_t("ui.page.access.gestures"))
    from ui import pages_people
    for index, (name_key, _note) in enumerate(pages_people.gesture_rows()[:3]):
        labels[f"ac_gest_card:{index}"].setStyleSheet(
            f"background:{pal['card']};border-radius:12px;")
        labels[f"ac_gest_name:{index}"].setText(_t(name_key))
        labels[f"ac_gest_act:{index}"].setText(_t("ui.page.access.unavailable"))
        edit = panel._buttons[f"ac_gest_edit:{index}"]
        edit.setText("")
        edit.setEnabled(False)
    labels["ac_footnote"].setText(_t("ui.page.access.footnote"))

def paint_plugins(panel, snap) -> None:
    from ui.plugin_panel import paint_plugins as paint
    paint(panel, snap)


def paint_light(panel, snap) -> None:
    """Board 18: board 6's content in whatever palette is on screen."""
    from ui.tray_panel_model import PERMISSIONS

    labels = _labels(panel)
    labels["l18_perm_header"].setText(_t("ui.panel.section.access"))
    # THE CARDS, DOT AND LOG BOX ARE COLOURED FROM THE LIVE PALETTE: `b18()`
    # is board 6 in light tokens, reading the on-screen palette, never its own.
    pal = PALETTES[getattr(panel, "_theme", "dark")]
    for index in range(4):
        labels[f"l18_card:{index}"].setStyleSheet(
            f"background:{pal['card']};border-radius:12px;")
    labels["l18_log_box"].setStyleSheet(f"background:{pal['card']};border-radius:12px;")
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
    # WHICH PALETTE IS ON SCREEN IS A FACT WORTH STATING: board 18 is the
    # light page, but under the dark theme it is the same content in dark.
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
    install = panel._buttons.get("in_install")
    if install is not None:
        install.setText(_t("ui.page.installer.install"))
    _paint_install_status(panel, labels)

