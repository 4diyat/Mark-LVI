"""Offline stress and interruption checks for assistant PCM backpressure."""
import ast
import asyncio
import traceback
from pathlib import Path
import threading
from types import SimpleNamespace

from core import playback_buffer, speech_sync


def test_bounded_backpressure_preserves_fifo_and_releases_producer():
    async def run():
        queue = asyncio.Queue(maxsize=2)
        data = b'a' * playback_buffer.SLICE_BYTES + b'b' * playback_buffer.SLICE_BYTES + b'c' * 25
        producer = asyncio.create_task(playback_buffer.enqueue(queue, data, lambda: False))
        await asyncio.sleep(0)
        assert queue.qsize() == 2 and not producer.done()
        chunks = [await queue.get()]
        await asyncio.wait_for(producer, 1)
        assert queue.qsize() == 2
        chunks += [queue.get_nowait(), queue.get_nowait()]
        assert b''.join(chunks) == data
    asyncio.run(run())


def test_interrupt_wakes_full_queue_and_discards_in_flight_stale_slice():
    async def run():
        queue = asyncio.Queue(maxsize=1)
        stopped = False
        data = b'a' * playback_buffer.SLICE_BYTES + b'b' * playback_buffer.SLICE_BYTES
        producer = asyncio.create_task(playback_buffer.enqueue(queue, data, lambda: stopped))
        await asyncio.sleep(0)
        assert queue.full() and not producer.done()
        stopped = True
        assert playback_buffer.drain(queue) == 1
        assert not await asyncio.wait_for(producer, 1)
        assert queue.empty()
        assert not await playback_buffer.enqueue(queue, data, lambda: stopped)
        assert queue.empty()
    asyncio.run(run())


def test_cancellation_while_full_is_prompt_and_does_not_enqueue_later():
    async def run():
        queue = asyncio.Queue(maxsize=1)
        producer = asyncio.create_task(playback_buffer.enqueue(
            queue, b'x' * (2 * playback_buffer.SLICE_BYTES), lambda: False))
        await asyncio.sleep(0)
        producer.cancel()
        try:
            await producer
            raise AssertionError('cancellation was swallowed')
        except asyncio.CancelledError:
            pass
        assert playback_buffer.drain(queue) == 1
        await asyncio.sleep(0)
        assert queue.empty()
    asyncio.run(run())


def interrupt_methods():
    path = Path(__file__).resolve().parents[1] / 'main.py'
    tree = ast.parse(path.read_text(encoding='utf8'))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'JarvisLive')
    nodes = [n for n in cls.body if isinstance(n, ast.FunctionDef)
             and n.name in ('interrupt', '_interrupt_on_loop')]
    ns = {'playback_buffer': playback_buffer, 'speech_sync': speech_sync}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), 'exec'), ns)
    return ns


def test_ui_thread_interrupt_runs_queue_and_engine_operations_on_owner_loop():
    async def run():
        loop = asyncio.get_running_loop()
        owner = threading.get_ident()
        queue = asyncio.Queue(maxsize=1)
        queue.put_nowait(b'a')
        calls = []
        done = asyncio.Event()
        def record(label):
            calls.append((label, threading.get_ident()))
            if label == 'logged':
                done.set()
        ns = interrupt_methods()
        obj = SimpleNamespace(_loop=loop, audio_in_queue=queue, _interrupted=False,
                              _turn_done_event=asyncio.Event(), _play_cursor=1.0,
                              set_speaking=lambda _: record('state'),
                              _visemes=SimpleNamespace(reset=lambda: record('visemes')),
                              _engine=SimpleNamespace(interrupt=lambda: record('engine')),
                              ui=SimpleNamespace(write_log=lambda _: record('logged')))
        obj._interrupt_on_loop = lambda q: ns['_interrupt_on_loop'](obj, q)
        await asyncio.to_thread(ns['interrupt'], obj)
        await asyncio.wait_for(done.wait(), 1)
        assert queue.empty() and obj._interrupted and obj._play_cursor == 0
        assert [name for name, _ in calls] == ['state', 'visemes', 'engine', 'logged']
        assert all(thread_id == owner for _, thread_id in calls)
        obj._interrupted = False
        replacement = asyncio.Queue(maxsize=1)
        obj.audio_in_queue = replacement
        ns['_interrupt_on_loop'](obj, queue)
        assert not obj._interrupted and len(calls) == 4
    asyncio.run(run())


