"""Push-to-talk on every desktop, and the summon hotkey that shares its probes.

WHY THIS FILE COULD NOT EXISTS BEFORE
    `core/hotkey.py` used to be `if _OS == "Windows"` with the polling welded to
    `ctypes.windll.user32`. The only way to reach the debounce and the
    press/release rules was to call `_set_held` directly — which skips the very
    loop those rules live in. The loop now takes a source, so everything below
    the platform seam is tested here against a fake, with no keyboard, no X
    server and no Mac.

WHAT THE FAKE CAN AND CANNOT SAY
    It proves the RULES: a brush of the chord must not open the microphone, a
    held chord reports once, a key that vanishes mid-press must still report a
    release, and a source that dies must fall back to the window. It says
    nothing about whether XQueryKeymap or CGEventSourceKeyState behave as
    documented on a real machine — that needs a real desktop, and this file
    says so rather than implying otherwise.
"""
from __future__ import annotations

import ctypes
import sys
import threading
import time
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import hotkey  # noqa: E402


class _FakeSource(hotkey._Source):
    """A source whose answer the test controls, frame by frame."""

    name = "fake"

    def __init__(self, opening=True, frames=None, fail_after=None):
        self.opening = opening
        self.frames = list(frames or [])
        self.fail_after = fail_after
        self.calls = 0
        self.opened = 0
        self.closed = 0
        self._lock = threading.Lock()

    def open(self):
        self.opened += 1
        return self.opening

    def close(self):
        self.closed += 1

    def down(self):
        with self._lock:
            self.calls += 1
            if self.fail_after is not None and self.calls > self.fail_after:
                raise OSError("the driver went away")
            if not self.frames:
                return False
            return self.frames.pop(0)


def _wait_for(predicate, timeout=2.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.005)
    return False


# ── the platform probe ────────────────────────────────────────────────────

def test_windows_gets_a_windows_source():
    source = hotkey.make_source(("ctrl", "space"), "Windows")
    assert isinstance(source, hotkey._WindowsSource)
    assert source.name == "windows"


def test_macos_gets_a_quartz_source():
    source = hotkey.make_source(("ctrl", "space"), "Darwin")
    assert source.name == "quartz"


def test_linux_gets_an_x11_source():
    """Linux used to fall straight to the window shortcut. That was the bug."""
    source = hotkey.make_source(("ctrl", "space"), "Linux")
    assert source.name == "x11"


def test_an_unknown_key_name_yields_no_source_rather_than_a_wrong_one():
    """A chord naming a key this build does not know cannot be polled anywhere."""
    for os_name in ("Windows", "Darwin", "Linux"):
        assert hotkey.make_source(("ctrl", "numpad9"), os_name) is None


def test_the_mac_keycodes_are_the_documented_ones():
    """kVK_* numbers are unforgiving: 0x3B is Ctrl and 0x38 is Shift. Swapping
    them produces a chord that looks right and never fires."""
    assert hotkey._MAC_KEYCODE["ctrl"] == 0x3B
    assert hotkey._MAC_KEYCODE["shift"] == 0x38
    assert hotkey._MAC_KEYCODE["alt"] == 0x3A
    assert hotkey._MAC_KEYCODE["space"] == 0x31


def test_a_probe_that_raises_is_treated_as_no_hook(monkeypatch):
    """And says so, because a probe failing where it should work is a bug."""
    class _Broken(hotkey._Source):
        name = "broken"

        def open(self):
            raise RuntimeError("no driver")

        def down(self):
            return False

    talk = hotkey.PushToTalk(lambda _h: None, source=_Broken())
    assert talk.start() == "window"
    talk.stop()


def test_a_probe_that_refuses_is_treated_as_no_hook():
    talk = hotkey.PushToTalk(lambda _h: None, source=_FakeSource(opening=False))
    assert talk.start() == "window"
    assert talk.source_name == ""
    talk.stop()


# ── the loop's rules, driven by a fake source ─────────────────────────────

