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


# ── the one correct way to turn a source into a QUrl ────────────────────────
#
# THIS FUNCTION IS THE FIX FOR "cannot play my video/lagu".
#
# Every player in the window used to do `QUrl(source)`. For a URL that is right.
# For a local path it is wrong, and wrong in a way that looks like the file is
# broken rather than the code: `QUrl(r"C:\\clips\\a b.mp4")` reads "C:" as a
# SCHEME, so the player is asked to fetch `c:\\clips\\a b.mp4` over a protocol
# that does not exist, fails, and reports a format error. A POSIX path with a
# space in it is not a local file either — `isLocalFile()` is False — because
# `QUrl` has no way to know a bare string is meant as a path.
#
# `QUrl.fromLocalFile` is what Qt provides for exactly this, and it is what a
# file:// URL, a Windows drive letter, a UNC share and a spaced path all need.
# The decision of which one applies lives in core/playback (`qurl_safe`) so it is
# tested without Qt; this is only the three lines that act on it.
def qurl_for(source: str):
    """A `QUrl` that actually points at what the user named."""
    raw = _pb.clean_source(source)
    if not raw:
        return QUrl()
    if _pb.qurl_safe(raw):
        # A path: expand `~`, and keep a file:// URL working by asking the
        # cleaner for the real file first.
        return QUrl.fromLocalFile(_pb.local_file(raw) or raw)
    return QUrl(_pb.media_url(raw) or raw)


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
                dev = self._audio_device_for(name)
                if dev is not None and not dev.isNull():
                    self._audio_out.setDevice(dev)
        except Exception:
            # A device that cannot be resolved is not a reason to refuse to
            # play: the system default is what would have happened anyway.
            pass

    def _audio_device_for(self, name: str):
        """The Qt output device whose description matches the chosen name.

        NOT `QAudioDevice.fromId`, which this used to call and which DOES NOT
        EXIST in PyQt6 — `QAudioDevice` has no such static method, so the call
        raised AttributeError inside `_apply_audio_device`'s try block and was
        swallowed. The result was that the user's chosen speaker was silently
        ignored and every song came out of the default device: exactly the
        complaint the AUDIO DEVICES panel exists to prevent.

        `QMediaDevices.audioOutputs()` is the real API. Matching on description
        is the only thing available without the device id: sounddevice and Qt
        are two different stacks with two different id spaces, so the name is
        the one thing they share. `core/audio_devices` already resolves that
        name to an endpoint, and the description Qt reports is the same string
        the panel showed.
        """
        try:
            from PyQt6.QtMultimedia import QMediaDevices
            outs = QMediaDevices.audioOutputs()
        except Exception:
            return None
        wanted = (name or "").strip()
        if not wanted:
            return None
        # EXACT FIRST. A partial match is the fallback because MME truncates
        # descriptions at 31 characters, which is the same reason
        # core/audio_devices matches a prefix.
        for dev in outs:
            try:
                if dev.description().strip() == wanted:
                    return dev
            except Exception:
                continue
        for dev in outs:
            try:
                desc = dev.description().strip()
            except Exception:
                continue
            if desc and (desc.startswith(wanted[:24]) or wanted.startswith(desc[:24])):
                return dev
        return None

    # ── slots ──────────────────────────────────────────────────────────────

    def _on_audio_open(self, source: str, title: str, volume: float,
                       loop: bool, fallbacks=None, on_exhausted=None) -> None:
        if not getattr(self, "_audio_player", None):
            self.write_log(_t("ui.audio.unavailable"))
            return
        self._apply_audio_device()
        self._audio_loop = bool(loop)
        self._audio_paused = False
        self._audio_on = True
        self._audio_fallbacks = _pb.normalize_audio_candidates(fallbacks or [])
        self._audio_exhausted_cb = (
            on_exhausted if callable(on_exhausted) else None
        )
        self._audio_seq = getattr(self, "_audio_seq", 0) + 1
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
        # A local file MUST go through qurl_for: `QUrl(r"C:\\music\\a.mp3")`
        # is a request for scheme "c", which no machine can fetch.
        self._audio_swapping = True
        try:
            self._audio_player.setSource(qurl_for(source))
        finally:
            self._audio_swapping = False
        # The bar lives inside the content panel, which is hidden by default.
        # Showing the bar alone is not enough — a widget cannot be visible
        # inside a hidden parent, and that was the state of the first version:
        # the tool answered "playing", and nothing appeared anywhere.
        self._show_audio_bar()
        self._audio_player.play()

    def _show_audio_bar(self) -> None:
        """Reveal the bar, and give it height if it lives in the splitter.

        THE BUG THIS REPLACES: the bar was parented to a wrapper widget that was
        never added to any layout, so playing a song answered "playing", wrote
        the right log line, and drew nothing at all. A widget is only visible if
        it is in a layout that is in the window.
        """
        try:
            self._audio_cont.show()
        except Exception:
            return
        split = getattr(self, "_center_split", None)
        try:
            if split is not None and self._audio_cont.parentWidget() is split:
                sizes = list(split.sizes())
                # A section that was never given height comes back as a 4-pixel
                # drag handle; 40 px is one line of the bar plus its margins.
                if len(sizes) > 3 and sizes[3] < 40:
                    sizes[3] = 40
                    split.setSizes(sizes)
        except Exception:
            pass

    def _collapse_audio_bar(self) -> None:
        """Give the bar's height back when the song stops.

        Without this the splitter keeps the 40 pixels it lent to a song that is
        over, and the HUD never gets them back — so playing one track would
        leave the window permanently smaller.
        """
        split = getattr(self, "_center_split", None)
        try:
            if split is not None and self._audio_cont.parentWidget() is split:
                sizes = list(split.sizes())
                if len(sizes) > 3 and sizes[3]:
                    spare = sizes[3]
                    sizes[3] = 0
                    sizes[0] += spare
                    split.setSizes(sizes)
        except Exception:
            pass

    def _on_audio_stop(self) -> None:
        if not getattr(self, "_audio_player", None):
            return
        self._audio_swapping = True
        try:
            self._audio_player.stop()
            self._audio_player.setSource(QUrl())
        except Exception:
            pass
        finally:
            self._audio_swapping = False
        self._audio_on = False
        self._audio_paused = False
        self._audio_fallbacks = []
        self._audio_exhausted_cb = None
        self._audio_cont.hide()
        self._collapse_audio_bar()

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
        if getattr(self, "_audio_swapping", False):
            return
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
        elif word in ("invalid", "no_media") and getattr(self, "_audio_on", False):
            self._on_audio_error()

    def _on_audio_error(self, *_a) -> None:
        if getattr(self, "_audio_swapping", False):
            return
        detail = _a[1] if len(_a) > 1 and isinstance(_a[1], str) else ""
        if not detail:
            try:
                detail = self._audio_player.errorString()
            except Exception:
                detail = ""
        fallbacks = getattr(self, "_audio_fallbacks", None) or []
        if fallbacks:
            nxt = fallbacks.pop(0)
            self.write_log(_t("ui.audio.retrying", detail=detail or "?"))
            self._audio_swapping = True
            try:
                self._audio_player.stop()
                self._audio_player.setSource(QUrl())
                self._audio_player.setSource(qurl_for(nxt))
            finally:
                self._audio_swapping = False
            self._audio_player.play()
            return
        cb = getattr(self, "_audio_exhausted_cb", None)
        if cb is not None:
            self._audio_exhausted_cb = None
            seq = getattr(self, "_audio_seq", 0)
            try:
                launched = bool(cb(detail or ""))
            except Exception:
                launched = False
            if launched:
                self.write_log(_t("ui.audio.searching_alt", detail=detail or "?"))
                if getattr(self, "_audio_seq", 0) == seq:
                    self._on_audio_stop()
                return
        self.write_log(_t("ui.audio.failed", detail=detail or "?"))
        self._on_audio_stop()

    # ── questions answered from other threads ──────────────────────────────

    def audio_is_playing(self) -> bool:
        """True only while sound is actually coming out — a paused song is not
        playing, and the tool answers its questions from this."""
        return bool(self._audio_on and not self._audio_paused)

    def stop_audio(self) -> None:
        self._audio_stop_sig.emit()
