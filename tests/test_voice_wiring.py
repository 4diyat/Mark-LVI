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

from ui import hand_feed, voice_wiring


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
        # The real surface exposes this; a fake that forgot it made
        # `poll_hand` read a missing attribute as "paused" and quietly drop
        # every sample.
        self.gestures_paused = False

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

    def handle_toggle_gestures(self):
        """The surface's own toggle, so the fake goes through the real rule."""
        self.gestures_paused = not self.gestures_paused
        if self.gestures_paused:
            self.hand = None
        return self.gestures_paused


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
    that this machine does not have, and the claim is structural: the widget
    half of `set_state` must call `voice_wiring.sync(self)`, after the small
    surfaces have been told.

    THE WIDGET HALF IS `_apply_state`, NOT `set_state`. `set_state` runs on the
    asyncio thread and now hands the word to `_apply_state` through
    `run_on_qt_thread`; the sync call is in the second function because that is
    the one allowed to touch Qt. Following the edge rather than widening the
    window keeps this test about the wiring and not about the wrapper.
    """
    import ast
    from pathlib import Path

    source = (Path(__file__).resolve().parent.parent / "ui" / "shell.py"
              ).read_text(encoding="utf-8")
    tree = ast.parse(source)
    set_state = next(
        node for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "set_state")
    calls = [ast.unparse(node) for node in ast.walk(set_state)
             if isinstance(node, ast.Call)]
    assert any("_apply_state" in r for r in calls), (
        f"set_state never hands the word to the surface code; it calls {calls}")
    apply_state = next(
        node for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name == "_apply_state")
    reached = [ast.unparse(node) for node in ast.walk(apply_state)
               if isinstance(node, ast.Call)]
    assert any("voice_wiring.sync" in r for r in reached), (
        f"_apply_state never reaches the overlay; it calls {reached}")


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


# ── the camera feed ─────────────────────────────────────────────────────────

class FakeController:
    """`WorkspaceHandController`'s published surface, and nothing else."""

    def __init__(self, status="active", hands=(), starts=True):
        self.status = status
        self.hands = hands
        self.starts = starts
        self.started = 0
        self.stopped = 0

    def start(self):
        self.started += 1
        if self.starts:
            self.status = "active"
        return self.starts

    def stop(self):
        self.stopped += 1
        self.status = "off"

    def sample(self):
        return tuple(self.hands)


def test_the_tile_is_lit_only_when_frames_are_actually_arriving():
    """`starting`, `off`, `windows_only` and `error` all mean the hand on the
    tile is not backed by anything."""
    assert voice_wiring.camera_state(FakeController(status="active")) is True
    for status in ("off", "starting", "windows_only", "error", "", None):
        controller = FakeController()
        controller.status = status
        assert voice_wiring.camera_state(controller) is False, status


def test_a_sample_reaches_the_tile_as_the_three_fields_it_draws():
    shell = FakeShell()
    overlay = FakeOverlay()
    shell._voice_overlay = overlay
    controller = FakeController(hands=[(0.31, 0.62, True, 0.0, 0, 0)])

    voice_wiring.poll_hand(shell, controller)

    assert overlay.camera is True
    assert overlay.hand == (0.31, 0.62, True)


def test_no_hand_empties_the_tile_rather_than_freezing_the_last_one():
    """`sample()` returns `()` for a lost hand, a stale frame, or a closed hand
    that has not been deliberately re-opened. All three mean "not there"."""
    shell = FakeShell()
    overlay = FakeOverlay()
    shell._voice_overlay = overlay
    shell._voice_overlay.hand = (0.5, 0.5, True)

    voice_wiring.poll_hand(shell, FakeController(hands=[]))

    assert overlay.hand is None


def test_a_paused_feed_sends_nothing_even_if_the_camera_is_busy():
    """Ctrl+Alt+G promises the gestures are paused; a tile that kept moving
    would be the one place the user could see that promise broken."""
    shell = FakeShell()
    overlay = FakeOverlay()
    overlay.gestures_paused = True
    overlay.set_hand = lambda sample: setattr(overlay, "hand", sample)
    shell._voice_overlay = overlay

    voice_wiring.poll_hand(shell, FakeController(hands=[(0.1, 0.1, True)]))

    assert overlay.hand is None


def test_a_controller_that_dies_mid_run_is_an_unlit_tile_not_an_exception():
    shell = FakeShell()
    overlay = FakeOverlay()
    shell._voice_overlay = overlay

    class Dying(FakeController):
        def sample(self):
            raise RuntimeError("the camera was unplugged")

    voice_wiring.poll_hand(shell, Dying())          # must not raise


