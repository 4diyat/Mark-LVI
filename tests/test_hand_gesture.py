from types import SimpleNamespace

import pytest

from core import camera_lease
from core.hand_gesture import GestureEngine, HandController


class Mouse:
    def __init__(self):
        self.events = []
    def size(self):
        return 1000, 800
    def moveTo(self, x, y):
        self.events.append(("move", x, y))
    def mouseDown(self):
        self.events.append(("down",))
    def mouseUp(self):
        self.events.append(("up",))
    def scroll(self, amount):
        self.events.append(("scroll", amount))
    def hotkey(self, *keys):
        self.events.append(("hotkey", *keys))
    def press(self, key):
        self.events.append(("press", key))


def points(*, pinch=False, middle=False, ring=False, little=False):
    p = [SimpleNamespace(x=.5, y=.7) for _ in range(21)]
    p[5].x, p[17].x = .4, .6
    p[8].x, p[8].y, p[6].y = .5, .3, .5
    p[4].x, p[4].y = (.51, .31) if pinch else (.3, .6)
    for tip, joint, up in [(12, 10, middle), (16, 14, ring), (20, 18, little)]:
        p[tip].y, p[joint].y = (.3, .5) if up else (.7, .5)
    return p


def test_pinch_dwell_and_lost_hand_releases():
    mouse, now = Mouse(), [0.0]
    engine = GestureEngine(mouse, lambda: now[0])
    engine.update(points(pinch=True))
    now[0] = .34
    engine.update(points(pinch=True))
    assert ("down",) not in mouse.events
    now[0] = .36
    engine.update(points(pinch=True))
    assert mouse.events[-1] == ("down",)
    engine.update(None)
    engine.update(None)
    assert mouse.events.count(("up",)) == 1


def test_scroll_and_open_palm_do_not_click():
    mouse = Mouse()
    engine = GestureEngine(mouse)
    engine.update(points(middle=True))
    p = points(middle=True)
    p[8].y = .2
    engine.update(p)
    engine.update(points(middle=True, ring=True, little=True))
    assert ("scroll", 1) in mouse.events
    assert ("down",) not in mouse.events
    assert not any(event[0] == "hotkey" for event in mouse.events)


def test_switch_requires_dwell_and_rearm():
    mouse, now = Mouse(), [0.0]
    engine = GestureEngine(mouse, lambda: now[0])
    pose = points(middle=True, ring=True)
    engine.update(pose)
    now[0] = 1.1
    engine.update(pose)
    now[0] = 5
    engine.update(pose)
    assert mouse.events == [("hotkey", "alt", "tab")]
    engine.update(None)
    engine.update(pose)
    now[0] = 6.1
    engine.update(pose)
    assert len(mouse.events) == 2


def test_stop_releases_and_prevents_more_input():
    mouse = Mouse()
    engine = GestureEngine(mouse, lambda: 1)
    engine.down = True
    ctl = HandController()
    ctl._engine = engine
    ctl.stop()
    assert mouse.events == [("up",)]
    assert ctl._stop.is_set()


def test_camera_lease_and_vision_capture_refusal():
    pytest.importorskip("numpy")
    from actions.screen_processor import _capture_camera
    assert camera_lease.acquire()
    try:
        assert not camera_lease.acquire()
        with pytest.raises(RuntimeError, match="in use"):
            _capture_camera()
    finally:
        camera_lease.release()
    assert camera_lease.acquire()
    camera_lease.release()


def test_non_windows_never_starts(monkeypatch):
    monkeypatch.setattr("core.hand_gesture.platform.system", lambda: "Linux")
    ctl = HandController()
    assert not ctl.start()
    assert ctl.status == "windows_only"
    assert ctl.thread is None


def test_thumb_up_opens_menu_once_until_pose_changes():
    mouse, now, calls = Mouse(), [0.0], []
    engine = GestureEngine(mouse, lambda: now[0], on_menu=lambda: calls.append("menu"))
    thumb = points()
    thumb[8].y = .7
    thumb[4].y, thumb[3].y, thumb[2].y = .2, .35, .5
    engine.update(thumb)
    now[0] = .9
    engine.update(thumb)
    assert not calls
    now[0] = 1.1
    engine.update(thumb)
    engine.update(thumb)
    assert calls == ["menu"]
    engine.update(None)
    engine.update(thumb)
    now[0] = 2.2
    engine.update(thumb)
    assert calls == ["menu", "menu"]


