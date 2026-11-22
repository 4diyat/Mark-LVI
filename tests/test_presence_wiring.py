"""Aktif / Fokus / Senyap, from the tray to the orb and back.

WHY THIS FILE EXISTS SEPARATELY FROM `test_presence_mode.py`
    That file tests the decision ("hold, show or drop"). This one tests the
    WIRING the owner asked for explicitly: that choosing Senyap dims the orb,
    that the choice survives a restart, and that the scheduler thread reads the
    same mode the panel wrote. A mode that is stored but never reaches the
    surface is a setting the user re-toggles forever.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def lifecycle():
    return _load("lifecycle_presence_under_test", ROOT / "ui" / "lifecycle.py")


class _Orb:
    def __init__(self):
        self.modes = []
        self.states = []

    def set_mode(self, mode):
        self.modes.append(mode)

    def set_state(self, state):
        self.states.append(state)


class _Shell:
    def __init__(self, orb=None):
        self._orb = orb
        self._win = None
        self._command_bar = None


@pytest.fixture(autouse=True)
def clean(monkeypatch):
    from core import presence_mode
    presence_mode.reset()
    saved = {}
    # `save_presence_mode` writes the real config; capture instead.
    import memory.config_manager as cfg
    for name in ("save_presence_mode", "get_presence_mode"):
        saved[name] = getattr(cfg, name, None)
    yield
    for name, value in saved.items():
        if value is not None:
            setattr(cfg, name, value)
    presence_mode.reset()


# ── the answered product question, end to end ─────────────────────────────

def test_choosing_senyap_dims_the_orb(lifecycle):
    """The owner's decision: the orb changes, not only the notifications."""
    orb = _Orb()
    shell = _Shell(orb=orb)
    assert lifecycle.apply_presence_mode(shell, "quiet") is True
    assert orb.modes == ["quiet"]


def test_fokus_dims_it_too(lifecycle):
    orb = _Orb()
    lifecycle.apply_presence_mode(_Shell(orb=orb), "focus")
    assert orb.modes == ["focus"]


def test_returning_to_aktif_restores_the_orb(lifecycle):
    orb = _Orb()
    shell = _Shell(orb=orb)
    lifecycle.apply_presence_mode(shell, "quiet")
    lifecycle.apply_presence_mode(shell, "active")
    assert orb.modes == ["quiet", "active"]


def test_an_unknown_mode_changes_nothing(lifecycle):
    orb = _Orb()
    shell = _Shell(orb=orb)
    assert lifecycle.apply_presence_mode(shell, "invisible") is False
    assert orb.modes == []


def test_the_mode_is_applied_without_an_orb(lifecycle):
    """A machine where the orb failed to build still gets Fokus."""
    from core import presence_mode

    assert lifecycle.apply_presence_mode(_Shell(orb=None), "focus") is True
    assert presence_mode.current() == "focus"


# ── the mode is held in one place, not in a widget ────────────────────────

def test_the_scheduler_thread_reads_the_mode_the_panel_wrote(lifecycle):
    """No widget involved: this is the state the toast queue consults."""
    from core import presence_mode

    lifecycle.apply_presence_mode(_Shell(orb=_Orb()), "focus")
    assert presence_mode.offer("laporan siap") == "hold"


def test_quiet_suppresses_banners_as_well_as_dimming(lifecycle):
    from core import presence_mode

    lifecycle.apply_presence_mode(_Shell(orb=_Orb()), "quiet")
    assert presence_mode.allows_banner() is False


def test_the_choice_is_saved_so_a_restart_agrees(lifecycle, monkeypatch):
    import memory.config_manager as cfg

    written = []
    monkeypatch.setattr(cfg, "save_presence_mode", written.append)
    lifecycle.apply_presence_mode(_Shell(orb=_Orb()), "quiet")
    assert written == ["quiet"]


def test_a_failing_save_does_not_stop_the_mode(lifecycle, monkeypatch):
    import memory.config_manager as cfg

    def boom(_mode):
        raise OSError("config is read-only")

    monkeypatch.setattr(cfg, "save_presence_mode", boom)
    orb = _Orb()
    assert lifecycle.apply_presence_mode(_Shell(orb=orb), "focus") is True
    assert orb.modes == ["focus"]


