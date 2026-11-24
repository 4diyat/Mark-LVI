"""Boards 5, 23, 26, 27 and 28 — the tray panel, proved without a display.

WHY THESE ASSERTIONS AND NOT "IT DRAWS"
    A panel is only worth building if it says something TRUE. Every test below
    is about a way the panel could lie:

      * board 05a's count saying 3 when `presence_mode` holds 4;
      * board 06a's Mikrofon drawn as a live switch on a machine with no
        microphone — a control that cannot work and does not say so;
      * board 08a's Urungkan offered when the stack is empty;
      * the panel reporting success when the caller's handler threw;
      * board 17a shipping a second widget instead of the same one recoloured.

    Each one fails if the behaviour is removed, not merely if a call is deleted:
    the mode test drives the REAL `core.presence_mode`, the undo test pushes a
    REAL entry through `core.undo`, and the fixed-switch test flips the real
    `audio_devices` answer rather than a mock.

HOW THE STUB IS USED
    `tests/qtstub.py` replaces PyQt6 with something narrow enough to be honest;
    every widget it invents is a name the code really uses. These tests build
    the panel through it, which is why they run on a runner with no libGL.
"""
from __future__ import annotations

import pytest

from tests.qtstub import fresh_ui, restore_ui


@pytest.fixture()
def indonesian():
    """The panel is drawn in the locale the user runs, and the artboards are
    Indonesian. Pinned so these assertions test the PANEL and not whichever
    locale a test that ran earlier happened to leave behind."""
    from core import i18n

    i18n.reload()
    i18n.set_locale("id")
    yield
    i18n.set_locale("en")


@pytest.fixture()
def panel_module(indonesian):
    """The panel, imported against the stub, and the real modules put back."""
    saved = fresh_ui()
    try:
        from ui import tray_panel, tray_pages, tray_panel_model

        yield tray_panel, tray_pages, tray_panel_model
    finally:
        restore_ui(saved)


@pytest.fixture()
def clean_state():
    """The two modules the panel reads, emptied around every test."""
    from core import presence_mode, undo

    presence_mode.reset()
    undo.clear()
    yield
    presence_mode.reset()
    undo.clear()


class Recorder:
    """An action map that records what the panel asked for."""

    def __init__(self, answer=None):
        self.calls = []
        self.answer = answer

    def __call__(self, *args):
        self.calls.append(args)
        return self.answer


# ── board 5: the default page ────────────────────────────────────────────────

def test_the_panel_opens_at_board_5_with_the_mode_it_found(panel_module, clean_state):
    tray_panel, _pages, _model = panel_module
    panel = tray_panel.TrayPanel({})

    assert panel.open() is True
    assert panel.page == "main"
    assert panel.snapshot.mode == "active"
    assert panel._labels["subtitle"].text() == "Panel baki · mengikuti posisi taskbar"


def test_the_four_quick_actions_are_the_artboards_and_carry_their_chords(
        panel_module, clean_state):
    tray_panel, _pages, model = panel_module
    panel = tray_panel.TrayPanel({})
    panel.open()

    # The catalogue is the source; these are translated at paint time.
    assert [model._t(row[1]) for row in model.QUICK_ACTIONS] == [
        "Tangkap layar", "Dikte", "Cari berkas", "Susun jendela"]
    # The chord is on the row, not in a tooltip: a quick action whose shortcut
    # is invisible is one the user retypes.
    for key, name, chord in model.QUICK_ACTIONS:
        text = panel._buttons[f"quick:{key}"].text()
        assert model._t(name) in text and chord in text


def test_pressing_a_quick_action_reaches_the_handler_once(panel_module, clean_state):
    tray_panel, _pages, _model = panel_module
    quick = Recorder()
    panel = tray_panel.TrayPanel({"quick": quick})
    panel.open()

    assert panel.press_quick("screenshot") is True
    assert quick.calls == [("screenshot",)]
    # An unknown key is refused rather than sent on, so a stale widget cannot
    # trigger a handler that was never meant for it.
    assert panel.press_quick("launch_missiles") is False
    assert len(quick.calls) == 1