def test_settings_are_bounded_and_three_fingers_remapped():
    from core.hand_gesture import normalize_settings
    assert normalize_settings({"pinch_ms": 0, "movement_range": 100, "three_finger": "shell"}) == {
        "pinch_ms": 350, "movement_range": 10, "three_finger": "switch", "pointed_vision": False}
    mouse, now = Mouse(), [0.0]
    engine = GestureEngine(mouse, lambda: now[0], settings={"three_finger": "task_view"})
    engine.update(points(middle=True, ring=True))
    now[0] = 1.1
    engine.update(points(middle=True, ring=True))
    assert mouse.events == [("hotkey", "win", "tab")]


def test_configured_pinch_dwell_and_range():
    mouse, now = Mouse(), [0.0]
    engine = GestureEngine(mouse, lambda: now[0], settings={"pinch_ms": 700, "movement_range": 20})
    p = points(pinch=True)
    p[8].x = .8
    p[4].x = .81
    engine.update(p)
    assert mouse.events[-1][1] == 1  # calibrated area spans the primary screen
    now[0] = .5
    engine.update(p)
    assert ("down",) not in mouse.events
    now[0] = .71
    engine.update(p)
    assert mouse.events[-1] == ("down",)


def test_watchdog_stops_when_frames_stall(monkeypatch):
    import ctypes
    import time

    fake = SimpleNamespace(user32=SimpleNamespace(GetAsyncKeyState=lambda _: 0))
    monkeypatch.setattr(ctypes, "windll", fake, raising=False)
    ctl = HandController()
    ctl._last_frame = time.monotonic() - 3
    mouse = Mouse()
    ctl._engine = GestureEngine(mouse)
    ctl._engine.down = True
    ctl._emergency()
    assert ctl._stop.is_set()
    assert ctl.status == "error"
    assert mouse.events == [("up",)]


@pytest.mark.parametrize("dx,dy,key", [(.15, 0, "left"), (-.15, 0, "right"),
                                        (0, -.15, "up"), (0, .15, "down")])
def test_arrow_swipe_requires_dwell_and_one_press_per_pose(dx, dy, key):
    mouse, now = Mouse(), [0.0]
    engine = GestureEngine(mouse, lambda: now[0], settings={"three_finger": "arrows"})
    pose = points(middle=True, ring=True)
    engine.update(pose)
    now[0] = .9
    engine.update(pose)
    assert not mouse.events
    now[0] = 1.1
    engine.update(pose)
    assert engine.gesture == "arrow_ready"
    pose[9].x += dx
    pose[9].y += dy
    engine.update(pose)
    assert mouse.events == [("press", key)]
    assert engine.gesture == "arrow_sent"
    now[0] = 5
    engine.update(pose)
    assert mouse.events == [("press", key)]
    engine.update(None)
    engine.update(pose)
    now[0] = 6.1
    engine.update(pose)
    pose[9].x += dx
    pose[9].y += dy
    engine.update(pose)
    assert mouse.events == [("press", key), ("press", key)]


def test_arrow_does_not_fire_from_jitter_or_when_menu_is_open():
    mouse, now, allowed = Mouse(), [0.0], [True]
    engine = GestureEngine(mouse, lambda: now[0], settings={"three_finger": "arrows"},
                           arrows_allowed=lambda: allowed[0])
    pose = points(middle=True, ring=True)
    engine.update(pose)
    now[0] = 1.1
    engine.update(pose)
    pose[9].x += .05
    engine.update(pose)
    assert not mouse.events
    allowed[0] = False
    now[0] = 2
    pose[9].x += .2
    engine.update(pose)
    allowed[0] = True
    now[0] = 2.5
    engine.update(pose)
    assert not mouse.events
    now[0] = 3.1
    engine.update(pose)
    pose[9].y -= .2
    engine.update(pose)
    assert mouse.events == [("press", "up")]


def test_pause_disarms_pointer_and_releases_drag_before_menu_action():
    mouse = Mouse()
    controller = HandController()
    controller._engine = GestureEngine(mouse)
    controller._engine.down = True
    controller.pause_input()
    assert controller._paused.is_set()
    assert mouse.events == [("up",)]
    controller.resume_input()
    assert not controller._paused.is_set()
