"""Native, in-session spatial board; no upstream Barehands code is used."""
from pathlib import Path

from PyQt6.QtCore import QRectF, QSize, Qt, QTimer
from PyQt6.QtGui import QBrush, QColor, QFont, QImageReader, QPainter, QPen, QPixmap
from PyQt6.QtWidgets import (QFileDialog, QGraphicsPixmapItem, QGraphicsRectItem,
                             QGraphicsScene, QGraphicsTextItem, QGraphicsView,
                             QHBoxLayout, QInputDialog, QLabel, QMessageBox, QPushButton, QVBoxLayout, QWidget)

from core.i18n import label as _t
from ui.theme import C

_MAX_ITEMS = 30


class Card(QGraphicsRectItem):
    """A movable item; child text/image never intercepts a pinch-drag."""
    def __init__(self, title, text="", pixmap=None):
        super().__init__(QRectF(0, 0, 280, 205))
        self.title = title[:120]
        self.text = text[:2000]
        self.kind = "image" if pixmap is not None else "note"
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
        if pixmap is not None:
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
    """Mouse or existing opt-in Windows hand pointer can move the real items."""
    def __init__(self, host):
        super().__init__()
        self._host = host
        self._owned_control = False
        self._items = []
        self.setObjectName("HandBoard")
        self.setStyleSheet(f"QWidget#HandBoard {{ background: {C.DESKTOP_PANEL}; color: {C.DESKTOP_TEXT}; }} "
                           f"QLabel {{ color: {C.DESKTOP_TEXT}; }} "
                           f"QPushButton {{ background: {C.DESKTOP_DOCK}; color: {C.DESKTOP_TEXT}; "
                           f"border: 1px solid {C.DESKTOP_BORDER}; border-radius: 6px; padding: 6px; }}")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        top = QHBoxLayout()
        note_button = QPushButton(_t("handboard.add_note"))
        note_button.clicked.connect(self._new_note)
        top.addWidget(note_button)
        image_button = QPushButton(_t("handboard.add_image"))
        image_button.clicked.connect(self._new_image)
        top.addWidget(image_button)
        remove_button = QPushButton(_t("handboard.remove"))
        remove_button.clicked.connect(self._remove_selected)
        top.addWidget(remove_button)
        top.addStretch(1)
        self._hand_button = QPushButton(_t("handboard.start_hand"))
        self._hand_button.clicked.connect(self._toggle_hand)
        top.addWidget(self._hand_button)
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
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._refresh_hand)
        self._timer.start(300)

    def _refresh_hand(self):
        ctl = getattr(self._host, "_hand_controller", None)
        active = bool(ctl and ctl.thread and ctl.thread.is_alive() and not ctl._stop.is_set())
        if not active and (not ctl or not ctl.thread or not ctl.thread.is_alive()):
            self._owned_control = False
        self._hand_button.setText(_t("handboard.stop_hand" if active else "handboard.start_hand"))
        self._status.setText(_t("handboard.instructions") + "\n" +
                             (getattr(self._host, "_hand_status", None).text()
                              if getattr(self._host, "_hand_status", None) else _t("gesture.off")))

    def _toggle_hand(self):
        ctl = self._host._hand_controller
        was_running = bool(ctl.thread and ctl.thread.is_alive() and not ctl._stop.is_set())
        self._host._hand_toggle()
        if was_running:
            self._owned_control = False
        elif ctl.thread and ctl.thread.is_alive() and not ctl._stop.is_set():
            self._owned_control = True
        self._refresh_hand()

    def stop_owned_control(self):
        if self._owned_control:
            self._host._hand_controller.stop()
            self._owned_control = False

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

    def items_snapshot(self):
        return [{"kind": item.kind, "title": item.title, "text": item.text,
                 "x": round(item.pos().x()), "y": round(item.pos().y())} for item in self._items]

    def _pause_for_dialog(self):
        # File and text dialogs require physical confirmation, not gestures.
        self._host._hand_controller.stop()
        self._owned_control = False
        self._refresh_hand()

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
