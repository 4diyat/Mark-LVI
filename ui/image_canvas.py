"""Image preview with a non-destructive, image-coordinate crop selection."""
from PyQt6.QtCore import QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import QLabel

from core.image_geometry import selection_from_points


class ImageCanvas(QLabel):
    selection_changed = pyqtSignal(object)
    brush_stroke = pyqtSignal(object)

    def __init__(self):
        super().__init__()
        self.selection = None
        self.image_size = (0, 0)
        self.selecting = False
        self.brushing = False
        self.brush_color = QColor("#4b9fff")
        self.brush_size = 8
        self._stroke = []
        self._start = None
        self._end = None

    def set_selecting(self, enabled):
        self.selecting = enabled
        self.brushing = False
        self._stroke = []
        self._start = self._end = None
        self.setCursor(Qt.CursorShape.CrossCursor if enabled else Qt.CursorShape.ArrowCursor)
        self.update()

    def set_brushing(self, enabled):
        self.brushing = enabled
        self.selecting = False
        self._stroke = []
        self._start = self._end = None
        self.setCursor(Qt.CursorShape.CrossCursor if enabled else Qt.CursorShape.ArrowCursor)
        self.update()

    def _brush_point(self, position):
        rect = self._image_rect()
        width, height = self.image_size
        if rect.isEmpty() or width <= 0 or height <= 0:
            return None
        x = max(0.0, min(width - 1.0, (position.x() - rect.left()) * width / rect.width()))
        y = max(0.0, min(height - 1.0, (position.y() - rect.top()) * height / rect.height()))
        return x, y

    def _append_brush_point(self, position):
        point = self._brush_point(position)
        if point is not None and (not self._stroke or point != self._stroke[-1]):
            # Bound memory for a very long drag while retaining its endpoint.
            if len(self._stroke) >= 8192:
                self._stroke[-1] = point
            else:
                self._stroke.append(point)
        self.update()

    def clear_selection(self):
        self.selection = None
        self._stroke = []
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
        if self.brushing and event.button() == Qt.MouseButton.LeftButton:
            if self._image_rect().contains(event.position()):
                self._stroke = []
                self._append_brush_point(event.position())
            event.accept()
            return
        if self.selecting and event.button() == Qt.MouseButton.LeftButton:
            pos = event.position()
            if self._image_rect().contains(pos):
                self._start = self._end = pos
                self.update()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.brushing and self._stroke:
            self._append_brush_point(event.position())
            event.accept()
            return
        if self._start is not None:
            self._end = event.position()
            self.update()
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.brushing and self._stroke and event.button() == Qt.MouseButton.LeftButton:
            self._append_brush_point(event.position())
            stroke, self._stroke = self._stroke, []
            self.brush_stroke.emit(stroke)
            self.update()
            event.accept()
            return
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
        if self._stroke and min(self.image_size) > 0:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setClipRect(rect)
            painter.translate(rect.left(), rect.top())
            painter.scale(rect.width() / self.image_size[0], rect.height() / self.image_size[1])
            pen = QPen(self.brush_color, self.brush_size, Qt.PenStyle.SolidLine,
                       Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            path = QPainterPath(QPointF(*self._stroke[0]))
            if len(self._stroke) == 1:
                painter.drawPoint(QPointF(*self._stroke[0]))
            else:
                for point in self._stroke[1:]:
                    path.lineTo(QPointF(*point))
                painter.drawPath(path)
            painter.end()
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
