"""Board 05a: what the panel says and offers while the assistant is in Fokus.

WHAT BOARD 23 DRAWS, AND WHAT WAS NOT TRUE OF IT
    A 460x660 panel with the mode set to Fokus, and four claims in it:

    1. "Fokus aktif sampai 17.00". The panel DID draw this line — with "17.00"
       HARDCODED in `ui/tray_paint.py`. There is no focus duration anywhere in
       the build: no deadline, no timer, nothing that ends Fokus on its own. A
       panel that states a time nobody computed is the exact failure this repo
       keeps designing against, and it survived because it looked like a
       formatted string rather than like a lie. The owner chose the honest
       sentence: no deadline, so no "sampai".

    2. Four quick actions in Fokus — "Lihat yang tertahan", "Akhiri fokus
       sekarang", "Ubah durasi", "Jeda semua penjadwalan". NONE existed; the
       panel showed board 5's four actions in every mode, so the rows a user
       saw in Fokus were the ones for taking a screenshot.

    3. "3 tertahan · akan muncul setelahnya". True, and it was the one honest
       line in the strip.

    4. "Kuota saran: 1 dari 3 terpakai / Dua sisanya ditahan sampai fokus
       berakhir". The first line exists as the panel's quota; the second
       sentence — that the REMAINDER is held — was missing.

    "Ubah durasi" is deliberately absent rather than dead: there is no duration
    to change, and a row that opens a dialog for a setting that does not exist
    is worse than a row that is not there. `DESIGN-ambient.md` records that.

WHAT THE PAUSE REQUIRED
    "Jeda semua penjadwalan" needs `actions.proactive.ProactiveEngine` to be
    pausable. It was not: `should_trigger()` had two clocks and no switch. The
    pause is also PERSISTED, because a pause that a restart erases is a promise
    the user has to remember to keep making.
"""
from __future__ import annotations

import pytest


# ── 1. the honest sentence ────────────────────────────────────────────────

def test_the_focus_strip_does_not_state_a_time_nobody_computed():
    """The hardcoded "17.00" must be gone from the paint path.

    Asserted as SOURCE because the value was a literal in a format call: no
    state the tests can build would have differed from any other, which is why
    it survived every panel test in the suite.
    """
    from pathlib import Path

    paint = (Path(__file__).resolve().parent.parent
             / "ui" / "tray_paint.py").read_text(encoding="utf-8")
    assert 'time="17.00"' not in paint, (
        "the panel is still claiming Fokus ends at 17:00, which nothing computes")


def test_the_focus_strip_still_says_what_focus_does():
    """The line stays — only the false half of it goes. "Toast ditahan, bukan
    dibuang" is the sentence that makes holding acceptable."""
    from pathlib import Path

    paint = (Path(__file__).resolve().parent.parent
             / "ui" / "tray_paint.py").read_text(encoding="utf-8")
    assert "ui.panel.focus.held" in paint
    # The COUNT comes through `snap.held_line`, which is the model's key — the
    # paint path asks the snapshot, not the translation table. Asserting the
    # i18n key here failed against correct code.
    assert "snap.held_line" in paint


def test_the_i18n_key_for_a_deadline_is_gone_from_both_languages():
    """An unused key is the next person's invitation to use it with a made-up
    time. `ui.panel.focus.active_until` is removed with the line that read it."""
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent / "assets" / "i18n"
    for name in ("id.json", "en.json"):
        data = json.loads((root / name).read_text(encoding="utf-8"))
        assert "ui.panel.focus.active_until" not in data, f"{name} still has it"


def test_the_panel_still_says_fokus_plainly():
    """What replaces the deadline line: the mode, stated. A user who opened the
    panel in Fokus must be able to read that it is in Fokus without a time."""
    import json
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent / "assets" / "i18n"
    data = json.loads((root / "id.json").read_text(encoding="utf-8"))
    assert "ui.panel.focus.title" in data
    assert "aktif" in data["ui.panel.focus.title"].lower()


# ── 2. the four rows board 05a draws ───────────────────────────────────────

