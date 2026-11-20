"""Late model/voice events from cancelled generations must not reach the app."""
import asyncio

from providers.base import FunctionCall
from providers.engine_pipeline import PipelineEngine


class StubbornLLM:
    caps = {'tools': True, 'tool_format': 'openai'}

    def __init__(self):
        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.calls = 0

    async def chat(self, messages, tools):
        self.calls += 1
        if self.calls == 1:
            self.started.set()
            try:
                await self.release.wait()
            except asyncio.CancelledError:
                await self.release.wait()  # a provider that suppresses cancellation
            yield {'text': 'Stale response.'}
            yield {'tool_calls': [FunctionCall(id='stale', name='dangerous', args={})]}
        else:
            yield {'text': 'Fresh response.'}


def test_uncooperative_model_cannot_emit_stale_text_or_tool_calls():
    async def run():
        llm = StubbornLLM()
        engine = PipelineEngine(llm)
        await engine.send_client_content(turns={'parts': [{'text': 'old'}]})
        await asyncio.wait_for(llm.started.wait(), 1)
        old = engine._gen
        marker = engine.interrupt()
        await engine.send_client_content(turns={'parts': [{'text': 'new'}]})
        await asyncio.wait_for(engine._gen, 1)
        llm.release.set()
        await asyncio.wait_for(old, 1)
        events = [engine._queue.get_nowait() for _ in range(engine._queue.qsize())]
        assert events[0].interruption_id == marker
        assert all(m.tool_call is None for m in events)
        assert [m.server_content.output_transcription.text for m in events
                if m.server_content and m.server_content.output_transcription] == ['Fresh response.']
        assert not any('Stale' in str(item) or 'dangerous' in str(item) for item in engine._history)
        await engine.close()
    asyncio.run(run())


def test_uncooperative_voice_cannot_emit_audio_or_end_for_old_generation():
    class Model:
        caps = {'tools': False, 'tool_format': None}
        async def chat(self, messages, tools):
            yield {'text': 'A sentence.'}
    class Voice:
        def __init__(self):
            self.started, self.release = asyncio.Event(), asyncio.Event()
            self.calls = 0
        async def speak(self, text):
            self.calls += 1
            if self.calls == 1:
                self.started.set()
                try:
                    await self.release.wait()
                except asyncio.CancelledError:
                    await self.release.wait()
                yield b'stale'
            else:
                yield b'fresh'
    async def run():
        voice = Voice()
        engine = PipelineEngine(Model(), tts=voice)
        await engine.send_client_content(turns={'parts': [{'text': 'old'}]})
        await asyncio.wait_for(voice.started.wait(), 1)
        old = engine._gen
        token = engine.interrupt()
        await engine.send_client_content(turns={'parts': [{'text': 'new'}]})
        await asyncio.wait_for(engine._gen, 1)
        voice.release.set()
        await asyncio.wait_for(old, 1)
        stream = engine.receive()
        events = []
        for _ in range(engine._queue.qsize()):
            events.append(await asyncio.wait_for(anext(stream), 1))
        assert [m.interruption_id for m in events if m.interruption_id] == [token]
        assert [m.data for m in events if m.data] == [b'fresh']
        assert sum(bool(m.server_content and m.server_content.turn_complete) for m in events) == 1
        assert sum(item.get('role') == 'assistant' for item in engine._history) == 1
        await stream.aclose()
        await engine.close()
    asyncio.run(run())
