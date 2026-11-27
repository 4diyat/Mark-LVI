"""Visual voice-idle state based on the microphone's measured level.

Idle is a visual state, not microphone mute: audio continues to stream. This is
an amplitude heuristic, not speech recognition; noisy rooms can delay idle and
very quiet speech can be missed. The UI must say the microphone remains active.
"""
import time

SILENCE_SECONDS = 8.0
NOISE_FLOOR = 0.06


class VoiceIdle:
    def __init__(self):
        self._last_sound = None

    def reset(self):
        self._last_sound = None

    def feed(self, level, state, now=None):
        now = time.monotonic() if now is None else now
        state = str(state or '').upper()
        if state not in {'LISTENING', 'IDLE'}:
            self.reset()
            return None
        if self._last_sound is None:
            self._last_sound = now
        if level >= NOISE_FLOOR:
            self._last_sound = now
            return 'LISTENING' if state == 'IDLE' else None
        if state == 'LISTENING' and now - self._last_sound >= SILENCE_SECONDS:
            return 'IDLE'
        return None