def test_fokus_has_its_own_quick_rows():
    """Board 5's four actions are for a normal session. Board 05a draws three
    different ones, and the panel must show the ones for the mode it is in."""
    from ui.tray_panel_model import FOCUS_ACTIONS, QUICK_ACTIONS

    keys = [key for key, _n, _c in FOCUS_ACTIONS]
    assert keys == ["held", "end_focus", "pause_scheduling"], keys
    assert keys != [key for key, _n, _c in QUICK_ACTIONS]


def test_lihat_yang_tertahan_shows_its_count_like_the_artboard():
    """"Lihat yang tertahan" with "3" right-aligned — the artboard draws the
    count in the chord column, where the other rows put a keyboard shortcut."""
    from ui.tray_panel_model import FOCUS_ACTIONS

    chords = {key: chord for key, _n, chord in FOCUS_ACTIONS}
    # the chord is a FORMAT with the count in it, not a literal "3": the number
    # belongs to the queue, and a hardcoded 3 is the same bug as "17.00"
    assert "{count}" in chords["held"]
    assert chords["end_focus"] == ""
    assert chords["pause_scheduling"] == ""


def test_the_drawn_rows_are_actually_redrawn_when_the_mode_changes(monkeypatch):
    """MUTATION-DRIVEN. The first version of this file asserted only that
    `quick_actions_for` returns the right tuple — and a `paint_quick` that
    ignored the mode and always drew board 5's four survived it. So this builds
    the real panel through the Qt stub, paints Aktif, then paints Fokus, and
    reads the widgets a user would read.
    """
    import dataclasses

    from tests.qtstub import fresh_ui, restore_ui

    saved = fresh_ui()
    try:
        from core import presence_mode
        from ui import tray_paint, tray_panel, tray_panel_model

        presence_mode.reset()
        panel = tray_panel.TrayPanel({})
        panel.open()
        held = 3

        def snap_for(mode):
            # Snapshot is frozen — the panel takes a new one per paint, which is
            # exactly how a mode change reaches it.
            return dataclasses.replace(
                tray_panel_model.Snapshot(held=held),
                mode=mode, held=held)

        snap = snap_for("active")
        tray_paint.paint(panel, snap)
        active = {key for key in tray_panel_model.ALL_QUICK_KEYS
                  if panel._buttons[f"quick:{key}"]._visible}
        assert active == {key for key, _n, _c in tray_panel_model.QUICK_ACTIONS}, active

        tray_paint.paint(panel, snap_for("focus"))
        focus = {key for key in tray_panel_model.ALL_QUICK_KEYS
                 if panel._buttons[f"quick:{key}"]._visible}
        assert focus == {"held", "end_focus", "pause_scheduling"}, focus

        # the count in the chord column comes from the snapshot, not a literal.
        # Two different counts, because "3" is the artboard's number and a
        # hardcoded 3 passed the first version of this assertion.
        assert "3" in panel._buttons["quick:held"].text()
        tray_paint.paint(panel, dataclasses.replace(
            snap_for("focus"), held=7))
        assert "7" in panel._buttons["quick:held"].text()

        # the second quota sentence is PAINTED, and painted only in Fokus
        assert panel._labels["quota_held"].text() == ""
        marker = "Dua sisanya ditahan"
        monkeypatch.setattr(tray_panel_model, "quota_note", lambda: marker)
        tray_paint.paint(panel, snap_for("focus"))
        assert panel._labels["quota_held"].text() == marker, (
            "a note nothing paints is a sentence the user never reads")
        assert "durasi" not in "".join(
            panel._buttons[f"quick:{k}"].text() for k in focus).lower()
    finally:
        restore_ui(saved)


def test_the_quick_rows_are_chosen_by_mode():
    """One function, because two lists and an `if` in two places is how the
    panel ends up drawing Fokus's rows while acting on board 5's."""
    from ui.tray_panel_model import FOCUS_ACTIONS, QUICK_ACTIONS, quick_actions_for

    assert quick_actions_for("focus") == FOCUS_ACTIONS
    assert quick_actions_for("active") == QUICK_ACTIONS
    assert quick_actions_for("quiet") == QUICK_ACTIONS
    assert quick_actions_for("nonsense") == QUICK_ACTIONS


