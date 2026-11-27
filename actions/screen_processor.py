"""
Screen & webcam capture for JARVIS vision.

Provides the two capture entry points main.py uses — `_capture_screen()` and
`_capture_camera()` — plus their helpers (compression, camera auto-detection,
config access). main.py grabs a frame here on demand, then injects it into the
main Gemini Live session; there is no separate vision session here.
"""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import numpy as np

from core.lazyimport import LazyModule, installed

# OpenCV is 224 ms and is only ever touched by the webcam path — see
# core/lazyimport.py. Screen capture, which is what this action does on almost
# every call, never reaches it. numpy above stays eager: main.py already
# imports it for audio, so it is in memory before this file is read.
_CV2 = installed("cv2")

cv2 = LazyModule("cv2")

try:
    import mss
    import mss.tools
    _MSS = True
except ImportError:
    _MSS = False

try:
    import PIL.Image
    _PIL = True
except ImportError:
    _PIL = False


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


_BASE        = _base_dir()
_CONFIG_PATH = _BASE / "config" / "api_keys.json"


def _load_config() -> dict:
    try:
        return json.loads(_CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_config_key(key: str, value) -> None:
    """Store one setting through the ONE config writer.

    This used to read the whole file, change one key and write it back. It runs
    on the vision worker thread, at the same time the Qt thread may be saving a
    voice and the session thread may be saving a device — three read-modify-
    write cycles on one file, so whichever finished last silently discarded the
    other two. memory.config_manager.update_config() serialises them.
    """
    try:
        from memory.config_manager import set_config_values
        set_config_values(**{key: value})
    except Exception as e:
        print(f"[Vision] ⚠️  Could not save config key '{key}': {e}")


def _get_os() -> str:
    return _load_config().get("os_system", "windows").lower()


_IMG_MAX_W = 1280
_IMG_MAX_H = 720
_JPEG_Q    = 82


def _compress(img_bytes: bytes, source_format: str = "PNG") -> tuple[bytes, str]:
    if not _PIL:
        return img_bytes, f"image/{source_format.lower()}"

    try:
        img = PIL.Image.open(io.BytesIO(img_bytes)).convert("RGB")
        img.thumbnail((_IMG_MAX_W, _IMG_MAX_H), PIL.Image.BILINEAR)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=_JPEG_Q, optimize=False)
        return buf.getvalue(), "image/jpeg"
    except Exception as e:
        print(f"[Vision] ⚠️  Image compress failed: {e}")
        return img_bytes, f"image/{source_format.lower()}"


def _capture_screen() -> tuple[bytes, str]:
    from core.vision_access import require
    require('screen')

    if not _MSS:
        raise RuntimeError("mss is not installed. Run: pip install mss")

    with mss.mss() as sct:
        monitors = sct.monitors          # [0] = all combined, [1..n] = real screens
        target   = monitors[1] if len(monitors) > 1 else monitors[0]
        shot     = sct.grab(target)
        png      = mss.tools.to_png(shot.rgb, shot.size)

    return _compress(png, "PNG")



def _capture_pointed_screen() -> tuple[bytes, str]:
    """Capture only after opt-in and a fresh local hand pointer; never save a file."""
    from core import pointing
    from memory.config_manager import load_api_keys

    settings = load_api_keys().get("hand_gesture")
    if not isinstance(settings, dict) or settings.get("pointed_vision") is not True:
        raise RuntimeError("Pointed screen analysis is disabled in Hand control settings.")
    point = pointing.recent()
    if point is None:
        raise RuntimeError("No current hand pointer. Hold one finger pointing at the object while asking again.")
    if not _PIL:
        raise RuntimeError("Pillow is needed to mark the pointed screen.")
    data, _ = _capture_screen()
    from PIL import ImageDraw
    img = PIL.Image.open(io.BytesIO(data)).convert("RGB")
    w, h = img.size
    x = max(0, min(w - 1, int(point[0] * w)))
    y = max(0, min(h - 1, int(point[1] * h)))
    draw = ImageDraw.Draw(img)
    radius = max(12, min(w, h) // 35)
    thickness = max(2, radius // 6)
    draw.ellipse((x-radius, y-radius, x+radius, y+radius), outline="red", width=thickness)
    draw.line((x-radius*2, y, x-radius, y), fill="red", width=thickness)
    draw.line((x+radius, y, x+radius*2, y), fill="red", width=thickness)
    draw.line((x, y-radius*2, x, y-radius), fill="red", width=thickness)
    draw.line((x, y+radius, x, y+radius*2), fill="red", width=thickness)
    out = io.BytesIO()
    img.save(out, format="JPEG", quality=_JPEG_Q)
    return out.getvalue(), "image/jpeg"

def _cv2_backend() -> int:
    """Return the best OpenCV camera backend for the current OS."""
    if not _CV2:
        return 0
    os_name = _get_os()
    if os_name == "windows":
        return cv2.CAP_DSHOW
    if os_name == "mac":
        return cv2.CAP_AVFOUNDATION
    return cv2.CAP_ANY


def _probe_camera(index: int, backend: int, warmup: int = 5) -> bool:

    if not _CV2:
        return False
    cap = cv2.VideoCapture(index, backend)
    if not cap.isOpened():
        cap.release()
        return False
    for _ in range(warmup):
        cap.read()
    ret, frame = cap.read()
    cap.release()
    if not ret or frame is None:
        return False
    return bool(np.mean(frame) > 8)


def _detect_camera_index() -> int:

    backend = _cv2_backend()
    print("[Vision] 🔍 Auto-detecting camera...")
    for idx in range(6):
        if _probe_camera(idx, backend):
            print(f"[Vision] ✅ Camera found at index {idx}")
            _save_config_key("camera_index", idx)
            return idx
        print(f"[Vision] ⚠️  Camera index {idx}: no usable frame")

    print("[Vision] ⚠️  No camera found — defaulting to index 0")
    _save_config_key("camera_index", 0)
    return 0


def _get_camera_index() -> int:
    cfg = _load_config()
    if "camera_index" in cfg:
        return int(cfg["camera_index"])
    return _detect_camera_index()


def _capture_camera() -> tuple[bytes, str]:
    from core.vision_access import require
    require('camera')
    from core import camera_lease
    if not camera_lease.acquire():
        raise RuntimeError("Camera is in use by live view or hand gesture control. Stop it first.")
    try:
        return _capture_camera_owned()
    finally:
        camera_lease.release()


def _capture_camera_owned() -> tuple[bytes, str]:
    if not _CV2:
        raise RuntimeError("OpenCV (cv2) is not installed. Run: pip install opencv-python")

    index   = _get_camera_index()
    backend = _cv2_backend()
    cap     = cv2.VideoCapture(index, backend)

    if not cap.isOpened():
        cap.release()
        raise RuntimeError(f"Camera index {index} could not be opened.")

    try:
        for _ in range(10):
            cap.read()
        ret, frame = cap.read()
    finally:
        cap.release()

    if not ret or frame is None:
        raise RuntimeError("Camera returned no frame.")

    if _PIL:
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img = PIL.Image.fromarray(rgb)
        img.thumbnail((_IMG_MAX_W, _IMG_MAX_H), PIL.Image.BILINEAR)
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=_JPEG_Q)
        return buf.getvalue(), "image/jpeg"

    _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, _JPEG_Q])
    return buf.tobytes(), "image/jpeg"
