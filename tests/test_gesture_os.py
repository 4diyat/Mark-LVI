"""Hand gestures that reach the desktop — and the leash.

This is the one feature where a wrong decision moves somebody's mouse, so the
tests are almost entirely about what is REFUSED:

  1. three actions and nothing else — no key, no shortcut, no close;
  2. JARVIS's own surfaces are never hand-operated;
  3. a held button is never left behind;
  4. ghost samples are dropped rather than followed.

All of it runs without a webcam, a desktop or Qt: the decision is a pure
function, which is the whole reason it lives in its own module.
"""
from __future__ import annotations

import ast
from pathlib import Path


from core import gesture_os as go

ROOT = Path(__file__).resolve().parent.parent


def on(**kwargs):
    """An OS-mode context, overriding whatever the test cares about."""
    kwargs.setdefault("os_mode", True)
    kwargs.setdefault("now", 0.0)
    return go.Context(**kwargs)


# ── 1. three actions, and nothing else ────────────────────────────────────

def test_the_vocabulary_is_exactly_three_actions():
    assert go.ALLOWED == ("pointer", "click", "scroll")


def test_the_intent_can_only_ever_carry_those_three():
    """A four-field intent with no `keys` and no `command` is a design that
    cannot grow a keylogger by accident."""
    fields = set(go.Intent.__dataclass_fields__)
    assert fields == {"action", "x", "y", "press", "release", "amount", "reason"}


def test_the_pointer_module_may_only_touch_four_driver_calls():
    """A future `press`/`hotkey`/`write` added here is rule 1 being broken in
    the one place it would be invisible."""
    tree = ast.parse((ROOT / "core" / "gesture_os_pointer.py").read_text(encoding="utf-8"))
    banned = {"press", "keyDown", "keyUp", "write", "hotkey", "typewrite",
              "click", "doubleClick", "dragTo", "tripleClick"}
    offenders = []
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr in banned):
            offenders.append(f"line {node.lineno}: {node.func.attr}()")
    assert not offenders, offenders


def test_no_gesture_module_imports_the_shortcut_allowlist():
    """`gesture_actions.py` holds every desktop shortcut this program knows
    (`Ctrl+W`, `lock_screen`, the lot). None of it may be reachable from a
    webcam pose.

    Scanned as an AST, not as text: these modules MENTION `gesture_actions.py`
    in a docstring explaining why they do not use it, and a substring check
    would fail on the explanation while missing nothing real. The repo has been
    bitten by exactly that before.
    """
    for name in ("gesture_os.py", "gesture_os_pointer.py"):
        tree = ast.parse((ROOT / "core" / name).read_text(encoding="utf-8"), filename=name)
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported |= {a.name for a in node.names}
            elif isinstance(node, ast.ImportFrom):
                imported.add(node.module or "")
                imported |= {f"{node.module}.{a.name}" for a in node.names}
        assert not {m for m in imported if "gesture_actions" in m}, (name, imported)


# ── 2. never hand-drive our own surfaces ─────────────────────────────────

def test_os_control_off_does_nothing_at_all():
    pointer = go.HandPointer()
    intent = pointer.step(go.Sample(.5, .5), go.Context(os_mode=False, now=0.0))
    assert intent.is_empty
    assert "off" in intent.reason


def test_our_own_window_having_focus_freezes_the_pointer():
    pointer = go.HandPointer()
    intent = pointer.step(go.Sample(.5, .5), on(own_window_focused=True))
    assert intent.is_empty
    assert "workspace gestures" in intent.reason


def test_a_confirmation_on_screen_stops_the_pointer_and_says_why():
    """The README's promise is that sensitive confirmations need physical
    input. A hand that could press one would break it silently."""
    pointer = go.HandPointer()
    intent = pointer.step(go.Sample(.5, .5), on(confirmation_open=True))
    assert intent.is_empty
    assert "mouse or keyboard" in intent.reason


def test_a_modal_of_ours_freezes_the_pointer_too():
    pointer = go.HandPointer()
    assert pointer.step(go.Sample(.5, .5), on(modal_open=True)).is_empty


def test_freezing_releases_a_button_that_was_being_held():
    """Rule 3 meets rule 2: the confirmation must not inherit a held drag."""
    pointer = go.HandPointer()
    pointer.step(go.Sample(.5, .5), on(now=0.0))
    pointer.step(go.Sample(.5, .5, pinch=True), on(now=0.1))
    assert pointer.step(go.Sample(.5, .5, pinch=True), on(now=0.5)).press is True

    intent = pointer.step(go.Sample(.5, .5), on(now=0.6, confirmation_open=True))

    assert intent.action == go.CLICK and intent.release is True
    assert pointer.holding_button is False


# ── 3. a held button is never left behind ────────────────────────────────

