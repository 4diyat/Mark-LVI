"""Experimental, opt-in Windows hand input. Frames never leave this process.

The camera worker never touches Qt. Input is serialized with stop(), so after
stop returns no further synthetic input can be issued, even if camera reads or
inference are blocked. Only a small fixed set of non-destructive shortcuts is
recognized; this is not a general purpose gesture/shortcut executor.
"""
from __future__ import annotations

import math
import platform
import threading
import time

from core import camera_lease


DEFAULT_SETTINGS = {"pinch_ms": 350, "movement_range": 10, "three_finger": "switch"}


def normalize_settings(raw):
    """Keep settings constrained even when configuration is edited by hand."""
    raw = raw if isinstance(raw, dict) else {}
    return {
        "pinch_ms": raw.get("pinch_ms") if raw.get("pinch_ms") in (350, 500, 700) else 350,
        "movement_range": raw.get("movement_range") if raw.get("movement_range") in (0, 10, 20) else 10,
        "three_finger": raw.get("three_finger") if raw.get("three_finger") in ("switch", "task_view", "arrows", "none") else "switch",
        "pointed_vision": raw.get("pointed_vision") is True,
    }


class GestureEngine:
    def __init__(self, mouse, clock=time.monotonic, on_menu=None, settings=None, arrows_allowed=None, on_point=None):
        self.mouse = mouse
        self.on_menu = on_menu
        self.arrows_allowed = arrows_allowed or (lambda: True)
        self.on_point = on_point or (lambda _point: None)
        self.settings = normalize_settings(settings)
        self.clock = clock
        self.pinch_since = None
        self.down = False
        self.pos = None
        self.scroll_y = None
        self.pose = None
        self.pose_since = 0.0
        self.triggered = False
        self.gesture = "rest"
        self.arrow_origin = None

    def _mouse_up(self):
        try:
            self.mouse.mouseUp()
        except Exception:
            # PyAutoGUI's corner fail-safe may reject mouseUp itself. A held
            # button must still be released when the user hits that fail-safe.
            if platform.system() != "Windows":
                raise
            import ctypes
            ctypes.windll.user32.mouse_event(0x0004, 0, 0, 0, 0)

    def release(self):
        self.on_point(None)
        if self.down:
            # Set the flag first even if the OS backend reports an error.
            self.down = False
            self._mouse_up()
        self.pinch_since = None
        self.pos = None
        self.scroll_y = None
        self.pose = None
        self.triggered = False
        self.gesture = "rest"
        self.arrow_origin = None

    def update(self, points):
        if points is None or len(points) != 21:
            self.release()
            return
        p = points
        index = p[8].y < p[6].y
        middle = p[12].y < p[10].y
        ring = p[16].y < p[14].y
        little = p[20].y < p[18].y
        palm = math.hypot(p[5].x - p[17].x, p[5].y - p[17].y)
        pinch = palm > .025 and math.hypot(p[4].x - p[8].x, p[4].y - p[8].y) < palm * .38

        # Three raised fingers perform the configured action. An open palm
        # remains a safe resting pose.
        thumb_up = p[4].y < p[3].y < p[2].y
        command = ("switch" if index and middle and ring and not little else
                   "menu" if not any((index, middle, ring, little)) and thumb_up else None)
        if command:
            self.on_point(None)
            self.gesture = "arrows" if command == "switch" and self.settings["three_finger"] == "arrows" else command
            if self.down:
                self._mouse_up()
                self.down = False
            self.pinch_since = None
            self.pos = self.scroll_y = None
            if command != self.pose:
                self.pose, self.pose_since, self.triggered = command, self.clock(), False
                self.arrow_origin = None
            elif command == "switch" and self.settings["three_finger"] == "arrows":
                self.gesture = "arrows"
                if not self.arrows_allowed():
                    # A menu has focus: require a fresh dwell after it closes.
                    self.pose_since = self.clock()
                    self.arrow_origin = None
                    return
                if not self.triggered and self.clock() - self.pose_since >= 1.0:
                    self.gesture = "arrow_ready"
                    if self.arrow_origin is None:
                        self.arrow_origin = (p[9].x, p[9].y)
                    else:
                        dx = p[9].x - self.arrow_origin[0]
                        dy = p[9].y - self.arrow_origin[1]
                        if max(abs(dx), abs(dy)) >= .12:
                            # The camera is mirrored like the pointer: an image
                            # x decrease is a movement to the user's right.
                            key = ("left" if dx > 0 else "right") if abs(dx) > abs(dy) else ("down" if dy > 0 else "up")
                            self.mouse.press(key)
                            self.triggered = True
                            self.gesture = "arrow_sent"
                elif self.triggered:
                    self.gesture = "arrow_sent"
            elif not self.triggered and self.clock() - self.pose_since >= 1.0:
                self.triggered = True
                if command == "menu":
                    if self.on_menu:
                        self.on_menu()
                elif self.settings["three_finger"] == "switch":
                    self.mouse.hotkey("alt", "tab")
                elif self.settings["three_finger"] == "task_view":
                    self.mouse.hotkey("win", "tab")
            return
        self.pose, self.triggered = None, False
        self.arrow_origin = None
        if middle and index and not ring and not little:
            self.on_point(None)
            self.gesture = "scroll"
            if self.down:
                self._mouse_up()
                self.down = False
            self.pinch_since = None
            y = p[8].y
            if self.scroll_y is None:
                self.scroll_y = y
            elif abs(y - self.scroll_y) >= .06:
                self.mouse.scroll(1 if y < self.scroll_y else -1)
                self.scroll_y = y
            return
        if middle or ring or little or not (index or pinch):
            self.release()
            return
        self.scroll_y = None
        self.gesture = "pinch" if pinch else "point"
        width, height = self.mouse.size()
        margin = self.settings["movement_range"] / 100
        scale = 1 - 2 * margin
        x = max(1, min(width - 2, int((1 - p[8].x - margin) / scale * width)))
        y = max(1, min(height - 2, int((p[8].y - margin) / scale * height)))
        if self.pos:
            x = int(.7 * self.pos[0] + .3 * x)
            y = int(.7 * self.pos[1] + .3 * y)
        self.pos = (x, y)
        self.mouse.moveTo(x, y)
        # No hand position is retained during menus, a pinch, or lost tracking.
        self.on_point((x / width, y / height) if not pinch and self.arrows_allowed() else None)
        if pinch:
            if self.pinch_since is None:
                self.pinch_since = self.clock()
            elif not self.down and self.clock() - self.pinch_since >= self.settings["pinch_ms"] / 1000:
                self.mouse.mouseDown()
                self.down = True
        else:
            if self.down:
                self._mouse_up()
                self.down = False
            self.pinch_since = None


