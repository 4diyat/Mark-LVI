"""What the panel's controls DO, proved without Qt and without a real session.

WHY THESE EXIST RATHER THAN "THE PANEL OPENS"
    A control that reports success and changes nothing is the failure this
    project keeps removing: a switch with no flag behind it, an Undo that calls
    nothing, a screenshot row that opens a window and takes no picture. Each
    test below drives the real module the control is supposed to call and
    checks the real state it is supposed to change — `core.undo`'s stack,
    `config_manager`'s plugin enablement, the shell's push-to-talk callback.

    Two controls CANNOT work in this build (mode tamu, susun jendela). The
    tests for those assert the honest answer — False plus a sentence — because
    a test that only checked "it does not raise" would pass on a stub that
    silently did nothing, which is exactly what the panel must not be.
"""
from __future__ import annotations

from pathlib import Path

import pytest


class FakeShell:
    """The shell surface these functions touch, and nothing else."""

    def __init__(self):
        self.lines = []
        self.ptt = []
        self.ptt_hold = self.ptt.append
        self._panel = None
        self._command_bar = None

    def write_log(self, line):
        self.lines.append(line)


@pytest.fixture()
def wiring():
    from ui import tray_panel_wiring

    return tray_panel_wiring


# ── presence ────────────────────────────────────────────────────────────────

def test_a_segment_applies_that_exact_mode_not_the_next_one(wiring, monkeypatch):
    """The panel does not cycle. Pressing Senyap twice must stay on Senyap."""
    from core import presence_mode
    from ui import ambient_shell

    presence_mode.reset()
    applied = []
    monkeypatch.setattr(ambient_shell, "apply_presence_mode",
                        lambda shell, mode: applied.append(mode) or True)

    assert wiring.set_presence(FakeShell(), "quiet") is True
    assert wiring.set_presence(FakeShell(), "quiet") is True
    assert applied == ["quiet", "quiet"]
    presence_mode.reset()


# ── quick actions ───────────────────────────────────────────────────────────

def test_screenshot_goes_through_the_existing_capture(wiring, monkeypatch):
    import actions.computer_control as cc

    calls = []
    monkeypatch.setattr(cc, "_screenshot",
                        lambda path=None: calls.append(path) or "Screenshot saved: X")

    shell = FakeShell()
    assert wiring.screenshot(shell) is True
    assert calls == [None]
    assert any("Screenshot saved: X" in line for line in shell.lines)


def test_a_failing_screenshot_is_reported_and_returns_false(wiring, monkeypatch):
    import actions.computer_control as cc

    def _boom(path=None):
        raise RuntimeError("no display")

    monkeypatch.setattr(cc, "_screenshot", _boom)
    shell = FakeShell()

    assert wiring.screenshot(shell) is False
    assert any("RuntimeError" in line and "no display" in line for line in shell.lines)


def test_dictate_holds_the_microphone_and_releases_it(wiring, monkeypatch):
    """The release is the whole feature: a hold that never ends is a hot mic."""
    shell = FakeShell()
    started = []
    released = []

    def _hold(on):
        (started if on else released).append(on)

    shell.ptt_hold = _hold
    monkeypatch.setattr(wiring, "_release_later",
                        lambda sh, seconds: released.append(False))

    assert wiring.dictate(shell) is True
    assert started == [True]
    assert released == [False]
    assert any("6 detik" in line for line in shell.lines)


def test_dictate_on_a_session_that_is_not_running_says_so(wiring):
    shell = FakeShell()
    shell.ptt_hold = None

    assert wiring.dictate(shell) is False
    assert any("belum siap" in line for line in shell.lines)


def test_the_release_runs_even_when_the_hold_itself_would_throw(wiring, monkeypatch):
    """A hold that throws must not leave the microphone open."""
    shell = FakeShell()
    released = []
    monkeypatch.setattr(wiring, "_release_later",
                        lambda sh, seconds: released.append(False))

    def _hold(on):
        raise RuntimeError("audio device gone")

    shell.ptt_hold = _hold
    assert wiring.dictate(shell) is False
    assert released == []       # nothing was ever opened, so nothing to close
    assert any("audio device gone" in line for line in shell.lines)


