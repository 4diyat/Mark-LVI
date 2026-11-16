"""Local camera tracking for the JARVIS workspace; never generates OS input."""
import math
import platform
import threading
import time

from core import camera_lease


def hand_sample(points):
    """Convert MediaPipe landmarks into a mirrored, normalized pointer and pinch."""
    if len(points) != 21:
        return None
    palm = math.hypot(points[5].x - points[17].x, points[5].y - points[17].y)
    x, y = points[8].x, points[8].y
    distance = math.hypot(points[4].x - x, points[4].y - y)
    if not all(math.isfinite(v) for v in (palm, x, y, distance)) or palm < .025:
        return None
    pinch = distance < palm * .38
    scroll = (not pinch and points[8].y < points[6].y and points[12].y < points[10].y
              and points[16].y > points[14].y and points[20].y > points[18].y)
    return (max(0., min(1., 1 - x)), max(0., min(1., y)), pinch, scroll)


class HandStabilizer:
    """Reduce pointer jitter and require two open frames before releasing a pinch.

    Tracks are matched only to nearby hands in the immediately previous frame.
    Missing or distant hands are discarded rather than extrapolated: this makes
    loss cancel an interaction instead of synthesizing a release/click.
    """
    def __init__(self):
        self._tracks = []

    def update(self, samples):
        previous = list(self._tracks)
        tracks = []
        for x, y, pinch, scroll in samples:
            candidates = [(math.hypot(x - track[0], y - track[1]), i, track)
                          for i, track in enumerate(previous) if track is not None]
            nearest = min(candidates, default=None, key=lambda c: c[0])
            if nearest is None or nearest[0] > .18:
                tracks.append((x, y, pinch, scroll, 0))
                continue
            _, index, old = nearest
            previous[index] = None
            sx = .55 * x + .45 * old[0]
            sy = .55 * y + .45 * old[1]
            open_frames = old[4] + 1 if old[2] and not pinch else 0
            held = pinch or (old[2] and open_frames < 2)
            tracks.append((sx, sy, held, scroll and not held, open_frames))
        self._tracks = tracks
        # If a pinching hand disappears or jumps out of the match radius,
        # explicitly cancel the whole frame. A different, open hand must not
        # be misinterpreted by the UI as that pinch being released.
        if any(track is not None and track[2] for track in previous):
            return ()
        return tuple(track[:4] for track in tracks)


class WorkspaceHandController:
    """Camera worker publishes only the newest hand sample for the Qt thread."""
    def __init__(self):
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._sample = None
        self.thread = None
        self.status = 'off'
        self.error = ''

    def start(self, camera_index=0, settings=None):
        del settings
        with self._lock:
            if self.thread and self.thread.is_alive():
                return False
            if platform.system() != 'Windows':
                self.status = 'windows_only'
                return False
            self._sample = None
            self._stop.clear()
            self.status, self.error = 'starting', ''
            self.thread = threading.Thread(target=self._run, args=(camera_index,), daemon=True,
                                           name='workspace-hand-tracking')
            self.thread.start()
            return True

    def stop(self):
        self._stop.set()
        with self._lock:
            self._sample = None
            if self.status in ('active', 'starting'):
                self.status = 'off'

    def sample(self):
        with self._lock:
            sample = self._sample
        if self._stop.is_set() or sample is None or time.monotonic() - sample[0] > .35:
            return ()
        return sample[1]

    def _run(self, camera_index):
        cap = hands = None
        leased = False
        try:
            import cv2
            import mediapipe as mp
            if not hasattr(mp, 'solutions'):
                raise RuntimeError('Install mediapipe==0.10.21 on Windows AMD64 / Python 3.10–3.12')
            if self._stop.is_set():
                return
            if not camera_lease.acquire():
                self.status = 'camera_busy'
                return
            leased = True
            cap = cv2.VideoCapture(camera_index, cv2.CAP_DSHOW)
            if not cap.isOpened():
                raise RuntimeError('Camera could not be opened')
            hands = mp.solutions.hands.Hands(max_num_hands=2, min_detection_confidence=.75,
                                            min_tracking_confidence=.75)
            with self._lock:
                if self._stop.is_set():
                    return
                self.status = 'active'
            failures = 0
            stabilizer = HandStabilizer()
            while not self._stop.is_set():
                ok, frame = cap.read()
                if not ok or frame is None:
                    with self._lock:
                        self._sample = None
                    stabilizer.update(())
                    failures += 1
                    if failures >= 10:
                        raise RuntimeError('Camera stopped returning frames')
                    self._stop.wait(.05)
                    continue
                failures = 0
                result = hands.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
                values = [hand_sample(hand.landmark) for hand in (result.multi_hand_landmarks or [])]
                values = stabilizer.update(v for v in values if v is not None)
                with self._lock:
                    if not self._stop.is_set():
                        self._sample = (time.monotonic(), values)
        except Exception as exc:
            self.error, self.status = str(exc), 'error'
        finally:
            self.stop()
            try:
                if hands is not None:
                    hands.close()
            finally:
                try:
                    if cap is not None:
                        cap.release()
                finally:
                    if leased:
                        camera_lease.release()