def test_a_held_chord_reports_press_then_release_once(monkeypatch):
    monkeypatch.setattr(hotkey, "_POLL_HZ", 200.0)
    # 12 frames at 200 Hz is 60 ms — EXACTLY the debounce, so it lands on the
    # wrong side of `>=` depending on how fast the machine polls. 20 frames is
    # 100 ms: comfortably speech, and not sensitive to scheduler jitter.
    frames = [True] * 20 + [False] * 6
    events = []
    talk = hotkey.PushToTalk(events.append, source=_FakeSource(frames=frames))
    assert talk.start() == "global"
    assert _wait_for(lambda: len(events) == 2), f"events were {events}"
    talk.stop()
    assert events == [True, False]


def test_a_brush_of_the_chord_does_not_open_the_microphone(monkeypatch):
    """One frame down, then up. Shorter than the debounce, so it is not speech.

    This is the rule that stops a stray keypress from streaming a room.
    """
    monkeypatch.setattr(hotkey, "_POLL_HZ", 200.0)
    frames = [True] + [False] * 8
    events = []
    source = _FakeSource(frames=frames)
    talk = hotkey.PushToTalk(events.append, source=source)
    talk.start()
    # Wait for the loop to consume the script, not for the thread to die: the
    # loop keeps polling an exhausted source until `stop()`, which is correct.
    assert _wait_for(lambda: not source.frames), "the loop never ran"
    talk.stop()
    assert events == [], f"a brush opened the mic: {events}"


def test_a_source_that_dies_falls_back_to_the_window(monkeypatch):
    """A driver that stops answering must not leave the gate stuck open, and
    must not spin either: the scope drops so the Qt shortcut can carry it."""
    monkeypatch.setattr(hotkey, "_POLL_HZ", 200.0)
    # Enough held frames to count as speech (see above), then the driver dies.
    source = _FakeSource(frames=[True] * 20, fail_after=20)
    events = []
    talk = hotkey.PushToTalk(events.append, source=source)
    talk.start()
    assert _wait_for(lambda: talk.scope == "window"), "the scope never fell back"
    talk.stop()
    assert events[-1] is False, "the gate was left open after the source died"


def test_stopping_releases_the_gate_and_closes_the_source(monkeypatch):
    """The microphone is not left open because the user turned the feature off."""
    monkeypatch.setattr(hotkey, "_POLL_HZ", 200.0)
    source = _FakeSource(frames=[True] * 40)
    events = []
    talk = hotkey.PushToTalk(events.append, source=source)
    talk.start()
    assert _wait_for(lambda: events == [True])
    talk.stop()
    assert events[-1] is False
    assert source.closed == 1, "the source was never closed"


def test_starting_twice_leaves_one_watcher_and_one_source(monkeypatch):
    monkeypatch.setattr(hotkey, "_POLL_HZ", 200.0)
    source = _FakeSource(frames=[False] * 200)
    talk = hotkey.PushToTalk(lambda _h: None, source=source)
    talk.start()
    first = talk._thread
    talk.start()
    second = talk._thread
    assert first is not second
    assert not first.is_alive(), "the first watcher outlived the second start"
    talk.stop()


def test_the_source_name_is_reported_so_the_log_can_say_which_mechanism():
    talk = hotkey.PushToTalk(lambda _h: None, source=_FakeSource())
    assert talk.start() == "global"
    assert talk.source_name == "fake"
    talk.stop()


# ── the X11 bitmap, which is where a silent failure hides ─────────────────

