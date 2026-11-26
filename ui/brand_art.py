"""Static circular brand art; it is decoration, not a device-status indicator."""
from pathlib import Path

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QImage, QPainter, QPainterPath, QPixmap


def brand_pixmap(size=100):
    image = QImage(str(Path(__file__).resolve().parent.parent / 'assets/workspace/orb-core.png'))
    pix = QPixmap(size, size); pix.fill(Qt.GlobalColor.transparent)
    if image.isNull():
        return pix
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
    path = QPainterPath(); path.addEllipse(QRectF(0, 0, size, size))
    painter.setClipPath(path); painter.drawImage(QRectF(0, 0, size, size), image); painter.end()
    return pix
