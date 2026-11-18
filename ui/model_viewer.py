"""Local OBJ wireframe viewer, independent of hand tracking and spatial boards."""
import math
from pathlib import Path

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import QFileDialog, QHBoxLayout, QLabel, QPushButton, QSlider, QVBoxLayout, QWidget

from core.i18n import label as _t
from core.obj_wireframe import MAX_OBJ_BYTES, component_directions, parse_obj
from ui.theme import C, workspace_stylesheet


class ModelCanvas(QWidget):
    """Bounded orthographic wireframe renderer, without textures or external files."""
    def __init__(self):
        super().__init__()
        self.vertices, self.edges, self.directions = (), (), ()
        self.parts = 0
        self.yaw, self.pitch, self.explode = -25., 20., 0.
        self.setMinimumSize(240, 180)
        self.setAccessibleName(_t('model.canvas'))

    def set_geometry(self, geometry):
        self.vertices, self.edges = geometry
        self.directions, self.parts = component_directions(self.vertices, self.edges)
        self.update()

    def paintEvent(self, event):
        del event
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor(C.DESKTOP_BAR))
        yaw, pitch = math.radians(self.yaw), math.radians(self.pitch)
        cy, sy, cp, sp = math.cos(yaw), math.sin(yaw), math.cos(pitch), math.sin(pitch)
        factor = min(self.width(), self.height()) * .7 / (1 + self.explode * .65)
        projected = []
        for (x, y, z), (dx, dy, dz) in zip(self.vertices, self.directions):
            x += dx * self.explode * .65
            y += dy * self.explode * .65
            z += dz * self.explode * .65
            x2, z2 = x * cy + z * sy, -x * sy + z * cy
            y2 = y * cp - z2 * sp
            projected.append(QPointF(self.width() / 2 + x2 * factor, self.height() / 2 - y2 * factor))
        pen = QPen(QColor(C.PRI))
        pen.setWidthF(1.5)
        painter.setPen(pen)
        for a, b in self.edges:
            painter.drawLine(projected[a], projected[b])
        painter.end()


class ModelViewer(QWidget):
    """User-selected OBJ files only; no camera starts when opening the viewer."""
    def __init__(self, host):
        super().__init__()
        self._host = host
        self.setObjectName('ModelViewer')
        self.setStyleSheet(workspace_stylesheet())
        layout = QVBoxLayout(self)
        self.open_button = QPushButton(_t('model.open'))
        self.open_button.clicked.connect(self.open_file)
        layout.addWidget(self.open_button)
        self._status_key, self._model_name = 'model.instructions', ''
        self.status = QLabel(_t(self._status_key))
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.canvas = ModelCanvas()
        layout.addWidget(self.canvas, 1)
        self._labels = []
        for key, minimum, maximum, initial, handler in (
                ('model.yaw', -180, 180, -25, self._yaw),
                ('model.pitch', -85, 85, 20, self._pitch),
                ('model.explode', 0, 100, 0, self._explode)):
            row = QHBoxLayout()
            label = QLabel(_t(key))
            row.addWidget(label)
            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setAccessibleName(_t(key))
            slider.setRange(minimum, maximum)
            slider.setValue(initial)
            slider.valueChanged.connect(handler)
            row.addWidget(slider, 1)
            layout.addLayout(row)
            self._labels.append((label, slider, key))
        self.explode_slider = self._labels[-1][1]
        self.explode_slider.setEnabled(False)

    def _yaw(self, value):
        self.canvas.yaw = value
        self.canvas.update()

    def _pitch(self, value):
        self.canvas.pitch = value
        self.canvas.update()

    def _explode(self, value):
        self.canvas.explode = value / 100
        self.canvas.update()

    def load_file(self, path):
        try:
            source = Path(path)
            if not source.is_file():
                raise ValueError('not a file')
            with source.open('rb') as stream:
                geometry = parse_obj(stream.read(MAX_OBJ_BYTES + 1))
            self.canvas.set_geometry(geometry)
            self.explode_slider.setValue(0)
            self.explode_slider.setEnabled(self.canvas.parts > 1)
            self._status_key, self._model_name = 'model.loaded', source.name
            self.status.setText(_t(self._status_key, name=self._model_name))
            return True
        except (OSError, ValueError):
            self._status_key = 'model.error'
            self.status.setText(_t(self._status_key))
            return False

    def open_file(self):
        controller = getattr(self._host, '_hand_controller', None)
        if controller is not None:
            controller.stop()
        path, _ = QFileDialog.getOpenFileName(self, _t('model.open'), '', 'Wavefront OBJ (*.obj)')
        if path:
            self.load_file(path)

    def retranslate(self):
        self.open_button.setText(_t('model.open'))
        self.canvas.setAccessibleName(_t('model.canvas'))
        self.status.setText(_t(self._status_key, name=self._model_name))
        for label, slider, key in self._labels:
            label.setText(_t(key))
            slider.setAccessibleName(_t(key))