def test_the_command_field_trims_and_clears_and_refuses_empties(
        panel_module, clean_state):
    tray_panel, _pages, _model = panel_module
    command = Recorder()
    panel = tray_panel.TrayPanel({"command": command})
    panel.open()

    panel._field.setText("   rangkum   laporan   ")
    assert panel.submit_command() is True
    assert command.calls == [("rangkum laporan",)]
    assert panel._field.text() == ""
    assert panel.submit_command("   ") is False
    assert len(command.calls) == 1


# ── board 5 + 23: the three modes, and what Fokus holds ─────────────────────

def test_a_segment_sets_that_mode_and_the_panel_says_so(panel_module, clean_state):
    from core import presence_mode

    tray_panel, _pages, _model = panel_module
    applied = []

    def _set(mode):
        applied.append(mode)
        presence_mode.set_mode(mode)
        return True

    panel = tray_panel.TrayPanel({"presence_set": _set})
    panel.open()

    assert panel.press_mode("focus") is True
    assert applied == ["focus"]
    # The snapshot is RE-READ, not remembered: this is the assertion that fails
    # if `refresh()` is dropped from `press_mode`.
    assert panel.snapshot.mode == "focus"
    assert presence_mode.current() == "focus"
    assert panel._labels["subtitle"].text() == "Panel baki · mode Fokus"


def test_fokus_shows_the_held_count_and_the_other_modes_hide_the_strip(
        panel_module, clean_state):
    from core import presence_mode

    tray_panel, _pages, _model = panel_module
    panel = tray_panel.TrayPanel({"presence_set": presence_mode.set_mode})
    panel.open()

    presence_mode.set_mode("focus")
    presence_mode.offer("satu")
    presence_mode.offer("dua")
    presence_mode.offer("tiga")
    panel.refresh()

    assert panel.snapshot.held == 3
    assert "3 tertahan" in panel._labels["held"].text()
    assert panel._labels["held"].isVisible() is True

    panel.press_mode("active")
    assert panel._labels["held"].isVisible() is False


def test_an_unknown_mode_is_refused_without_reaching_the_handler(
        panel_module, clean_state):
    tray_panel, _pages, _model = panel_module
    setter = Recorder()
    panel = tray_panel.TrayPanel({"presence_set": setter})
    panel.open()

    assert panel.press_mode("loud") is False
    assert setter.calls == []


# ── board 08a: history and undo ──────────────────────────────────────────────

def test_the_history_page_lists_the_undo_stack_newest_first(panel_module, clean_state):
    from core import undo

    tray_panel, _pages, _model = panel_module
    undo.push_undo("Ringkas 14 baris terpilih", lambda: "ok")
    undo.push_undo("Susun jendela 2 kolom", lambda: "ok")

    panel = tray_panel.TrayPanel({})
    panel.open()
    assert panel.set_page("history") is True
    assert panel.page == "history"

    assert panel._labels["history:0"].text() == "Susun jendela 2 kolom"
    assert panel._labels["history:1"].text() == "Ringkas 14 baris terpilih"
    assert panel._labels["history_count"].text() == "Hari ini · 2 bisa diurungkan"


def test_urungkan_is_offered_once_and_only_on_the_oldest_row(panel_module, clean_state):
    from core import undo

    tray_panel, _pages, _model = panel_module
    undo.push_undo("satu", lambda: "ok")
    undo.push_undo("dua", lambda: "ok")
    panel = tray_panel.TrayPanel({"undo": undo.undo_last})
    panel.open()
    # THE HISTORY PAGE MUST BE THE OPEN ONE. These buttons are children of the
    # history page, so while board 5 is on screen they are invisible for the
    # right reason — and this test used to pass only because the Qt stub never
    # recorded `QPushButton("", page)`'s parent, making everything invisible
    # and `[i for i ...]` accidentally agree with a different bug.
    panel.set_page("history")

    visible = [i for i in range(4) if panel._buttons[f"undo:{i}"].isVisible()]
    assert visible == [1], "exactly one row may carry the button — undo is a stack"

    assert panel.press_undo() is True
    assert undo.can_undo() is True
    assert panel._labels["history:0"].text() == "satu"
    assert panel._buttons["undo:0"].isVisible() is True
    assert panel._buttons["undo:1"].isVisible() is False


