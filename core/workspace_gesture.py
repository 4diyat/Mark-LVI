"""Local camera tracking for the JARVIS workspace; never generates OS input."""
import itertools
import math
import platform
import threading
import time

from core import camera_lease


def _hand_measurement(points):
    """Convert landmarks to pointer, pose and pinch distance relative to the palm."""
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
    return (max(0., min(1., 1 - x)), max(0., min(1., y)), pinch, scroll, distance / palm)


def hand_sample(points):
    """Public four-field sample; the worker also uses the raw pinch ratio."""
    measured = _hand_measurement(points)
    return measured[:4] if measured is not None else None


class HandStabilizer:
    """Reduce pointer jitter and require two open frames before releasing a pinch.

    Tracks are matched only to nearby hands in the immediately previous frame.
    Missing or distant hands are discarded rather than extrapolated: this makes
    loss cancel an interaction instead of synthesizing a release/click.
    """
    def __init__(self):
        self._tracks = []

    def update(self, samples):
        samples = list(samples)
        if len(samples) > 2:
            self._tracks = []
            return ()
        previous = list(self._tracks)
        # A remaining hand must not inherit a disappeared pinching hand's
        # state. Cancel first; a fresh frame can establish new tracks.
        if len(samples) < len(previous) and any(track[2] for track in previous):
            self._tracks = []
            return ()
        # At most two hands: choose the globally closest one-to-one assignment.
        # Greedy matching can swap identities when the detector changes order.
        possibilities = []
        for assignment in itertools.product(range(-1, len(previous)), repeat=len(samples)):
            matched = [i for i in assignment if i >= 0]
            if len(set(matched)) != len(matched):
                continue
            distances = [math.hypot(sample[0] - previous[i][5], sample[1] - previous[i][6])
                         for sample, i in zip(samples, assignment) if i >= 0]
            if any(distance > .18 for distance in distances):
                continue
            possibilities.append((-len(matched), sum(distances), assignment))
        assignment = min(possibilities)[2]
        tracks = []
        for sample, index in zip(samples, assignment):
            x, y, pinch, scroll = sample[:4]
            ratio = sample[4] if len(sample) > 4 else None
            if index < 0:
                tracks.append((x, y, pinch, scroll and not pinch, 0, x, y))
                continue
            old = previous[index]
            previous[index] = None
            # Adaptive smoothing: fine hand jitter is damped, deliberate fast
            # movement follows more closely than a fixed low-pass filter.
            delta = math.hypot(x - old[0], y - old[1])
            alpha = max(.30, min(.85, .30 + delta * 7))
            sx = old[0] + alpha * (x - old[0])
            sy = old[1] + alpha * (y - old[1])
            # A larger release threshold prevents a pinched gesture oscillating
            # at the boundary. It still needs two consecutive open frames.
            closed = ratio < .50 if old[2] and ratio is not None else pinch
            open_frames = old[4] + 1 if old[2] and not closed else 0
            held = closed or (old[2] and open_frames < 2)
            tracks.append((sx, sy, held, scroll and not held, open_frames, x, y))
        self._tracks = tracks
        # Tracking loss cancels rather than synthesizing a release/click.
        if any(track is not None and track[2] for track in previous):
            self._tracks = []
            return ()
        return tuple(track[:4] for track in tracks)


def dwell_matches(pending, count, identity, coords, radius=25):
    """Keep a dwell only while the same target and hand positions remain stable."""
    return bool(pending and pending[0] == count and pending[2] == identity
                and len(pending[3]) == len(coords)
                and all(abs(point[0] - start[0]) + abs(point[1] - start[1]) <= radius
                        for point, start in zip(coords, pending[3])))


class WorkspaceHandController:
    """Camera worker publishes only the newest hand sample for the Qt thread."""
    def __init__(self):
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._sample = None
        self._cancel_pending = False
        self._unseen_transitions = 0
        self._await_open = False
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
            self._cancel_pending = False
            self._unseen_transitions = 0
            self._await_open = False
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

    def _publish(self, values):
        """Preserve tracking interruptions even when newer frames arrive first."""
        with self._lock:
            if self._stop.is_set():
                return
            now = time.monotonic()
            if not values or (self._sample is not None and now - self._sample[0] > .35):
                self._cancel_pending = True
            if self._sample is not None:
                # Ignore detector ordering, but do not let multiple pose/count
                # changes disappear between UI reads. In particular an unseen
                # release/re-pinch/release must not act as the original release.
                signature = lambda hands: (len(hands), sum(bool(hand[2]) for hand in hands))
                if signature(values) != signature(self._sample[1]):
                    self._unseen_transitions += 1
                    if self._unseen_transitions > 1:
                        self._cancel_pending = True
            self._sample = (now, values)

    def sample(self):
        with self._lock:
            sample = self._sample
            self._unseen_transitions = 0
            if self._stop.is_set() or sample is None or time.monotonic() - sample[0] > .35:
                self._cancel_pending = False
                self._await_open = True
                return ()
            if self._cancel_pending:
                self._cancel_pending = False
                self._await_open = True
                return ()
            if self._await_open:
                # A re-detected closed hand must not start a new interaction
                # until all visible hands have been deliberately opened.
                if not sample[1] or any(hand[2] for hand in sample[1]):
                    return ()
                self._await_open = False
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
            # Drivers may ignore these hints. A modest capture size and a
            # one-frame buffer reduce processing and stale frames when supported.
            for prop, value in (("CAP_PROP_FRAME_WIDTH", 640),
                                ("CAP_PROP_FRAME_HEIGHT", 480),
                                ("CAP_PROP_BUFFERSIZE", 1)):
                code = getattr(cv2, prop, None)
                if code is not None and hasattr(cap, "set"):
                    try:
                        cap.set(code, value)
                    except Exception:
                        # Some camera backends do not support property hints.
                        pass
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
                    self._publish(())
                    stabilizer.update(())
                    failures += 1
                    if failures >= 10:
                        raise RuntimeError('Camera stopped returning frames')
                    self._stop.wait(.05)
                    continue
                failures = 0
                rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                rgb.flags.writeable = False
                result = hands.process(rgb)
                values = [_hand_measurement(hand.landmark) for hand in (result.multi_hand_landmarks or [])]
                values = stabilizer.update(v for v in values if v is not None)
                self._publish(values)
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
