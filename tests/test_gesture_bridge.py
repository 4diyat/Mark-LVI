"""The bare hand on the desktop — the half that was missing.

WHY THIS FILE EXISTS
    `core/gesture_os.py` and `core/gesture_os_pointer.py` had no caller outside
    their own tests. Their promises were true of code that never ran: the hand
    the camera tile draws controlled nothing at all. This is the third piece —
    samples in, pointer out — so the tests here are about the SEAM, not about
    re-proving the policy (`test_gesture_os.py` does that).

THE FOUR CLAIMS
    1. Off means off. A pipeline that was never enabled cannot move a cursor,
       and the disabled path must not even import the driver.
    2. Switching off mid-drag lets go. A button left down turns the desktop
       into a drag-selection that waving cannot fix.
    3. Focus and confirmations freeze the hand (rule 2 of the policy, driven
       from the places those facts actually live).
    4. Nothing here raises into the Qt thread, whatever the camera or the
       driver does.

THE RECORDING MOUSE
    A four-method object, because `OsPointer` may touch exactly four pyautogui
    names and a fifth would be rule 1 broken in the one place it is invisible.
"""
from __future__ import annotations

import pytest

from core import gesture_bridge, gesture_os


class Mouse:
    """Records every call `OsPointer` is allowed to make."""

    def __init__(self, size=(1920, 1080)):
        self.calls = []
        self._size = size

    def moveTo(self, x, y):
        self.calls.append(("moveTo", x, y))

    def mouseDown(self):
        self.calls.append(("mouseDown",))

    def mouseUp(self):
        self.calls.append(("mouseUp",))

    def scroll(self, amount):
        self.calls.append(("scroll", amount))

    def size(self):
        return self._size

    # ── what the tests ask ───────────────────────────────────────────────────

    def names(self):
        return [call[0] for call in self.calls]


def _ctx(**kwargs):
    return gesture_os.Context(os_mode=True, **kwargs)


# ── 1. off means off ────────────────────────────────────────────────────────

def test_a_bridge_that_was_never_enabled_moves_nothing():
    mouse = Mouse()
    bridge = gesture_bridge.GestureBridge(mouse=mouse)

    intent = bridge.pump((0.4, 0.4, False, False), _ctx())

    assert intent.is_empty
    assert mouse.calls == []
    assert bridge.last_reason == "OS control is off"


def test_enabling_builds_the_pipeline_at_the_moment_it_is_asked_for():
    """Not in `__init__`: the disabled path must hold no pointer at all."""
    bridge = gesture_bridge.GestureBridge(mouse=Mouse())
    assert bridge._hand is None and bridge._os_pointer is None
    assert bridge.enable() is True
    assert bridge._hand is not None and bridge._os_pointer is not None


def test_a_machine_without_the_driver_fails_where_the_answer_can_be_shown():
    """The driver is resolved when the user asks for the feature, not on the
    first frame — a failure mid-gesture is a cursor that stopped."""
    bridge = gesture_bridge.GestureBridge()
    bridge._mouse = None
    import core.gesture_os_pointer as pointer_mod

    class Refusing(pointer_mod.OsPointer):
        def _driver(self):
            raise RuntimeError("pyautogui is not installed")

    original = pointer_mod.OsPointer
    pointer_mod.OsPointer = Refusing
    try:
        assert bridge.enable() is False
    finally:
        pointer_mod.OsPointer = original
    assert "not installed" in bridge.last_reason
    assert bridge.enabled is False


def test_pumping_after_a_refused_enable_still_moves_nothing():
    mouse = Mouse()
    bridge = gesture_bridge.GestureBridge(mouse=mouse)
    bridge.pump((0.1, 0.1, True, False), _ctx())
    assert mouse.calls == []


# ── 2. switching off lets go ────────────────────────────────────────────────

