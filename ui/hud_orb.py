"""Blue visualizer: audio rings respond only to real input/output levels."""
from __future__ import annotations

import math
import time
from collections import deque
from pathlib import Path

from PyQt6.QtCore import QPointF, QRectF, Qt, QTimer, QSize, pyqtSignal
from PyQt6.QtGui import QColor, QImage, QPainter, QPainterPath, QPen, QRadialGradient
from PyQt6.QtWidgets import QPushButton, QSizePolicy, QWidget

from ui.hud_icons import icon


def colour(r, g, b, alpha=255):
    return QColor(r, g, b, alpha)


class OrbCore(QWidget):
    activated = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.level = 0.0
        self.samples = deque([0.0] * 96, maxlen=96)
        self.last_sample = 0.0
        self.state = 'initialising'
        self.phase = 0.0
        self.reduced_motion = False
        self.art = QImage(str(Path(__file__).resolve().parent.parent / 'assets/workspace/orb-core.png'))
        if not self.art.isNull():
            self.art = self.art.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
            mask_painter = QPainter(self.art)
            mask_painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
            mask = QRadialGradient(self.art.width()/2, self.art.height()/2, self.art.width()/2)
            mask.setColorAt(0, QColor(0, 0, 0, 255))
            mask.setColorAt(.82, QColor(0, 0, 0, 255))
            mask.setColorAt(1, QColor(0, 0, 0, 0))
            mask_painter.fillRect(self.art.rect(), mask)
            mask_painter.end()
            # A subtle blue glaze softens the bright rim and lifts dark interiors.
            glaze = QPainter(self.art)
            glaze.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceAtop)
            glaze.fillRect(self.art.rect(), QColor(22, 92, 185, 38))
            glaze.end()
        self.setAccessibleName('Orb JARVIS — kontrol mikrofon')
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(250, 250)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(80)

    def tick(self):
        self.phase = (self.phase + .09) % (2 * math.pi)
        if time.monotonic() - self.last_sample > .3:
            self.level = 0.0
            if any(self.samples):
                self.samples.append(0.0)
        if self.isVisible():
            self.update()

    def set_reduced_motion(self, reduced):
        self.reduced_motion = bool(reduced)
        if reduced:
            self.timer.stop()
            self.level = 0.0
            self.samples = deque([0.0] * 96, maxlen=96)
        else:
            self.timer.start(80)
        self.update()

    def set_level(self, level):
        if self.reduced_motion:
            return
        self.level = max(0.0, min(1.0, float(level)))
        self.samples.append(self.level)
        self.last_sample = time.monotonic()
        self.update()

    def set_state(self, state):
        self.state = str(state).lower()
        self.update()

    def mouseReleaseEvent(self, event):  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.position().toPoint()):
            self.activated.emit()
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event):  # noqa: N802
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.activated.emit()
            event.accept()
        else:
            super().keyPressEvent(event)

    def paintEvent(self, event):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        cx, cy = w / 2, h * .51
        r = min(w * .235, h * .19, 175)
        if r <= 0:
            return
        halo = QRadialGradient(cx, cy, r * 2.25)
        halo.setColorAt(0, colour(0, 87, 230, 65))
        halo.setColorAt(.55, colour(0, 72, 176, 45))
        halo.setColorAt(1, colour(0, 40, 105, 0))
        p.setPen(Qt.PenStyle.NoPen); p.setBrush(halo)
        p.drawEllipse(QPointF(cx, cy), r*2.25, r*2.25)
        floor = QRadialGradient(cx, cy+r*1.92, r*1.55)
        floor.setColorAt(0, colour(29, 130, 255, 105))
        floor.setColorAt(1, colour(0, 55, 155, 0))
        p.save(); p.translate(cx, cy+r*1.92); p.scale(1, .18); p.translate(-cx, -(cy+r*1.92))
        p.setBrush(floor); p.drawEllipse(QPointF(cx, cy+r*1.92), r*1.55, r*1.55); p.restore()
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(colour(80, 176, 255, 70), 1))
        p.drawEllipse(QPointF(cx, cy), r*1.54, r*1.54)
        for i, sample in enumerate(self.samples):
            angle = 2 * math.pi * i / len(self.samples) - math.pi/2
            inner = r*1.56
            # Each bar is a recent audio sample, never a made-up spectrum.
            outer = inner + 2 + sample * r * .30
            p.setPen(QPen(colour(65, 172, 255, 125 + int(sample*110)), 1.6,
                          Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
            p.drawLine(QPointF(cx+inner*math.cos(angle), cy+inner*math.sin(angle)),
                       QPointF(cx+outer*math.cos(angle), cy+outer*math.sin(angle)))
        if not self.art.isNull():
            p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            # A gentle breathing effect is decorative; only the outer ring
            # represents actual recent audio samples.
            art_r = (r / .80) * (1.0 + .05 * math.sin(self.phase))
            p.drawImage(QRectF(cx-art_r, cy-art_r, art_r*2, art_r*2), self.art)
            p.end()
            return
        # The fallback breathes too; the audio-sample ring remains independent.
        r *= 1.0 + .05 * math.sin(self.phase)
        sphere = QRadialGradient(cx-r*.26, cy-r*.38, r*1.55)
        sphere.setColorAt(0, colour(27, 119, 237))
        sphere.setColorAt(.44, colour(7, 54, 129))
        sphere.setColorAt(.83, colour(2, 19, 51))
        sphere.setColorAt(1, colour(21, 92, 188))
        p.setBrush(sphere)
        p.setPen(QPen(colour(111, 206, 255, 245), 3))
        p.drawEllipse(QPointF(cx, cy), r, r)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(colour(72, 167, 255, 60), 1))
        for factor in (.92, .78, .60):
            p.drawEllipse(QPointF(cx, cy), r*factor, r*factor)
        # Internal light ribbons are decorative; the outer bars are real samples.
        for index in range(4):
            path = QPainterPath(QPointF(cx-r*.86, cy+r*.10+index*2))
            path.cubicTo(cx-r*.47, cy-r*.52+index*4, cx-r*.16, cy+r*.55-index*6, cx, cy+r*.12)
            path.cubicTo(cx+r*.35, cy-r*.38+index*4, cx+r*.48, cy-r*.32, cx+r*.88, cy+r*.16)
            p.setPen(QPen(colour(86, 207, 255, 125-index*22), 1.4))
            p.drawPath(path)
        p.end()


class MiniOrb(QWidget):
    """Status avatar; green is reserved for a known active session."""
    def __init__(self):
        super().__init__()
        self.art = QImage(str(Path(__file__).resolve().parent.parent / 'assets/workspace/orb-core.png'))
        self.connected = None
        self.setFixedSize(64, 64)
        self.setAccessibleName('Status sesi')

    def set_connected(self, connected):
        if connected != self.connected:
            self.connected = connected
            self.update()

    def paintEvent(self, event):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        circle = QPainterPath()
        circle.addEllipse(QRectF(1, 1, 57, 57))
        p.setClipPath(circle)
        p.fillRect(QRectF(1, 1, 57, 57), QColor('#102c50'))
        if not self.art.isNull():
            p.drawImage(QRectF(-6, -6, 71, 71), self.art)
        p.setClipping(False)
        p.setPen(QPen(QColor('#5699d7'), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(QRectF(1, 1, 57, 57))
        p.setPen(QPen(QColor('#0b121d'), 2))
        p.setBrush(QColor('#4dd992' if self.connected is True else '#94a5b7'))
        p.drawEllipse(QPointF(55, 55), 5.5, 5.5)
        p.end()


class Waveform(QWidget):
    """A horizontal history of actual audio, never fabricated samples."""
    def __init__(self):
        super().__init__()
        self.samples = deque([0.0] * 31, maxlen=31)
        self.last_sample = 0.0
        self.setFixedHeight(30)
        self.setAccessibleName('Level audio terbaru')
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.decay)
        self.timer.start(120)

    def add_level(self, level):
        self.last_sample = time.monotonic()
        self.samples.append(max(0.0, min(1.0, float(level))))
        self.update()

    def decay(self):
        if time.monotonic() - self.last_sample > .3 and any(self.samples):
            self.samples.append(0.0)
            self.update()

    def set_reduced_motion(self, reduced):
        if reduced:
            self.timer.stop()
            self.samples = deque([0.0] * 31, maxlen=31)
        else:
            self.timer.start(120)
        self.update()

    def paintEvent(self, event):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        count = len(self.samples)
        pitch = min(7.0, self.width()/max(count, 1))
        start = (self.width()-pitch*count)/2
        p.setPen(QPen(QColor('#56b9ff'), 2, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap))
        for i, sample in enumerate(self.samples):
            height = 2 + sample*24
            x = start+(i+.5)*pitch
            p.drawLine(QPointF(x, self.height()/2-height/2), QPointF(x, self.height()/2+height/2))
        p.end()


class MicButton(QPushButton):
    """Lucide microphone button with an accessible name supplied by the shell."""
    def __init__(self):
        super().__init__()
        self.setIcon(icon('mic', '#b9cfe5', 25))
        self.setIconSize(QSize(25, 25))