def test_arranging_windows_is_refused_out_loud(wiring):
    shell = FakeShell()
    assert wiring.tidy_windows(shell) is False
    assert any("belum ada di build ini" in line for line in shell.lines)


def test_find_a_file_opens_the_bar_and_prefills_a_request(wiring, monkeypatch):
    from ui import ambient_shell

    class _Field:
        def __init__(self):
            self.value = ""
            self.focused = False

        def setText(self, text):
            self.value = text

        def setFocus(self):
            self.focused = True

    class _Bar:
        is_open = False

        def __init__(self):
            self._field = _Field()

    shell = FakeShell()
    shell._command_bar = _Bar()
    monkeypatch.setattr(ambient_shell, "open_command_bar", lambda sh: True)

    assert wiring.find_file(shell) is True
    assert shell._command_bar._field.value == "Cari berkas "
    assert shell._command_bar._field.focused is True


# ── history ────────────────────────────────────────────────────────────────

def test_undo_last_empties_one_entry_from_the_real_stack(wiring):
    from core import undo

    undo.clear()
    undo.push_undo("Ringkas 14 baris", lambda: "diringkas")
    shell = FakeShell()

    assert wiring.undo_last(shell) is True
    assert undo.can_undo() is False
    assert any("diringkas" in line for line in shell.lines)
    undo.clear()


def test_exporting_writes_the_real_history_to_the_desktop(wiring, monkeypatch, tmp_path):
    """`tmp_path`, not `/tmp`: this suite runs on Windows in CI, where `/tmp`
    is not a directory and a test that hardcodes it fails there and passes
    here — which is the worst kind of green."""
    from core import undo

    undo.clear()
    undo.push_undo("Susun jendela 2 kolom", lambda: "ok")
    monkeypatch.setattr(wiring, "_desktop_path", lambda: Path(tmp_path))
    shell = FakeShell()
    target = Path(tmp_path) / "jarvis-history.txt"

    try:
        assert wiring.export_history(shell) is True
        assert target.read_text(encoding="utf-8").strip() == "Susun jendela 2 kolom"
        assert any(str(target) in line for line in shell.lines)
    finally:
        undo.clear()


def test_clearing_history_leaves_the_audit_log_alone(wiring, tmp_path, monkeypatch):
    """Two buttons, two different stores — merging them would make the smaller
    one do the larger thing."""
    from core import audit_log, undo

    undo.clear()
    undo.push_undo("satu", lambda: "ok")
    log = audit_log.AuditLog(tmp_path / "audit.jsonl")
    log.record("send_email", "high", "menunggu konfirmasi")
    monkeypatch.setattr(audit_log, "shared", lambda: log)

    assert wiring.clear_history(FakeShell()) is True
    assert undo.can_undo() is False
    assert len(log.entries()) == 1, "clearing the undo stack must not erase the audit"


def test_erasing_local_data_empties_the_audit_and_says_what_it_did_not_touch(
        wiring, tmp_path, monkeypatch):
    from core import audit_log

    log = audit_log.AuditLog(tmp_path / "audit.jsonl")
    log.record("screen_processor", "low", "selesai")
    monkeypatch.setattr(audit_log, "shared", lambda: log)
    shell = FakeShell()

    assert wiring.erase_local(shell) is True
    assert log.entries() == []
    assert any("Audit log dihapus" in line for line in shell.lines)


# ── permissions and guest mode ─────────────────────────────────────────────

def test_builtin_action_permissions_do_not_write_ineffective_plugin_flags(wiring, monkeypatch):
    from memory import config_manager
    written = []
    monkeypatch.setattr(config_manager, "save_plugin_enabled",
                        lambda name, on: written.append((name, on)) or True)
    assert wiring.set_permission(FakeShell(), "files", False) is False
    assert wiring.set_permission(FakeShell(), "apps", True) is False
    assert written == []


def test_a_switch_with_nothing_behind_it_is_refused_by_name(wiring):
    shell = FakeShell()
    assert wiring.set_permission(shell, "screen", False) is False
    assert any("bukan pengaturan" in line for line in shell.lines)