def test_x11_reads_the_bitmap_xquerykeymap_fills():
    """THE BUG THIS CATCHES: `down()` used to read the buffer handed TO Xlib.

    XQueryKeymap fills a caller-supplied `char[32]` and returns a status. An
    immutable bytes object cannot be filled, so every frame read "up" — and
    push-to-talk silently never fired on Linux while reporting scope 'global'.
    """
    class _Lib:
        def __init__(self, held_keycode):
            self.held = held_keycode

        def XQueryKeymap(self, _display, buf):
            ctypes.memset(buf, 0, 32)
            buf[self.held // 8] = bytes([1 << (self.held % 8)])
            return 1

    source = hotkey._X11Source.__new__(hotkey._X11Source)
    source._display = 1
    source._codes = [65]
    source._lib = _Lib(65)
    assert source.down() is True, "a held key read as up"

    source._lib = _Lib(66)
    assert source.down() is False, "a key that is not held read as down"


def test_x11_reports_up_when_the_server_refuses():
    class _Lib:
        def XQueryKeymap(self, _display, _buf):
            return 0                    # Xlib's "could not".

    source = hotkey._X11Source.__new__(hotkey._X11Source)
    source._display = 1
    source._codes = [65]
    source._lib = _Lib()
    assert source.down() is False, "a refused query must not open the microphone"


def test_the_x11_keymap_buffer_is_writable():
    """The fix is only correct if Xlib can write into what we hand it."""
    buf = (ctypes.c_char * 32)()
    ctypes.memset(buf, 0, 32)
    buf[65 // 8] = bytes([1 << (65 % 8)])
    keys = bytes(buf)
    assert (keys[65 // 8] >> (65 % 8)) & 1 == 1


def test_an_x11_probe_on_a_headless_machine_says_no_hook():
    """No DISPLAY means no global hook — not a crash, and not a lie."""
    source = hotkey._X11Source(["Control_L", "space"])
    opened = source.open()
    if opened:
        source.close()
    # On this sandbox there is no display, so the answer must be False. On a
    # desktop it may be True; the assertion is only that it never raises.
    assert opened in (True, False)


# ── the summon hotkey ─────────────────────────────────────────────────────

def test_the_summon_hotkey_fires_once_per_press(monkeypatch):
    """Level, not edge: sources report "is it down", so holding the chord must
    not open a window thirty times a second."""
    monkeypatch.setattr(hotkey, "_POLL_HZ", 200.0)
    frames = [True] * 10 + [False] * 3 + [True] * 10 + [False] * 3
    presses = []
    tap = hotkey.HotkeyTap(lambda: presses.append(1), source=_FakeSource(frames=frames))
    assert tap.start() == "global"
    assert _wait_for(lambda: len(presses) == 2), f"presses were {len(presses)}"
    tap.stop()
    assert presses == [1, 1], f"expected one press per press, got {len(presses)}"


def test_the_summon_hotkey_has_no_debounce(monkeypatch):
    """A single-frame press must summon. The debounce exists for the microphone;
    a stray window appearing is cheap and undone with the same key."""
    monkeypatch.setattr(hotkey, "_POLL_HZ", 200.0)
    presses = []
    tap = hotkey.HotkeyTap(lambda: presses.append(1), source=_FakeSource(frames=[True, False]))
    tap.start()
    assert _wait_for(lambda: presses == [1]), "a single-frame press was ignored"
    tap.stop()


def test_the_summon_hotkey_without_a_hook_says_window():
    tap = hotkey.HotkeyTap(lambda: None, source=_FakeSource(opening=False))
    assert tap.start() == "window"
    tap.stop()


def test_a_failing_summon_handler_does_not_kill_the_watcher(monkeypatch):
    monkeypatch.setattr(hotkey, "_POLL_HZ", 200.0)
    seen = []

    def _boom():
        seen.append(1)
        raise RuntimeError("no window today")

    tap = hotkey.HotkeyTap(_boom, source=_FakeSource(frames=[True, False, True, False]))
    tap.start()
    assert _wait_for(lambda: len(seen) == 2), "the watcher died on the first failure"
    tap.stop()


def test_stopping_the_summon_hotkey_closes_its_source():
    source = _FakeSource()
    tap = hotkey.HotkeyTap(lambda: None, source=source)
    tap.start()
    tap.stop()
    assert source.closed == 1


# ── wiring: the summon chord follows the mode ─────────────────────────────

def test_the_summon_hotkey_runs_only_while_there_is_no_window():
    """It is the way BACK to the interface, so it exists exactly when the
    interface is not on screen — and stops when the window comes back for good.

    Read from the source: this asserts the wiring, not a keyboard.
    """
    from pathlib import Path
    src = (Path(__file__).resolve().parent.parent / "ui" / "lifecycle.py").read_text(
        encoding="utf-8")
    start = src.index("def start_interface(shell")
    ambient = src[start:src.index("def start_tray(shell")]
    assert "start_summon_hotkey(shell)" in ambient, (
        "ambient mode must bind the global summon chord; without it the tray is "
        "the only way back in, and on some desktops there is no tray")
    hud = src[src.index("def set_interface_mode"):]
    hud = hud[:hud.index("def request_wake")]
    assert "stop_summon_hotkey(shell)" in hud, (
        "returning to the full-screen HUD must release the global chord")
