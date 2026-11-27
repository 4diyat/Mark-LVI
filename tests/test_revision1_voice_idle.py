"""Eight seconds of low input changes presentation, not microphone streaming."""
import asyncio
import threading
from types import SimpleNamespace

from core import voice_idle
from tests.test_voice_command_regressions import methods


def test_silence_and_voice_transitions():
    idle = voice_idle.VoiceIdle()
    assert idle.feed(0, 'LISTENING', now=0) is None
    assert idle.feed(0, 'LISTENING', now=7.99) is None
    assert idle.feed(0, 'LISTENING', now=8) == 'IDLE'
    assert idle.feed(.4, 'IDLE', now=8.2) == 'LISTENING'
    assert idle.feed(0, 'LISTENING', now=16.1) is None
    assert idle.feed(0, 'LISTENING', now=16.2) == 'IDLE'


def test_other_states_reset_clock_and_are_never_overwritten():
    idle = voice_idle.VoiceIdle()
    idle.feed(0, 'LISTENING', now=0)
    assert idle.feed(0, 'THINKING', now=20) is None
    assert idle.feed(0, 'LISTENING', now=21) is None
    assert idle.feed(0, 'LISTENING', now=29) == 'IDLE'


def test_audio_callback_still_streams_when_visually_idle(monkeypatch):
    now = [0.0]
    monkeypatch.setattr(voice_idle.time, 'monotonic', lambda: now[0])
    async def check():
        callbacks = []
        class Samples:
            level = 0
            def tobytes(self): return b'audio'
        sample = Samples()
        class Stream:
            active = True
            def __enter__(self): return self
            def __exit__(self, *args): pass
        def factory(**kw):
            callbacks.append(kw['callback'])
            return Stream()
        device = SimpleNamespace(resolve=lambda *a: None,
                                 open_input_stream=lambda opener, dev, **kw: (opener(dev), ''))
        frames = []
        ns = methods('_listen_audio', extra={'audio_devices': device, 'sd': SimpleNamespace(InputStream=factory),
                     'get_input_device': lambda: '', 'CHANNELS': 1, 'CHUNK_SIZE': 1024,
                     '_pcm_level': lambda data: data.level,
                     '_queue_mic_frame': lambda q, frame: frames.append(frame)})
        class UI:
            _state = 'LISTENING'; muted = False; _voice_mode_active = True
            def compare_set_state(self, expected, new):
                if self._state != expected: return False
                self._state = new; return True
            def write_log(self, text): pass
            def set_audio_level(self, value): pass
        ui = UI()
        obj = SimpleNamespace(_wake_enabled=False, _awake=True, _speaking_lock=threading.Lock(),
                              _is_speaking=False, _tail_active=lambda: False,
                              _echo=SimpleNamespace(_hist=[]), _ptt_enabled=False,
                              _phone_active=False, out_queue=object(), _mic_recovered=False,
                              _deaf=False, _mic_recovered_first=True, ui=ui,
                              _apply_listening_state=lambda: None)
        task = asyncio.create_task(ns['_listen_audio'](obj))
        await asyncio.sleep(0)
        cb = callbacks[0]
        cb(sample, 1024, None, None); now[0] = 8.0
        cb(sample, 1024, None, None); assert ui._state == 'IDLE'
        now[0] = 8.1; sample.level = .5
        cb(sample, 1024, None, None); assert ui._state == 'LISTENING'
        ui._voice_mode_active = False; sample.level = 0
        now[0] = 30; cb(sample, 1024, None, None)
        now[0] = 50; cb(sample, 1024, None, None)
        assert ui._state == 'LISTENING'
        await asyncio.sleep(0)
        assert len(frames) == 5
        task.cancel()
        try: await task
        except asyncio.CancelledError: pass
    asyncio.run(check())