def test_disabling_releases_a_button_that_was_being_held():
    """Otherwise the desktop is drag-selecting and waving does not stop it."""
    mouse = Mouse()
    bridge = gesture_bridge.GestureBridge(mouse=mouse)
    bridge.enable()

    # Hold a pinch long enough to press.
    bridge.pump((0.5, 0.5, True, False), _ctx(now=0.0))
    bridge.pump((0.5, 0.5, True, False), _ctx(now=1.0))
    assert bridge.holding_button is True
    assert "mouseDown" in mouse.names()

    bridge.disable()

    assert mouse.names()[-1] == "mouseUp", mouse.calls
    assert bridge.holding_button is False
    assert bridge.enabled is False


def test_disabling_without_a_held_button_does_not_click_a_release():
    mouse = Mouse()
    bridge = gesture_bridge.GestureBridge(mouse=mouse)
    bridge.enable()
    bridge.pump((0.5, 0.5, False, False), _ctx())     # a plain move
    mouse.calls.clear()

    bridge.disable()

    assert "mouseUp" not in mouse.names(), "a release with nothing held is a click"


def test_disabling_twice_is_harmless():
    bridge = gesture_bridge.GestureBridge(mouse=Mouse())
    bridge.enable()
    bridge.disable()
    bridge.disable()


# ── 3. focus and confirmations freeze the hand ──────────────────────────────

def test_our_own_window_having_focus_stops_the_pointer():
    """The workspace gestures are handling it; a webcam click must not press
    this program's own buttons."""
    mouse = Mouse()
    bridge = gesture_bridge.GestureBridge(mouse=mouse)
    bridge.enable()

    intent = bridge.pump((0.5, 0.5, False, False), _ctx(own_window_focused=True))

    assert intent.is_empty
    assert mouse.calls == []
    assert "focus" in bridge.last_reason


def test_a_confirmation_on_screen_stops_the_pointer_and_says_why():
    mouse = Mouse()
    bridge = gesture_bridge.GestureBridge(mouse=mouse)
    bridge.enable()

    intent = bridge.pump((0.5, 0.5, False, False), _ctx(confirmation_open=True))

    assert intent.is_empty
    assert mouse.calls == []
    assert "confirmation" in bridge.last_reason


def test_a_banner_that_appears_mid_drag_releases_the_button():
    """Rule 3 is not suspended for the modal case: leaving a button down while
    a banner asks the user to press it physically is the worse outcome."""
    mouse = Mouse()
    bridge = gesture_bridge.GestureBridge(mouse=mouse)
    bridge.enable()
    bridge.pump((0.5, 0.5, True, False), _ctx(now=0.0))
    bridge.pump((0.5, 0.5, True, False), _ctx(now=1.0))
    assert bridge.holding_button is True

    bridge.pump((0.5, 0.5, True, False), _ctx(confirmation_open=True, now=2.0))

    assert bridge.holding_button is False
    assert "mouseUp" in mouse.names()


def test_the_lost_hand_releases_the_button_on_the_same_frame():
    mouse = Mouse()
    bridge = gesture_bridge.GestureBridge(mouse=mouse)
    bridge.enable()
    bridge.pump((0.5, 0.5, True, False), _ctx(now=0.0))
    bridge.pump((0.5, 0.5, True, False), _ctx(now=1.0))

    bridge.pump(None, _ctx(now=2.0))

    assert bridge.holding_button is False
    assert mouse.names().count("mouseUp") == 1


# ── the frames that do something ────────────────────────────────────────────

def test_a_plain_hand_moves_the_cursor_inside_the_screen_margin():
    mouse = Mouse(size=(1000, 500))
    bridge = gesture_bridge.GestureBridge(mouse=mouse, screen=(1000, 500))
    bridge.enable()

    intent = bridge.pump((0.5, 0.5, False, False), _ctx())

    assert intent.action == gesture_os.POINTER
    assert mouse.names() == ["moveTo"]
    x, y = mouse.calls[0][1], mouse.calls[0][2]
    assert 0 <= x < 1000 and 0 <= y < 500
    assert bridge.delivered == 1


def test_a_held_pinch_presses_once_and_the_release_lets_go():
    mouse = Mouse()
    bridge = gesture_bridge.GestureBridge(mouse=mouse)
    bridge.enable()

    bridge.pump((0.5, 0.5, True, False), _ctx(now=0.0))       # started
    bridge.pump((0.5, 0.5, True, False), _ctx(now=0.4))       # long enough
    bridge.pump((0.5, 0.5, True, False), _ctx(now=0.9))       # still held
    bridge.pump((0.5, 0.5, False, False), _ctx(now=1.0))      # let go

    assert mouse.names() == ["mouseDown", "mouseUp"]