def test_urungkan_refuses_an_empty_stack_instead_of_reporting_success(
        panel_module, clean_state):
    tray_panel, _pages, _model = panel_module
    undo_call = Recorder()
    panel = tray_panel.TrayPanel({"undo": undo_call})
    panel.open()

    assert panel.press_undo() is False
    assert undo_call.calls == [], "an empty stack must not reach the handler"


def test_the_audit_tail_is_newest_first_and_never_empty_looking(
        panel_module, clean_state, tmp_path):
    from core import audit_log

    tray_panel, _pages, _model = panel_module
    log = audit_log.AuditLog(tmp_path / "audit.jsonl")
    log.record("send_email", "high", "menunggu konfirmasi")
    log.record("screen_processor", "low", "selesai")

    original = audit_log.shared
    audit_log.shared = lambda: log
    try:
        panel = tray_panel.TrayPanel({})
        panel.open()
        text = panel._labels["audit"].text()
    finally:
        audit_log.shared = original

    assert "screen_processor" in text
    assert text.index("screen_processor") < text.index("send_email")


# ── board 6: permissions, and the ones that cannot be switched ──────────────

def test_a_fact_about_the_machine_is_drawn_as_disabled_not_as_a_switch(
        panel_module, clean_state, monkeypatch):
    from core import audio_devices

    tray_panel, _pages, model = panel_module
    monkeypatch.setattr(audio_devices, "input_available", lambda refresh=False: False)

    panel = tray_panel.TrayPanel({})
    panel.open()

    mic = panel.snapshot.permissions["microphone"]
    assert mic["on"] is False and mic["fixed"] is True
    # Board 6's page (this replaced 06a's on 2026-11-22). The switch is
    # DISABLED, not merely refused on click: a live switch over a fact no click
    # can change teaches the user not to trust the panel.
    assert panel._buttons["p6:microphone"].isEnabled() is False
    # And the readout beside it is dark, because the permission is off. It does
    # NOT say "tidak terpasang": there is no key for that, and inventing one
    # would be this build claiming to know why there is no device.
    #
    # The dot is painted by `_paint_dot` on every refresh, not at build time —
    # asserting on a styleSheet nobody has written yet is how this test first
    # failed. Drive the paint, then read what it drew.
    from ui import tray_paint

    tray_paint.paint(panel, panel.snapshot)
    # The stub stores a stylesheet in `_style`; `styleSheet()` is not part of
    # the stub's surface, and asking for it answered None — a test failing on
    # its own read, not on the code.
    dot = panel._labels["perm_dot:microphone"]._style
    assert dot, "the permission readout was never painted"
    assert "#4FD8F0" not in dot, (
        "the microphone readout is lit for a permission that is off")

    # And pressing it does nothing, because there is nothing behind it.
    refused = Recorder()
    panel._actions["permission"] = refused
    assert panel.press_permission("microphone", True) is False
    assert refused.calls == []
    assert any("not a setting" in line for line in panel.notes)


def test_the_two_real_switches_are_enabled_and_reach_the_handler(
        panel_module, clean_state):
    tray_panel, _pages, model = panel_module
    permission = Recorder(answer=True)
    panel = tray_panel.TrayPanel({"permission": permission})
    panel.open()

    assert panel._buttons["p6:files"].isEnabled() is True
    assert panel.press_permission("files", True) is True
    assert permission.calls == [("files", True)]
    assert panel.press_permission("apps", False) is True
    assert permission.calls[-1] == ("apps", False)


def test_board_6_draws_all_four_explicit_permissions(panel_module, clean_state):
    tray_panel, _pages, model = panel_module
    panel = tray_panel.TrayPanel({})
    panel.open()

    assert [model._t(row[1]) for row in model.PERMISSIONS] == [
        "Layar", "Mikrofon", "Berkas", "Kontrol aplikasi"]
    # The LABEL is on the button, because the row is the click target; the
    # subtitle is its own label inside the card. Same split as board 5.
    for key, name, sub in model.PERMISSIONS:
        assert panel._buttons[f"p6:{key}"].text() == model._t(name)
        assert panel._labels[f"p6_sub:{key}"].text() == model._t(sub)


# ── board 17a: one widget, two palettes ─────────────────────────────────────