def test_session_uses_bounded_queue_and_receiver_uses_enqueue():
    source = (Path(__file__).resolve().parents[1] / 'main.py').read_text(encoding='utf8')
    assert 'asyncio.Queue(maxsize=playback_buffer.MAX_SLICES)' in source
    assert 'await playback_buffer.enqueue(' in source
    assert playback_buffer.MAX_SLICES * playback_buffer.SLICE_BYTES == 480_000


def test_receive_path_preserves_audio_transcript_and_tool_call_with_backpressure():
    async def run():
        source = Path(__file__).resolve().parents[1] / 'main.py'
        tree = ast.parse(source.read_text(encoding='utf8'))
        cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'JarvisLive')
        node = next(n for n in cls.body if isinstance(n, ast.AsyncFunctionDef) and n.name == '_receive_audio')
        ns = {'asyncio': asyncio, 'playback_buffer': playback_buffer,
              '_clean_transcript': lambda text: text, '_is_repeat_chunk': lambda *_: False,
          # The method is exec'd out of main.py, so it sees exactly the
          # globals given here — every module-level name it uses must be one of
          # them. `keep_turn` is the transcript writer; `traceback` was already
          # missing and only ever surfaced as a NameError raised from inside
          # the except block, which hid the real error.
          'keep_turn': lambda role, text: None, 'traceback': traceback,
              # The method reads its transcript rules from core/transcript.py
              # now. The threshold is lowered here so the test can exercise a
              # short duplicate without inventing a 12-character sentence.
              '_transcript': SimpleNamespace(REPEAT_MIN=5,
                                             is_repeat_chunk=lambda *_: False)}
        exec(compile(ast.Module(body=[node], type_ignores=[]), str(source), 'exec'), ns)
        logs, tool_calls, tool_responses = [], [], []
        pcm = b'a' * playback_buffer.SLICE_BYTES + b'b' * playback_buffer.SLICE_BYTES
        response = SimpleNamespace(data=pcm, session_resumption_update=None,
                                   server_content=SimpleNamespace(
                                       output_transcription=SimpleNamespace(text='Answer'),
                                       input_transcription=None, turn_complete=True),
                                   tool_call=SimpleNamespace(function_calls=[SimpleNamespace(name='example')]))
        class Session:
            async def receive(self):
                yield response
                await asyncio.Event().wait()
            async def send_tool_response(self, function_responses):
                tool_responses.extend(function_responses)
        async def execute(call):
            tool_calls.append(call.name)
            return 'result'
        async def flush():
            pass
        obj = SimpleNamespace(session=Session(), audio_in_queue=asyncio.Queue(maxsize=1),
                              _clear_stall=lambda: None, _interrupted=False,
                              _turn_done_event=asyncio.Event(), _last_out_logged='',
                              _asst_name='JARVIS', _session_log=[], _dashboard=None,
                              _vision_close_pending=False,
                              _visemes=SimpleNamespace(feed_text=lambda _: None, reset=lambda: None),
                              ui=SimpleNamespace(write_log=logs.append),
                              _execute_tool=execute, _flush_pending_vision=flush)
        receiver = asyncio.create_task(ns['_receive_audio'](obj))
        await asyncio.sleep(0)
        assert obj.audio_in_queue.full() and not obj._turn_done_event.is_set() and not tool_calls
        first = obj.audio_in_queue.get_nowait()
        await asyncio.sleep(0)
        assert first + obj.audio_in_queue.get_nowait() == pcm
        assert logs == ['JARVIS: Answer'] and tool_calls == ['example']
        assert tool_responses == ['result'] and obj._turn_done_event.is_set()
        receiver.cancel()
        try:
            await receiver
        except asyncio.CancelledError:
            pass
    asyncio.run(run())
