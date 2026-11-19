"""Image preview with a non-destructive, image-coordinate crop selection."""
from PyQt6.QtCore import QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import QLabel

from core.image_geometry import selection_from_points


class ImageCanvas(QLabel):
    selection_changed = pyqtSignal(object)

    def __init__(self):
        super().__init__()
        self.selection = None
        self.image_size = (0, 0)
        self.selecting = False
        self._start = None
        self._end = None

    def set_selecting(self, enabled):
        self.selecting = enabled
        self._start = self._end = None
        self.setCursor(Qt.CursorShape.CrossCursor if enabled else Qt.CursorShape.ArrowCursor)
        self.update()

    def clear_selection(self):
        self.selection = None
        self._start = self._end = None
        self.update()

    def _image_rect(self):
        pixmap = self.pixmap()
        if pixmap is None or pixmap.isNull():
            return QRectF()
        width = pixmap.width() / pixmap.devicePixelRatio()
        height = pixmap.height() / pixmap.devicePixelRatio()
        area = self.contentsRect()
        return QRectF(area.x() + (area.width() - width) // 2,
                      area.y() + (area.height() - height) // 2, width, height)

    def mousePressEvent(self, event):
        if self.selecting and event.button() == Qt.MouseButton.LeftButton:
            pos = event.position()
            if self._image_rect().contains(pos):
                self._start = self._end = pos
                self.update()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._start is not None:
            self._end = event.position()
            self.update()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self._start is not None and event.button() == Qt.MouseButton.LeftButton:
            rect = self._image_rect()
            result = selection_from_points(*self.image_size, rect.left(), rect.top(), rect.width(), rect.height(),
                                           (self._start.x(), self._start.y()),
                                           (event.position().x(), event.position().y()))
            self._start = self._end = None
            if result:
                self.selection = result
                self.selection_changed.emit(result)
            self.update()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def paintEvent(self, event):
        super().paintEvent(event)
        rect = self._image_rect()
        if rect.isEmpty():
            return
        overlay = None
        if self._start is not None and self._end is not None:
            overlay = QRectF(self._start, self._end).normalized().intersected(rect)
        elif self.selection and min(self.image_size) > 0:
            x, y, width, height = self.selection
            overlay = QRectF(rect.left() + x * rect.width() / self.image_size[0],
                             rect.top() + y * rect.height() / self.image_size[1],
                             width * rect.width() / self.image_size[0],
                             height * rect.height() / self.image_size[1])
        if overlay and not overlay.isEmpty():
            painter = QPainter(self)
            pen = QPen(QColor("#67b7ff"), 2, Qt.PenStyle.DashLine)
            painter.setPen(pen)
            painter.setBrush(QColor(80, 160, 255, 45))
            painter.drawRect(overlay)
            painter.end()