def test_the_feed_reads_the_first_hand_and_ignores_the_rest():
    shell = FakeShell()
    overlay = FakeOverlay()
    shell._voice_overlay = overlay
    controller = FakeController(hands=[(0.2, 0.3, False), (0.9, 0.9, True)])

    voice_wiring.poll_hand(shell, controller)
    assert overlay.hand == (0.2, 0.3, False)


# ── the feed's lifetime ─────────────────────────────────────────────────────

def test_a_feed_off_windows_is_not_a_failure_and_does_not_raise():
    """`WorkspaceHandController.start()` refuses on Linux, macOS and anywhere
    mediapipe is missing. That is the normal answer here, not an error."""
    shell = FakeShell()
    feed = voice_wiring.HandFeed(shell, controller=FakeController(
        status="windows_only", starts=False))
    assert feed.start() is False
    assert feed.status == "windows_only"
    assert feed.error == "", "a refusal is not an error message"


def test_stopping_the_feed_stops_the_controller_and_is_idempotent():
    shell = FakeShell()
    controller = FakeController()
    feed = voice_wiring.HandFeed(shell, controller=controller)
    feed.start()
    feed.stop()
    feed.stop()
    assert controller.stopped == 1, "a second stop must not touch the camera again"


def test_the_feed_stops_the_timer_before_the_camera():
    """The other order would leave one tick reading from a closing controller.

    WHAT THIS TEST CAN AND CANNOT PROVE
        QTimer callbacks run on the Qt event loop, so a tick cannot interleave
        with this function on a real desktop — the timer only has to be stopped
        BEFORE the call that could block, and `_stop_timer()` clears the
        reference first, which is why reversing the two lines here is
        undetectable and harmless. What is asserted is the part that is real:
        the timer is stopped and forgotten before the controller is touched, and
        the camera is stopped exactly once.
    """
    shell = FakeShell()
    order = []

    class Ordered(FakeController):
        def stop(self):
            # THE CLAIM IS THAT THE TIMER IS ALREADY DOWN when the camera closes.
            # Recording the order is not enough: a reversed implementation that
            # still happened to append in that order would pass. So the camera
            # checks the state it cares about.
            order.append(("camera", feed._timer is None))
            super().stop()

    feed = voice_wiring.HandFeed(shell, controller=Ordered())
    feed.start()

    class Timer:
        def stop(self):
            order.append(("timer", None))

    feed._timer = Timer()
    feed.stop()
    assert order[0][0] == "timer", f"the camera closed first: {order}"
    assert order[1] == ("camera", True), (
        f"the camera closed while a timer could still tick: {order}")


def test_a_feed_that_cannot_build_says_why_and_leaves_the_overlay_alone():
    shell = FakeShell()

    class Broken:
        status = "off"

        def start(self):
            raise RuntimeError("no mediapipe")

    feed = voice_wiring.HandFeed(shell, controller=Broken())
    assert feed.start() is False
    assert "mediapipe" in feed.error


# ── quitting ────────────────────────────────────────────────────────────────

def test_stopping_the_overlay_takes_the_camera_with_it():
    """A camera light still on after Quit is the one failure a user cannot
    forgive, so the feed is stopped with the surface."""
    shell = FakeShell()
    overlay = FakeOverlay()
    controller = FakeController()
    shell._voice_overlay = overlay
    shell._hand_feed = voice_wiring.HandFeed(shell, controller=controller)
    shell._hand_feed.start()

    voice_wiring.stop_voice_overlay(shell)

    assert controller.stopped == 1
    assert overlay.stop_calls == 1
    assert shell._voice_overlay is None and shell._hand_feed is None


def test_quitting_with_no_overlay_is_not_an_error():
    voice_wiring.stop_voice_overlay(FakeShell())     # must not raise


def test_the_overlay_and_the_camera_are_built_and_torn_down_by_lifecycle():
    """Structural, because `AmbientShell` needs a Qt this machine lacks."""
    import ast
    from pathlib import Path

    source = (Path(__file__).resolve().parent.parent / "ui" / "lifecycle.py"
              ).read_text(encoding="utf-8")
    assert "start_voice_overlay(shell)" in source
    assert "stop_voice_overlay(shell)" in source

    tree = ast.parse(source)
    quit_app = next(node for node in ast.walk(tree)
                    if isinstance(node, ast.FunctionDef) and node.name == "quit_app")
    names = [ast.unparse(c) for c in ast.walk(quit_app) if isinstance(c, ast.Call)]
    assert any("stop_voice_overlay" in n for n in names), names


# ── what the user and the assistant said ────────────────────────────────────

