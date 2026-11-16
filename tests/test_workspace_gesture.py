"""Workspace gestures never emit OS input and discard stale tracking data."""
import math
import time
from types import SimpleNamespace

from core.workspace_gesture import WorkspaceHandController, hand_sample


def landmarks(pinch=True):
    points = [SimpleNamespace(x=.5, y=.5) for _ in range(21)]
    points[5] = SimpleNamespace(x=.4, y=.5)
    points[17] = SimpleNamespace(x=.6, y=.5)
    points[8] = SimpleNamespace(x=.2, y=.4)
    points[4] = SimpleNamespace(x=.21 if pinch else .4, y=.4)
    return points


def test_pinch_and_mirror_and_invalid_landmarks():
    assert hand_sample(landmarks()) == (.8, .4, True, False)
    assert hand_sample(landmarks(False)) == (.8, .4, False, False)
    assert hand_sample([]) is None
    points = landmarks()
    points[8].x = math.nan
    assert hand_sample(points) is None


def test_two_fingers_make_scroll_pose_but_pinch_takes_priority():
    points = landmarks(False)
    points[8].y, points[6].y = .2, .5
    points[12].y, points[10].y = .2, .5
    points[16].y, points[14].y = .7, .5
    points[20].y, points[18].y = .7, .5
    assert hand_sample(points)[3] is True
    points[4].x, points[4].y = points[8].x, points[8].y
    assert hand_sample(points)[2:] == (True, False)


def test_stale_and_stopped_samples_are_never_used():
    controller = WorkspaceHandController()
    value = ((.4, .5, True), (.6, .5, True))
    controller._sample = (time.monotonic(), value)
    assert controller.sample() == value
    controller._sample = (time.monotonic() - 1, value)
    assert controller.sample() == ()
    controller._sample = (time.monotonic(), value)
    controller.stop()
    assert controller.sample() == ()


def test_unsupported_platform_never_starts_camera(monkeypatch):
    monkeypatch.setattr('core.workspace_gesture.platform.system', lambda: 'Linux')
    controller = WorkspaceHandController()
    assert not controller.start()
    assert controller.status == 'windows_only'
    assert controller.thread is None


def test_worker_requests_two_hands_and_releases_camera_on_failure(monkeypatch):
    import sys
    import threading
    from core import camera_lease

    capture_released = threading.Event()
    tracker_closed = threading.Event()
    options = {}

    class Capture:
        def isOpened(self):
            return True
        def read(self):
            return False, None
        def release(self):
            capture_released.set()

    class Hands:
        def __init__(self, **kwargs):
            options.update(kwargs)
        def close(self):
            tracker_closed.set()

    cv2 = SimpleNamespace(VideoCapture=lambda *_: Capture(), CAP_DSHOW=0)
    mp = SimpleNamespace(solutions=SimpleNamespace(hands=SimpleNamespace(Hands=Hands)))
    monkeypatch.setitem(sys.modules, 'cv2', cv2)
    monkeypatch.setitem(sys.modules, 'mediapipe', mp)
    monkeypatch.setattr('core.workspace_gesture.platform.system', lambda: 'Windows')
    controller = WorkspaceHandController()
    assert controller.start()
    controller.thread.join(timeout=3)
    assert not controller.thread.is_alive()
    assert options['max_num_hands'] == 2
    assert controller.status == 'error'
    assert capture_released.is_set() and tracker_closed.is_set()
    assert camera_lease.acquire()
    camera_lease.release()


def test_stabilizer_requires_consistent_release_and_cancels_on_loss():
    from core.workspace_gesture import HandStabilizer
    tracker = HandStabilizer()
    assert tracker.update([(.5, .5, True, False)])[0][2]
    first = tracker.update([(.52, .5, False, False)])[0]
    assert first[2] and .5 < first[0] < .52
    assert not tracker.update([(.52, .5, False, False)])[0][2]
    assert tracker.update([]) == ()
    assert not tracker.update([(.52, .5, False, False)])[0][2]


def test_stabilizer_does_not_transfer_pinch_to_distant_hand():
    from core.workspace_gesture import HandStabilizer
    tracker = HandStabilizer()
    tracker.update([(.1, .2, True, False)])
    assert tracker.update([(.9, .2, False, False)]) == ()
    assert not tracker.update([(.9, .2, False, False)])[0][2]


def test_one_lost_pinching_hand_cancels_even_if_other_hand_is_visible():
    from core.workspace_gesture import HandStabilizer
    tracker = HandStabilizer()
    tracker.update([(.2, .5, True, False), (.8, .5, False, False)])
    assert tracker.update([(.8, .5, False, False)]) == ()
    assert tracker.update([(.8, .5, False, False)])[0][2] is False
