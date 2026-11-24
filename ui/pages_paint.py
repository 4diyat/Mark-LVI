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
    rows = pages_memory.entries()
    shown = pages_memory.LIST_ROWS

    # THE COUNT IS THE HEADER'S, NOT THIS PAGE'S: `b09()` passes it to
    # `panel_head()`, rendered in the shared subtitle at (24,54).
    labels["mem_section"].setText(_t("ui.page.memory.section"))

    # THE CARDS STAY ON SCREEN EVEN WHEN THE STORE IS EMPTY: hiding them left
    # a header over blank space. An empty list is a fact; an empty PAGE is a
    # bug. The first card carries the nothing-yet sentence.
    for index in range(shown):
        row = rows[index] if index < len(rows) else None
        empty = row is None
        labels[f"mem_card:{index}"].show()
        if empty:
            labels[f"mem_key:{index}"].setText(
                _t("ui.page.memory.empty_row") if index == 0 and not rows else "")
            labels[f"mem_val:{index}"].setText("")
            panel._buttons[f"mem_open:{index}"].hide()
            continue
        labels[f"mem_key:{index}"].setText(str(row.get("key") or ""))
        labels[f"mem_val:{index}"].setText(str(row.get("value") or ""))
        button = panel._buttons[f"mem_open:{index}"]
        button.show()
        button.setText(_t("ui.page.memory.open"))

    # THE REMAINDER IS STATED, NOT HIDDEN: the header counts the store, the
    # list counts the widgets, so showing eight of twelve must say so.
    rest = max(0, len(rows) - shown)
    labels["mem_more"].setText(_t("ui.page.memory.more", count=rest) if rest else "")
    panel._buttons["mem_add"].setText(_t("ui.page.memory.add"))
    panel._buttons["mem_clear"].setText(_t("ui.page.memory.clear"))

def paint_memory_one(panel, snap) -> None:
    """Board 10: one memory, and four bands the store cannot fill.

    The store returns key/value/updated only — no source, lifetime or
    confidence. Each band states its absence at the artboard's coordinates.
    """
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