def test_the_light_theme_is_the_same_widget_with_another_palette(
        panel_module, clean_state):
    tray_panel, pages, _model = panel_module
    panel = tray_panel.TrayPanel({})
    panel.open()

    window = panel._window
    dark = window._style
    assert "#0A1722" in dark

    assert panel.set_theme("light") is True
    assert panel.theme == "light"
    assert panel._window is window, "board 17a must not build a second widget"
    assert "#FFFFFF" in window._style and "#F6F9FB" not in window._style
    # The artboard's own light accent, not a tinted dark one.
    assert pages.PALETTES["light"]["accent"] == "#0A7A93"
    assert pages.PALETTES["dark"]["accent"] == "#4FD8F0"

    assert panel.set_theme("neon") is False
    assert panel.theme == "light"


# ── honesty under failure ──────────────────────────────────────────────────

def test_a_throwing_handler_is_reported_and_the_panel_stays_open(
        panel_module, clean_state):
    tray_panel, _pages, _model = panel_module

    def _boom(*_args):
        raise RuntimeError("the session went away")

    panel = tray_panel.TrayPanel({"quick": _boom})
    panel.open()

    assert panel.press_quick("dictate") is True     # attempted, then failed
    joined = " | ".join(panel.notes)
    assert "'quick' failed" in joined and "RuntimeError" in joined
    assert panel.available is True, "a failing control must not take the panel down"


def test_a_missing_handler_is_named_rather_than_silently_ignored(
        panel_module, clean_state):
    tray_panel, _pages, _model = panel_module
    panel = tray_panel.TrayPanel({})
    panel.open()

    assert panel.press_quick("screenshot") is True
    assert any("no handler for 'quick'" in line for line in panel.notes)


def test_escape_closes_and_reports_it(panel_module, clean_state):
    tray_panel, _pages, _model = panel_module
    closed = Recorder()
    panel = tray_panel.TrayPanel({}, on_close=closed)
    panel.open()

    class _Event:
        def key(self):
            from PyQt6.QtCore import Qt
            return Qt.Key.Key_Escape

        def accept(self):
            self.accepted = True

    event = _Event()
    panel._on_key(event)
    assert getattr(event, "accepted", False) is True
    assert panel._window.isVisible() is False
    assert len(closed.calls) == 1


def test_an_unknown_page_is_refused_and_the_current_one_stays(
        panel_module, clean_state):
    tray_panel, _pages, _model = panel_module
    panel = tray_panel.TrayPanel({})
    panel.open()

    assert panel.set_page("privacy") is True
    assert panel.set_page("trading") is False
    assert panel.page == "privacy"


# ── placement: the one geometry bug worth a test ───────────────────────────

class _Screen:
    def __init__(self, x, y, w, h):
        self._box = (x, y, w, h)

    def x(self):
        return self._box[0]

    def y(self):
        return self._box[1]

    def width(self):
        return self._box[2]

    def height(self):
        return self._box[3]


def test_the_panel_opens_inside_the_screen_wherever_the_taskbar_is(panel_module):
    _tray_panel, pages, _model = panel_module
    size = (pages.PANEL_W, pages.PANEL_H)

    # A plain 1920×1080 desktop: bottom-right with a margin.
    assert pages.panel_position(_Screen(0, 0, 1920, 1080), size) == (1448, 408)

    # A taskbar at the BOTTOM is already accounted for, because the available
    # rectangle excludes it; the point case must stay above the icon.
    x, y = pages.panel_position(_Screen(0, 0, 1920, 1040), size, point=(1900, 1030))
    assert 0 <= x <= 1920 - size[0]
    assert 0 <= y <= 1040 - size[1]

    # A second screen to the RIGHT, and an icon at its edge: the panel must not
    # land on the first screen, which is the classic multi-monitor bug.
    x, y = pages.panel_position(_Screen(1920, 0, 1280, 1024), size, point=(3190, 1010))
    assert x >= 1920 and y >= 0

    # A tiny screen smaller than the panel: clamp, do not centre off-screen.
    assert pages.panel_position(_Screen(0, 0, 400, 300), size) == (0, 0)


