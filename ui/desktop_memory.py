"""Memory page: the existing store and guarded single-entry deletion."""
import threading

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QMessageBox, QPushButton, QVBoxLayout, QWidget

from ui.hud_icons import icon
from ui.hud_pages import heading, tr
from ui.tray_panel_model import _t


class MemoryCard(QFrame):
    def __init__(self, workspace, row):
        super().__init__()
        self.workspace = workspace
        self.row = dict(row)
        self.setObjectName('memoryCard')
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(10)
        top = QHBoxLayout()
        kind = str(row.get('category') or '')
        symbols = {'identity': 'circle-dot', 'preferences': 'sparkles', 'projects': 'layout-grid',
                   'relationships': 'message-circle', 'wishes': 'zap', 'notes': 'file-text'}
        glyph = QLabel()
        glyph.setObjectName('workspaceIcon')
        glyph.setFixedSize(44, 44)
        glyph.setAlignment(Qt.AlignmentFlag.AlignCenter)
        glyph.setPixmap(icon(symbols.get(kind, 'brain'), '#73c1ff', 23).pixmap(QSize(23, 23)))
        top.addWidget(glyph)
        names = {'identity': tr('Identitas', 'Identity'), 'preferences': tr('Preferensi', 'Preferences'),
                 'projects': tr('Proyek', 'Projects'), 'relationships': tr('Hubungan', 'Relationships'),
                 'wishes': tr('Keinginan', 'Wishes'), 'notes': tr('Catatan', 'Notes')}
        category = QLabel(names.get(kind, kind))
        category.setObjectName('memoryCategory')
        category.setTextFormat(Qt.TextFormat.PlainText)
        top.addWidget(category)
        self.value = QLabel(str(row.get('value') or ''))
        self.value.setTextFormat(Qt.TextFormat.PlainText)
        self.value.setWordWrap(True)
        self.value.setObjectName('memoryValue')
        top.addWidget(self.value, 1)
        date = QLabel(str(row.get('updated') or _t('ui.workspace.unknown')))
        date.setObjectName('muted')
        date.setTextFormat(Qt.TextFormat.PlainText)
        top.addWidget(date)
        self.expand = QPushButton()
        self.expand.setIcon(icon('chevron-down', '#a8d9ff', 20))
        self.expand.setIconSize(QSize(20, 20))
        self.expand.setObjectName('expand')
        self.expand.setAccessibleName(_t('ui.workspace.expand', field_name=str(row.get('key') or '')))
        self.expand.clicked.connect(self.toggle)
        top.addWidget(self.expand)
        layout.addLayout(top)
        self.details = QLabel('')
        self.details.setObjectName('memoryDetails')
        self.details.setTextFormat(Qt.TextFormat.PlainText)
        self.details.setWordWrap(True)
        self.details.setText(_t('ui.workspace.memory_details',
                                field_name=str(row.get('key') or ''),
                                value=str(row.get('value') or ''),
                                updated=str(row.get('updated') or _t('ui.workspace.unknown')),
                                unknown=_t('ui.workspace.unknown')))
        self.details.hide()
        layout.addWidget(self.details)
        self.delete = QPushButton(_t('ui.workspace.forget_one'))
        self.delete.setObjectName('danger')
        self.delete.setAccessibleName(_t('ui.workspace.forget_named', field_name=str(row.get('key') or '')))
        self.delete.clicked.connect(lambda: workspace.confirm_forget(self.row))
        self.delete.hide()
        layout.addWidget(self.delete, 0, Qt.AlignmentFlag.AlignLeft)

    def toggle(self):
        expanded = self.details.isHidden()
        self.details.setVisible(expanded)
        self.delete.setVisible(expanded)
        self.expand.setIcon(icon('chevron-up' if expanded else 'chevron-down', '#a8d9ff', 20))