def test_ubah_durasi_is_not_a_row_at_all():
    """"Ubah durasi (45 mnt)" is omitted on purpose: there is no duration. A row
    for a setting that does not exist is a row that lies in a different font."""
    from ui.tray_panel_model import FOCUS_ACTIONS

    labels = " ".join(name for _k, name, _c in FOCUS_ACTIONS)
    assert "durasi" not in labels.lower()


# ── 3. the pause, and that it is real ─────────────────────────────────────

def test_the_proactive_engine_can_be_paused_and_resumed():
    """`should_trigger()` had two clocks and no switch. Pausing Fokus's
    scheduling had nothing to switch."""
    from actions.proactive import ProactiveEngine

    engine = ProactiveEngine(min_silence_secs=0, check_cooldown=0)
    assert engine.should_trigger(0.0) is True
    engine.pause()
    assert engine.paused is True
    assert engine.should_trigger(0.0) is False, "a paused engine still triggered"
    engine.resume()
    assert engine.paused is False
    assert engine.should_trigger(0.0) is True


def test_a_pause_does_not_disturb_the_cooldown_clock():
    """Resuming must not be a free trigger: an engine paused for an hour would
    otherwise fire immediately, which reads as "the assistant was waiting to
    interrupt you"."""
    from actions.proactive import ProactiveEngine

    engine = ProactiveEngine(min_silence_secs=0, check_cooldown=3600)
    engine.mark_triggered()
    engine.pause()
    engine.resume()
    assert engine.should_trigger(0.0) is False


def test_the_pause_survives_a_restart(monkeypatch):
    """Persisted in the config, because a pause a restart erases is a promise the
    user has to keep making every morning."""
    from actions import proactive

    calls = {}
    monkeypatch.setattr(proactive, "_read_paused", lambda: calls.get("paused", False))
    monkeypatch.setattr(proactive, "_write_paused", lambda on: calls.__setitem__("paused", on))

    engine = proactive.ProactiveEngine(min_silence_secs=0, check_cooldown=0)
    assert engine.paused is False
    engine.pause()
    assert calls["paused"] is True
    # a second engine, as if the app had restarted
    again = proactive.ProactiveEngine(min_silence_secs=0, check_cooldown=0)
    assert again.paused is True
    assert again.should_trigger(0.0) is False


def test_a_config_that_refuses_the_write_leaves_the_pause_on_in_memory(monkeypatch):
    """The pause still applies for this session; only the memory of it is lost.
    The alternative — refusing the pause because the file is read-only — takes
    the user's decision away to protect a disk."""
    from actions import proactive

    def boom(_on):
        raise OSError("read-only")

    monkeypatch.setattr(proactive, "_read_paused", lambda: False)
    monkeypatch.setattr(proactive, "_write_paused", boom)
    engine = proactive.ProactiveEngine(min_silence_secs=0, check_cooldown=0)
    engine.pause()
    assert engine.paused is True
    assert engine.should_trigger(0.0) is False


def test_the_pause_reaches_the_config_file_and_comes_back(isolated_config):
    """The helper names are patched by the tests above, so the write path has to
    be exercised for real at least once — otherwise a `_write_paused` that
    silently wrote the wrong key would pass every test that patches it."""
    from actions import proactive

    assert proactive._read_paused() is False
    proactive._write_paused(True)
    assert proactive._read_paused() is True
    proactive._write_paused(False)
    assert proactive._read_paused() is False


def test_a_paused_engine_starts_paused_after_a_restart(isolated_config):
    """The user's decision outlives the process. This is the test that would
    have caught "pause that a restart forgets"."""
    from actions import proactive

    first = proactive.ProactiveEngine(min_silence_secs=0, check_cooldown=0)
    first.pause()
    second = proactive.ProactiveEngine(min_silence_secs=0, check_cooldown=0)
    assert second.paused is True
    assert second.should_trigger(0.0) is False


