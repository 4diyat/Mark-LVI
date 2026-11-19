"""A small local image editor; AI suggestions never open or save files."""
from PyQt6.QtCore import QSize, Qt
from PyQt6.QtGui import QColor, QFont, QImage, QImageReader, QPainter, QPixmap, QTransform
from PyQt6.QtWidgets import (QDialog, QDialogButtonBox, QFileDialog, QFormLayout,
                             QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
                             QMessageBox, QPushButton, QScrollArea, QSlider, QSpinBox, QToolButton, QVBoxLayout, QWidget)

from core.i18n import label as _t
from core.image_geometry import preview_size, valid_crop
from core.image_layers import make_text_layer, set_visible
from ui.theme import workspace_stylesheet
from ui.localization import TranslationBindings
from ui.image_tool_icons import image_tool_icon
from ui.image_canvas import ImageCanvas


class ImageEditor(QDialog):
    def __init__(self, host, request):
        super().__init__(host)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self._translations = TranslationBindings()
        self._translations.title(self, "image_editor.title")
        self.resize(900, 680)
        self.setStyleSheet(workspace_stylesheet())
        self._image = None
        self._layers = []
        self._undo_state = None
        self._dirty = False
        self._source = ""
        layout = QVBoxLayout(self)
        # File actions stay above the canvas; image operations live beside it.
        toolbar_widget = QWidget()
        toolbar = QHBoxLayout(toolbar_widget)
        toolbar.setContentsMargins(0, 0, 0, 0)
        toolbar.addWidget(self._translations.text(QLabel(), "image_editor.zoom"))
        self._zoom = QSlider(Qt.Orientation.Horizontal)
        self._zoom.setRange(25, 200)
        self._zoom.setSingleStep(10)
        self._zoom.setPageStep(25)
        self._zoom.setValue(100)
        self._zoom.setFixedWidth(120)
        self._zoom.setAccessibleName(_t("image_editor.zoom"))
        self._zoom.setToolTip(_t("image_editor.zoom_hint"))
        toolbar.addWidget(self._zoom)
        self._zoom_value = QLabel()
        self._zoom_value.setText("100%")
        toolbar.addWidget(self._zoom_value)
        self._file_tools = {}
        for key, callback in (("image_editor.open", self.open_file),
                              ("image_editor.undo", self.undo),
                              ("image_editor.save_as", self.save_as)):
            button = self._translations.text(QPushButton(), key)
            if key == "image_editor.save_as":
                button.setObjectName("WorkspacePrimary")
            button.clicked.connect(callback)
            toolbar.addWidget(button)
            self._file_tools[key] = button
        toolbar.addStretch()
        toolbar_scroll = QScrollArea()
        toolbar_scroll.setWidgetResizable(True)
        toolbar_scroll.setWidget(toolbar_widget)
        toolbar_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        toolbar_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        toolbar_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        toolbar_scroll.setFixedHeight(58)
        layout.addWidget(toolbar_scroll)
        self._status = self._translations.text(QLabel(), "image_editor.empty", conditional=True)
        self._status.setTextFormat(Qt.TextFormat.PlainText)
        self._status.setWordWrap(True)
        layout.addWidget(self._status)
        self._preview = ImageCanvas()
        self._preview.selection_changed.connect(self._selection_changed)
        self._preview.setAccessibleName(_t("image_editor.title"))
        self._preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._preview.setMinimumSize(200, 150)
        scroll = QScrollArea()
        self._canvas_scroll = scroll
        scroll.setWidgetResizable(True)
        scroll.setWidget(self._preview)
        workspace = QHBoxLayout()
        tool_panel = QWidget()
        tool_layout = QVBoxLayout(tool_panel)
        tool_layout.setContentsMargins(0, 0, 0, 0)
        self._image_tools = {}
        for icon, key, callback in (("select", "image_editor.select", self._toggle_selection),
                                    ("rotate", "image_editor.rotate", self.rotate),
                                    ("flip", "image_editor.flip", self.flip),
                                    ("grayscale", "image_editor.grayscale", self.grayscale),
                                    ("crop", "image_editor.crop", self.crop),
                                    ("text", "image_editor.add_text", self.add_text)):
            button = QToolButton()
            button.setIcon(image_tool_icon(icon))
            if icon == "select":
                button.setCheckable(True)
            button.setIconSize(QSize(22, 22))
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
            button.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            button.setToolTip(_t(key))
            button.setAccessibleName(_t(key))
            button.setFixedSize(40, 40)
            button.clicked.connect(lambda _checked=False, fn=callback: fn())
            tool_layout.addWidget(button)
            self._image_tools[key] = button
        tool_layout.addStretch()
        tool_scroll = QScrollArea()
        tool_scroll.setWidgetResizable(True)
        tool_scroll.setWidget(tool_panel)
        tool_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        tool_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        tool_scroll.setFixedWidth(60)
        self._tool_scroll = tool_scroll
        workspace.addWidget(tool_scroll)
        workspace.addWidget(scroll, 1)
        layers_panel = QWidget()
        layers_panel.setMaximumWidth(220)
        layers_layout = QVBoxLayout(layers_panel)
        layers_layout.addWidget(self._translations.text(QLabel(), "image_editor.layers"))
        layers_layout.addWidget(self._translations.text(QLabel(), "image_editor.background"))
        self._layer_list = QListWidget()
        self._layer_list.setAccessibleName(_t("image_editor.layers"))
        self._layer_list.itemChanged.connect(self._toggle_layer)
        layers_layout.addWidget(self._layer_list, 1)
        remove = self._translations.text(QPushButton(), "image_editor.remove_layer")
        remove.clicked.connect(self.remove_layer)
        layers_layout.addWidget(remove)
        workspace.addWidget(layers_panel)
        layout.addLayout(workspace, 1)
        self._zoom.valueChanged.connect(self._zoom_changed)
        suggestion = request.get("suggestion", "")
        if suggestion in ("rotate", "flip", "grayscale", "crop", "add_text"):
            row = QHBoxLayout()
            label = QLabel(_t("image_editor.suggestion", operation=_t("image_editor." + suggestion)))
            label.setWordWrap(True)
            row.addWidget(label, 1)
            apply = self._translations.text(QPushButton(), "image_editor.apply")
            apply.clicked.connect({"rotate": self.rotate, "flip": self.flip,
                                   "grayscale": self.grayscale, "crop": self.crop,
                                   "add_text": lambda: self.add_text(str(request.get("text") or "")[:500])}[suggestion])
            row.addWidget(apply)
            layout.addLayout(row)

    def retranslate(self):
        self._translations.refresh()
        self._preview.setAccessibleName(_t("image_editor.title"))
        self._layer_list.setAccessibleName(_t("image_editor.layers"))
        self._zoom.setAccessibleName(_t("image_editor.zoom"))
        self._zoom.setToolTip(_t("image_editor.zoom_hint"))
        for key, button in self._image_tools.items():
            button.setToolTip(_t(key))
            button.setAccessibleName(_t(key))

    def _toggle_selection(self):
        enabled = self._image_tools["image_editor.select"].isChecked()
        self._preview.set_selecting(enabled)
        if enabled:
            self._status.setText(_t("image_editor.select_hint") if self._image is not None
                                 else _t("image_editor.empty"))

    def _selection_changed(self, selection):
        self._status.setText(_t("image_editor.selected", width=selection[2], height=selection[3]))

    def _may_discard(self):
        return not self._dirty or QMessageBox.question(
            self, _t("image_editor.title"), _t("image_editor.discard"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes

    def open_file(self):
        if not self._may_discard():
            return
        path, _ = QFileDialog.getOpenFileName(self, _t("image_editor.open"), "",
                                              "Images (*.png *.jpg *.jpeg *.bmp *.webp);;All files (*)")
        if not path:
            return
        reader = QImageReader(path)
        reader.setAutoTransform(True)
        size = reader.size()
        # Avoid creating giant in-memory images before decoding untrusted files.
        if not size.isValid() or size.width() * size.height() > 40_000_000:
            self._status.setText(_t("image_editor.too_large"))
            return
        image = reader.read()
        if image.isNull():
            self._status.setText(_t("image_editor.read_error"))
            return
        self._preview.clear_selection()
        self._image, self._undo_state, self._source, self._dirty = image, None, path, False
        self._layers = []
        self._update_layers()
        self._status.setText(path)
        self._render()

    def save_as(self):
        if self._image is None:
            return
        if self._layers and QMessageBox.question(
                self, _t("image_editor.title"), _t("image_editor.save_flatten_warning"),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
        path, _ = QFileDialog.getSaveFileName(self, _t("image_editor.save_as"), "edited.png",
                                              "PNG (*.png);;JPEG (*.jpg *.jpeg);;BMP (*.bmp)")
        if not path:
            return
        if not self._composite().save(path):
            self._status.setText(_t("image_editor.save_error"))
            return
        self._source, self._dirty = path, False
        self._status.setText(_t("image_editor.saved", path=path))

    def _snapshot(self):
        self._undo_state = (self._image, tuple(self._layers))

    def _change(self, image):
        if self._image is None:
            self._status.setText(_t("image_editor.empty"))
            return
        # Image-wide transforms apply to the whole visible composition. Hidden
        # layers are also removed; warn before changing anything. Undo restores.
        if self._layers and QMessageBox.question(
                self, _t("image_editor.title"), _t("image_editor.flatten_warning"),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
        had_layers = bool(self._layers)
        self._snapshot()
        self._preview.clear_selection()
        self._image, self._layers = image, []
        self._dirty = True
        self._update_layers()
        self._status.setText(_t("image_editor.flattened" if had_layers else "image_editor.unsaved"))
        self._render()

    def rotate(self):
        if self._image is not None:
            self._change(self._composite().transformed(QTransform().rotate(90)))

    def flip(self):
        if self._image is not None:
            self._change(self._composite().mirrored(True, False))

    def grayscale(self):
        if self._image is not None:
            original = self._composite()
            image = original.convertToFormat(QImage.Format.Format_Grayscale8).convertToFormat(
                QImage.Format.Format_ARGB32)
            painter = QPainter(image)
            painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
            painter.drawImage(0, 0, original)
            painter.end()
            self._change(image)

    def crop(self):
        if self._image is None:
            self._status.setText(_t("image_editor.empty"))
            return
        width, height = self._image.width(), self._image.height()
        x, y, selected_width, selected_height = self._preview.selection or (0, 0, width, height)
        dialog = QDialog(self)
        dialog.setWindowTitle(_t("image_editor.crop"))
        form = QFormLayout(dialog)
        controls = []
        for key, minimum, maximum, value in (
            ("image_editor.crop_x", 0, width - 1, x),
            ("image_editor.crop_y", 0, height - 1, y),
            ("image_editor.crop_width", 1, width, selected_width),
            ("image_editor.crop_height", 1, height, selected_height),
        ):
            control = QSpinBox()
            control.setRange(minimum, maximum)
            control.setValue(value)
            form.addRow(_t(key), control)
            controls.append(control)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        x, y, crop_width, crop_height = (control.value() for control in controls)
        if not valid_crop(width, height, x, y, crop_width, crop_height):
            self._status.setText(_t("image_editor.crop_invalid"))
            return
        self._change(self._composite().copy(x, y, crop_width, crop_height))

    def _paint_layers(self, painter):
        painter.setPen(QColor("white"))
        for layer in self._layers:
            if layer.visible:
                font = QFont("Courier New")
                font.setPixelSize(layer.size)
                painter.setFont(font)
                painter.drawText(layer.x, layer.y, layer.text)

    def _composite(self):
        if not any(layer.visible for layer in self._layers):
            return self._image
        result = self._image.convertToFormat(QImage.Format.Format_ARGB32)
        # Detach even if the original already has this format.
        result = result.copy()
        painter = QPainter(result)
        self._paint_layers(painter)
        painter.end()
        return result

    def _update_layers(self):
        self._layer_list.blockSignals(True)
        try:
            self._layer_list.clear()
            for layer in self._layers:
                item = QListWidgetItem(layer.text[:60])
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Checked if layer.visible else Qt.CheckState.Unchecked)
                self._layer_list.addItem(item)
        finally:
            self._layer_list.blockSignals(False)

    def add_text(self, initial=""):
        if self._image is None:
            self._status.setText(_t("image_editor.empty"))
            return
        dialog = QDialog(self)
        dialog.setWindowTitle(_t("image_editor.add_text"))
        form = QFormLayout(dialog)
        text = QLineEdit(initial)
        text.setMaxLength(500)
        form.addRow(_t("image_editor.text"), text)
        controls = []
        for key, minimum, maximum, value in (
            ("image_editor.crop_x", 0, self._image.width() - 1, 0),
            ("image_editor.baseline", 0, self._image.height() - 1, min(40, self._image.height() - 1)),
            ("image_editor.font_size", 1, 500, 32),
        ):
            control = QSpinBox()
            control.setRange(minimum, maximum)
            control.setValue(value)
            form.addRow(_t(key), control)
            controls.append(control)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            layer = make_text_layer(text.text(), *(control.value() for control in controls),
                                    self._image.width(), self._image.height())
        except ValueError:
            self._status.setText(_t("image_editor.invalid_text"))
            return
        self._snapshot()
        self._layers.append(layer)
        self._dirty = True
        self._update_layers()
        self._status.setText(_t("image_editor.unsaved"))
        self._render()

    def _toggle_layer(self, item):
        row = self._layer_list.row(item)
        if not 0 <= row < len(self._layers):
            return
        visible = item.checkState() == Qt.CheckState.Checked
        if self._layers[row].visible == visible:
            return
        self._snapshot()
        self._layers[row] = set_visible(self._layers[row], visible)
        self._dirty = True
        self._status.setText(_t("image_editor.unsaved"))
        self._render()

    def remove_layer(self):
        row = self._layer_list.currentRow()
        if not 0 <= row < len(self._layers):
            return
        self._snapshot()
        del self._layers[row]
        self._dirty = True
        self._update_layers()
        self._status.setText(_t("image_editor.unsaved"))
        self._render()

    def undo(self):
        if self._undo_state is not None:
            self._preview.clear_selection()
            self._image, layers = self._undo_state
            self._layers, self._undo_state = list(layers), None
            self._dirty = True
            self._update_layers()
            self._status.setText(_t("image_editor.unsaved"))
            self._render()

    def _zoom_changed(self, value):
        self._zoom_value.setText(f"{value}%")
        self._render()

    def _render(self):
        if self._image is not None:
            # Use the scrollbar-free maximum viewport so scrolling does not
            # continually change the fitted size when scrollbars appear.
            viewport = self._canvas_scroll.maximumViewportSize()
            width, height = preview_size(self._image.width(), self._image.height(),
                                         viewport.width(), viewport.height(), self._zoom.value())
            pixmap = QPixmap.fromImage(self._image).scaled(
                width, height, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation)
            painter = QPainter(pixmap)
            painter.scale(pixmap.width() / self._image.width(), pixmap.height() / self._image.height())
            self._paint_layers(painter)
            painter.end()
            self._preview.image_size = (self._image.width(), self._image.height())
            self._preview.setMinimumSize(max(200, pixmap.width()), max(150, pixmap.height()))
            self._preview.setPixmap(pixmap)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._render()

    def closeEvent(self, event):
        if self._may_discard():
            event.accept()
        else:
            event.ignore()


def open_editor(window, request):
    dialog = ImageEditor(window, request)
    if not hasattr(window, "_image_editors"):
        window._image_editors = set()
    window._image_editors.add(dialog)
    dialog.destroyed.connect(lambda: window._image_editors.discard(dialog))
    from ui.desktop_workspace import show_document
    show_document(window, dialog, "image_editor")
