"""Exercise the live audio/error paths without microphone, Qt, or network."""
import ast
import asyncio
from pathlib import Path
from types import SimpleNamespace

SOURCE = Path(__file__).resolve().parents[1] / "main.py"


def _live_functions(*names):
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
    namespace = {"asyncio": asyncio}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(SOURCE), "exec"), namespace)
    return namespace


def test_taskgroup_error_classification_does_not_confuse_1007_with_bad_key():
    f = _live_functions("_exception_details", "_is_invalid_api_key")
    detail = f["_exception_details"](ExceptionGroup("tasks", [ValueError("1007 invalid payload")]))
    assert "1007 invalid payload" in detail
    assert not f["_is_invalid_api_key"](detail)
    detail = f["_exception_details"](ExceptionGroup("tasks", [ValueError("API key not valid")]))
    assert f["_is_invalid_api_key"](detail)


def test_mic_queue_drops_frame_when_full():
    f = _live_functions("_queue_mic_frame")["_queue_mic_frame"]
    queue = asyncio.Queue(maxsize=1)
    f(queue, b"first")
    f(queue, b"second")
    assert queue.get_nowait() == b"first"


def test_realtime_audio_declares_sample_rate_for_mic_and_phone():
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "JarvisLive")
    fn = next(n for n in cls.body if isinstance(n, ast.AsyncFunctionDef) and n.name == "_send_realtime")
    namespace = {"types": SimpleNamespace(Blob=lambda **kwargs: kwargs), "SEND_SAMPLE_RATE": 16000}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), str(SOURCE), "exec"), namespace)

    async def run():
        queue = asyncio.Queue()
        queue.put_nowait({"data": b"pcm", "mime_type": "audio/pcm"})
        received = []
        async def send_realtime_input(**kwargs):
            received.append(kwargs)
            raise StopAsyncIteration
        obj = SimpleNamespace(out_queue=queue, session=SimpleNamespace(send_realtime_input=send_realtime_input))
        try:
            await namespace["_send_realtime"](obj)
        except StopAsyncIteration:
            pass
        assert received[0]["audio"] == {"data": b"pcm", "mime_type": "audio/pcm;rate=16000"}
    asyncio.run(run())