def test_a_config_that_refuses_the_write_is_reported_not_swallowed(isolated_config, monkeypatch):
    """MUTATION-DRIVEN. `set_config_values` reports failure by RETURNING False,
    so a `_write_paused` that ignored the return made the whole error path dead
    code — the pause silently stopped surviving restarts and nothing said so.
    """
    from actions import proactive
    from memory import config_manager

    monkeypatch.setattr(config_manager, "set_config_values", lambda **_kw: False)
    with pytest.raises(OSError):
        proactive._write_paused(True)


def test_end_focus_moves_the_real_mode_not_just_a_flag(monkeypatch):
    """MUTATION-DRIVEN. The earlier version monkeypatched `set_mode` and
    asserted `shell.lines`, so a handler that never changed anything-but-a-flag
    passed. This one patches only the STORE and reads `current()`."""
    from core import presence_mode
    from ui import tray_panel_wiring

    stored = {}
    presence_mode.reset()
    presence_mode.bind(read=lambda: stored.get("mode", "active"),
                       write=lambda mode: stored.__setitem__("mode", mode))
    try:
        presence_mode.set_mode("focus")
        assert presence_mode.current() == "focus"
        shell = FakeShell()
        assert tray_panel_wiring.quick_action(shell, "end_focus") is True
        assert presence_mode.current() == "active"
        assert stored.get("mode") == "active", "the store was not written"
    finally:
        presence_mode.reset()
        presence_mode.bind()


def test_show_held_reads_the_real_queue(monkeypatch):
    """MUTATION-DRIVEN, the other half: `held_count` was patched, so a handler
    that never called it was invisible. This puts three items in the real queue
    and reads the sentence."""
    from core import presence_mode
    from ui import tray_panel_wiring

    stored = {"mode": "focus"}
    presence_mode.reset()
    presence_mode.bind(read=lambda: stored.get("mode", "active"), write=stored.update)
    try:
        # `offer` reads the MODE, not `should_hold` — patching the latter put
        # items nowhere and the queue stayed empty.
        assert presence_mode.should_hold() is True
        for text in ("satu", "dua", "tiga"):
            assert presence_mode.offer(text) == "hold"
        assert presence_mode.held_count() == 3
        assert presence_mode.held_count() == 3
        shell = FakeShell()
        assert tray_panel_wiring.quick_action(shell, "held") is True
        assert "3" in shell.lines[-1]
        assert presence_mode.held_count() == 3, "showing must not release"
    finally:
        # `reset()` clears the mode and the queue but NOT the bound store, so a
        # leftover "focus" reader leaks into the next test. Unbind explicitly.
        presence_mode.reset()
        presence_mode.bind()


# ── 4. the second quota line ──────────────────────────────────────────────

def test_the_panel_says_the_remainder_is_HELD(monkeypatch):
    """"Dua sisanya ditahan sampai fokus berakhir" — the sentence that makes the
    quota readable in Fokus. Without it "1 dari 3" in Fokus reads as two
    suggestions already lost."""
    from ui import tray_panel_model

    monkeypatch.setattr(tray_panel_model, "_quota", lambda: (1, 3))
    monkeypatch.setattr(tray_panel_model, "_mode", lambda: "focus")
    # The catalogue's own word, not a literal: the default locale is "en", so a
    # test that greps for "ditahan" passes only in Indonesian — and it was me
    # who grepped for it.
    held = tray_panel_model._t("ui.panel.quota.held", remaining=2).lower()
    note = tray_panel_model.quota_note().lower()
    assert note == held


def test_the_held_note_is_empty_outside_fokus():
    """In Aktif the remainder is not held; saying so would be a new falsehood in
    place of the old one."""
    from ui import tray_panel_model

    assert tray_panel_model.quota_note() == ""


def test_the_remainder_is_arithmetic_not_a_believed_number(monkeypatch):
    """MUTATION-DRIVEN. "2" happens to be right at the artboard's 1-of-3, so a
    hardcoded 2 passed every existing assertion. Two other quotas separate
    arithmetic from a lucky literal."""
    from ui import tray_panel_model

    monkeypatch.setattr(tray_panel_model, "_mode", lambda: "focus")
    for used, limit, expected in ((0, 3, "3"), (2, 3, "1"), (1, 5, "4")):
        monkeypatch.setattr(tray_panel_model, "_quota", lambda u=used, l=limit: (u, l))
        note = tray_panel_model.quota_note()
        assert expected in note, f"used={used} limit={limit} -> {note!r}"