def test_a_lost_hand_releases_the_button():
    """The hand leaving the frame mid-drag is the ordinary case, not an edge."""
    pointer = go.HandPointer()
    pointer.step(go.Sample(.5, .5), on(now=0.0))
    pointer.step(go.Sample(.5, .5, pinch=True), on(now=0.1))
    pointer.step(go.Sample(.5, .5, pinch=True), on(now=0.5))

    intent = pointer.step(None, on(now=0.6))

    assert intent.action == go.CLICK and intent.release
    assert pointer.holding_button is False


def test_release_now_always_releases_whatever_the_hand_is_doing():
    pointer = go.HandPointer()
    pointer.step(go.Sample(.5, .5), on(now=0.0))
    pointer.step(go.Sample(.5, .5, pinch=True), on(now=0.1))
    pointer.step(go.Sample(.5, .5, pinch=True), on(now=0.5))

    assert pointer.release_now().release is True
    assert pointer.release_now().action == ""       # nothing left to release


def test_the_button_is_released_on_the_frame_the_pinch_ends():
    pointer = go.HandPointer()
    pointer.step(go.Sample(.5, .5), on(now=0.0))
    pointer.step(go.Sample(.5, .5, pinch=True), on(now=0.1))
    pointer.step(go.Sample(.5, .5, pinch=True), on(now=0.5))

    intent = pointer.step(go.Sample(.5, .5), on(now=0.6))

    assert intent.action == go.CLICK and intent.release is True
    assert pointer.holding_button is False


# ── the click itself ─────────────────────────────────────────────────────

def test_a_brief_pinch_is_not_a_click():
    pointer = go.HandPointer()
    pointer.step(go.Sample(.5, .5), on(now=0.0))
    intent = pointer.step(go.Sample(.5, .5, pinch=True), on(now=0.1))
    assert intent.is_empty
    intent = pointer.step(go.Sample(.5, .5, pinch=True), on(now=0.2))
    assert intent.is_empty
    assert "not held long enough" in intent.reason


def test_a_held_pinch_presses_once_and_does_not_repeat():
    pointer = go.HandPointer()
    pointer.step(go.Sample(.5, .5), on(now=0.0))
    pointer.step(go.Sample(.5, .5, pinch=True), on(now=0.1))
    assert pointer.step(go.Sample(.5, .5, pinch=True), on(now=0.5)).press is True

    again = pointer.step(go.Sample(.5, .5, pinch=True), on(now=0.9))

    assert again.is_empty, "the button was pressed twice for one pinch"


# ── scroll ───────────────────────────────────────────────────────────────

def test_scroll_is_rate_limited_rather_than_one_event_per_frame():
    """A held pose is a stream of frames; one scroll event each is unusable."""
    pointer = go.HandPointer()
    first = pointer.step(go.Sample(.5, .5, scroll=True), on(now=1.0))
    same_frame = pointer.step(go.Sample(.5, .5, scroll=True), on(now=1.001))
    later = pointer.step(go.Sample(.5, .5, scroll=True), on(now=1.2))

    assert first.action == go.SCROLL
    assert same_frame.is_empty
    assert later.action == go.SCROLL


def test_a_pinch_outranks_scroll():
    """Two poses at once is a tracking disagreement, not an instruction."""
    pointer = go.HandPointer()
    pointer.step(go.Sample(.5, .5), on(now=0.0))
    intent = pointer.step(go.Sample(.5, .5, scroll=True, pinch=True), on(now=0.1))
    assert intent.action != go.SCROLL


# ── 4. ghost samples ─────────────────────────────────────────────────────

def test_a_jump_across_the_screen_is_dropped_not_followed():
    """A face, a sleeve or a second person appearing is not a movement, and a
    pointer that teleports lands on whatever was there."""
    pointer = go.HandPointer()
    pointer.step(go.Sample(.10, .10), on(now=0.0))

    intent = pointer.step(go.Sample(.90, .90), on(now=0.1))

    assert intent.is_empty
    assert "too far" in intent.reason
    assert pointer.dropped_samples == 1


def test_a_small_movement_is_followed():
    pointer = go.HandPointer()
    pointer.step(go.Sample(.50, .50), on(now=0.0))
    intent = pointer.step(go.Sample(.55, .52), on(now=0.1))
    assert intent.action == go.POINTER
    assert (intent.x, intent.y) == (.55, .52)


def test_a_jump_does_not_release_a_held_button():
    """Letting go mid-drag because one frame was bad would drop whatever the
    user was carrying."""
    pointer = go.HandPointer()
    pointer.step(go.Sample(.5, .5), on(now=0.0))
    pointer.step(go.Sample(.5, .5, pinch=True), on(now=0.1))
    pointer.step(go.Sample(.5, .5, pinch=True), on(now=0.5))

    intent = pointer.step(go.Sample(.95, .95, pinch=True), on(now=0.6))

    assert intent.is_empty
    assert pointer.holding_button is True


# ── the pointer, in pixels ───────────────────────────────────────────────

def test_the_hand_cannot_reach_the_corners_of_the_screen():
    """Tracking is least accurate at the frame edges, and the corners hold the
    close buttons."""
    for x, y in ((0, 0), (1, 1), (1, 0), (0, 1)):
        px, py = go.coordinate(x, y, 1920, 1080)
        assert 0 < px < 1918 and 0 < py < 1078


