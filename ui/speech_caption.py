"""Playback-timed captions, owned and scheduled exclusively on the Qt thread."""
import time

from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtWidgets import QLabel, QPlainTextEdit, QVBoxLayout, QWidget

from core.i18n import label as _t
from ui.theme import C


class SpeechCaption(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.epoch = -1
        self.last_at = 0.0
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        self.heading = QLabel()
        self.heading.setTextFormat(Qt.TextFormat.PlainText)
        self.heading.setStyleSheet(f'color: {C.DESKTOP_MUTED};')
        layout.addWidget(self.heading)
        self.text = QPlainTextEdit()
        self.text.setReadOnly(True)
        self.text.setMaximumHeight(75)
        layout.addWidget(self.text)
        self.retranslate()
        self.hide()

    def retranslate(self):
        self.heading.setText(_t('speech.caption_heading'))
        self.text.setAccessibleName(_t('speech.caption_heading'))

    def handle(self, event):
        epoch = event.get('epoch', -1)
        if not isinstance(epoch, int) or epoch < self.epoch:
            return
        if epoch > self.epoch:
            self.epoch = epoch
            self.last_at = 0.0
            self.hide()
        if event.get('kind') == 'reset':
            self.last_at = 0.0
            self.text.clear()
            self.hide()
            return
        at = event.get('at', 0.0)
        value = event.get('text', '')
        if not isinstance(at, (int, float)) or not isinstance(value, str):
            return
        # The timer can outlive an interrupted or replaced connection.
        def show_if_current():
            if self.epoch != epoch or at < self.last_at:
                return
            self.last_at = at
            if value:
                self.text.setPlainText(value[:1200] + ('…' if len(value) > 1200 else ''))
                self.show()
            else:
                self.text.clear()
                self.hide()
        delay = max(0, min(60000, round((at - time.time()) * 1000)))
        QTimer.singleShot(delay, show_if_current)