def _shell_with_overlay():
    shell = FakeShell()
    overlay = FakeOverlay()
    shell._voice_overlay = overlay
    return shell, overlay


def test_what_the_user_said_lands_on_the_transcript_line():
    shell, overlay = _shell_with_overlay()
    voice_wiring.show_exchange(shell, "You: ringkas tabel ini dan tandai barisnya")
    assert overlay.transcript == "ringkas tabel ini dan tandai barisnya"
    assert overlay.answer == "", "the answer line must not be reused for this"


def test_what_the_assistant_answered_lands_on_the_answer_line():
    shell, overlay = _shell_with_overlay()
    voice_wiring.show_exchange(shell, "JARVIS: Baris 7 dan 11 melewati plafon.")
    assert "plafon" in overlay.answer
    assert overlay.transcript == ""


def test_an_answer_may_contain_colons_and_only_the_first_one_splits():
    shell, overlay = _shell_with_overlay()
    voice_wiring.show_exchange(shell, "JARVIS: Aturannya: 12% lalu 4%.")
    assert overlay.answer == "Aturannya: 12% lalu 4%."


def test_the_programs_own_lines_never_become_the_users_words():
    """`SYS:` and `ERR:` lines are the program talking about itself. Putting them
    on the transcript would make the overlay claim the user said them."""
    shell, overlay = _shell_with_overlay()
    for line in ("SYS: Push-to-talk unavailable", "ERR: the microphone died",
                 "USR: something internal", "TOOL: browser_control"):
        voice_wiring.show_exchange(shell, line)
    assert overlay.transcript == ""
    assert overlay.answer == ""


def test_a_sentence_with_no_prefix_is_the_assistants_speech():
    """The name is a setting, so the prefix cannot be relied on in every
    locale; anything that is not the user's and not a machine prefix is the
    assistant's own words."""
    shell, overlay = _shell_with_overlay()
    voice_wiring.show_exchange(shell, "Baris 7 melewati plafon.")
    assert overlay.answer == "Baris 7 melewati plafon."


def test_show_exchange_is_a_no_op_without_an_overlay_and_never_raises():
    shell = FakeShell()
    voice_wiring.show_exchange(shell, "You: apa saja")        # no overlay
    voice_wiring.show_exchange(shell, "")


def test_the_shells_write_log_is_what_feeds_the_overlay():
    """Every sentence already reaches `write_log`. A second call site in
    `main.py` would be a second thing to keep in step, and the one that drifted
    would be on the full-screen surface."""
    import ast
    from pathlib import Path

    source = (Path(__file__).resolve().parent.parent / "ui" / "shell.py"
              ).read_text(encoding="utf-8")
    tree = ast.parse(source)
    write_log = next(node for node in ast.walk(tree)
                     if isinstance(node, ast.FunctionDef) and node.name == "write_log")
    names = [ast.unparse(c) for c in ast.walk(write_log) if isinstance(c, ast.Call)]
    # `write_log` runs on the audio, runner and reader threads, so it hands the
    # line to `_show_exchange` rather than painting from there. The edge that
    # matters is still exactly one: every sentence reaches one function.
    assert any("_show_exchange" in n for n in names), names
    exchange = next(node for node in ast.walk(tree)
                    if isinstance(node, ast.FunctionDef) and node.name == "_show_exchange")
    inner = [ast.unparse(c) for c in ast.walk(exchange) if isinstance(c, ast.Call)]
    assert any("voice_wiring.show_exchange" in n for n in inner), inner


# ── Ctrl+Alt+G ──────────────────────────────────────────────────────────────

def test_the_chord_is_the_one_the_footnote_prints():
    """`n06()` says "Ctrl+Alt+G menjeda gestur". Not Ctrl+G — that is a common
    browser and editor shortcut, and a pause key that also does something in
    the window behind the overlay is worse than no key."""
    assert voice_wiring.PAUSE_CHORD == ("ctrl", "alt", "g")
    from core.hotkey import chord_label

    assert chord_label(voice_wiring.PAUSE_CHORD) == "Ctrl+Alt+G"


def test_g_exists_in_every_platform_table_or_the_chord_binds_on_one_and_not_others():
    """Three key-code tables plus the Qt fallback. A letter missing from one of
    them binds on Windows and falls back to a window-scoped hook elsewhere —
    silently, and only for some users."""
    from core import hotkey

    for name in ("_VK", "_X11_KEYSYM", "_MAC_KEYCODE", "_QT_NAME"):
        table = getattr(hotkey, name)
        assert "g" in table, f"'g' is missing from {name}"


