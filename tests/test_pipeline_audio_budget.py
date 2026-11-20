"""Bounded PCM while keeping pipeline control messages ordered and available."""
import asyncio

from providers.base import Msg
from providers.engine_pipeline import PipelineEngine, _PIPELINE_AUDIO_SLICES
from core.playback_buffer import SLICE_BYTES


class LLM:
    caps = {'tools': False, 'tool_format': None}


class WholeVoice:
    def __init__(self, pcm):
        self.pcm = pcm

    async def speak(self, text):
        yield self.pcm


def test_large_tts_block_is_bounded_and_emerges_complete_in_order():
    async def run():
        count = _PIPELINE_AUDIO_SLICES + 5
        pcm = bytes(range(256)) * ((SLICE_BYTES * count) // 256 + 1)
        pcm = pcm[:SLICE_BYTES * count]
        engine = PipelineEngine(LLM(), tts=WholeVoice(pcm))
        speaker = asyncio.create_task(engine._speak('Something to say.'))
        await asyncio.sleep(0)
        assert engine._queue.qsize() == _PIPELINE_AUDIO_SLICES
        assert not speaker.done()
        stream = engine.receive()
        received = []
        for _ in range(count):
            msg = await asyncio.wait_for(anext(stream), 1)
            assert len(msg.data) <= SLICE_BYTES
            received.append(msg.data)
        await asyncio.wait_for(speaker, 1)
        assert b''.join(received) == pcm
        await stream.aclose()
        await engine.close()
    asyncio.run(run())


def test_interrupt_barrier_and_new_audio_survive_saturated_pipeline():
    async def run():
        engine = PipelineEngine(LLM())
        old = b'o' * (SLICE_BYTES * (_PIPELINE_AUDIO_SLICES + 1))
        engine._gen = asyncio.create_task(engine._emit(Msg.audio(old)))
        old_task = engine._gen
        await asyncio.sleep(0)
        assert not old_task.done() and engine._queue.qsize() == _PIPELINE_AUDIO_SLICES
        token = engine.interrupt()
        assert token == 1 and engine._queue.qsize() == _PIPELINE_AUDIO_SLICES + 1
        try:
            await old_task
        except asyncio.CancelledError:
            pass
        new_task = asyncio.create_task(engine._emit(Msg.audio(b'new')))
        stream = engine.receive()
        for _ in range(_PIPELINE_AUDIO_SLICES):
            assert (await asyncio.wait_for(anext(stream), 1)).data == b'o' * SLICE_BYTES
        assert (await asyncio.wait_for(anext(stream), 1)).interruption_id == token
        assert (await asyncio.wait_for(anext(stream), 1)).data == b'new'
        await asyncio.wait_for(new_task, 1)
        await stream.aclose()
        await engine.close()
    asyncio.run(run())


def test_close_while_audio_producer_waits_does_not_deadlock():
    async def run():
        engine = PipelineEngine(LLM())
        engine._gen = asyncio.create_task(engine._emit(
            Msg.audio(b'a' * (SLICE_BYTES * (_PIPELINE_AUDIO_SLICES + 1)))))
        task = engine._gen
        await asyncio.sleep(0)
        await asyncio.wait_for(engine.close(), 1)
        try:
            await task
        except asyncio.CancelledError:
            pass
        stream = engine.receive()
        messages = []
        async for message in stream:
            messages.append(message)
        assert len(messages) == _PIPELINE_AUDIO_SLICES
        assert all(len(m.data) == SLICE_BYTES for m in messages)
        assert engine._audio_slots._value == _PIPELINE_AUDIO_SLICES
    asyncio.run(run())


def test_tool_call_waits_behind_spoken_acknowledgement_without_loss():
    from providers.base import FunctionCall
    class ToolLLM:
        caps = {'tools': True, 'tool_format': 'openai'}
        async def chat(self, messages, tools):
            yield {'text': 'Working on it.'}
            yield {'tool_calls': [FunctionCall(id='call-1', name='sample', args={})]}
    async def run():
        pcm = b'x' * (SLICE_BYTES * (_PIPELINE_AUDIO_SLICES + 2))
        engine = PipelineEngine(ToolLLM(), tts=WholeVoice(pcm))
        await engine.send_client_content(turns={'parts': [{'text': 'go'}]})
        await asyncio.sleep(0)
        assert not engine._gen.done()
        stream = engine.receive()
        transcript = await asyncio.wait_for(anext(stream), 1)
        assert transcript.server_content.output_transcription.text == 'Working on it.'
        output = []
        for _ in range(_PIPELINE_AUDIO_SLICES + 2):
            output.append((await asyncio.wait_for(anext(stream), 1)).data)
        call = await asyncio.wait_for(anext(stream), 1)
        assert b''.join(output) == pcm
        assert call.tool_call.function_calls[0].name == 'sample'
        await engine._gen
        await stream.aclose()
        await engine.close()
    asyncio.run(run())


def test_closed_engine_releases_producers_waiting_outside_generation():
    async def run():
        engine = PipelineEngine(LLM())
        producer = asyncio.create_task(engine._emit(
            Msg.audio(b'a' * SLICE_BYTES * (_PIPELINE_AUDIO_SLICES + 1))))
        await asyncio.sleep(0)
        assert not producer.done()
        await asyncio.wait_for(engine.close(), 1)
        stream = engine.receive()
        assert (await asyncio.wait_for(anext(stream), 1)).data == b'a' * SLICE_BYTES
        await asyncio.wait_for(producer, 1)
        async for _ in stream:
            pass
        assert engine._audio_slots._value == _PIPELINE_AUDIO_SLICES
    asyncio.run(run())