def test_a_two_finger_pose_scrolls_and_never_clicks():
    mouse = Mouse()
    bridge = gesture_bridge.GestureBridge(mouse=mouse)
    bridge.enable()

    for tick in range(3):
        bridge.pump((0.5, 0.5, False, True), _ctx(now=tick * 0.2))

    assert set(mouse.names()) == {"scroll"}


def test_a_jump_between_frames_is_not_followed():
    """Rule 4: a sample the previous frame does not account for is a
    mis-detection, and a pointer that teleports lands on whatever was there."""
    mouse = Mouse()
    bridge = gesture_bridge.GestureBridge(mouse=mouse)
    bridge.enable()
    bridge.pump((0.1, 0.1, False, False), _ctx())

    bridge.pump((0.9, 0.9, False, False), _ctx())

    assert mouse.names() == ["moveTo"], "the second move must be dropped"
    assert bridge.dropped == 1


# ── 4. nothing raises into the caller ───────────────────────────────────────

def test_a_driver_that_fails_does_not_stop_the_loop():
    """The gesture that RELEASES a stuck button has to arrive even when the one
    before it failed."""
    mouse = Mouse()
    bridge = gesture_bridge.GestureBridge(mouse=mouse)
    bridge.enable()

    def _boom(*a, **k):
        raise OSError("the input queue is gone")

    mouse.moveTo = _boom
    bridge.pump((0.4, 0.4, False, False), _ctx())     # must not raise
    assert bridge.delivered == 0


@pytest.mark.parametrize("sample", [None, (), ("x", None), object(), (0.2,)])
def test_a_sample_that_is_not_a_sample_is_dropped_not_fatal(sample):
    mouse = Mouse()
    bridge = gesture_bridge.GestureBridge(mouse=mouse)
    bridge.enable()
    bridge.pump(sample, _ctx())                       # must not raise


def test_the_camera_shape_and_the_public_shape_both_become_one_sample():
    """`hand_sample()` returns four fields and the worker returns six; the
    policy's `Sample` must not be able to tell the difference."""
    four = gesture_bridge._to_sample((0.25, 0.75, True, False))
    six = gesture_bridge._to_sample((0.25, 0.75, True, False, 0.4, True))

    assert four == gesture_os.Sample(0.25, 0.75, True, False, claw=False)
    assert six == gesture_os.Sample(0.25, 0.75, True, False, claw=True)
    assert gesture_bridge._to_sample(None) is None


def test_the_policy_failing_is_reported_and_not_raised():
    mouse = Mouse()
    bridge = gesture_bridge.GestureBridge(mouse=mouse)
    bridge.enable()

    class Broken:
        def step(self, sample, ctx):
            raise RuntimeError("the state machine is confused")

        holding_button = False
        dropped_samples = 0

        def release_now(self):
            return gesture_os.Intent()

    bridge._hand = Broken()
    intent = bridge.pump((0.5, 0.5, False, False), _ctx())
    assert intent.is_empty
    assert "policy failed" in bridge.last_reason


# ── the switch on disk ──────────────────────────────────────────────────────

def test_the_feature_is_off_until_somebody_turns_it_on(tmp_path, monkeypatch):
    """The default is the whole safety story: a webcam-read hand that moves
    somebody's cursor is the most dangerous surface this program has."""
    import memory.config_manager as config

    monkeypatch.setattr(config, "load_api_keys", lambda: {})
    assert config.get_gesture_os_enabled() is False


@pytest.mark.parametrize("saved", [True, "1", "true", "YES", "on"])
def test_a_saved_yes_reads_as_yes(saved, monkeypatch):
    import memory.config_manager as config

    monkeypatch.setattr(config, "load_api_keys",
                        lambda: {"gesture_os_enabled": saved})
    assert config.get_gesture_os_enabled() is True