# ── board 17a: the setting, not just the palette ────────────────────────────
#
# The light palette existed for a while and NOBODY COULD REACH IT: the settings
# drawer that would have held the switch was deleted with the window, and
# `set_theme` was a method only a test called. Board 17a is the same panel in
# light colours, so a panel with no way to get there is a board that does not
# ship. These tests are about the way in.

def test_auto_is_a_setting_and_not_a_palette(panel_module, clean_state):
    """`auto` resolves to one of exactly two palettes, never to itself.

    A palette dict keyed `auto` would be a third set of colours that somebody
    has to keep in step; `auto` resolves to one of the real palettes instead.
    There are three now: `dark`, `light` and the high-contrast `high` — a
    MODIFIER the panel switches in, not a fourth theme setting.
    """
    tray_panel, pages, _model = panel_module
    theme = tray_panel.resolve_theme

    assert set(pages.PALETTES) == {"dark", "light", "high"}
    assert theme("dark") == "dark"
    assert theme("light") == "light"
    # Whatever the OS says, `auto` names a palette that exists.
    assert theme("auto") in pages.PALETTES
    # Garbage from a hand-edited config file is not a third answer.
    assert theme("neon") in pages.PALETTES
    assert theme("") in pages.PALETTES


def test_auto_follows_the_operating_system_when_it_says_so(
        panel_module, clean_state, monkeypatch):
    from memory import config_manager

    tray_panel, _pages, _model = panel_module
    monkeypatch.setattr(config_manager, "system_prefers_light", lambda: True)
    assert tray_panel.resolve_theme("auto") == "light"

    monkeypatch.setattr(config_manager, "system_prefers_light", lambda: False)
    assert tray_panel.resolve_theme("auto") == "dark"

    # A config layer that raises must not take the panel with it: the answer is
    # the palette the mockup has drawn since board 5.
    def _boom():
        raise RuntimeError("no config file")

    monkeypatch.setattr(config_manager, "system_prefers_light", _boom)
    assert tray_panel.resolve_theme("auto") == "dark"


def test_the_panel_opens_on_the_saved_theme_not_on_dark(
        panel_module, clean_state, monkeypatch):
    """The setting is read ONCE, when the window is built.

    This is the assertion that fails if `_load_saved_theme()` is dropped from
    `_build()` — the panel would open dark for a user who chose light, which is
    the whole complaint this fixes.
    """
    from memory import config_manager

    tray_panel, _pages, _model = panel_module
    monkeypatch.setattr(config_manager, "get_ui_theme", lambda: "light")
    monkeypatch.setattr(config_manager, "system_prefers_light", lambda: False)

    panel = tray_panel.TrayPanel({})
    assert panel.open() is True
    assert panel.theme == "light"
    assert panel.requested_theme == "light"
    assert "#FFFFFF" in panel._window._style


def test_the_theme_control_cycles_three_values_and_says_which(
        panel_module, clean_state, monkeypatch):
    """Board 17a in reach: one control, three settings, no second widget.

    The button shows the SETTING ("A"/"D"/"L"), not the resolved palette — a
    button reading "light" because `auto` resolved light could never be set
    back to auto.
    """
    from memory import config_manager

    tray_panel, _pages, _model = panel_module
    monkeypatch.setattr(config_manager, "get_ui_theme", lambda: "auto")
    monkeypatch.setattr(config_manager, "system_prefers_light", lambda: False)

    panel = tray_panel.TrayPanel({})
    panel.open()
    assert panel.requested_theme == "auto"
    assert panel._buttons["theme"].text() == "A"
    assert panel.theme == "dark", "auto on a dark desktop is the dark palette"

    assert panel.cycle_theme() == "dark"
    assert panel._buttons["theme"].text() == "D"
    assert panel.cycle_theme() == "light"
    assert panel.theme == "light" and panel._buttons["theme"].text() == "L"
    assert panel.cycle_theme() == "auto"
    assert panel.theme == "dark", "back to auto, which is dark here"


