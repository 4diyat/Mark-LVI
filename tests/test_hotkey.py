"""Push-to-talk: the part that can be checked without a keyboard.

WHY THE DEBOUNCE AND THE SCOPE ARE THE TESTS
    The chord itself cannot be pressed here, but the two decisions that decide
    what the user EXPERIENCES can be:

      * `scope` — 'global' means it works while another window has focus,
        'window' means only when the assistant's window does. The app promises
        neither more nor less than what it reports, so the report must be
        honest: a platform with no hook installed says 'window'.
      * the debounce — a stray brush of the chord must not open the microphone,
        and a release must always be reported even if the key vanished.

    The polling loop itself is Windows-only ctypes; it is exercised through the
    same `_set_held` the loop calls, which is where the state machine lives.
"""
from __future__ import annotations

from core import hotkey


def test_the_chord_is_readable_by_a_person_and_by_qt():
    assert hotkey.chord_label(("ctrl", "space")) == "Ctrl+Space"
    assert hotkey.qt_sequence(("ctrl", "space")) == "Ctrl+Space"
    assert hotkey.chord_label(("shift", "f9")) == "Shift+F9"


def test_an_unknown_key_name_is_title_cased_rather_than_dropped():
    """The chord map is small; a new key must not render as an empty string."""
    assert hotkey.chord_label(("ctrl", "q")) == "Ctrl+Q"


def test_a_machine_without_the_platform_hook_says_window_not_global(monkeypatch):
    monkeypatch.setattr(hotkey, "_OS", "Linux")
    talk = hotkey.PushToTalk(lambda _held: None)

    assert talk.start() == "window"
    assert talk.scope == "window"
    talk.stop()


def test_windows_without_the_key_codes_falls_back_to_the_window(monkeypatch):
    """A chord naming keys this build does not know cannot be polled."""
    monkeypatch.setattr(hotkey, "_OS", "Windows")
    talk = hotkey.PushToTalk(lambda _held: None, chord=("ctrl", "numpad9"))

    assert talk.start() == "window"
    talk.stop()


def test_press_and_release_reach_the_listener_once_each():
    events = []
    talk = hotkey.PushToTalk(events.append)

    talk.set_held(True)
    talk.set_held(True)          # key repeat, not a second press
    talk.set_held(False)
    talk.set_held(False)

    assert events == [True, False]
    assert talk.held is False


def test_the_listener_being_broken_does_not_kill_the_watcher():
    """A UI callback that raised would otherwise silence push-to-talk forever."""
    calls = []

    def broken(held):
        calls.append(held)
        raise RuntimeError("the window went away")

    talk = hotkey.PushToTalk(broken)

    talk.set_held(True)          # must not raise
    talk.set_held(False)

    assert calls == [True, False]


def test_stop_always_reports_a_release():
    """Released between polls: the app would otherwise stay 'listening'."""
    events = []
    talk = hotkey.PushToTalk(events.append)
    talk.set_held(True)

    talk.stop()

    assert events[-1] is False
    assert talk.held is False


def test_stopping_something_that_never_started_is_harmless():
    talk = hotkey.PushToTalk(lambda _held: None)
    talk.stop()
    talk.stop()
    assert talk.scope == "window"


def test_starting_twice_does_not_leave_two_watchers(monkeypatch):
    """`start()` stops first; a second watcher would double every event."""
    monkeypatch.setattr(hotkey, "_OS", "Linux")
    events = []
    talk = hotkey.PushToTalk(events.append)

    talk.start()
    talk.start()
    talk.set_held(True)
    talk.stop()

    assert events == [True, False]


def test_the_label_survives_a_custom_chord():
    talk = hotkey.PushToTalk(lambda _held: None, chord=("alt", "f10"))
    assert talk.label == "Alt+F10"


def test_a_held_key_is_reported_after_the_debounce_window(monkeypatch):
    """The polling loop's state machine, driven without ctypes.

    `_poll_loop` itself needs Windows and a keyboard; everything it decides is in
    `_set_held`, and the debounce is the rule that a key must be down for 60 ms
    before it counts. That window is asserted from the constant, so shortening
    it to zero would have to be a deliberate edit rather than an accident.
    """
    assert hotkey._DEBOUNCE_S >= 0.03, "a brush of the chord must not open the mic"
    events = []
    talk = hotkey.PushToTalk(events.append)

    # What the loop does once the key has been down long enough:
    talk._set_held(True)
    assert talk.held is True and events == [True]
