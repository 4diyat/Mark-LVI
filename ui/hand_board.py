"""Native, in-session spatial board; no upstream Barehands code is used."""
import math
from pathlib import Path

from PyQt6.QtCore import QPointF, QRectF, QSize, Qt
from PyQt6.QtGui import QBrush, QColor, QFont, QImageReader, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import (QFileDialog, QGraphicsItem, QGraphicsPixmapItem, QGraphicsRectItem,
                             QGraphicsScene, QGraphicsTextItem, QGraphicsView,
                             QHBoxLayout, QInputDialog, QLabel, QMessageBox, QPushButton, QSlider, QVBoxLayout, QWidget)

from core.i18n import label as _t
from core.obj_wireframe import MAX_OBJ_BYTES, component_directions, parse_obj
from ui.theme import C, workspace_stylesheet

_MAX_ITEMS = 30


class ModelWireframe(QGraphicsItem):
    """A bounded CPU-rendered orthographic OBJ preview, without external assets."""
    def __init__(self, geometry, parent):
        super().__init__(parent)
        self.vertices, self.edges = geometry
        self.directions, self.parts = component_directions(self.vertices, self.edges)
        self.explode = 0.0
        self.yaw = -25.0
        self.pitch = 20.0
        self.setPos(12, 42)
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)

    def boundingRect(self):
        return QRectF(0, 0, 256, 150)

    def paint(self, painter, option, widget=None):
        del option, widget
        yaw, pitch = math.radians(self.yaw), math.radians(self.pitch)
        cy, sy, cp, sp = math.cos(yaw), math.sin(yaw), math.cos(pitch), math.sin(pitch)
        projected = []
        factor = 110 / (1 + self.explode * .65)
        for (x, y, z), (dx, dy, dz) in zip(self.vertices, self.directions):
            x += dx * self.explode * .65
            y += dy * self.explode * .65
            z += dz * self.explode * .65
            x2, z2 = x * cy + z * sy, -x * sy + z * cy
            y2 = y * cp - z2 * sp
            projected.append(QPointF(128 + x2 * factor, 75 - y2 * factor))
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor(C.PRI), 1.2))
        for a, b in self.edges:
            painter.drawLine(projected[a], projected[b])

    def set_explode(self, value):
        self.explode = max(0., min(1., value))
        self.update()

    def set_view(self, yaw, pitch):
        self.yaw = yaw % 360
        self.pitch = max(-85, min(85, pitch))
        self.update()