def test_the_saved_theme_is_read_once_and_cycling_is_not_overruled(
        panel_module, clean_state, monkeypatch):
    """Re-opening the panel must not undo the user's click.

    `_load_saved_theme` runs from `_build`, and `_build` happens once. If it ran
    on every open, a user who cycled to light would be dragged back to the file
    the next time they clicked the tray icon.
    """
    from memory import config_manager

    tray_panel, _pages, _model = panel_module
    monkeypatch.setattr(config_manager, "get_ui_theme", lambda: "dark")
    monkeypatch.setattr(config_manager, "system_prefers_light", lambda: False)

    panel = tray_panel.TrayPanel({})
    panel.open()
    assert panel.theme == "dark"
    panel.cycle_theme()                       # -> light
    assert panel.theme == "light"

    panel.close()
    panel.open()                              # second open, same widget
    assert panel.theme == "light", "re-opening reloaded the file over the click"


def test_high_contrast_is_orthogonal_to_the_theme(panel_module, clean_state, monkeypatch):
    """Board 15's contrast level swaps the palette WITHOUT touching the theme.

    The whole point of modelling high contrast as a modifier on the palette
    rather than a fourth theme setting: the auto/dark/light cycle keeps
    working underneath it, and turning it off restores the palette the theme
    was on. If it were a theme value, cycling would silently drop it.
    """
    from memory import config_manager

    tray_panel, _pages, _model = panel_module
    monkeypatch.setattr(config_manager, "get_ui_theme", lambda: "light")
    monkeypatch.setattr(config_manager, "system_prefers_light", lambda: True)
    monkeypatch.setattr(config_manager, "get_high_contrast", lambda: False)

    panel = tray_panel.TrayPanel({})
    panel.open()
    assert panel.theme == "light"

    panel.set_high_contrast(True)
    assert panel.high_contrast is True
    assert panel.theme == "high", "the on-screen palette is the high-contrast one"
    # The underlying theme is untouched: cycling still goes light -> auto -> dark.
    assert panel.requested_theme == "light"
    panel.cycle_theme()                       # -> auto (resolves light here)
    assert panel.theme == "high", "high contrast survives a theme cycle"
    assert panel.requested_theme == "auto"

    panel.set_high_contrast(False)
    assert panel.theme == "light", "turning it off restores the theme's palette"
    assert panel.high_contrast is False


def test_high_contrast_is_restored_from_the_saved_choice(
        panel_module, clean_state, monkeypatch):
    """A user who chose high contrast sees it when the panel is opened.

    `_load_saved_theme` applies the theme first and THEN the modifier, so a
    saved choice is not overwritten by the palette it sits on top of.
    """
    from memory import config_manager

    tray_panel, _pages, _model = panel_module
    monkeypatch.setattr(config_manager, "get_ui_theme", lambda: "dark")
    monkeypatch.setattr(config_manager, "system_prefers_light", lambda: False)
    monkeypatch.setattr(config_manager, "get_high_contrast", lambda: True)

    panel = tray_panel.TrayPanel({})
    panel.open()
    assert panel.high_contrast is True
    assert panel.theme == "high"


def test_the_two_theme_tuples_are_the_same_three_values(panel_module):
    """`ui/tray_theme.THEMES` is written out twice on purpose.

    `ui/` must validate a value without importing the config layer, which reads
    a file on import. The price of writing it twice is that one copy can drift.
    """
    from memory import config_manager
    from ui import tray_theme

    assert tray_theme.THEMES == config_manager.THEMES
    assert tray_theme.THEMES == ("auto", "dark", "light")


def test_a_theme_saved_by_the_config_layer_comes_back_out_of_it(tmp_path, monkeypatch):
    """The round trip, through the real writer.

    `save_ui_theme` collapses an unknown value rather than rejecting it, which
    is what makes a hand-edited `"ui_theme": "neon"` a working panel instead of
    a KeyError — so the collapse is the behaviour under test, not just a nicety.
    """
    from memory import config_manager

    written = {}

    def _set(**values):
        written.update(values)

    monkeypatch.setattr(config_manager, "set_config_values", _set)
    monkeypatch.setattr(config_manager, "load_api_keys", lambda: dict(written))

    config_manager.save_ui_theme("light")
    assert written == {"ui_theme": "light"}
    assert config_manager.get_ui_theme() == "light"

    config_manager.save_ui_theme("neon")
    assert written == {"ui_theme": "auto"}, "an unknown value collapses to auto"
    assert config_manager.get_ui_theme() == "auto"
