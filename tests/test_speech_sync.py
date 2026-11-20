"""Speech segment metadata is tied to playback, not transcript arrival."""
import ast
import asyncio
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np

from core import playback_buffer, speech_sync
from providers.engine_pipeline import PipelineEngine


class Model:
    caps = {'tools': False, 'tool_format': None}
    async def chat(self, messages, tools):
        yield {'text': 'First sentence. Second sentence.'}


class Voice:
    async def speak(self, text):
        yield b'a' * 4800
        yield b'b' * 2400


def test_pipeline_only_marks_first_audio_slice_per_spoken_sentence():
    async def run():
        engine = PipelineEngine(Model(), tts=Voice())
        await engine.send_client_content(turns={'parts': [{'text': 'Hi'}]})
        await asyncio.wait_for(engine._gen, 1)
        stream = engine.receive()
        events = [await asyncio.wait_for(anext(stream), 1) for _ in range(engine._queue.qsize())]
        audio = [m for m in events if m.data]
        assert [m.speech_caption for m in audio] == [
            'First sentence.', None, None, 'Second sentence.', None, None]
        assert b''.join(m.data for m in audio) == (b'a' * 4800 + b'b' * 2400) * 2
        await stream.aclose()
        await engine.close()
    asyncio.run(run())


def test_captioned_enqueue_retains_caption_only_on_first_slice():
    async def run():
        queue = asyncio.Queue()
        await playback_buffer.enqueue(queue, b'a' * 4800, lambda: False, 'Example')
        assert queue.get_nowait() == playback_buffer.CaptionedChunk(b'a' * 2400, 'Example')
        assert queue.get_nowait() == b'a' * 2400
    asyncio.run(run())


def test_reset_invalidates_older_scheduled_captions():
    events = []
    host = SimpleNamespace(ui=SimpleNamespace(speech_caption=events.append))
    speech_sync.reset(host)
    speech_sync.schedule(host, 'First', 123.0)
    speech_sync.reset(host)
    speech_sync.schedule(host, 'Second', 124.0)
    assert [e['epoch'] for e in events] == [1, 1, 2, 2]
    assert [e['kind'] for e in events] == ['reset', 'caption', 'reset', 'caption']


def test_player_schedules_each_caption_with_corresponding_pcm_not_on_receive():
    source = Path(__file__).resolve().parents[1] / 'main.py'
    tree = ast.parse(source.read_text(encoding='utf8'))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'JarvisLive')
    node = next(n for n in cls.body if isinstance(n, ast.AsyncFunctionDef) and n.name == '_play_audio')
    written = []
    class Stream:
        latency = .1
        def start(self): pass
        def stop(self): pass
        def close(self): pass
        def write(self, pcm): written.append(pcm)
    ns = {'asyncio': asyncio, 'time': time, 'np': np,
          'sd': SimpleNamespace(RawOutputStream=lambda **kwargs: Stream()),
          'audio_devices': SimpleNamespace(resolve=lambda *_: None), 'get_output_device': lambda: '',
          'RECEIVE_SAMPLE_RATE': 24000, 'CHANNELS': 1, 'CHUNK_SIZE': 1024, '_TAIL_MARGIN': .1,
          '_VIS_HOP': 480, '_CURSOR_SLACK': .15, '_FIRST_SOUND': 1024 / 24000,
          '_pcm_visemes': lambda *args, **kwargs: [], '_pcm_level': lambda _: 0.0}
    exec(compile(ast.Module(body=[node], type_ignores=[]), str(source), 'exec'), ns)
    async def run():
        queue = asyncio.Queue()
        await queue.put(playback_buffer.CaptionedChunk(b'\x01\x00' * 1200, 'First'))
        await queue.put(playback_buffer.CaptionedChunk(b'\x02\x00' * 1200, 'Second'))
        events = []
        done = asyncio.Event()
        done.set()
        obj = SimpleNamespace(audio_in_queue=queue, _engine=object(), _caption_epoch=7,
                              _out_latency=.1, _play_cursor=0.0, _turn_done_event=done, _dashboard=None,
                              ui=SimpleNamespace(speech_caption=events.append, set_audio_level=lambda _: None),
                              _echo=SimpleNamespace(note_output=lambda *_: None),
                              set_speaking=lambda _: None)
        task = asyncio.create_task(ns['_play_audio'](obj))
        await asyncio.sleep(.2)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        assert written == [b'\x01\x00' * 1200, b'\x02\x00' * 1200]
        assert [e['text'] for e in events] == ['First', 'Second', '']
        assert all(e['epoch'] == 7 for e in events)
        assert abs((events[1]['at'] - events[0]['at']) - .05) < .005
        assert events[2]['at'] >= events[1]['at']
    asyncio.run(run())
