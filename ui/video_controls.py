"""Local video transport, including the separate YouTube soundtrack."""
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtMultimedia import QMediaPlayer
from PyQt6.QtWidgets import QFileDialog, QHBoxLayout, QLabel, QPushButton, QSlider

from core.i18n import label as _t


def install(window, layout):
    row = QHBoxLayout()
    open_button = QPushButton(_t("video_control.open"))
    open_button.clicked.connect(lambda: open_local(window))
    row.addWidget(open_button)
    window._video_pause_btn = QPushButton(_t("video_control.pause"))
    window._video_pause_btn.clicked.connect(lambda: toggle_pause(window))
    row.addWidget(window._video_pause_btn)
    window._video_seek = QSlider(Qt.Orientation.Horizontal)
    window._video_seek.setRange(0, 0)
    window._video_seek.setEnabled(False)
    window._video_seek.sliderReleased.connect(lambda: seek(window))
    row.addWidget(window._video_seek, 1)
    window._video_time = QLabel("0:00 / 0:00")
    row.addWidget(window._video_time)
    layout.addLayout(row)
    window._video_duration_ms = 0
    window._video_seekable = False
    if window._video_player is None:
        window._video_pause_btn.setEnabled(False)
        return
    window._video_player.positionChanged.connect(lambda value: position_changed(window, value))
    window._video_player.durationChanged.connect(lambda value: duration_changed(window, value))
    window._video_player.seekableChanged.connect(lambda value: seekable_changed(window, value))
    window._video_player.playbackStateChanged.connect(lambda value: state_changed(window, value))


def _clock(milliseconds):
    seconds = max(0, int(milliseconds)) // 1000
    hours, seconds = divmod(seconds, 3600)
    minutes, seconds = divmod(seconds, 60)
    return f"{hours}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes}:{seconds:02d}"


def position_changed(window, value):
    value = max(0, int(value))
    if not window._video_seek.isSliderDown():
        window._video_seek.setValue(min(value, 2_147_483_647))
    window._video_time.setText(f"{_clock(value)} / {_clock(window._video_duration_ms)}")


def duration_changed(window, value):
    window._video_duration_ms = max(0, int(value))
    window._video_seek.setRange(0, min(window._video_duration_ms, 2_147_483_647))
    window._video_seek.setEnabled(window._video_seekable and window._video_duration_ms > 0)
    position_changed(window, window._video_player.position())


def seekable_changed(window, value):
    window._video_seekable = bool(value)
    window._video_seek.setEnabled(window._video_seekable and window._video_duration_ms > 0)


def state_changed(window, state):
    label = "video_control.pause" if state == QMediaPlayer.PlaybackState.PlayingState else "video_control.play"
    window._video_pause_btn.setText(_t(label))


def toggle_pause(window):
    if not window._video_on or window._video_player is None:
        return
    if window._video_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
        window._video_player.pause()
        if window._video_split and window._video_sound:
            window._video_sound.pause()
    else:
        if window._video_split and window._video_sound:
            window._video_sound.setPosition(window._video_player.position())
            window._video_sound.play()
        window._video_player.play()
    state_changed(window, window._video_player.playbackState())


def seek(window):
    if not (window._video_on and window._video_seekable and window._video_duration_ms > 0):
        return
    position = min(window._video_duration_ms, max(0, int(window._video_seek.value())))
    window._video_player.setPosition(position)
    if window._video_split and window._video_sound:
        window._video_sound.setPosition(position)


def reset(window):
    window._video_duration_ms = 0
    window._video_seekable = False
    window._video_seek.setRange(0, 0)
    window._video_seek.setEnabled(False)
    window._video_time.setText("0:00 / 0:00")
    window._video_pause_btn.setText(_t("video_control.play"))


def open_local(window):
    path, _ = QFileDialog.getOpenFileName(window, _t("video_control.open"), "",
                                         "Videos (*.mp4 *.mkv *.webm *.mov *.avi);;All files (*)")
    if path:
        window._on_video_open(path, Path(path).name, True)
