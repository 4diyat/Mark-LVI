"""Embed the same audio-reactive orb as the main surface in voice mode.

The orb itself owns its paint and timer. This module only synchronizes it with
voice visibility, incoming audio and the main window's reduced-motion choice.
"""
import time
from collections import deque


def attach(overlay, canvas):
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QWidget
    from ui.voice_orb_art import VoiceOrb

    # Clip the main orb's floor glow before the transcript area. The visible
    # centre matches the voice artboard while retaining the same renderer.
    clip = QWidget(canvas)
    clip.setGeometry(340, 0, 600, 518)
    clip.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
    orb = VoiceOrb()
    orb.setParent(clip)
    orb.setGeometry(0, -40, 600, 640)
    orb.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    orb.timer.stop()
    overlay._voice_orb_clip = clip
    overlay._voice_orb = orb
    overlay._reduced_motion = False
    overlay._last_voice_sample = 0.0
    clip.show(); orb.show()


def visibility(overlay, visible):
    orb = getattr(overlay, '_voice_orb', None)
    if orb is None:
        return
    if visible:
        orb.set_reduced_motion(getattr(overlay, '_reduced_motion', False))
    else:
        orb.timer.stop()
        orb.level = 0.0
        orb.samples = deque([0.0] * 96, maxlen=96)
        overlay._audio_level = 0.0
        overlay._last_voice_sample = 0.0


def set_reduced_motion(overlay, reduced):
    overlay._reduced_motion = bool(reduced)
    orb = getattr(overlay, '_voice_orb', None)
    if orb is not None:
        orb.set_reduced_motion(reduced)
        if not overlay.active:
            orb.timer.stop()
    if reduced:
        overlay._audio_level = 0.0
    overlay._refresh()


def audio(overlay, value):
    if not overlay.active or getattr(overlay, '_reduced_motion', False):
        overlay._audio_level = 0.0
        return
    overlay._audio_level = value
    overlay._last_voice_sample = time.monotonic()
    orb = getattr(overlay, '_voice_orb', None)
    if orb is not None:
        orb.set_level(value)


def tick(overlay):
    if time.monotonic() - getattr(overlay, '_last_voice_sample', 0.0) > .3:
        overlay._audio_level = 0.0
    overlay._refresh()
