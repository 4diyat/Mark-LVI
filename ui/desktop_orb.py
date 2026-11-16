"""Software-painted assistant orb for the desktop workspace."""
from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QPen, QRadialGradient

from ui.theme import C, qcol


def paint_orb(painter, width, height, amplitude, muted):
    """A softly glowing ring. Its brightness follows the real audio level."""
    painter.fillRect(QRectF(0, 0, width, height), qcol(C.DESKTOP_PANEL))
    cx, cy = width / 2, height / 2
    r = max(1.0, min(width, height) * .33)
    glow = QRadialGradient(cx, cy, r * 1.6)
    if muted:
        glow.setColorAt(0, QColor(130, 65, 83, 90))
        glow.setColorAt(.45, QColor(135, 75, 90, 70))
    else:
        glow.setColorAt(0, QColor(108, 186, 224, 80))
        glow.setColorAt(.45, QColor(81, 170, 219, 100))
    glow.setColorAt(1, QColor(45, 106, 148, 0))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QBrush(glow))
    painter.drawEllipse(QRectF(cx-r*1.6, cy-r*1.6, r*3.2, r*3.2))
    painter.setBrush(Qt.BrushStyle.NoBrush)
    for scale, color, thickness in (
        (1.17, QColor(160, 200, 230, 42), 2),
        (1.00, QColor(150, 196, 225, 75), 6),
        (.79, QColor(124, 186, 224, 140), 7),
        (.68, QColor(218, 244, 255, min(255, int(210 + amplitude * 45))), 6),
        (.60, QColor(106, 178, 227, 155), 2),
    ):
        painter.setPen(QPen(color, thickness))
        rr = r * scale
        painter.drawEllipse(QRectF(cx-rr, cy-rr, rr*2, rr*2))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QBrush(qcol(C.DESKTOP_PANEL)))
    inner = r * .54
    painter.drawEllipse(QRectF(cx-inner, cy-inner, inner*2, inner*2))
