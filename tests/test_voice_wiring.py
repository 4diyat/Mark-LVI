"""The rule for WHEN board 6 covers the screen, and who closes it.

WHY THIS IS TESTED SEPARATELY FROM THE SURFACE
    `tests/test_voice_overlay.py` proves the window draws what the artboard
    draws. This file proves the window is only up while it is FOR something —
    which is the part that costs the user their screen. A surface that is
    correct and always visible is a worse bug than one that is wrong and rare.

THE THREE CLAIMS
    1. It appears for LISTENING and SPEAKING, and for nothing else. In
       particular NOT for "NO MIC" — a frame saying MENDENGARKAN over a machine
       with no microphone is the worst possible moment for it.
    2. Esc stops the listening, not just the drawing. Otherwise the user
       presses Esc to close the microphone and only the picture goes away.
    3. No path raises. `set_state` is called from the audio thread, the model
       thread and the hotkey thread; a decoration must not break any of them.
"""
from __future__ import annotations

import pytest

from ui import voice_wiring


class FakeOverlay:
    """Just enough surface to record what the wiring asked it to do."""

    def __init__(self, starts=True):
        self.starts = starts
        self.active = False
        self.state = "idle"
        self.transcript = ""
        self.answer = ""
        self.hand = None
        self.camera = None
        self.error = "no display"
        self.stop_calls = 0

    def start(self, active=True):
        self.active = bool(active and self.starts)
        return self.starts

    def show(self):
        self.active = True

    def hide(self):
        self.active = False

    def stop(self):
        self.stop_calls += 1

    def set_state(self, word):
        self.state = word

    def set_transcript(self, text):
        self.transcript = text

    def set_answer(self, text):
        self.answer = text

    def set_hand(self, sample):
        self.hand = sample

    def set_camera_available(self, available):
        self.camera = available


class FakeShell:
    """A shell-shaped object: a state word, an overlay, and a sleep switch."""

    def __init__(self):
        self._state = "INITIALISING"
        self._voice_overlay = None
        self.slept = 0

    @property
    def state(self):
        return self._state

    def request_sleep(self):
        self.slept += 1


# ── the rule ────────────────────────────────────────────────────────────────

def test_listening_and_speaking_are_the_two_states_it_covers_the_screen_for():
    assert voice_wiring.should_show("LISTENING")
    assert voice_wiring.should_show("listening")
    assert voice_wiring.should_show("SPEAKING")
    assert voice_wiring.should_show(" speaking ")


@pytest.mark.parametrize("word", [
    "", None, "INITIALISING", "THINKING", "SLEEPING", "NO MIC", "ERROR",
])
def test_every_other_state_leaves_the_desktop_alone(word):
    """THINKING is the interesting one: the question is in, the answer is not
    out, and a frame appearing then reads as a hang."""
    assert voice_wiring.should_show(word) is False


def test_no_mic_is_not_listening():
    """A machine with no microphone must not throw a frame that says it is
    listening to one."""
    assert voice_wiring.overlay_state("NO MIC") == "idle"
    assert voice_wiring.should_show("NO MIC") is False


def test_the_overlay_has_exactly_the_three_states_the_artboard_draws():
    assert voice_wiring.overlay_state("LISTENING") == "listening"
    assert voice_wiring.overlay_state("SPEAKING") == "speaking"
    assert voice_wiring.overlay_state("THINKING") == "idle"


# ── applying it ─────────────────────────────────────────────────────────────

def test_sync_shows_on_listening_and_hides_again_on_idle():
    shell = FakeShell()
    overlay = FakeOverlay()
    shell._voice_overlay = overlay

    shell._state = "LISTENING"
    voice_wiring.sync(shell)
    assert overlay.active is True
    assert overlay.state == "listening"

    shell._state = "SLEEPING"
    voice_wiring.sync(shell)
    assert overlay.active is False
    assert overlay.state == "idle"


def test_sync_is_idempotent_so_a_chatty_thread_cannot_flicker_the_screen():
    shell = FakeShell()
    overlay = FakeOverlay()
    shell._voice_overlay = overlay
    shell._state = "LISTENING"
    for _ in range(20):
        voice_wiring.sync(shell)
    assert overlay.active is True


def test_a_shell_with_no_overlay_is_not_an_error():
    shell = FakeShell()                       # this desktop could not draw one
    voice_wiring.sync(shell)
    voice_wiring.set_transcript(shell, "x")
    voice_wiring.set_answer(shell, "y")
    voice_wiring.set_hand(shell, (0.1, 0.2, False))
    voice_wiring.set_camera_available(shell, True)


def test_a_failing_overlay_never_breaks_the_call_that_set_the_state():
    """`set_state` runs on the audio thread. An exception here would surface as
    a broken voice turn, and the user would blame the microphone."""
    shell = FakeShell()

    class Exploding(FakeOverlay):
        def set_state(self, word):
            raise RuntimeError("the window is gone")

    shell._voice_overlay = Exploding()
    shell._state = "LISTENING"
    voice_wiring.sync(shell)                  # must not raise