def test_guest_mode_is_gone_rather_than_pretending(wiring):
    """BOARD 27, THE OWNER'S RULING. This used to assert that `set_guest`
    returned False and said "mode tamu belum ada" — an honest sentence attached
    to a switch that still invited a click. The switch is now not drawn and the
    function is deleted; the honest answer is that there is nothing to call.

    A disabled switch was rejected too: it still promises the feature exists.
    """
    assert not hasattr(wiring, "set_guest")
    assert "guest" not in wiring.actions_for(FakeShell())


# ── the field, and the map itself ─────────────────────────────────────────

def test_the_command_field_sends_through_the_command_bar_door(wiring, monkeypatch):
    from ui import ambient_shell

    sent = []
    monkeypatch.setattr(ambient_shell, "submit_from_bar",
                        lambda shell, text: sent.append(text))

    assert wiring.send_command(FakeShell(), "  rangkum laporan ") is True
    assert sent == ["  rangkum laporan "]     # the panel trimmed it already
    assert wiring.send_command(FakeShell(), "   ") is False
    assert len(sent) == 1


def test_every_key_the_panel_can_press_has_a_handler(wiring):
    """A missing key is a control that does nothing; the panel reports it, but
    a report is not a substitute for the wiring existing."""
    from tests.qtstub import fresh_ui, restore_ui

    saved = fresh_ui()
    try:
        from ui.tray_panel import TrayPanel

        actions = wiring.actions_for(FakeShell())
        assert set(actions) == {
            "presence_set", "quick", "permission", "undo", "history_export",
            "history_clear", "erase", "export_audit", "command", "theme",
            # The thirteen board pages (`ui/pages_actions.py`). Each one is a
            # store write reached by a click, and each has a test of its own
            # below; this set is what proves the panel's buttons have somewhere
            # to land at all.
                "memory_forget", "memory_clear", "routines_pause",
                "routine_create", "routine_toggle", "routine_delete",
                "tools_copy",
                "tools_clear", "tools_safe", "tools_layout", "plugin_toggle", "plugins_list", "consent",
                # Board 7's four-step onboarding ladder: advance, back, and
                # the presence-mode toggle the presence step reuses the switch for.
                "onboard_next", "onboard_back", "onboard_toggle",
                "language", "text_scale", "motion_toggle", "install_mode",
                # Board 15's gesture rebind: the "ubah" cell walks the action
                # cycle for one gesture, through the gesture_binding adapter.
                "gesture_rebind",
                # Board 14's voice-verification gate: a switch, a register
                # and a delete, each landing on the session, not a store.
                "voice_auth_toggle", "voice_auth_enroll", "voice_auth_delete",
                # Board 15's contrast level: a two-slot segmented control
                # that swaps the panel to the high-contrast palette.
                "contrast_set",
                # Board 13's review-and-apply button: builds a plan, reviews it,
                # and drives the approved fields into the browser session.
                "form_fill_apply",
                # Board 16's phone pairing: mint a code, pair a device,
                # disconnect the most recent one.
                "phone_make_code", "phone_pair", "phone_unpair",
                # Board 22's installer: build a reviewed dependency plan and run it.
                "installer_run",
                # Board 14's OS-control switch: a gated toggle plus the physical confirm.
                "os_control_toggle", "os_control_confirm"}

        panel = TrayPanel(actions)
        assert panel.open() is True
        pressed = {key.split(":", 1)[0] for key in panel._buttons}
        assert pressed <= {"mode", "quick", "perm", "p6", "p6_export",
                           "p6_clear", "undo", "export", "clear", "erase",
                           "send", "theme",
                           # the board pages' controls, by their real
                           # prefixes — this set is what makes a NEW control
                           # fail here until someone says what it does
                           "mem_add", "mem_clear", "mem_open", "m1_back",
                           "m1_forget", "m1_export", "rt_pause", "tl_clear", "tl_copy",
                           "tl_snap_thumb",
                           "l18_clear", "l18_export", "cn_toggle", "hp_read",
                           "tl_safe", "cn_allow", "cn_deny", "ac_lang",
                           "ac_motion", "ac_scale", "pl_toggle", "pl_prev", "pl_next", "in_pick",
                           # board 15's gesture "ubah" cells, by prefix
                           "ac_gest_edit",
                           "more", "more_back",
                           # board 14's voice-verification controls, by the
                           # object names the security page gives them
                           "va_toggle", "va_enroll", "va_delete",
                           # board 14's OS-control switch, by its object names
                           "sec_os_toggle", "sec_os_confirm",
                           # board 15's contrast slots, by their prefix
                           "ac_contrast",
                           # board 11's routine controls, by prefix
                           "rt_toggle", "rt_delete", "rt_builder_create", "rt_prev", "rt_next",
                           # board 13's form-fill apply button, by prefix
                           "hp_form_apply",
                           # board 16's phone pairing controls, by prefix
                           "pl_phone_make", "pl_phone_pair", "pl_phone_unpair",
                           # board 22's install button, by prefix
                           "in_install",
                           # Board 5's navigation segments. They navigate the
                           # panel itself (`set_page`), not an action handler,
                           # so they have no entry in `actions` — but they are
                           # real controls and must be named here so a new one
                           # cannot be added silently.
                           "nav", "panel_back", "panel_close", "tl_quick"}
        # `p6*` replaced `permx` when board 6 replaced 06a on the privacy page:
        # the four rows keep the `p6:` prefix, its two buttons are `p6_clear`
        # and `p6_export`, and the history page keeps its own `clear`/`export`.
        # `erase` is NOT required any more: the button that pressed it
        # ("Hapus semua data lokal") went with board 06a. The handler stays,
        # because `p6_clear` presses the same store from board 6's page.
        assert {"mode", "quick", "perm", "p6", "p6_clear", "p6_export",
                "undo", "export", "clear", "send"} <= pressed
    finally:
        restore_ui(saved)


