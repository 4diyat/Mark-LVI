"""Pointed vision is opt-in, short-lived, and never captures on refusal."""
import io

import pytest

pytest.importorskip("numpy")
Image = pytest.importorskip("PIL.Image")

from actions import screen_processor as screen  # noqa: E402
from core import pointing  # noqa: E402
from core.hand_gesture import GestureEngine  # noqa: E402
from memory import config_manager  # noqa: E402


@pytest.fixture(autouse=True)
def reset_point():
    pointing.update(None)
    yield
    pointing.update(None)


def test_requires_explicit_opt_in_and_live_point_before_capture(monkeypatch):
    calls = []
    monkeypatch.setattr(screen, "_capture_screen", lambda: calls.append(True))
    monkeypatch.setattr(config_manager, "load_api_keys", lambda: {"hand_gesture": {"pointed_vision": False}})
    pointing.update((.5, .5))
    with pytest.raises(RuntimeError, match="disabled"):
        screen._capture_pointed_screen()
    assert not calls
    monkeypatch.setattr(config_manager, "load_api_keys", lambda: {"hand_gesture": {"pointed_vision": True}})
    pointing.update(None)
    with pytest.raises(RuntimeError, match="No current hand pointer"):
        screen._capture_pointed_screen()
    assert not calls


def test_capture_marks_pointer_and_keeps_full_image(monkeypatch):
    img = Image.new("RGB", (200, 100), "white")
    out = io.BytesIO()
    img.save(out, format="PNG")
    monkeypatch.setattr(screen, "_capture_screen", lambda: (out.getvalue(), "image/png"))
    monkeypatch.setattr(config_manager, "load_api_keys", lambda: {"hand_gesture": {"pointed_vision": True}})
    pointing.update((.5, .5))
    encoded, mime = screen._capture_pointed_screen()
    assert mime == "image/jpeg"
    marked = Image.open(io.BytesIO(encoded))
    assert marked.size == (200, 100)
    r, g, b = marked.getpixel((100, 38))
    assert r > g + 50 and r > b + 50
    assert marked.getpixel((0, 0)) == (255, 255, 255)


def test_pointer_expires_and_clears(monkeypatch):
    import time
    now = [10.0]
    monkeypatch.setattr(time, "monotonic", lambda: now[0])
    pointing.update((.1, .3))
    assert pointing.recent() == (.1, .3)
    now[0] = 11.6
    assert pointing.recent() is None
    pointing.update(None)
    assert pointing.recent() is None


def test_engine_publishes_only_single_finger_and_clears_on_loss():
    from tests.test_hand_gesture import Mouse, points
    events = []
    engine = GestureEngine(Mouse(), on_point=events.append)
    engine.update(points())
    assert events[-1] is not None
    engine.update(points(pinch=True))
    assert events[-1] is None
    engine.update(points(middle=True))
    assert events[-1] is None
    engine.update(None)
    assert events[-1] is None


def test_live_tool_routes_pointed_screen_without_silent_fallback():
    import ast
    import asyncio
    import time
    import traceback
    from pathlib import Path
    from types import SimpleNamespace

    path = Path(__file__).resolve().parents[1] / "main.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "JarvisLive")
    fn = next(node for node in cls.body if isinstance(node, ast.AsyncFunctionDef) and node.name == "_execute_tool")
    captures = []
    def pointed_capture():
        captures.append("pointed")
        return b"marked image", "image/jpeg"
    def ordinary_capture():
        captures.append("ordinary")
        return b"normal image", "image/jpeg"
    env = {"asyncio": asyncio, "time": time, "traceback": traceback,
           "types": SimpleNamespace(FunctionResponse=lambda **kw: kw),
           "_capture_screen": ordinary_capture, "_capture_pointed_screen": pointed_capture}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), str(path), "exec"), env)
    registry = SimpleNamespace(scheduling=lambda _: None)
    logs = []
    obj = SimpleNamespace(ui=SimpleNamespace(set_state=lambda _: None, muted=False, write_log=logs.append),
                          _vision_busy=False, _vision_last_time=0, _vision_cam_active=False,
                          _pending_vision=None, _action_registry=registry, _plugin_registry=registry,
                          speak_error=lambda *args: None)
    call = SimpleNamespace(name="screen_process", args={"text": "Explain this", "pointed": True}, id="1")
    response = asyncio.run(env["_execute_tool"](obj, call))
    assert captures == ["pointed"]
    assert obj._pending_vision[:2] == (b"marked image", "image/jpeg")
    assert "red ring" in obj._pending_vision[2]
    assert "VISION_ACTIVE" in response["response"]["result"]
    assert logs
    obj._vision_busy = False
    obj._vision_last_time = 0
    obj._pending_vision = None
    def refused():
        raise RuntimeError("sharing disabled")
    env["_capture_pointed_screen"] = refused
    response = asyncio.run(env["_execute_tool"](obj, call))
    assert "sharing disabled" in response["response"]["result"]
    assert captures == ["pointed"]
    assert obj._pending_vision is None
    assert obj._vision_busy is False
