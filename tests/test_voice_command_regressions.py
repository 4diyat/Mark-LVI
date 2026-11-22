"""Drive the real voice methods with simulated devices and sessions, offline."""
import ast
import asyncio
from pathlib import Path

from core import mic_status
from types import SimpleNamespace

SOURCE = Path(__file__).resolve().parents[1] / "main.py"


def methods(*names, extra=None):
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "JarvisLive")
    nodes = [n for n in cls.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
             and n.name in names]
    # `_listen_audio` reads its sentences from core/mic_status.py now, and the
    # method is exec'd out of main.py — so every module-level name it uses has
    # to be handed to it. The REAL module is used, not a stub: the sentences are
    # part of what the test asserts.
    ns = {"asyncio": asyncio, "SEND_SAMPLE_RATE": 16000,
          "_mic_status": mic_status,
          "types": SimpleNamespace(Blob=lambda **kw: kw)}
    ns.update(extra or {})
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(SOURCE), "exec"), ns)
    return ns


def test_ptt_end_is_ordered_after_audio_for_live_and_local():
    async def check(local):
        queue = asyncio.Queue()
        queue.put_nowait({"data": b"first", "mime_type": "audio/pcm"})
        queue.put_nowait({"data": b"last", "mime_type": "audio/pcm"})
        queue.put_nowait({"audio_stream_end": True})
        calls = []
        async def send_realtime_input(**kwargs):
            calls.append(kwargs)
            if kwargs.get("audio_stream_end"):
                raise StopAsyncIteration
        async def flush(rate):
            calls.append({"flush": rate})
            raise StopAsyncIteration
        obj = SimpleNamespace(out_queue=queue,
                              session=SimpleNamespace(send_realtime_input=send_realtime_input),
                              _engine=SimpleNamespace(flush_microphone=flush) if local else None)
        try:
            await methods("_send_realtime")["_send_realtime"](obj)
        except StopAsyncIteration:
            pass
        assert [c["audio"]["data"] for c in calls[:2]] == [b"first", b"last"]
        assert calls[2] == ({"flush": 16000} if local else {"audio_stream_end": True})
    asyncio.run(check(False))
    asyncio.run(check(True))


def test_releasing_ptt_queues_one_end_only_when_held():
    async def check():
        loop = asyncio.get_running_loop()
        queue = asyncio.Queue()
        state = []
        def end(q):
            q.put_nowait({"audio_stream_end": True})
        obj = SimpleNamespace(_ptt_held=True, _ptt_enabled=True, _loop=loop,
                              out_queue=queue, _wake_enabled=False, _awake=True,
                              ui=SimpleNamespace(set_state=state.append))
        method = methods("_on_ptt", extra={"_queue_audio_end": end})["_on_ptt"]
        method(obj, False)
        method(obj, False)
        await asyncio.sleep(0)
        assert queue.get_nowait() == {"audio_stream_end": True}
        assert queue.empty()
    asyncio.run(check())


def test_boundary_is_not_lost_if_audio_queue_is_full():
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_queue_audio_end")
    ns = {"asyncio": asyncio}
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(SOURCE), "exec"), ns)
    queue = asyncio.Queue(maxsize=2)
    queue.put_nowait({"data": b"old"})
    queue.put_nowait({"data": b"new"})
    ns["_queue_audio_end"](queue)
    assert queue.get_nowait() == {"data": b"new"}
    assert queue.get_nowait() == {"audio_stream_end": True}


def test_mic_start_failure_waits_before_retry_and_does_not_claim_listening():
    async def check():
        states, logs = [], []
        class BadStream:
            def __enter__(self):
                raise OSError("device busy")
            def __exit__(self, *args):
                pass
        async def wait():
            raise asyncio.CancelledError
        device = SimpleNamespace(resolve=lambda *args: None,
                                 open_input_stream=lambda *args, **kwargs: (BadStream(), ""))
        obj = SimpleNamespace(ui=SimpleNamespace(set_state=states.append, write_log=logs.append),
                              _mic_recovered=False, _deaf=False, _wait_for_microphone=wait,
                              _apply_listening_state=lambda: states.append("LISTENING"))
        ns = methods("_listen_audio", extra={"audio_devices": device,
                                             "get_input_device": lambda: ""})
        try:
            await ns["_listen_audio"](obj)
        except asyncio.CancelledError:
            pass
        assert states == ["NO MIC"]
        assert any("device busy" in line for line in logs)
    asyncio.run(check())


