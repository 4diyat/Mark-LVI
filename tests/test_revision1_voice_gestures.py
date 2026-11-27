"""Hand tracking is real data, single-read, opt-in and safely stopped."""
import math
import time
from types import SimpleNamespace

from core.workspace_gesture import WorkspaceHandController, preview_landmarks
from ui import hand_feed, voice_gesture_controls


def test_landmarks_validate_and_disappear_after_stale_or_stop():
    raw = [SimpleNamespace(x=.2, y=.4) for _ in range(21)]
    points = preview_landmarks(raw)
    assert len(points) == 21 and points[0] == (.8, .4)
    raw[0].x = math.nan
    assert preview_landmarks(raw) == ()
    assert preview_landmarks(raw[:20]) == ()
    controller = WorkspaceHandController()
    controller._publish(((.8, .4, False, False),), points)
    assert controller.landmarks() == points
    controller._landmarks = (time.monotonic() - 1, points)
    assert controller.landmarks() == ()
    controller._publish((), points)
    assert controller.landmarks() == ()
    controller.stop(); assert controller.landmarks() == ()


def test_one_poll_uses_one_sample_and_releases_on_camera_loss(monkeypatch):
    class Controller:
        status = 'active'
        calls = 0
        def sample(self):
            self.calls += 1
            return ((.2, .4, True, False),) if self.calls == 1 else ()
        def landmarks(self):
            return ((.2, .4),) * 21
    class Overlay:
        gestures_paused = False
        active = True
        def set_hand(self, hand): self.hand = hand
        def set_camera_available(self, value): self.camera = value
    class Bridge:
        enabled = False
        def pump(self, sample, ctx): self.last = sample
    monkeypatch.setattr(hand_feed, 'gesture_bridge_enabled', lambda: False)
    shell = SimpleNamespace(_voice_overlay=Overlay())
    controller, bridge = Controller(), Bridge()
    feed = hand_feed.HandFeed(shell, controller=controller, bridge=bridge)
    shell._hand_feed = feed
    feed.poll()
    assert controller.calls == 1 and bridge.last == (.2, .4, True, False)
    assert shell._voice_overlay.hand == (.2, .4, True)
    assert len(shell._voice_overlay._gesture_points) == 21
    controller.status = 'error'; feed.poll()
    assert bridge.last is None and shell._voice_overlay.hand is None
    assert shell._voice_overlay._gesture_points == ()


def test_camera_loss_releases_an_os_button_without_an_extra_sample(monkeypatch):
    from core.gesture_bridge import GestureBridge
    from core.gesture_os import Context

    class Mouse:
        def __init__(self): self.calls = []
        def moveTo(self, x, y): self.calls.append('move')
        def mouseDown(self): self.calls.append('down')
        def mouseUp(self): self.calls.append('up')
        def scroll(self, amount): pass
        def size(self): return (1000, 1000)
    class Controller:
        status = 'active'
        def sample(self): return ((.5, .5, True, False),)
    class Overlay:
        gestures_paused = False
        def set_hand(self, hand): pass
        def set_camera_available(self, value): pass
    times = iter((0.0, 1.0, 2.0))
    monkeypatch.setattr(hand_feed, 'gesture_bridge_enabled', lambda: False)
    monkeypatch.setattr(hand_feed, 'gesture_context', lambda shell: Context(os_mode=True, now=next(times)))
    mouse, controller = Mouse(), Controller()
    bridge = GestureBridge(mouse=mouse); assert bridge.enable()
    shell = SimpleNamespace(_voice_overlay=Overlay())
    feed = hand_feed.HandFeed(shell, controller=controller, bridge=bridge)
    shell._hand_feed = feed
    feed.poll(); feed.poll()
    assert 'down' in mouse.calls and bridge.holding_button
    controller.status = 'error'; feed.poll()
    assert mouse.calls[-1] == 'up' and not bridge.holding_button


def test_tracking_starts_only_on_explicit_request_and_stops_with_voice(monkeypatch):
    monkeypatch.setattr(hand_feed, 'gesture_bridge_enabled', lambda: False)
    class Overlay:
        active = True
        gestures_paused = False
        def set_gestures_paused(self, value): self.gestures_paused = value
        def set_camera_available(self, value): self.camera = value
        def set_hand(self, value): self.hand = value
        def _refresh(self): pass
    class Feed:
        _started = False
        status = 'off'
        def start(self): self._started = True; self.status = 'active'; return True
        def stop(self): self._started = False; self.status = 'off'
    shell = SimpleNamespace(_voice_overlay=Overlay(), _hand_feed=Feed())
    assert not shell._hand_feed._started
    voice_gesture_controls.toggle_tracking(shell)
    assert shell._hand_feed._started and shell._hand_feed._voice_owned
    voice_gesture_controls.close_voice(shell)
    assert not shell._hand_feed._started


def test_preview_is_opt_in_latest_only_and_cleared_on_hide_stop_or_staleness():
    controller = WorkspaceHandController()
    controller._publish_preview(b'not enabled')
    assert controller.preview() == b''
    controller.set_preview_enabled(True)
    controller._publish_preview(b'first')
    controller._publish_preview(b'second')
    assert controller.preview() == b'second'
    controller._preview = (time.monotonic() - 1, b'stale')
    assert controller.preview() == b''
    controller._publish_preview(b'frame')
    controller.set_preview_enabled(False)
    assert controller.preview() == b'' and controller._preview is None
    controller.set_preview_enabled(True)
    controller._publish_preview(b'frame')
    controller.stop()
    assert controller.preview() == b'' and controller._preview is None
    assert not controller._preview_enabled
