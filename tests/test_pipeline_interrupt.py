"""Local interrupt barriers separate cancelled output from the next user turn."""
import ast
import asyncio
import traceback
from pathlib import Path
from types import SimpleNamespace

from core import playback_buffer, speech_sync
from providers.base import Msg
from providers.engine_pipeline import PipelineEngine


class LLM:
    caps = {'tools': False, 'tool_format': None}

    def __init__(self):
        self.calls = 0
        self.started = asyncio.Event()

    async def chat(self, messages, tools):
        self.calls += 1
        if self.calls == 1:
            self.started.set()
            await asyncio.Event().wait()
        yield {'text': 'Fresh answer.'}


def test_cancelled_generation_does_not_block_new_turn_and_barrier_precedes_it():
    async def run():
        llm = LLM()
        engine = PipelineEngine(llm)
        await engine.send_client_content(turns={'parts': [{'text': 'old'}]})
        await asyncio.wait_for(llm.started.wait(), 1)
        old_task = engine._gen
        token = engine.interrupt()
        assert token == 1 and old_task.cancelling()
        await engine.send_client_content(turns={'parts': [{'text': 'new'}]})
        assert engine._gen is not old_task
        await asyncio.wait_for(engine._gen, 1)
        events = [engine._queue.get_nowait() for _ in range(engine._queue.qsize())]
        assert events[0].interruption_id == token
        assert any(m.server_content and m.server_content.output_transcription
                   and m.server_content.output_transcription.text == 'Fresh answer.' for m in events)
        assert events[-1].server_content.turn_complete
        await engine.close()
    asyncio.run(run())


def test_idle_repeated_interrupts_have_distinct_ordered_barriers():
    async def run():
        engine = PipelineEngine(LLM())
        one, two = engine.interrupt(), engine.interrupt()
        assert (one, two) == (1, 2)
        assert [engine._queue.get_nowait().interruption_id for _ in range(2)] == [1, 2]
        await engine.close()
        assert engine.interrupt() is None
    asyncio.run(run())


def _main_methods():
    source = Path(__file__).resolve().parents[1] / 'main.py'
    tree = ast.parse(source.read_text(encoding='utf8'))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'JarvisLive')
    nodes = [n for n in cls.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
             and n.name in ('_receive_audio', '_interrupt_on_loop')]
    ns = {'asyncio': asyncio, 'playback_buffer': playback_buffer, 'speech_sync': speech_sync,
          '_clean_transcript': lambda text: text, '_is_repeat_chunk': lambda *_: False,
          # The method is exec'd out of main.py, so it sees exactly the
          # globals given here — every module-level name it uses must be one of
          # them. `keep_turn` is the transcript writer; `traceback` was already
          # missing and only ever surfaced as a NameError raised from inside
          # the except block, which hid the real error.
          'keep_turn': lambda role, text: None, 'traceback': traceback,
          '_transcript': SimpleNamespace(REPEAT_MIN=5,
                                         is_repeat_chunk=lambda *_: False)}
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(source), 'exec'), ns)
    return ns


def test_main_pipeline_interrupt_barrier_discards_old_audio_not_next_answer():
    async def run():
        ns = _main_methods()
        llm = LLM()
        llm.calls = 1  # the next turn responds immediately
        class Voice:
            async def speak(self, text):
                yield b'fresh'
        engine = PipelineEngine(llm, tts=Voice())
        queue = asyncio.Queue(maxsize=1)
        engine._queue.put_nowait(Msg.audio(b'a' * (2 * playback_buffer.SLICE_BYTES)))
        # An old ordinary completion must not clear the interrupt before its barrier.
        engine._queue.put_nowait(Msg.said('Old partial answer.'))
        engine._queue.put_nowait(Msg.turn_end())
        engine._queue.put_nowait(Msg.audio(b'stale'))
        engine._queue.put_nowait(Msg.said('Old late transcript.'))
        logs, traffic = [], []
        logged = asyncio.Event()
        def log(text):
            logs.append(text)
            if text == 'JARVIS: Fresh answer.':
                logged.set()
        obj = SimpleNamespace(session=engine, _engine=engine, audio_in_queue=queue,
                              _clear_stall=lambda: traffic.append(True), _interrupted=False,
                              _interrupt_local_token=None, _turn_done_event=asyncio.Event(),
                              _last_out_logged='', _asst_name='JARVIS', _session_log=[], _dashboard=None,
                              _vision_close_pending=False, _play_cursor=1,
                              _visemes=SimpleNamespace(feed_text=lambda _: None, reset=lambda: None),
                              ui=SimpleNamespace(write_log=log), set_speaking=lambda _: None)
        receiver = asyncio.create_task(ns['_receive_audio'](obj))
        await asyncio.sleep(0)
        assert queue.full()
        ns['_interrupt_on_loop'](obj, queue)
        assert obj._interrupted and obj._interrupt_local_token == 1
        # Second interrupt's barrier supersedes the first one.
        ns['_interrupt_on_loop'](obj, queue)
        assert obj._interrupt_local_token == 2
        await engine.send_client_content(turns={'parts': [{'text': 'new'}]})
        await asyncio.wait_for(logged.wait(), 1)
        assert not obj._interrupted and obj._interrupt_local_token is None
        assert queue.get_nowait() == playback_buffer.CaptionedChunk(b'fresh', 'Fresh answer.')
        assert queue.empty()
        assert obj._session_log == ['JARVIS: Fresh answer.']
        assert len(traffic) == 8  # two local barriers are not provider traffic
        receiver.cancel()
        try:
            await receiver
        except asyncio.CancelledError:
            pass
        await engine.close()
    asyncio.run(run())


def test_pending_user_turn_is_not_lost_when_interrupting_prior_generation():
    async def run():
        llm = LLM()
        engine = PipelineEngine(llm)
        await engine.send_client_content(turns={'parts': [{'text': 'old'}]})
        await asyncio.wait_for(llm.started.wait(), 1)
        await engine.send_client_content(turns={'parts': [{'text': 'already queued'}]})
        assert engine._followup
        token = engine.interrupt()
        assert token == 1 and not engine._followup
        await asyncio.wait_for(engine._gen, 1)
        events = [engine._queue.get_nowait() for _ in range(engine._queue.qsize())]
        assert events[0].interruption_id == token
        assert events[-1].server_content.turn_complete
        assert any(m.server_content and m.server_content.output_transcription
                   and m.server_content.output_transcription.text == 'Fresh answer.' for m in events)
        await engine.close()
    asyncio.run(run())
