"""Voice-specific glass orb, sharing OrbCore's audio and motion lifecycle."""
import math

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPen, QRadialGradient

from ui.hud_orb import OrbCore


class VoiceOrb(OrbCore):
    def paintEvent(self, event):  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        cx, cy = self.width() / 2, self.height() * .51
        r = min(self.width() * .205, self.height() * .175, 130)
        centre = QPointF(cx, cy)
        halo = QRadialGradient(centre, r * 2.6)
        halo.setColorAt(0, QColor(14, 92, 208, 125))
        halo.setColorAt(.55, QColor(2, 63, 158, 45))
        halo.setColorAt(1, QColor(0, 31, 90, 0))
        p.setPen(Qt.PenStyle.NoPen); p.setBrush(halo)
        p.drawEllipse(centre, r * 2.6, r * 2.6)
        p.setBrush(Qt.BrushStyle.NoBrush)
        for i, factor in enumerate((1.25, 1.44, 1.63, 1.80, 1.95)):
            p.setPen(QPen(QColor(32, 128, 243, 70 - i * 11), 1.3))
            p.drawEllipse(centre, r * factor, r * factor)
        # The breathing is decorative. Only the size of the glow changes with
        # the actual input/output level; silence remains visually still here.
        breath = 1.0 + .018 * math.sin(self.phase)
        radius = r * breath
        sphere = QRadialGradient(QPointF(cx - radius * .32, cy - radius * .44), radius * 1.65)
        sphere.setColorAt(0, QColor('#71c6ff'))
        sphere.setColorAt(.25, QColor('#237bd3'))
        sphere.setColorAt(.65, QColor('#063777'))
        sphere.setColorAt(.87, QColor('#05204b'))
        sphere.setColorAt(1, QColor('#176fd0'))
        p.setBrush(sphere)
        for width, alpha in ((12, 35), (7, 75), (3, 230)):
            p.setPen(QPen(QColor(77, 180, 255, alpha), width))
            p.drawEllipse(centre, radius, radius)
        # Faint hexagonal texture is a decorative surface, not data.
        clip = QPainterPath(); clip.addEllipse(centre, radius * .92, radius * .92)
        p.save(); p.setClipPath(clip)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(121, 199, 255, 24), .8))
        unit = 10.0
        for row in range(-9, 10):
            for col in range(-8, 9):
                hx = cx + col * unit * 1.73 + (row % 2) * unit * .865
                hy = cy + row * unit * 1.5
                hexagon = QPainterPath()
                for point in range(6):
                    angle = math.pi / 3 * point + math.pi / 6
                    px, py = hx + unit * math.cos(angle), hy + unit * math.sin(angle)
                    if point == 0:
                        hexagon.moveTo(px, py)
                    else:
                        hexagon.lineTo(px, py)
                hexagon.closeSubpath(); p.drawPath(hexagon)
        p.restore()
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(QColor(147, 218, 255, 180), 1.5))
        p.drawEllipse(centre, radius * .94, radius * .94)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(190, 233, 255, 115))
        p.save(); p.translate(cx - radius * .38, cy - radius * .66); p.rotate(-32)
        p.drawEllipse(QRectF(-radius * .28, -radius * .055, radius * .56, radius * .11))
        p.restore()
        if self.level > 0:
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(QColor(76, 193, 255, int(35 + self.level * 120)), 2))
            p.drawEllipse(centre, radius * (1.10 + self.level * .12), radius * (1.10 + self.level * .12))
        p.end()