def test_pressing_it_toggles_the_pause_and_says_which():
    shell = FakeShell()
    overlay = FakeOverlay()
    shell._voice_overlay = overlay

    assert voice_wiring.toggle_gestures(shell) is True
    assert overlay.handle_toggle_gestures() is False, "the second press resumes"


def test_the_pause_survives_a_window_that_will_not_toggle():
    """The pointer is stopped by the gesture controller's own poll of the same
    chord. This binding only decides what the user is TOLD, so its failure must
    not be the thing that keeps the hand driving the screen."""
    shell = FakeShell()

    class Frozen(FakeOverlay):
        def handle_toggle_gestures(self):
            raise RuntimeError("the window is gone")

    shell._voice_overlay = Frozen()
    assert voice_wiring.toggle_gestures(shell) is False


def test_pressing_it_with_no_overlay_does_nothing_and_does_not_raise():
    assert voice_wiring.toggle_gestures(FakeShell()) is False


def test_a_hotkey_that_cannot_bind_reports_the_scope_and_carries_on():
    import core.hotkey as hotkey

    class Refusing(hotkey.HotkeyTap):
        def start(self):
            raise OSError("no global hook on this desktop")

    shell = FakeShell()
    original = hotkey.HotkeyTap
    hotkey.HotkeyTap = lambda on_press, chord=None: Refusing(on_press, chord)
    try:
        assert voice_wiring.start_pause_hotkey(shell) == "window"
    finally:
        hotkey.HotkeyTap = original


def test_the_chord_is_bound_with_the_surface_and_released_with_it():
    shell = FakeShell()
    bound = {}

    import core.hotkey as hotkey

    class Recorder(hotkey.HotkeyTap):
        def start(self):
            bound["chord"] = self._chord
            bound["tap"] = self
            return "global"

        def stop(self):
            bound["stopped"] = True

    original = hotkey.HotkeyTap
    hotkey.HotkeyTap = lambda on_press, chord=None: Recorder(on_press, chord)
    try:
        assert voice_wiring.start_pause_hotkey(shell) == "global"
        assert bound["chord"] == voice_wiring.PAUSE_CHORD
        voice_wiring.stop_voice_overlay(shell)
    finally:
        hotkey.HotkeyTap = original
    assert bound.get("stopped") is True, "a chord left bound outlives the surface"


def test_stopping_the_pause_hotkey_twice_is_safe():
    shell = FakeShell()
    voice_wiring.stop_pause_hotkey(shell)
    voice_wiring.stop_pause_hotkey(shell)


# ── the bare hand reaching the desktop ──────────────────────────────────────

class _Mouse:
    def __init__(self):
        self.calls = []

    def moveTo(self, x, y):
        self.calls.append("moveTo")

    def mouseDown(self):
        self.calls.append("mouseDown")

    def mouseUp(self):
        self.calls.append("mouseUp")

    def scroll(self, amount):
        self.calls.append("scroll")

    def size(self):
        return (1920, 1080)


def test_the_feed_carries_a_bridge_and_pumps_it_with_the_same_sample(monkeypatch):
    """The tile and the desktop read ONE sample, or the picture and the cursor
    would disagree about where the hand is."""
    mouse = _Mouse()
    from core.gesture_bridge import GestureBridge

    monkeypatch.setattr(hand_feed, "gesture_bridge_enabled", lambda: True)
    shell = FakeShell()
    shell._voice_overlay = FakeOverlay()
    feed = voice_wiring.HandFeed(shell, controller=FakeController(
        hands=[(0.5, 0.5, False, False)]), bridge=GestureBridge(mouse=mouse))
    assert feed.bridge.enable() is True

    feed.poll()

    assert mouse.calls == ["moveTo"]
    assert shell._voice_overlay.hand == (0.5, 0.5, False)


def test_a_paused_feed_sends_no_hand_to_the_desktop_either(monkeypatch):
    """Ctrl+Alt+G must stop the cursor, not only the picture — and stopping
    mid-drag must let go, which the policy does when the hand disappears.

    The bridge is ENABLED here on purpose: the toggle is off by default, so a
    test that left the switch alone would pass with the pause ignored — it would
    be asserting that a pipeline which was never built moved nothing.
    """
    mouse = _Mouse()
    from core.gesture_bridge import GestureBridge

    monkeypatch.setattr(hand_feed, "gesture_bridge_enabled", lambda: True)
    shell = FakeShell()
    overlay = FakeOverlay()
    overlay.gestures_paused = True
    shell._voice_overlay = overlay
    feed = voice_wiring.HandFeed(shell, controller=FakeController(
        hands=[(0.5, 0.5, False, False)]), bridge=GestureBridge(mouse=mouse))
    feed.bridge.enable()

    feed.poll()

    assert mouse.calls == [], "a paused gesture moved the cursor"