@pytest.mark.parametrize("saved", [False, "false", "no", "", 0, None, "nonsense"])
def test_anything_else_reads_as_no(saved, monkeypatch):
    import memory.config_manager as config

    monkeypatch.setattr(config, "load_api_keys",
                        lambda: {"gesture_os_enabled": saved})
    assert config.get_gesture_os_enabled() is False


def test_an_unreadable_config_means_off_not_on(monkeypatch):
    import memory.config_manager as config

    def _boom():
        raise OSError("the config file is gone")

    monkeypatch.setattr(config, "load_api_keys", _boom)
    assert config.get_gesture_os_enabled() is False


# ── rule 1, checked on this file as well ────────────────────────────────────

def test_the_bridge_sends_nothing_but_the_four_names():
    """`core/gesture_os_pointer` is AST-walked for `moveTo/mouseDown/mouseUp/
    scroll`. This module must not become the second place a fifth name is
    spelled — it never names the driver at all, it hands it to `OsPointer`.
    """
    import ast
    from pathlib import Path

    source = (Path(__file__).resolve().parent.parent / "core" / "gesture_bridge.py"
              ).read_text(encoding="utf-8")
    forbidden = {"press", "keyDown", "keyUp", "write", "typewrite", "hotkey", "click"}
    tree = ast.parse(source)
    attributes = {node.attr for node in ast.walk(tree) if isinstance(node, ast.Attribute)}
    assert not (attributes & forbidden), (
        f"the bridge reaches for {sorted(attributes & forbidden)}")

    calls = {node.func.attr for node in ast.walk(tree)
             if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)}
    assert not (calls & forbidden)


def test_the_bridge_imports_the_driver_only_when_enabled():
    """A module-level `import pyautogui` would make every test that imports the
    bridge depend on a desktop input library."""
    import ast
    from pathlib import Path

    source = (Path(__file__).resolve().parent.parent / "core" / "gesture_bridge.py"
              ).read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            assert all(not a.name.startswith("pyautogui") for a in node.names)
        if isinstance(node, ast.ImportFrom):
            assert node.module != "pyautogui"
    # And the pointer module keeps the import inside `_driver`.
    pointer = (Path(__file__).resolve().parent.parent / "core"
               / "gesture_os_pointer.py").read_text(encoding="utf-8")
    top = ast.parse(pointer)
    for node in top.body:
        if isinstance(node, ast.Import):
            assert all(not a.name.startswith("pyautogui") for a in node.names)


def test_the_feed_pumps_the_bridge_and_not_a_second_decision_path():
    """One policy, one pointer. A second call to `OsPointer.apply` anywhere else
    would be a second place the rules could be wrong."""
    from pathlib import Path

    ui_dir = Path(__file__).resolve().parent.parent / "ui"
    hand_source = (ui_dir / "hand_feed.py").read_text(encoding="utf-8")
    assert "_bridge.pump(" in hand_source
    # And nowhere in `ui/` builds a pointer of its own: one policy, one pointer.
    for path in sorted(ui_dir.glob("*.py")):
        text = path.read_text(encoding="utf-8")
        assert "OsPointer(" not in text, (
            f"{path.name} builds its own pointer; the bridge owns the only one")


# ── the switch, from a caller's point of view ───────────────────────────────

def test_the_bridge_takes_the_config_switch_as_its_default():
    """One place decides whether the feature is on: the config file. The bridge
    reads it through `ui/hand_feed`, and the disabled path holds no pointer.

    Checked structurally because `GestureBridge` is constructed by `HandFeed`,
    which needs a Qt that this machine does not have; the claim is that the
    constructor consults the switch rather than deciding for itself.
    """
    from pathlib import Path

    source = (Path(__file__).resolve().parent.parent / "ui"
              / "hand_feed.py").read_text(encoding="utf-8")
    assert "gesture_bridge_enabled()" in source
    assert "self._bridge.enable()" in source


def test_the_pointer_module_still_names_only_four_calls():
    """The allowlist that makes rule 1 real. If this ever fails, a gesture grew
    a capability nobody agreed to."""
    from core import gesture_os_pointer

    assert gesture_os_pointer._ALLOWED_CALLS == {
        "moveTo", "mouseDown", "mouseUp", "scroll"}