def _keyed(labels, prefix, count, text_key) -> None:
    """Write each row's text, reading its own i18n key off the label.

    Board 19 and 22 carry a key per row rather than a fixed string, so the
    painter does not have to know which row says what.
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
    pal = PALETTES[getattr(panel, "_theme", "dark")]
    paused = pages_people.suggestion_paused()

    # UP TO THREE ROUTINE CARDS from the store; a card past the store's length
    # says so and disables its controls, matching the artboard's three slots.
    for index in range(3):
        row = rows[index] if index < len(rows) else None
        labels[f"rt_card:{index}"].setStyleSheet(
            f"background:{pal['card']};border-radius:12px;")
        toggle = panel._buttons.get(f"rt_toggle:{index}")
        delete = panel._buttons.get(f"rt_delete:{index}")
        if row is None:
            labels[f"rt_name:{index}"].setText(_t("ui.page.routines.empty"))
            labels[f"rt_when:{index}"].setText("")
            labels[f"rt_what:{index}"].setText("")
            for ctrl in (toggle, delete):
                if ctrl is not None:
                    ctrl.setEnabled(False)
        else:
            labels[f"rt_name:{index}"].setText(str(row["name"]))
            labels[f"rt_when:{index}"].setText(str(row["when"]))
            labels[f"rt_what:{index}"].setText(str(row["what"]))
            if toggle is not None:
                toggle.setEnabled(True)
                toggle.setCheckable(True)
                toggle.setChecked(bool(row["on"]))
                toggle.setToolTip(_t("ui.page.routines.resume") if row["on"]
                                  else _t("ui.page.routines.pause"))
            if delete is not None:
                delete.setEnabled(True)
                delete.setText(_t("ui.page.routines.delete"))

    # THE BUILDER: one line for the schedule phrase.
    labels["rt_builder_label"].setText(_t("ui.page.routines.builder_label"))
    if (create := panel._buttons.get("rt_builder_create")) is not None:
        create.setText(_t("ui.page.routines.create"))
    labels["rt_suggest_header"].setText(_t("ui.page.routines.suggest"))
    labels["rt_suggest_note"].setText(
        _t("ui.page.routines.paused" if paused else "ui.page.routines.no_engine"))
    labels["rt_footnote"].setText(_t("ui.page.routines.footnote"))
    if (button := panel._buttons.get("rt_pause")) is not None:
        button.setText(_t("ui.page.routines.resume" if paused else "ui.page.routines.pause"))

def paint_tools(panel, snap) -> None:
    from ui import pages_people

    labels = _labels(panel)
    labels["tl_clip_header"].setText(_t("ui.page.tools.clipboard"))
    text = pages_people.clipboard_text()
    # THE MARK BELONGS TO THE TEXT, NOT THE PAGE: "safe" was a decision about
    # ONE clipboard, so it never carries to the next. New text, new question.
    if text != getattr(panel, "_marked_text", ""):
        panel._marked_text = text
        panel._marked_safe = False
    labels["tl_clip"].setText(text or _t("ui.page.tools.empty_clip"))
    # "TANDAI AMAN" changes what this line says, or the button does nothing.
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
    # `hits` is a PROPERTY (a tuple), not a method.
    hits = tuple(getattr(panel, "hits", ()) or ())
    for index in range(3):
        label = labels[f"tl_hit:{index}"]
        label.setText(str(hits[index]) if index < len(hits)
                      else (_t("ui.page.tools.find_none") if index == 0 else ""))
    labels["tl_snap_header"].setText(_t("ui.page.tools.snap"))
    # Drawn because the artboard draws it; no window manager sits behind it.
    for index in range(3):
        labels[f"tl_snap_thumb:{index}"].setText(
            _t(f"ui.page.tools.snap_thumb{index + 1}"))
    # The absence sits where the artboard's thumbnails are, not its caption.
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

    # THE FOUR SEGMENTS ARE THE ARTBOARD'S FOUR-STEP FLOW. One step exists, so
    # ONE is lit and the rest are the unfilled track; two lit would claim a
    # step nobody will be shown.
    accent = PALETTES[panel._theme]["accent"]
    idle = PALETTES[panel._theme]["line"]
    for index in range(4):
        labels[f"cn_step:{index}"].setStyleSheet(
            f"background:{accent if index == 0 else idle};border-radius:2px;")

    for index in range(3):
        labels[f"cn_point:{index}"].setText(
            _t(f"ui.page.consent.point{index + 1}"))
    labels["cn_ack"].setText(_t("ui.page.consent.ack"))
    # The toggle is a READOUT of the recorded consent, not a second control.
    toggle = panel._buttons["cn_toggle"]
    toggle.setText("")
    toggle.setChecked(given)
    labels["cn_card"].setStyleSheet(
        f"background:{PALETTES[panel._theme]['card']};border-radius:12px;")
    panel._buttons["cn_allow"].setText(
        _t("ui.page.consent.done") if given else _t("ui.page.consent.allow"))
    panel._buttons["cn_deny"].setText(_t("ui.page.consent.deny"))

def paint_help(panel, snap) -> None:
    """Board 13: three panels, and the form strip that reports review status."""
    labels = _labels(panel)
    labels["hp_dictate_header"].setText(_t("ui.page.help.dictate"))
    labels["hp_dictate"].setText(_t("ui.page.help.dictate.note"))
    labels["hp_read_header"].setText(_t("ui.page.help.read"))
    labels["hp_read"].setText(_t("ui.page.help.read.note"))
    panel._buttons["hp_read"].setText(_t("ui.page.help.read.act"))
    labels["hp_form_header"].setText(_t("ui.page.help.form"))
    # Field rows are editable inputs, so only the strip reports review status.
    for index in range(3):
        labels[f"hp_form_label:{index}"].setText(
            _t(f"ui.page.help.form_field{index + 1}"))
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
    for index, (level, name_key, note_key) in enumerate(pages_admin.levels()):
        labels[f"sec_name:{index}"].setText(_t(name_key))
        labels[f"sec_note:{index}"].setText(_t(note_key))
        labels[f"sec_count:{index}"].setText(str(counts.get(level, 0)))
    # OS-CONTROL absence, stated in the band b14 draws it (header 176).
    labels["sec_os_header"].setText(_t("ui.page.security.os"))
    labels["sec_os"].setText(_t("ui.page.security.os_absent"))

    # VERIFIKASI SUARA: the deleted guest-mode card now carries the voice gate.
    # The guest-mode dot at (378,216) stays absent; the voice switch sits clear
    # of it and its status comes from the snapshot.
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
    labels["sec_os_card"].setStyleSheet(
        f"background:{PALETTES[panel._theme]['panel']};border-radius:12px;"
        f"border:1px solid {PALETTES[panel._theme]['amber']};")

def paint_access(panel, snap) -> None:
    from ui import pages_admin

    labels = _labels(panel)
    labels["ac_lang_header"].setText(_t("ui.page.access.language"))
    pal = PALETTES[getattr(panel, "_theme", "dark")]
    labels["ac_lang_track"].setStyleSheet(
        f"background:{pal['panel']};border-radius:19px;"
        f"border:1px solid {pal['line']};")
    active = pages_admin.active_language()
    from ui.pages_access import language_slots

    # The same order the builder used: two loops that disagree left-to-right
    # is how the slots got reversed in the first place.
    for code in language_slots():
        button = panel._buttons.get(f"ac_lang:{code}")
        if button is not None:
            # THE NAME, NOT THE CODE. `b15()` draws "Indonesia" and "English" in
            # the 137 px slots; "ID"/"EN" was a different word in the same
            # place. The build pass already sets this and the paint pass used to
            # overwrite it with the code — one of the two had to be wrong, and
            # the drawing settles which.
            button.setText(_t(f"ui.page.access.language.{code}"))
            button.setChecked(code == active)
    # THE THIRD SLOT IS DRAWN AND SAYS IT IS UNAVAILABLE: `core.i18n` has no
    # mixed mode, so the third segment exists as a disabled label, not a gap.
    mixed = panel._buttons.get("ac_lang:mixed")
    if mixed is not None:
        mixed.setText(_t("ui.page.access.language.mixed_absent"))
    labels["ac_size_header"].setText(_t("ui.page.access.size"))
    scale = pages_admin.text_scale()
    labels["ac_size_note"].setText(_t("ui.page.access.size.value",
                                      percent=int(round(scale * 100))))
    # THE SLIDER MATCHES b15: a 380 px track whose fill width IS the setting.
    # It is a static bar, not a drag target — the three buttons below change the
    # value — so the artboard's proportions hold without a new control.
    low, high = pages_admin.TEXT_SCALES[0], pages_admin.TEXT_SCALES[-1]
    fraction = 0.0 if high == low else (scale - low) / (high - low)
    labels["ac_size_track"].setStyleSheet(
        f"background:{PALETTES[panel._theme]['line']};border-radius:1px;")
    labels["ac_size_fill"].setStyleSheet(
        f"background:{PALETTES[panel._theme]['accent']};border-radius:1px;")
    labels["ac_size_fill"].setGeometry(24, 194, max(2, round(380 * fraction)), 3)
    # The knob is a 7 px disc centred on the fill's end, as the drawing shows.
    labels["ac_size_knob"].setStyleSheet(
        f"background:{PALETTES[panel._theme]['accent']};border-radius:7px;")
    labels["ac_size_knob"].setGeometry(
        max(17, round(24 + 380 * fraction - 7)), 187, 14, 14)
    for index, value in enumerate(pages_admin.TEXT_SCALES):
        button = panel._buttons.get(f"ac_scale:{index}")
        if button is not None:
            button.setText(f"{int(round(value * 100))}%")
            button.setChecked(abs(value - scale) < 1e-6)
    labels["ac_contrast_header"].setText(_t("ui.page.access.contrast"))
    pal_c = PALETTES[panel._theme]
    labels["ac_contrast_track"].setStyleSheet(
        f"background:{pal_c['panel']};border-radius:19px;"
        f"border:1px solid {pal_c['line']};")
    high = bool(getattr(panel, "_high_contrast", False))
    for level, label_key in (("standard", "ac_contrast_std"),
                             ("high", "ac_contrast_high")):
        button = panel._buttons.get(f"ac_contrast:{level}")
        if button is not None:
            button.setText(_t(f"ui.page.access.contrast.{label_key}"))
            button.setCheckable(True)
            button.setChecked(high and level == "high")
    # The note states what the level does, so a reader who cannot tell the two
    # slots apart still knows which one they chose.
    labels["ac_contrast_note"].setText(
        _t("ui.page.access.contrast.high_note") if high
        else _t("ui.page.access.contrast.standard_note"))
    labels["ac_motion_header"].setText(_t("ui.page.access.motion"))
    labels["ac_motion_card"].setStyleSheet(
        f"background:{PALETTES[panel._theme]['card']};border-radius:12px;")
    labels["ac_motion_name"].setText(_t("ui.page.access.motion.name"))
    labels["ac_motion_note"].setText(_t("ui.page.access.motion.note"))
    # A TOGGLE IS A STATE, NOT A LABEL: `b15()` draws a bare 40x22 pill, and
    # writing "Motion on" inside overflowed and repeated the switch. Text is
    # empty; the checked state carries the answer, the accessible name in the
    # tooltip.
    motion = panel._buttons["ac_motion"]
    motion.setText("")
    motion.setCheckable(True)
    motion.setChecked(pages_admin.reduced_motion())
    motion.setToolTip(
        _t("ui.page.access.motion.off") if pages_admin.reduced_motion()
        else _t("ui.page.access.motion.on"))
    labels["ac_gestures_header"].setText(_t("ui.page.access.gestures"))
    # The artboard draws three gesture rows with a "ubah" affordance each;
    # `core.gesture_os` knows the gestures but no rebinding, so the rows are
    # drawn from it and the third column says what is missing.
    from ui import pages_people

    for index, (name_key, note_key) in enumerate(pages_people.gesture_rows()[:3]):
        labels[f"ac_gest_card:{index}"].setStyleSheet(
            f"background:{PALETTES[panel._theme]['card']};border-radius:12px;")
        labels[f"ac_gest_name:{index}"].setText(_t(name_key))
        # THE MIDDLE COLUMN IS THE ACTION `b15()` DRAWS AS CYAN TEXT. The
        # first version put "fixed" here — a third-column statement in the
        # second column's space. "No rebinding" belongs to the THIRD column.
        labels[f"ac_gest_act:{index}"].setText(_t(note_key))
        # Right-aligned as `b15()` draws its "ubah" at x=416; Qt has no
        # per-label anchor, so the cell ends there and the style finishes it.
        edit = labels[f"ac_gest_edit:{index}"]
        edit.setText(_t("ui.page.access.gestures_rebind_absent"))
        edit.setStyleSheet(f"color:{pal['muted']};")
    labels["ac_footnote"].setText(_t("ui.page.access.footnote"))

def paint_plugins(panel, snap) -> None:
    from ui import pages_admin

    labels = _labels(panel)
    rows = pages_admin.plugin_rows()
    labels["pl_section"].setText(_t("ui.page.plugins.section"))
    # THREE ROWS AS `b16()` DRAWS, the rest counted not crammed: the phone
    # card sits at 360, so a fourth row would land on it. Fifteen would not
    # fit; three silently would hide twelve.
    drawn = 0
    for index, row in enumerate(rows):
        if f"pl_name:{index}" not in labels:
            continue
        drawn += 1
        name = _t(row["label"]) if row.get("label") else row["name"]
        labels[f"pl_name:{index}"].setText(name)
        # THE SECOND LINE IS "version · trust" as the artboard draws it; the
        # description does not fit a 60 px card, so the row omits it. A missing
        # level must not leave a dangling "1.0.0 · " — unreadable gets version.
        version = row.get("version") or "—"
        labels[f"pl_desc:{index}"].setText(
            _t("ui.page.plugins.row", version=version, trust=_t(row["level"]))
            if row.get("level") else
            _t("ui.page.plugins.row.version_only", version=version))
        button = panel._buttons[f"pl_toggle:{index}"]
        button.setText("")
        button.setChecked(bool(row["on"]))
    pal = PALETTES[getattr(panel, "_theme", "dark")]
    for index, row in enumerate(rows[:3]):
        if f"pl_card:{index}" in labels:
            labels[f"pl_card:{index}"].setStyleSheet(
                f"background:{pal['card']};border-radius:12px;")
    # THE UNSHOWN ROWS ARE COUNTED, not dropped: b16 draws three, the build
    # ships fifteen, and the band says how many exist.
    rest = max(0, len(rows) - drawn)
    labels["pl_more"].setText(
        _t("ui.page.plugins.more", count=rest) if rest else "")
    labels["pl_phone_header"].setText(_t("ui.page.plugins.phone"))
    labels["pl_phone_card"].setStyleSheet(
        f"background:{pal['card']};border-radius:12px;")
    labels["pl_phone_shape"].setStyleSheet(
        f"background:{pal['panel']};border-radius:10px;"
        f"border:1px solid {pal['line']};")
    _paint_phone_state(panel, labels, pal)
    labels["pl_code_header"].setText(_t("ui.page.plugins.code"))
    labels["pl_code_box"].setStyleSheet(
        f"background:{pal['card']};border-radius:10px;"
        f"border:1px solid {pal['line']};padding-left:18px;color:{pal['muted']};")
    labels["pl_code_box"].setText(_paint_phone_code(panel))
    if drawn == 0:
        labels["pl_section"].setText(_t("ui.page.plugins.section") + " — 0")

def _paint_phone_state(panel, labels, pal) -> None:
    """Board 16's phone card: paired device, or the idle sentence.

    Reads the panel's pairing state. When a device is paired it names it and
    tints the silhouette accent; otherwise the card states no device and the
    silhouette stays neutral.
    """
    session = getattr(panel, "_phone_pair", None)
    devices = getattr(session, "devices", []) if session is not None else []
    paired = bool(devices)
    fill = pal["accent"] if paired else pal["panel"]
    labels["pl_phone"].setText(
        _t("ui.page.plugins.phone_paired", name=devices[-1].name)
        if paired else _t("ui.page.plugins.phone_idle"))
    labels["pl_phone2"].setText(
        _t("ui.page.plugins.phone_connected_short") if paired else "")
    labels["pl_phone_shape"].setStyleSheet(
        f"background:{fill};border-radius:10px;"
        f"border:1px solid {pal['line']};")

def _paint_phone_code(panel) -> str:
    """Board 16's pairing-code box: the live code, or the no-code sentence."""
    session = getattr(panel, "_phone_pair", None)
    code = getattr(session, "pending_code", None) if session is not None else None
    if code is None:
        return _t("ui.page.plugins.phone_no_code")
    remaining = max(0, int(code.expires_at - session._clock()))
    return _t("ui.page.plugins.phone_code_shown", code=code.code, secs=remaining)

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
    # THE CARDS, DOT AND LOG BOX ARE COLOURED FROM THE LIVE PALETTE: `b18()`
    # is board 6 in light tokens, reading the on-screen palette, never its own.
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

def _paint_install_status(panel, labels) -> None:
    """Board 22's installer strip: the pending count, or the ready sentence."""
    labels["in_status_header"].setText(_t("ui.page.installer.status"))
    state = getattr(panel, "_install_state", None)
    if state is None:
        return
    status = state.get("status")
    if status == "installed":
        labels["in_status"].setText(_t("ui.page.installer.installed"))
    elif status == "running":
        labels["in_status"].setText(
            _t("ui.page.installer.installing", count=state.get("count", 0)))
    else:
        labels["in_status"].setText(
            _t("ui.page.installer.needs_review", count=state.get("count", 0)))