# ── the bar is a second door, and both are wired ──────────────────────────

def test_the_bar_chord_is_ctrl_space_not_the_summon_chord(lifecycle):
    """Two chords for two wishes: one brings the WINDOW back, one opens a line."""
    assert lifecycle.BAR_CHORD == ("ctrl", "space")
    assert lifecycle.BAR_CHORD != lifecycle.SUMMON_CHORD


def test_ambient_start_binds_the_bar_and_the_orb(lifecycle):
    """Read from the source: the wiring, not a desktop."""
    source = (ROOT / "ui" / "lifecycle.py").read_text(encoding="utf-8")
    block = source[source.index("def start_interface(shell"):
                   source.index("def start_tray(shell")]
    assert "start_orb(shell)" in block
    assert "start_command_bar(shell)" in block


def test_the_orb_click_opens_the_bar(lifecycle):
    """Read from the module that now owns the orb: the shell moved out of
    `lifecycle.py` when that file hit its ceiling, and a test pinned to the old
    location fails for the move rather than for the behaviour."""
    shell = (ROOT / "ui" / "ambient_shell.py").read_text(encoding="utf-8")
    orb_block = shell[shell.index("def start_orb(shell"):
                      shell.index("def start_command_bar(shell")]
    assert "open_command_bar" in orb_block, (
        "the orb is the only clickable surface in ambient mode; without this "
        "the ring is decoration")


def test_the_orb_follows_the_assistant_state(lifecycle):
    """A ring that keeps drawing "idle" while the assistant speaks is a still
    picture pretending to be a status light — and in ambient mode it is the
    only status light there is.

    `apply_state_everywhere` was a `lifecycle` free function taking a shell. It
    is `AmbientShell.set_state` now: the shell already owned every surface, and
    a module-level function that reached into three private attributes was the
    same code with a longer walk to it.
    """
    from ui.shell import AmbientShell

    orb, tray = _Orb(), _Orb()
    shell = AmbientShell.__new__(AmbientShell)      # no surfaces, no Qt
    shell._orb, shell._tray, shell._bubble = orb, tray, None
    shell._state = ""
    shell.set_state("SPEAKING")
    assert orb.states == ["speaking"], "the surfaces are told in one spelling"
    assert tray.states == ["speaking"], "the tooltip is the only readout in the tray"


def test_a_failing_orb_does_not_stop_the_tooltip(lifecycle):
    """The surfaces are independent: one that raises must not take the others
    down, because the tooltip is the only readout in the tray.

    The order matters as much as the guard: the tray is updated FIRST, so a
    broken orb cannot leave the one readable surface saying the old word.
    """
    from ui.shell import AmbientShell

    class _BrokenOrb:
        def set_state(self, _state):
            raise RuntimeError("no paint device")

    seen = []

    class _Tray:
        def set_state(self, state):
            seen.append(state)

    shell = AmbientShell.__new__(AmbientShell)
    shell._orb, shell._tray, shell._bubble = _BrokenOrb(), _Tray(), None
    shell._state = ""
    shell.set_state("LISTENING")
    assert seen == ["listening"], "the orb raised and the tray update was lost"


def test_there_is_no_mode_that_leaves_the_bar_chord_bound(lifecycle):
    """The bar is no longer one mode's door — it is the ONLY door.

    `set_interface_mode` used to bind Ctrl+Space in ambient and release it in
    HUD, because a window had a text field of its own. There is no window, so
    the chord is bound for the life of the process and released only on quit —
    which is what this asserts, because a chord released at the wrong moment
    leaves a running assistant with no way to say anything.
    """
    source = (ROOT / "ui" / "lifecycle.py").read_text(encoding="utf-8")
    quit_body = source[source.index("def quit_app(shell"):]
    quit_body = quit_body[:quit_body.index("def needs_attention")]
    assert "stop_bar_hotkey(shell)" in quit_body, (
        "the chord outlives the app, so Ctrl+Space is grabbed after exit")
    assert "def set_interface_mode" not in source, (
        "interface modes are back: the mockup has one, and it has no window")
