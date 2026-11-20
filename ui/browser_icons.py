"""High-DPI vector icons for the browser's real navigation controls."""
from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap

from ui.theme import C


def browser_nav_icon(kind):
    pixmap = QPixmap(48, 48)
    pixmap.setDevicePixelRatio(2)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(C.DESKTOP_TEXT))
    pen.setWidthF(1.7)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    path = QPainterPath()
    if kind in ('back', 'forward'):
        start, end = (19, 5) if kind == 'back' else (5, 19)
        head = 10 if kind == 'back' else 14
        path.moveTo(start, 12)
        path.lineTo(end, 12)
        path.moveTo(head, 7)
        path.lineTo(end, 12)
        path.lineTo(head, 17)
    elif kind == 'close':
        path.moveTo(7, 7)
        path.lineTo(17, 17)
        path.moveTo(17, 7)
        path.lineTo(7, 17)
    elif kind == 'reload':
        path.arcMoveTo(QRectF(4, 4, 16, 16), 40)
        path.arcTo(QRectF(4, 4, 16, 16), 40, 280)
        path.moveTo(18, 2)
        path.lineTo(18, 7)
        path.lineTo(13, 7)
    else:
        raise ValueError('Unknown navigation icon')
    painter.drawPath(path)
    painter.end()
    return QIcon(pixmap)