class HandController:
    def __init__(self, on_menu=None):
        self.on_menu = on_menu
        self.settings = normalize_settings(None)
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self.menu_open = threading.Event()
        self._paused = threading.Event()
        self._engine = None
        self.thread = None
        self.status = "off"
        self.error = ""
        self._last_frame = 0.0

    def start(self, camera_index=0, settings=None):
        with self._lock:
            if self.thread and self.thread.is_alive():
                return False
            if platform.system() != "Windows":
                self.status = "windows_only"
                return False
            self.settings = normalize_settings(settings)
            from core import pointing
            pointing.update(None)
            self._stop.clear()
            self.menu_open.clear()
            self._paused.clear()
            self.status, self.error = "starting", ""
            self.thread = threading.Thread(target=self._run, args=(camera_index,), name="hand-gesture", daemon=True)
            self.thread.start()
        return True

    def stop(self):
        from core import pointing
        self._stop.set()
        pointing.update(None)
        with self._lock:
            if self._engine:
                try:
                    self._engine.release()
                except Exception as exc:
                    self.error = str(exc)
                    self.status = "error"

    def pause_input(self):
        """Disarm generated input while a menu command targets a window."""
        self._paused.set()
        with self._lock:
            if self._engine:
                self._engine.release()

    def resume_input(self):
        self._paused.clear()

    def _emergency(self):
        try:
            import ctypes
            key = ctypes.windll.user32.GetAsyncKeyState
            while not self._stop.wait(.05):
                if key(0x11) & 0x8000 and key(0x12) & 0x8000 and key(0x47) & 0x8000:
                    self.stop()
                    return
                if time.monotonic() - self._last_frame > 2.0:
                    self.error = "Camera or hand tracking stopped responding"
                    self.status = "error"
                    self.stop()
                    return
        except Exception as exc:
            self.error = f"Emergency stop unavailable: {exc}"
            self.status = "error"
            self.stop()

    def _run(self, camera_index):
        cap = hands = watcher = None
        leased = False
        try:
            import cv2
            import mediapipe as mp
            import pyautogui
            if not hasattr(mp, "solutions"):
                raise RuntimeError("Install mediapipe==0.10.21 on Windows AMD64 / Python 3.10–3.12")
            if self._stop.is_set():
                return
            if not camera_lease.acquire():
                self.status = "camera_busy"
                return
            leased = True
            cap = cv2.VideoCapture(camera_index, cv2.CAP_DSHOW)
            if not cap.isOpened():
                raise RuntimeError("Camera could not be opened")
            hands = mp.solutions.hands.Hands(max_num_hands=1, min_detection_confidence=.75,
                                            min_tracking_confidence=.75)
            with self._lock:
                if self._stop.is_set():
                    return
                from core import pointing
                self._engine = GestureEngine(pyautogui, on_menu=self.on_menu, settings=self.settings,
                                             arrows_allowed=lambda: not self.menu_open.is_set(),
                                             on_point=pointing.update)
                self._last_frame = time.monotonic()
                self.status = "active"
            watcher = threading.Thread(target=self._emergency, name="hand-emergency", daemon=True)
            watcher.start()
            failures = 0
            while not self._stop.is_set():
                ok, frame = cap.read()
                if not ok or frame is None:
                    failures += 1
                    with self._lock:
                        if self._engine:
                            self._engine.release()
                    if failures >= 10:
                        raise RuntimeError("Camera stopped returning frames")
                    self._stop.wait(.05)
                    continue
                failures = 0
                result = hands.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
                landmarks = result.multi_hand_landmarks
                with self._lock:
                    if not self._stop.is_set():
                        self._last_frame = time.monotonic()
                        if not self._paused.is_set():
                            self._engine.update(landmarks[0].landmark if landmarks else None)
        except Exception as exc:
            self.error = str(exc)
            self.status = "error"
        finally:
            self.stop()
            if watcher is not None:
                watcher.join(timeout=.5)
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
                    with self._lock:
                        self._engine = None
                        if self.status in ("starting", "active"):
                            self.status = "off"