class MemoryPage(QWidget):
    def __init__(self, dialog_parent):
        super().__init__()
        self.setObjectName('desktopPage')
        self.dialog_parent = dialog_parent
        self.owner = threading.get_ident()
        self._loading = self._reload = self._busy = False
        self.memory_cards = []
        box = QVBoxLayout(self)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(14)
        header = QHBoxLayout()
        header.addWidget(heading(_t('ui.workspace.memory_title'), 'desktopHeading'), 1)
        self.memory_count = heading(_t('ui.workspace.unknown'), 'workspaceCount')
        header.addWidget(self.memory_count)
        box.addLayout(header)
        description = heading(_t('ui.workspace.memory_description'), 'desktopMuted')
        description.setWordWrap(True)
        box.addWidget(description)
        self.status = heading('', 'workspaceStatus')
        self.status.setWordWrap(True)
        box.addWidget(self.status)
        self.list_layout = QVBoxLayout()
        self.list_layout.setSpacing(10)
        box.addLayout(self.list_layout)
        actions = QHBoxLayout()
        self.refresh_button = QPushButton(_t('ui.workspace.refresh'))
        self.refresh_button.setObjectName('workspaceButton')
        self.refresh_button.clicked.connect(self.refresh)
        actions.addWidget(self.refresh_button)
        actions.addStretch()
        self.clear_button = QPushButton(_t('ui.workspace.clear_unavailable'))
        self.clear_button.setObjectName('workspaceButton')
        self.clear_button.setEnabled(False)
        self.clear_button.setToolTip(_t('ui.workspace.clear_explanation'))
        actions.addWidget(self.clear_button)
        box.addLayout(actions)
        box.addStretch()

    def _clear_rows(self):
        while self.list_layout.count():
            item = self.list_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self.memory_cards = []

    def refresh(self):
        if self._loading:
            self._reload = True
            return
        if self._busy:
            return
        self._loading = True
        self.refresh_button.setEnabled(False)
        self._clear_rows()
        self.memory_count.setText(_t('ui.workspace.unknown'))
        self.status.setText(_t('ui.workspace.loading'))
        def read():
            try:
                from memory.memory_manager import all_entries_for_ui
                rows, error = all_entries_for_ui(strict=True), None
            except Exception as exc:  # noqa: BLE001
                rows, error = None, f'{type(exc).__name__}: {exc}'
            from ui.qt_thread import run_on_qt_thread
            run_on_qt_thread(self.owner, lambda: self._finish_read(rows, error))
        try:
            threading.Thread(target=read, name='workspace-memory-read', daemon=True).start()
        except RuntimeError as exc:
            self._finish_read(None, str(exc))

    def _finish_read(self, rows, error):
        self._loading = False
        self.refresh_button.setEnabled(True)
        if error is not None:
            self.memory_count.setText(_t('ui.workspace.unknown'))
            self.status.setText(_t('ui.workspace.memory_unavailable'))
            print(f'[JARVIS] Memory unavailable: {error}')
        else:
            self.memory_count.setText(_t('ui.workspace.memory_count', count=len(rows)))
            self.status.setText(_t('ui.workspace.memory_empty') if not rows else '')
            for row in rows:
                card = MemoryCard(self, row)
                self.memory_cards.append(card)
                self.list_layout.addWidget(card)
        self.list_layout.addStretch(1)
        if self._reload:
            self._reload = False
            self.refresh()

    def confirm_forget(self, row):
        if self._busy or self._loading:
            return
        dialog = QMessageBox(self.dialog_parent)
        dialog.setIcon(QMessageBox.Icon.Warning)
        dialog.setTextFormat(Qt.TextFormat.PlainText)
        dialog.setWindowTitle(_t('ui.workspace.forget_title'))
        dialog.setText(_t('ui.workspace.forget_confirm', field_name=str(row.get('key') or '')))
        dialog.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        dialog.button(QMessageBox.StandardButton.Yes).setText(tr('Lupakan', 'Forget'))
        dialog.button(QMessageBox.StandardButton.No).setText(tr('Batal', 'Cancel'))
        dialog.setDefaultButton(QMessageBox.StandardButton.No)
        if dialog.exec() != QMessageBox.StandardButton.Yes:
            return
        self._busy = True
        self.refresh_button.setEnabled(False)
        for card in self.memory_cards:
            card.delete.setEnabled(False)
        self.status.setText(_t('ui.workspace.forgetting'))
        def remove():
            try:
                from memory.memory_manager import forget_if_unchanged
                result, error = forget_if_unchanged(row), None
            except Exception as exc:  # noqa: BLE001
                result, error = False, f'{type(exc).__name__}: {exc}'
            from ui.qt_thread import run_on_qt_thread
            run_on_qt_thread(self.owner, lambda: self._finish_forget(result, error))
        try:
            threading.Thread(target=remove, name='workspace-memory-forget', daemon=True).start()
        except RuntimeError as exc:
            self._finish_forget(False, str(exc))

    def _finish_forget(self, result, error):
        self._busy = False
        self.refresh_button.setEnabled(True)
        for card in self.memory_cards:
            card.delete.setEnabled(True)
        if error:
            self.status.setText(_t('ui.workspace.forget_failed'))
            print(f'[JARVIS] Memory deletion failed: {error}')
        elif not result:
            self.status.setText(_t('ui.workspace.memory_changed'))
        else:
            self.refresh()