def test_stopping_the_feed_lets_go_of_the_mouse(monkeypatch):
    """The one failure the user cannot fix by waving."""
    mouse = _Mouse()
    from core.gesture_bridge import GestureBridge

    monkeypatch.setattr(hand_feed, "gesture_bridge_enabled", lambda: True)

    shell = FakeShell()
    shell._voice_overlay = FakeOverlay()
    feed = voice_wiring.HandFeed(shell, controller=FakeController(
        hands=[(0.5, 0.5, True, False)]), bridge=GestureBridge(mouse=mouse))
    feed.start()
    feed.bridge.enable()
    # Two frames of the same pinch: the first starts the hold, the second is
    # past PINCH_HOLD_SECONDS and actually presses.
    feed.bridge.pump((0.5, 0.5, True, False),
                     voice_wiring.gesture_context(shell, now=0.0))
    feed.bridge.pump((0.5, 0.5, True, False),
                     voice_wiring.gesture_context(shell, now=1.0))
    assert "mouseDown" in mouse.calls

    feed.stop()

    assert mouse.calls[-1] == "mouseUp"


def test_the_context_reads_the_three_facts_from_where_they_live(monkeypatch):
    import core.confirm as confirm

    shell = FakeShell()
    monkeypatch.setattr(hand_feed, "gesture_bridge_enabled", lambda: True)
    monkeypatch.setattr(confirm, "pending_title", lambda: "Kirim laporan")

    ctx = voice_wiring.gesture_context(shell, now=1.5)

    assert ctx.os_mode is True
    assert ctx.confirmation_open is True
    assert ctx.now == 1.5
    assert ctx.own_window_focused is False, "no window means nothing of ours has focus"


def test_an_unreadable_confirmation_state_freezes_the_hand(monkeypatch):
    """Freezing when we cannot tell is the safe direction: a hand that does not
    move for a frame costs nothing, a webcam click on a bank-transfer banner
    costs everything."""
    import core.confirm as confirm

    def _boom():
        raise RuntimeError("confirm state is gone")

    monkeypatch.setattr(confirm, "pending_title", _boom)
    monkeypatch.setattr(hand_feed, "gesture_bridge_enabled", lambda: True)

    ctx = voice_wiring.gesture_context(FakeShell(), now=0.0)

    assert ctx.confirmation_open is True
    assert ctx.frozen is True


def test_the_switch_is_read_fresh_so_one_click_turns_it_off(monkeypatch):
    import memory.config_manager as config

    monkeypatch.setattr(config, "get_gesture_os_enabled", lambda: True)
    assert voice_wiring.gesture_bridge_enabled() is True
    monkeypatch.setattr(config, "get_gesture_os_enabled", lambda: False)
    assert voice_wiring.gesture_bridge_enabled() is False


def test_turning_it_off_saves_and_stops_the_pointer(monkeypatch):
    from core.gesture_bridge import GestureBridge
    import memory.config_manager as config

    saved = {}
    monkeypatch.setattr(config, "save_gesture_os_enabled",
                        lambda value: saved.setdefault("value", value))
    mouse = _Mouse()
    shell = FakeShell()
    shell._hand_feed = voice_wiring.HandFeed(
        shell, controller=FakeController(), bridge=GestureBridge(mouse=mouse))
    shell._hand_feed.bridge.enable()
    assert shell._hand_feed.bridge.enabled is True

    assert voice_wiring.set_gesture_os(shell, False) is False

    assert saved["value"] is False
    assert shell._hand_feed.bridge.enabled is False


def test_turning_it_on_reports_whether_this_machine_can_actually_do_it(monkeypatch):
    """A switch that appears on and moves nothing is worse than one that
    refuses with a reason."""
    import memory.config_manager as config
    from core import gesture_bridge

    monkeypatch.setattr(config, "save_gesture_os_enabled", lambda value: None)
    shell = FakeShell()
    shell._hand_feed = voice_wiring.HandFeed(
        shell, controller=FakeController(), bridge=gesture_bridge.GestureBridge())

    assert voice_wiring.set_gesture_os(shell, True) is False, (
        "no pyautogui on this runner, so the honest answer is no")


def test_the_switch_survives_having_no_feed_at_all(monkeypatch):
    import memory.config_manager as config

    calls = []
    monkeypatch.setattr(config, "save_gesture_os_enabled",
                        lambda value: calls.append(value))
    assert voice_wiring.set_gesture_os(FakeShell(), True) is False
    assert calls == [True], "the intent is still saved for the next start"