def test_the_middle_of_the_hand_range_is_the_middle_of_the_screen():
    px, py = go.coordinate(.5, .5, 1920, 1080)
    assert abs(px - 960) <= 48 and abs(py - 540) <= 28


def test_coordinates_are_clamped_rather_than_wrapping():
    """A tracker that reports -0.2 must not put the pointer off the left edge."""
    assert go.coordinate(-5, -5, 800, 600)[0] >= 0
    assert go.coordinate(5, 5, 800, 600)[0] <= 799


def test_no_desktop_write_can_leave_the_screen_bounds():
    for x in (-1.0, 0.0, 0.5, 1.0, 2.0):
        for y in (-1.0, 0.0, 0.5, 1.0, 2.0):
            px, py = go.coordinate(x, y, 100, 100)
            assert 0 <= px <= 98 and 0 <= py <= 98, (x, y, px, py)


# ── the driver, against a recorder ────────────────────────────────────────

class _Recorder:
    """Stands in for pyautogui, and remembers every call it was given."""

    def __init__(self):
        self.calls = []
        self.fail = None

    def moveTo(self, x, y):                      # noqa: N802 — pyautogui's name
        if self.fail:
            raise self.fail
        self.calls.append(("moveTo", x, y))

    def mouseDown(self):                         # noqa: N802
        self.calls.append(("mouseDown",))

    def mouseUp(self):                           # noqa: N802
        self.calls.append(("mouseUp",))

    def scroll(self, amount):                    # noqa: N802
        self.calls.append(("scroll", amount))

    def size(self):
        return (1920, 1080)


def _pointer_module():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "gesture_os_pointer", ROOT / "core" / "gesture_os_pointer.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_driver_performs_exactly_what_the_intent_says():
    gop = _pointer_module()
    mouse = _Recorder()
    out = gop.OsPointer(mouse)

    out.apply(go.Intent(action=go.POINTER, x=.5, y=.5))
    out.apply(go.Intent(action=go.CLICK, press=True))
    out.apply(go.Intent(action=go.CLICK, release=True))
    out.apply(go.Intent(action=go.SCROLL, amount=3))

    assert [c[0] for c in mouse.calls] == ["moveTo", "mouseDown", "mouseUp", "scroll"]


def test_an_empty_intent_touches_nothing():
    gop = _pointer_module()
    mouse = _Recorder()
    assert gop.OsPointer(mouse).apply(go.Intent(reason="thinking")) is False
    assert mouse.calls == []


def test_a_driver_failure_does_not_kill_the_frame_loop():
    """The loop must keep running after one bad frame: the gesture that
    releases a stuck button still has to arrive."""
    gop = _pointer_module()
    mouse = _Recorder()
    mouse.fail = RuntimeError("pyautogui fail-safe corner")
    out = gop.OsPointer(mouse)

    assert out.apply(go.Intent(action=go.POINTER, x=.5, y=.5)) is False
    assert out.errors == 1


def test_release_works_without_any_state_at_all():
    """The escape hatch must not depend on a decision being correct."""
    gop = _pointer_module()
    mouse = _Recorder()
    assert gop.release(mouse) is True
    assert mouse.calls == [("mouseUp",)]


def test_the_screen_size_falls_back_rather_than_raising():
    gop = _pointer_module()

    class NoSize(_Recorder):
        def size(self):
            raise RuntimeError("headless")

    out = gop.OsPointer(NoSize())
    assert out.apply(go.Intent(action=go.POINTER, x=.5, y=.5)) is True

# ── what the deletion took ────────────────────────────────────────────────

def test_the_ui_half_of_the_gesture_layer_is_gone():
    """The bridge, the loop and the cursor overlay were all `ui/` widgets.

    `core/gesture_os.py` decides — it is a pure function over a context, which
    is why its tests are here and why it survives. What drove it was
    `ui/gesture_os_bridge.py` (read the focus window every frame),
    `ui/hand_gesture.py` (the camera loop) and `ui/desktop_ring.py` (the
    cursor). All three went with the window, because the mockup draws no
    gesture surface at all.

    This is asserted rather than described so the deletion cannot be quietly
    undone by re-adding a widget without a decision.
    """
    for gone in ("gesture_os_bridge.py", "hand_gesture.py", "desktop_ring.py"):
        assert not (ROOT / "ui" / gone).exists(), f"ui/{gone} came back"

    # The decision module is still importable and still pure — no Qt, no
    # pyautogui, no window. If a future edit gives it a dependency on the
    # desktop, this catches it before the tests that follow do.
    tree = ast.parse((ROOT / "core" / "gesture_os.py").read_text(encoding="utf-8"))
    imported = {n.module for n in ast.walk(tree)
                if isinstance(n, ast.ImportFrom) and n.module}
    assert not {m for m in imported if m.startswith(("ui", "PyQt6"))}