def test_wake_word_buttons_are_gone_and_the_setting_survives():
    """The two buttons lived in the settings drawer; the drawer went with the window.

    What must not go with them is the RULE they enforced: a wake word whose
    model never loaded must not be left enabled, or the app listens for a phrase
    it can never hear and the user waits for a response that cannot come.
    `main.py` enforces it on the path that actually matters — the toggle the
    session calls — so that is where it is asserted now.
    """
    window = SOURCE.parent / "ui" / "window.py"
    assert not window.exists()

    main_src = (SOURCE.parent / "main.py").read_text(encoding="utf-8")
    assert "_ui_wake_toggle" in main_src
    assert "wake_is_ready" in main_src, (
        "the readiness check left with the buttons; the model can now be "
        "enabled and never fire")
    assert "need_download" in main_src


def test_wake_word_not_enabled_when_model_fails_to_start():
    saves = []
    ns = methods("_ui_wake_toggle", extra={"wake_is_ready": lambda: True,
                                           "save_wake_word_enabled": saves.append})
    obj = SimpleNamespace(_wake_enabled=False, _ensure_wake_detector=lambda: False)
    assert ns["_ui_wake_toggle"](obj, True) == "need_download"
    assert obj._wake_enabled is False and saves == []


def test_push_to_talk_says_when_it_is_window_scoped_instead_of_pretending():
    """PTT used to hand a bool to the window through a Qt signal.

    There is no window, so the signal is gone — and the honest thing that
    replaces it is a log line saying the desktop offers no global key hook. The
    failure this guards against is the loud one being deleted along with the
    widget: a shortcut that silently only works when something has focus is a
    shortcut the user reports as broken.
    """
    source = SOURCE.read_text(encoding="utf-8")
    tree = ast.parse(source)
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "JarvisLive")
    init = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == "__init__")
    body = ast.unparse(init)

    assert "_ptt_shortcut_sig" not in body, (
        "a Qt signal to a window that no longer exists")
    assert "Push-to-talk only works while" in body, (
        "a window-scoped PTT chord is now silent")
    assert "self.ui.write_log" in body


def test_open_mic_forwards_captured_pcm_to_queue():
    import threading
    async def check():
        callbacks = []
        states = []
        class Samples:
            def tobytes(self):
                return b"voice-pcm"
        class Stream:
            active = True
            def __enter__(self):
                callbacks[0](Samples(), 1024, None, None)
                return self
            def __exit__(self, *args):
                pass
        def factory(**kw):
            callbacks.append(kw["callback"])
            return Stream()
        device = SimpleNamespace(resolve=lambda *args: None,
                                 open_input_stream=lambda opener, dev, **kw: (opener(dev), ""))
        ns = methods("_listen_audio", extra={"audio_devices": device, "sd": SimpleNamespace(InputStream=factory),
                     "get_input_device": lambda: "", "CHANNELS": 1, "CHUNK_SIZE": 1024,
                     "_pcm_level": lambda _: 0.5,
                     "_queue_mic_frame": lambda q, frame: q.put_nowait(frame)})
        queue = asyncio.Queue()
        obj = SimpleNamespace(_wake_enabled=False, _awake=True, _speaking_lock=threading.Lock(),
                              _is_speaking=False, _tail_active=lambda: False,
                              _echo=SimpleNamespace(_hist=[]), _ptt_enabled=False,
                              _phone_active=False, out_queue=queue, _mic_recovered=False, _deaf=False,
                              _mic_recovered_first=True,
                              ui=SimpleNamespace(muted=False, write_log=lambda _: None,
                                                 set_audio_level=lambda _: None),
                              _apply_listening_state=lambda: states.append("LISTENING"))
        task = asyncio.create_task(ns["_listen_audio"](obj))
        frame = await asyncio.wait_for(queue.get(), 1)
        assert frame == {"data": b"voice-pcm", "mime_type": "audio/pcm;rate=16000"}
        assert states == ["LISTENING"]
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
    asyncio.run(check())
