"""Font-independent icons for the image editor's available operations."""
from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap

from ui.theme import C


def image_tool_icon(kind):
    pixmap = QPixmap(48, 48)
    pixmap.setDevicePixelRatio(2)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    pen = QPen(QColor(C.DESKTOP_TEXT))
    pen.setWidthF(1.5)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)
    path = QPainterPath()
    if kind == "rotate":
        path.arcMoveTo(QRectF(4, 4, 16, 16), 35)
        path.arcTo(QRectF(4, 4, 16, 16), 35, 260)
        path.moveTo(17, 3)
        path.lineTo(20, 6)
        path.lineTo(16, 7)
    elif kind == "flip":
        path.moveTo(12, 3)
        path.lineTo(12, 21)
        path.moveTo(9, 5)
        path.lineTo(3, 19)
        path.lineTo(9, 19)
        path.closeSubpath()
        path.moveTo(15, 5)
        path.lineTo(21, 19)
        path.lineTo(15, 19)
        path.closeSubpath()
    elif kind == "grayscale":
        path.addEllipse(QRectF(4, 4, 16, 16))
        path.moveTo(12, 4)
        path.lineTo(12, 20)
        path.moveTo(12, 8)
        path.lineTo(18, 8)
        path.moveTo(12, 12)
        path.lineTo(20, 12)
        path.moveTo(12, 16)
        path.lineTo(18, 16)
    elif kind == "crop":
        path.moveTo(7, 3)
        path.lineTo(7, 17)
        path.lineTo(21, 17)
        path.moveTo(3, 7)
        path.lineTo(17, 7)
        path.lineTo(17, 21)
    elif kind == "text":
        path.moveTo(4, 6)
        path.lineTo(20, 6)
        path.moveTo(12, 6)
        path.lineTo(12, 20)
        path.moveTo(8, 20)
        path.lineTo(16, 20)
    else:
        raise ValueError(f"Unknown image tool: {kind}")
    painter.drawPath(path)
    painter.end()
    return QIcon(pixmap)