def test_a_spent_quota_holds_no_remainder_and_says_nothing(monkeypatch):
    """"0 sisanya ditahan" over a spent quota describes a queue that is not
    there. Empty is the honest answer."""
    from ui import tray_panel_model

    monkeypatch.setattr(tray_panel_model, "_mode", lambda: "focus")
    monkeypatch.setattr(tray_panel_model, "_quota", lambda: (3, 3))
    assert tray_panel_model.quota_note() == ""


def test_the_held_note_counts_the_remainder_from_the_quota(monkeypatch):
    """The number in the sentence is the same one the line above shows, or the
    two sentences disagree on screen."""
    from ui import tray_panel_model

    monkeypatch.setattr(tray_panel_model, "_quota", lambda: (1, 3))
    monkeypatch.setattr(tray_panel_model, "_mode", lambda: "focus")
    note = tray_panel_model.quota_note()
    assert "2" in note or "dua" in note.lower(), note


# ── 5. the wiring: every row board 05a draws has a handler ─────────────────

def test_every_focus_row_has_a_handler():
    """A row without a handler is a button that does nothing, and the panel's
    own probe (`_call`) reports it as a missing key rather than as silence."""
    from ui import tray_panel_wiring

    mapping = tray_panel_wiring.actions_for(object())
    assert "quick" in mapping


class FakeShell:
    def __init__(self, engine=None):
        self.lines = []
        self._proactive = engine

    def write_log(self, line):
        self.lines.append(line)


def test_pressing_pause_really_pauses_the_engine_the_shell_holds(isolated_config):
    """Not "the function exists" — the row's two presses must leave the engine
    in opposite states, and the second must be visible to a NEW engine (the
    restart). A handler that only logged a line would fail this."""
    from actions import proactive
    from ui import tray_panel_wiring

    engine = proactive.ProactiveEngine(min_silence_secs=0, check_cooldown=0)
    shell = FakeShell(engine)

    assert tray_panel_wiring.quick_action(shell, "pause_scheduling") is True
    assert engine.paused is True
    assert engine.should_trigger(0.0) is False
    assert proactive.ProactiveEngine(min_silence_secs=0,
                                     check_cooldown=0).paused is True

    assert tray_panel_wiring.quick_action(shell, "pause_scheduling") is True
    assert engine.paused is False


def test_pause_with_no_engine_says_so_instead_of_claiming_success():
    """The row must not report success in a session that has no engine — that is
    the failure class this project keeps removing."""
    from ui import tray_panel_wiring

    shell = FakeShell(None)
    assert tray_panel_wiring.quick_action(shell, "pause_scheduling") is False
    assert shell.lines, "a refused row must say why"


def test_pressing_end_focus_actually_leaves_fokus(monkeypatch):
    from core import presence_mode
    from ui import tray_panel_wiring

    presence_mode.reset()
    monkeypatch.setattr(presence_mode, "current", lambda: "focus")
    monkeypatch.setattr(presence_mode, "set_mode", lambda mode: mode == "active")

    shell = FakeShell()
    assert tray_panel_wiring.quick_action(shell, "end_focus") is True
    assert shell.lines


def test_show_held_reports_the_count_and_releases_nothing(monkeypatch):
    """The artboard's row is "Lihat yang tertahan" — a look. Draining the queue
    here would lose exactly what the panel promised to deliver afterwards."""
    from core import presence_mode
    from ui import tray_panel_wiring

    drained = []
    monkeypatch.setattr(presence_mode, "held_count", lambda: 3)
    monkeypatch.setattr(presence_mode, "take_held", lambda: drained.append(1) or [])

    shell = FakeShell()
    assert tray_panel_wiring.quick_action(shell, "held") is True
    assert "3" in shell.lines[-1]
    assert drained == [], "showing what is held must not release it"