class Card(QGraphicsRectItem):
    """A movable item; child text/image never intercepts a pinch-drag."""
    def __init__(self, title, text="", pixmap=None, model=None):
        super().__init__(QRectF(0, 0, 280, 205))
        self.title = title[:120]
        self.text = text[:2000]
        self.kind = "model" if model is not None else "image" if pixmap is not None else "note"
        self.model_view = None
        self.setTransformOriginPoint(self.rect().center())
        self.setBrush(QBrush(QColor(C.DESKTOP_DOCK)))
        self.setPen(QPen(QColor(C.DESKTOP_BORDER), 1.5))
        self.setFlag(self.GraphicsItemFlag.ItemClipsChildrenToShape, True)
        self.setFlag(self.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(self.GraphicsItemFlag.ItemIsSelectable, True)
        heading = QGraphicsTextItem(self)
        heading.setPlainText(self.title)
        heading.setDefaultTextColor(QColor(C.DESKTOP_TEXT))
        heading.setFont(QFont("Arial", 11, QFont.Weight.Bold))
        heading.setTextWidth(258)
        heading.setPos(8, 6)
        heading.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        if model is not None:
            self.model_view = ModelWireframe(model, self)
        elif pixmap is not None:
            image = QGraphicsPixmapItem(pixmap, self)
            image.setPos(12, 40)
            image.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        else:
            body = QGraphicsTextItem(self)
            body.setPlainText(self.text[:160] + ("…" if len(self.text) > 160 else ""))
            body.setDefaultTextColor(QColor(C.DESKTOP_TEXT))
            body.setFont(QFont("Arial", 9))
            body.setTextWidth(258)
            body.setPos(8, 40)
            body.setAcceptedMouseButtons(Qt.MouseButton.NoButton)


class BoardView(QGraphicsView):
    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.fitInView(self.scene().sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)


class HandBoard(QWidget):
    """In-session board; cards support mouse and workspace hand gestures."""
    def __init__(self, host):
        super().__init__()
        self._host = host
        self._items = []
        self.setObjectName("HandBoard")
        self.setStyleSheet(workspace_stylesheet() +
                           f"QWidget#HandBoard {{ background: {C.DESKTOP_PANEL}; color: {C.DESKTOP_TEXT}; }}")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        top = QHBoxLayout()
        note_button = QPushButton(_t("handboard.add_note"))
        note_button.clicked.connect(self._new_note)
        top.addWidget(note_button)
        image_button = QPushButton(_t("handboard.add_image"))
        image_button.clicked.connect(self._new_image)
        top.addWidget(image_button)
        model_button = QPushButton(_t("handboard.add_model"))
        model_button.clicked.connect(self._new_model)
        top.addWidget(model_button)
        remove_button = QPushButton(_t("handboard.remove"))
        remove_button.clicked.connect(self._remove_selected)
        top.addWidget(remove_button)
        top.addStretch(1)
        layout.addLayout(top)
        self._status = QLabel(_t("handboard.instructions"))
        self._status.setWordWrap(True)
        layout.addWidget(self._status)
        self._feedback = QLabel("")
        self._feedback.setWordWrap(True)
        layout.addWidget(self._feedback)
        self.scene = QGraphicsScene(self)
        self.scene.setSceneRect(0, 0, 1200, 700)
        self.scene.setBackgroundBrush(QBrush(QColor(C.DESKTOP_BAR)))
        self.view = BoardView(self.scene)
        self.view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.view.setStyleSheet(f"border: 1px solid {C.DESKTOP_BORDER}; border-radius: 8px;")
        layout.addWidget(self.view, 1)
        explode_row = QHBoxLayout()
        explode_row.addWidget(QLabel(_t("handboard.explode")))
        self._explode = QSlider(Qt.Orientation.Horizontal)
        self._explode.setRange(0, 100)
        self._explode.setEnabled(False)
        self._explode.setToolTip(_t("handboard.explode_help"))
        self._explode.valueChanged.connect(self._set_explode)
        explode_row.addWidget(self._explode, 1)
        layout.addLayout(explode_row)
        self.scene.selectionChanged.connect(self._sync_explode)

    def _selected_model(self):
        selected = [item for item in self.scene.selectedItems() if item in self._items]
        return selected[0].model_view if len(selected) == 1 else None

    def _sync_explode(self):
        model = self._selected_model()
        self._explode.setEnabled(model is not None and model.parts > 1)
        self._explode.blockSignals(True)
        self._explode.setValue(round(model.explode * 100) if model is not None else 0)
        self._explode.blockSignals(False)

    def _set_explode(self, value):
        model = self._selected_model()
        if model is not None and model.parts > 1:
            model.set_explode(value / 100)

    def _put(self, item):
        if len(self._items) >= _MAX_ITEMS:
            return False
        self.scene.addItem(item)
        index = len(self._items)
        item.setPos(30 + (index % 4) * 290, 30 + ((index // 4) % 3) * 220)
        self._items.append(item)
        return True

    def add_note(self, title, text):
        if not isinstance(title, str) or not title.strip() or len(title) > 120:
            return False
        if not isinstance(text, str) or len(text) > 2000:
            return False
        return self._put(Card(title.strip(), text))

    def add_model(self, title, geometry):
        if not isinstance(title, str) or not title.strip() or len(title) > 120:
            return False
        return self._put(Card(title.strip(), model=geometry))

    def items_snapshot(self):
        result = []
        for item in self._items:
            entry = {"kind": item.kind, "title": item.title, "text": item.text,
                     "x": round(item.pos().x()), "y": round(item.pos().y()),
                     "scale": round(item.scale(), 2), "rotation": round(item.rotation(), 1)}
            if item.model_view is not None:
                entry.update(yaw=round(item.model_view.yaw, 1), pitch=round(item.model_view.pitch, 1),
                             explode=round(item.model_view.explode, 2), parts=item.model_view.parts)
            result.append(entry)
        return result

    def _pause_for_dialog(self):
        # File and text dialogs require physical confirmation, not gestures.
        self._host._hand_controller.stop()

    def _new_note(self):
        self._pause_for_dialog()
        title, ok = QInputDialog.getText(self, _t("handboard.add_note"), _t("handboard.note_title"))
        if not ok or not title.strip():
            return
        text, ok = QInputDialog.getMultiLineText(self, _t("handboard.add_note"), _t("handboard.note_body"))
        if ok and not self.add_note(title, text):
            self._feedback.setText(_t("handboard.limit"))

    def _remove_selected(self):
        selected = [item for item in self.scene.selectedItems() if item in self._items]
        if not selected:
            self._feedback.setText(_t("handboard.select_item"))
            return
        self._pause_for_dialog()
        answer = QMessageBox.question(self, _t("handboard.remove"), _t("handboard.confirm_remove"),
                                      QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                      QMessageBox.StandardButton.No)
        if answer != QMessageBox.StandardButton.Yes:
            return
        for item in selected:
            self.scene.removeItem(item)
            self._items.remove(item)
        self._feedback.setText("")

    def _new_model(self):
        self._pause_for_dialog()
        path, _ = QFileDialog.getOpenFileName(self, _t("handboard.add_model"), "", "Wavefront OBJ (*.obj)")
        if not path:
            return
        try:
            source = Path(path)
            if not source.is_file():
                raise ValueError("not a file")
            with source.open("rb") as stream:
                geometry = parse_obj(stream.read(MAX_OBJ_BYTES + 1))
            if not self.add_model(source.name, geometry):
                raise ValueError("board is full")
            self._feedback.setText("")
        except (OSError, ValueError):
            self._feedback.setText(_t("handboard.model_error"))

    def _new_image(self):
        self._pause_for_dialog()
        path, _ = QFileDialog.getOpenFileName(self, _t("handboard.add_image"), "",
                                              "Images (*.png *.jpg *.jpeg *.webp *.bmp)")
        if not path:
            return
        try:
            source = Path(path)
            if not source.is_file() or source.stat().st_size > 10 * 1024 * 1024:
                raise ValueError("image too large")
            reader = QImageReader(str(source))
            dimensions = reader.size()
            if not dimensions.isValid() or dimensions.width() > 8192 or dimensions.height() > 8192:
                raise ValueError("invalid image dimensions")
            reader.setAutoTransform(True)
            dimensions.scale(QSize(256, 150), Qt.AspectRatioMode.KeepAspectRatio)
            reader.setScaledSize(dimensions)
            image = reader.read()
            if image.isNull() or not self._put(Card(source.name, pixmap=QPixmap.fromImage(image))):
                raise ValueError("could not add image")
        except (OSError, ValueError):
            self._feedback.setText(_t("handboard.image_error"))