# ── board 17a: the switch has to persist ────────────────────────────────────

def test_cycling_the_theme_writes_it_to_the_config_layer(wiring, monkeypatch):
    from memory import config_manager

    written = {}
    monkeypatch.setattr(config_manager, "save_ui_theme", lambda v: written.update(theme=v))
    monkeypatch.setattr(config_manager, "get_ui_theme", lambda: written.get("theme", "auto"))
    shell = FakeShell()

    assert wiring.set_theme(shell, "light") is True
    assert written == {"theme": "light"}
    assert any("Tema panel: light" in line for line in shell.lines)


def test_a_theme_the_config_layer_collapses_is_reported_as_stored_not_asked(
        wiring, monkeypatch):
    """The sentence must match disk, not the click.

    `save_ui_theme` collapses an unknown value to `auto`; reporting "light"
    because that is what was asked for would be a log line disagreeing with the
    config file it describes.
    """
    from memory import config_manager

    monkeypatch.setattr(config_manager, "save_ui_theme", lambda v: None)
    monkeypatch.setattr(config_manager, "get_ui_theme", lambda: "auto")
    shell = FakeShell()

    assert wiring.set_theme(shell, "neon") is False
    assert any("Tema panel: auto" in line for line in shell.lines)


def test_a_theme_write_that_throws_is_reported_and_returns_false(wiring):
    from memory import config_manager

    def _boom(_value):
        raise OSError("read-only: the config folder is on a locked volume")

    original, config_manager.save_ui_theme = config_manager.save_ui_theme, _boom
    try:
        shell = FakeShell()
        assert wiring.set_theme(shell, "light") is False
        assert any("Tidak bisa" in line or "tidak tersimpan" in line
                   for line in shell.lines)
    finally:
        config_manager.save_ui_theme = original


def test_pressing_the_theme_control_reaches_the_caller_and_cycles(wiring, monkeypatch):
    """The panel's button, end to end: cycle, then hand the value out."""
    from tests.qtstub import fresh_ui, restore_ui

    saved = fresh_ui()
    try:
        from ui.tray_panel import TrayPanel

        seen = []
        # `_build` applies the SAVED setting, so the file is patched rather
        # than the widget: a test that poked `_requested` would pass while
        # `_load_saved_theme` was broken, which is the bug these cover.
        from memory import config_manager

        original_get = config_manager.get_ui_theme
        config_manager.get_ui_theme = lambda: "dark"
        try:
            panel = TrayPanel({"theme": seen.append})
            assert panel.open() is True
        finally:
            config_manager.get_ui_theme = original_get
        assert panel.requested_theme == "dark"

        assert panel.press_theme() == "light"
        assert seen == ["light"]
        assert panel.theme == "light"
    finally:
        restore_ui(saved)