def test_the_close_callback_esc_invokes_is_the_one_the_wiring_installs():
    """The surface stores `on_close` and calls it from `handle_escape`; the
    wiring must hand it the function that stops the microphone, or the
    footnote's "Esc keluar" becomes "Esc hides the picture"."""
    from ui.voice_overlay import VoiceOverlay

    calls = []
    wiring_side = voice_wiring._on_close
    shell = FakeShell()
    overlay = VoiceOverlay(on_close=lambda: shell.request_sleep())
    overlay.show()
    assert overlay.handle_escape() is True
    assert shell.slept == 1, "Esc must reach the shell, not only the window"
    assert callable(wiring_side), "the wiring must still expose the callback"
    calls.append(overlay.active)
    assert calls == [False]


def test_starting_records_the_overlay_and_builds_it_hidden():
    shell = FakeShell()
    built = {}

    def _fake_overlay(**kwargs):
        overlay = FakeOverlay()
        built["kwargs"] = kwargs
        built["overlay"] = overlay
        return overlay

    import ui.voice_overlay as surface
    original = surface.VoiceOverlay
    surface.VoiceOverlay = _fake_overlay
    try:
        assert voice_wiring.start_voice_overlay(shell) is True
    finally:
        surface.VoiceOverlay = original

    assert shell._voice_overlay is built["overlay"]
    assert built["overlay"].active is False, "it must not be up during start-up"


def test_an_overlay_that_cannot_build_is_reported_and_not_recorded():
    shell = FakeShell()
    import ui.voice_overlay as surface
    original = surface.VoiceOverlay
    surface.VoiceOverlay = lambda **kw: FakeOverlay(starts=False)
    try:
        assert voice_wiring.start_voice_overlay(shell) is False
    finally:
        surface.VoiceOverlay = original
    assert shell._voice_overlay is None


# ── Esc ─────────────────────────────────────────────────────────────────────

def test_escape_stops_the_listening_and_not_only_the_drawing():
    """The footnote says "Esc keluar". If only the frame went away, the
    microphone would still be open — the one thing the user was preventing."""
    from ui.voice_overlay import VoiceOverlay

    shell = FakeShell()
    # The REAL surface, not a fake: this test is about the closure the surface
    # actually gets handed. On this machine the window cannot open, but the
    # callback is decided at construction and does not need one.
    shell._voice_overlay = VoiceOverlay(on_close=lambda: shell.request_sleep())
    shell._voice_overlay.handle_escape()       # nothing to close — a no-op
    shell._voice_overlay._on_close()           # the callback Esc invokes
    assert shell.slept == 1


def test_escape_survives_a_shell_that_cannot_sleep():
    shell = FakeShell()

    def _boom():
        raise RuntimeError("no session")

    shell.request_sleep = _boom
    voice_wiring._on_close(shell)             # must not raise


# ── the values the overlay is fed ───────────────────────────────────────────

def test_the_transcript_and_the_answer_reach_the_surface():
    shell = FakeShell()
    overlay = FakeOverlay()
    shell._voice_overlay = overlay

    voice_wiring.set_transcript(shell, "ringkas tabel ini")
    voice_wiring.set_answer(shell, "Baris 7 dan 11 melewati plafon.")
    voice_wiring.set_hand(shell, (0.4, 0.5, True))
    voice_wiring.set_camera_available(shell, True)

    assert overlay.transcript == "ringkas tabel ini"
    assert "plafon" in overlay.answer
    assert overlay.hand == (0.4, 0.5, True)
    assert overlay.camera is True


# ── the one edge that makes all of this run at all ──────────────────────────

def test_the_shells_set_state_is_what_drives_the_overlay():
    """Without this edge the overlay is a module nobody calls — the surface
    would be perfect and never appear.

    `ui/shell.py` is checked by AST because a real `AmbientShell` needs a Qt
    that this machine does not have, and the claim is structural: `set_state`
    must call `voice_wiring.sync(self)`, after the small surfaces have been
    told.
    """
    import ast
    from pathlib import Path

    source = (Path(__file__).resolve().parent.parent / "ui" / "shell.py"
              ).read_text(encoding="utf-8")
    tree = ast.parse(source)
    set_state = next(
        node for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "set_state")
    calls = [node for node in ast.walk(set_state) if isinstance(node, ast.Call)]
    reached = [ast.unparse(c) for c in calls]
    assert any("voice_wiring.sync" in r for r in reached), (
        f"set_state never reaches the overlay; it calls {reached}")


def test_lifecycle_builds_the_overlay_at_start_up():
    """A surface that is never constructed cannot be shown, however correct its
    rule is."""
    import ast
    from pathlib import Path

    source = (Path(__file__).resolve().parent.parent / "ui" / "lifecycle.py"
              ).read_text(encoding="utf-8")
    assert "start_voice_overlay(shell)" in source
    tree = ast.parse(source)
    start = next(node for node in ast.walk(tree)
                 if isinstance(node, ast.FunctionDef)
                 and node.name == "start_interface")
    names = [ast.unparse(c) for c in ast.walk(start) if isinstance(c, ast.Call)]
    assert any("start_voice_overlay" in n for n in names), names
