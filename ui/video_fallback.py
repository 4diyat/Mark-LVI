"""ui/video_fallback.py — stream fallback, retry & A/V sync for the HUD video player.

WHY THIS IS A MIXIN AND NOT IN ui/window.py
    `ui/window.py` has a 7,000-line ceiling enforced by tests/test_ui_split.py.
    Putting the fallback queue, stream swapper, sound-stream recovery, and sync
    helper here keeps the window readable and isolates all non-widget playback
    recovery on the Qt side, mirroring ui/audio.py (`AudioMixin`).
"""
from __future__ import annotations

from PyQt6.QtCore import QUrl

try:
    from PyQt6.QtMultimedia import QMediaPlayer
except Exception:
    QMediaPlayer = None

from core import playback as _pb
from core.i18n import label as _t
from ui.audio import qurl_for


class VideoFallbackMixin:
    """Mixed into MainWindow. Expects the video attributes created in __init__."""

    def _init_video_fallback(self) -> None:
        self._video_fallbacks: list[dict[str, str]] = []
        self._video_audio_fallbacks: list[str] = []
        self._video_exhausted_cb = None
        self._video_swapping = False
        self._video_seq = 0

    def _set_video_fallbacks(self, audio_source: str, fallbacks,
                             on_exhausted) -> None:
        audio_list = []
        video_raw = fallbacks
        if isinstance(fallbacks, dict):
            video_raw = fallbacks.get("video") or []
            audio_list = fallbacks.get("audio") or []
        self._video_fallbacks = _pb.normalize_video_candidates(
            video_raw, default_audio=audio_source)
        self._video_audio_fallbacks = _pb.normalize_audio_candidates(audio_list)
        self._video_exhausted_cb = on_exhausted if callable(on_exhausted) else None

    def _clear_video_fallbacks(self) -> None:
        self._video_fallbacks = []
        self._video_audio_fallbacks = []
        self._video_exhausted_cb = None

    def _try_next_video_source(self, detail: str = "") -> bool:
        """Try the next pre-resolved stream, or trigger an alternative search.

        Returns True when recovery was initiated (either swapped to the next
        stream candidate or handed off to an async search for another source),
        False when no more fallback options exist.
        """
        if getattr(self, "_video_swapping", False):
            return True
        fallbacks = getattr(self, "_video_fallbacks", None) or []
        if fallbacks:
            cand = fallbacks.pop(0)
            self.write_log(_t("ui.video.retrying", detail=detail or "?"))
            self._swap_video_stream(cand["url"], cand.get("audio", ""))
            return True
        cb = getattr(self, "_video_exhausted_cb", None)
        if cb is not None:
            self._video_exhausted_cb = None
            seq = getattr(self, "_video_seq", 0)
            try:
                launched = bool(cb(detail or ""))
            except Exception:
                launched = False
            if launched:
                self.write_log(_t("ui.video.searching_alt", detail=detail or "?"))
                if getattr(self, "_video_seq", 0) == seq:
                    self._on_video_close()
                return True
        return False

    def _swap_video_stream(self, source: str, audio_source: str = "") -> None:
        """Load the next candidate stream cleanly without leaving stale audio."""
        muted = self._video_muted_state()
        self._video_swapping = True
        try:
            if self._video_sync:
                self._video_sync.stop()
            for p in (self._video_player, self._video_sound):
                if p:
                    try:
                        p.stop()
                        p.setSource(QUrl())
                    except Exception:
                        pass
            self._video_split = bool(audio_source)
            self._video_ended = False
            self._video_sound_failed = False
            self._set_video_muted(muted)
            self._video_player.setSource(qurl_for(source))
            if self._video_split and self._video_sound:
                self._video_sound.setSource(qurl_for(audio_source))
            self._hud_cam_stack.setCurrentIndex(2)
            self._video_on = True
        finally:
            self._video_swapping = False
        self._sync_mic_for_video()
        self._video_player.play()
        if self._video_split and self._video_sound:
            self._video_sound.play()
            if self._video_sync:
                self._video_sync.start()

    def _try_next_video_sound(self, detail: str = "") -> bool:
        """Try the next backup audio stream if the separate soundtrack failed."""
        if getattr(self, "_video_swapping", False):
            return True
        audio_fbs = getattr(self, "_video_audio_fallbacks", None) or []
        if not (getattr(self, "_video_split", False) and audio_fbs
                and getattr(self, "_video_sound", None)):
            return False
        next_audio = audio_fbs.pop(0)
        self.write_log(_t("ui.video.audio_retrying", detail=detail or "?"))
        self._video_swapping = True
        try:
            self._video_sound.stop()
            self._video_sound.setSource(QUrl())
            self._video_sound.setSource(qurl_for(next_audio))
            self._video_sound_failed = False
        finally:
            self._video_swapping = False
        self._video_sound.play()
        return True

    def _sync_video_sound(self) -> None:
        """Keep the separate soundtrack in step with the picture.

        Two players started at the same moment do not stay together: they buffer
        independently, and measured on a real stream they were about half a
        second apart after nine seconds. So the sound is nudged back to the
        picture whenever it drifts far enough to hear — and only then, because
        correcting a smaller gap is itself audible.
        """
        if not (self._video_split and self._video_sound and self._video_player):
            return
        try:
            if QMediaPlayer and (
                self._video_player.playbackState()
                != QMediaPlayer.PlaybackState.PlayingState
            ):
                return
            state = self._sound_state()
            d = _pb.sync_decision(self._video_player.position(),
                                  self._video_sound.position(), state)
            if d["restart"]:
                self._video_sound.setPosition(d["position"])
                self._video_sound.play()
                self._video_sound_failed = False
                self._sync_video_mute_btn()
            elif d["seek"]:
                self._video_sound.setPosition(d["position"])
        except Exception:
            pass

    def _sound_state(self) -> str:
        """The sound player's state as a plain word, so the rule stays testable."""
        if not (self._video_sound and QMediaPlayer):
            return "stopped"
        try:
            st = self._video_sound.playbackState()
            if st == QMediaPlayer.PlaybackState.PlayingState:
                return "playing"
            if st == QMediaPlayer.PlaybackState.PausedState:
                return "paused"
        except Exception:
            pass
        return "stopped"
