"""ui/audio.py — the audio bar: a song, a podcast, a stream, playing under the HUD.

WHY THIS IS A MIXIN AND NOT JUST A FEW METHODS IN window.py
    Two reasons, and the second is the one that made the file.

    1. Sound is not video. A video takes the centre of the HUD and starts
       muted; audio plays *while the assistant stays on screen* and is the thing
       people actually ask for by name ("put on some music"). Keeping its
       progress, its pause state, its loop switch and its volume in the video
       surface would have meant two features sharing a boolean about who owns
       the speakers.

    2. `ui/window.py` has a ceiling, enforced by its own test. This bar added a
       hundred and eighteen lines to a file that was already at seven thousand,
       and the test — correctly — refused. The mixin is the shape the project
       already uses for `ui/metrics.py` and `ui/theme.py`: the window owns the
       widgets, a small module owns one concern, and the package re-exports both
       so nothing outside has to know the difference.

THE OUTPUT DEVICE IS THE POINT
    The user picks a speaker in AUDIO DEVICES and that is where the sound must
    come out. Leaving it to Qt means a song plays through laptop speakers while
    the headset they configured sits silent — the exact complaint the device
    panel exists to fix. So `_apply_audio_device` resolves the chosen name
    through `core.audio_devices.resolve` and hands the result to the output.

WHAT THIS DOES NOT DO
    It does not fetch anything. YouTube audio is resolved by the tool
    (`actions/video_player.py`) on its own thread and arrives here as a URL,
    because the window must never block on the network — that rule is older
    than this file and is why every method here is a slot on the Qt thread.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QSlider, QWidget

from core import playback as _pb
from core.i18n import label as _t
from ui.theme import C


class AudioMixin:
    """Mixed into MainWindow. Expects the attributes `_build_audio_bar` creates."""

    # ── the bar ────────────────────────────────────────────────────────────

    def _build_audio_bar(self, button_factory) -> None:
        """Create the strip under the HUD. `button_factory` is the window's own
        header-button helper, so the bar cannot drift away from the video
        header's styling."""
        self._audio_on = False
        self._audio_paused = False
        self._audio_loop = False
        self._audio_cont = QWidget()
        self._audio_cont.setStyleSheet(
            f"background: {C.PANEL}; border-top: 1px solid {C.BORDER};")
        row = QHBoxLayout(self._audio_cont)
        row.setContentsMargins(10, 4, 10, 4)
        row.setSpacing(6)

        self._audio_lbl = QLabel(_t("ui.audio.heading"))
        self._audio_lbl.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
        self._audio_lbl.setStyleSheet(f"color: {C.PRI}; background: transparent;")
        row.addWidget(self._audio_lbl, stretch=1)

        self._audio_pause_btn = button_factory(_t("ui.audio.pause"))
        self._audio_pause_btn.clicked.connect(self._toggle_audio_pause)
        row.addWidget(self._audio_pause_btn)

        self._audio_loop_btn = button_factory(_t("ui.audio.loop"))
        self._audio_loop_btn.clicked.connect(self._toggle_audio_loop)
        row.addWidget(self._audio_loop_btn)

        self._audio_vol = QSlider(Qt.Orientation.Horizontal)
        self._audio_vol.setFixedWidth(90)
        self._audio_vol.setRange(0, 100)
        self._audio_vol.setValue(70)
        self._audio_vol.valueChanged.connect(self._on_audio_volume_slider)
        row.addWidget(self._audio_vol)

        close = button_factory(_t("ui.close_x"))
        close.clicked.connect(self.stop_audio)
        row.addWidget(close)
        self._audio_cont.hide()

    # ── device ─────────────────────────────────────────────────────────────

    def _apply_audio_device(self) -> None:
        if not getattr(self, "_audio_out", None):
            return
        try:
            from core import audio_devices
            from memory.config_manager import get_output_device
            name = get_output_device() or ""
            if not name:
                return
            idx = audio_devices.resolve(name, "output")
            if idx is not None:
                self._audio_out.setDevice(self._audio_device_for(idx))
        except Exception:
            # A device that cannot be resolved is not a reason to refuse to
            # play: the system default is what would have happened anyway.
            pass

    def _audio_device_for(self, index):
        from PyQt6.QtMultimedia import QAudioDevice
        return QAudioDevice.fromId(str(index))

    # ── slots ──────────────────────────────────────────────────────────────

    def _on_audio_open(self, source: str, title: str, volume: float,
                       loop: bool) -> None:
        if not getattr(self, "_audio_player", None):
            self.write_log(_t("ui.audio.unavailable"))
            return
        self._apply_audio_device()
        self._audio_loop = bool(loop)
        self._audio_paused = False
        self._audio_on = True
        self._audio_lbl.setText(_t("ui.audio.playing",
                                  title=(title or "AUDIO")[:40]))
        self._audio_pause_btn.setText(_t("ui.audio.pause"))
        self._audio_loop_btn.setText(_t("ui.audio.loop_on") if loop
                                     else _t("ui.audio.loop"))
        vol = max(0.0, min(1.0, float(volume)))
        try:
            self._audio_vol.blockSignals(True)
            self._audio_vol.setValue(int(vol * 100))
            self._audio_vol.blockSignals(False)
        except Exception:
            pass
        self._audio_out.setVolume(vol)
        self._audio_player.setSource(QUrl(_pb.media_url(source) or source))
        self._audio_cont.show()
        self._audio_player.play()

    def _on_audio_stop(self) -> None:
        if not getattr(self, "_audio_player", None):
            return
        try:
            self._audio_player.stop()
            self._audio_player.setSource(QUrl())
        except Exception:
            pass
        self._audio_on = False
        self._audio_paused = False
        self._audio_cont.hide()

    def _on_audio_pause(self, paused: bool) -> None:
        if not (getattr(self, "_audio_player", None) and self._audio_on):
            return
        try:
            self._audio_player.pause() if paused else self._audio_player.play()
        except Exception:
            return
        self._audio_paused = bool(paused)
        self._audio_pause_btn.setText(_t("ui.audio.resume") if paused
                                      else _t("ui.audio.pause"))

    def _on_audio_volume(self, volume: float) -> None:
        if getattr(self, "_audio_out", None):
            self._audio_out.setVolume(max(0.0, min(1.0, float(volume))))
        try:
            self._audio_vol.blockSignals(True)
            self._audio_vol.setValue(int(float(volume) * 100))
            self._audio_vol.blockSignals(False)
        except Exception:
            pass

    def _on_audio_volume_slider(self, value: int) -> None:
        if getattr(self, "_audio_out", None):
            self._audio_out.setVolume(max(0.0, min(1.0, value / 100.0)))

    def _toggle_audio_pause(self) -> None:
        self._on_audio_pause(not self._audio_paused)

    def _toggle_audio_loop(self) -> None:
        self._audio_loop = not self._audio_loop
        self._audio_loop_btn.setText(_t("ui.audio.loop_on") if self._audio_loop
                                     else _t("ui.audio.loop"))

    def _on_audio_status(self, status) -> None:
        word = self._status_word(status)
        if word == "ended":
            if self._audio_loop:
                # The one case where an end is not an end: background music was
                # asked for, so put it back to the start instead of closing the
                # bar the user is listening to.
                try:
                    self._audio_player.setPosition(0)
                    self._audio_player.play()
                except Exception:
                    pass
                return
            self.write_log(_t("ui.audio.finished"))
            self._on_audio_stop()
        elif word in ("invalid", "no_media"):
            self._on_audio_error()

    def _on_audio_error(self, *_a) -> None:
        detail = ""
        try:
            detail = self._audio_player.errorString()
        except Exception:
            pass
        self.write_log(_t("ui.audio.failed", detail=detail or "?"))
        self._on_audio_stop()

    # ── questions answered from other threads ──────────────────────────────

    def audio_is_playing(self) -> bool:
        """True only while sound is actually coming out — a paused song is not
        playing, and the tool answers its questions from this."""
        return bool(self._audio_on and not self._audio_paused)

    def stop_audio(self) -> None:
        self._audio_stop_sig.emit()
