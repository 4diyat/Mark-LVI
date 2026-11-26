"""History desktop page: session undo and separately sourced audit records."""
import threading

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtWidgets import QLabel, QFrame, QHBoxLayout, QLineEdit, QMessageBox, QPushButton, QVBoxLayout, QWidget

from ui.hud_icons import icon
from ui.hud_pages import heading, tr
from ui.qt_thread import run_on_qt_thread
from ui.tray_panel_model import _t


class HistoryPage(QWidget):
    def __init__(self, dialog_parent):
        super().__init__()
        self.setObjectName('desktopPage')
        self.dialog_parent = dialog_parent
        self.owner = threading.get_ident()
        self.loading = self.busy = self.reload_requested = False
        self.undo_rows = None
        self.audit_rows = None
        self.row_widgets = []
        self.notice = ''
        self._build()

    def _build(self):
        box = QVBoxLayout(self)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(14)
        header = QHBoxLayout()
        header.addWidget(heading(tr('Riwayat', 'History'), 'desktopHeading'), 1)
        self.search = QLineEdit()
        self.search.setObjectName('workspaceSearch')
        self.search.setPlaceholderText(tr('Cari riwayat yang dimuat…', 'Search loaded history…'))
        self.search.setAccessibleName(tr('Cari riwayat', 'Search history'))
        self.search.textChanged.connect(self.render)
        header.addWidget(self.search)
        box.addLayout(header)
        intro = heading(tr('Riwayat urungkan berlaku selama sesi ini. Audit adalah catatan terpisah, bukan daftar semua percakapan.',
                           'Undo history lasts for this session. Audit records are separate, not a history of every conversation.'), 'desktopMuted')
        intro.setWordWrap(True)
        box.addWidget(intro)
        bar = QHBoxLayout()
        self.undo_count = heading('', 'desktopEyebrow')
        bar.addWidget(self.undo_count, 1)
        self.refresh_button = QPushButton(tr('Muat ulang', 'Refresh'))
        self.refresh_button.setObjectName('workspaceButton')
        self.refresh_button.clicked.connect(self.refresh)
        bar.addWidget(self.refresh_button)
        self.clear_button = QPushButton(tr('Hapus daftar urungkan', 'Clear undo list'))
        self.clear_button.setObjectName('danger')
        self.clear_button.clicked.connect(self.confirm_clear)
        bar.addWidget(self.clear_button)
        box.addLayout(bar)
        self.status = heading('', 'workspaceStatus')
        self.status.setWordWrap(True)
        box.addWidget(self.status)
        self.undo_layout = QVBoxLayout()
        self.undo_layout.setSpacing(9)
        box.addLayout(self.undo_layout)
        box.addSpacing(12)
        box.addWidget(heading(tr('AUDIT TERBARU · MAKSIMAL 12 CATATAN', 'RECENT AUDIT · UP TO 12 RECORDS'), 'desktopEyebrow'))
        explanation = heading(tr('Status ditampilkan sebagaimana tercatat; tidak menunjukkan bahwa hasil diverifikasi.',
                                 'Statuses are shown as recorded; they do not establish that outcomes were verified.'), 'desktopMuted')
        explanation.setWordWrap(True)
        box.addWidget(explanation)
        self.audit_layout = QVBoxLayout()
        self.audit_layout.setSpacing(9)
        box.addLayout(self.audit_layout)
        box.addStretch()
        self.render()

    @staticmethod
    def _clear(layout):
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def refresh(self):
        if self.loading:
            self.reload_requested = True
            return
        if self.busy:
            return
        self.loading = True
        self.refresh_button.setEnabled(False)
        self.clear_button.setEnabled(False)
        self.status.setText(tr('Memuat riwayat…', 'Loading history…'))
        def read():
            from core import audit_log, undo
            try:
                rows, undo_error = undo.history_with_tokens(), None
            except Exception as exc:  # noqa: BLE001
                rows, undo_error = None, str(exc)
            try:
                audit, audit_error = audit_log.shared().entries(12, strict=True), None
            except Exception as exc:  # noqa: BLE001
                audit, audit_error = None, str(exc)
            run_on_qt_thread(self.owner, lambda: self._finish_read(rows, audit, undo_error, audit_error))
        try:
            threading.Thread(target=read, name='desktop-history-read', daemon=True).start()
        except RuntimeError as exc:
            self._finish_read(None, None, str(exc), str(exc))

    def _finish_read(self, rows, audit, undo_error, audit_error):
        self.loading = False
        self.undo_rows, self.audit_rows = rows, audit
        self.refresh_button.setEnabled(True)
        self.status.setText(self.notice)
        self.notice = ''
        if undo_error or audit_error:
            print(f'[JARVIS] History read unavailable: undo={undo_error}, audit={audit_error}')
        self.render()
        if self.reload_requested:
            self.reload_requested = False
            self.refresh()

    def render(self):
        self._clear(self.undo_layout)
        self._clear(self.audit_layout)
        self.row_widgets = []
        query = self.search.text().strip().casefold()
        rows = self.undo_rows
        self.clear_button.setEnabled(bool(rows) and not self.loading and not self.busy)
        if rows is None:
            self.undo_count.setText(tr('DAFTAR URUNGKAN TIDAK TERSEDIA', 'UNDO HISTORY UNAVAILABLE'))
            self.undo_layout.addWidget(heading(tr('Daftar urungkan tidak dapat dibaca.', 'Undo history could not be read.'), 'workspaceStatus'))
        else:
            self.undo_count.setText(tr(f'URUNGKAN SESI · {len(rows)} ENTRI', f'SESSION UNDO · {len(rows)} ENTRIES'))
            shown = [(i, token, label) for i, (token, label) in enumerate(rows) if query in str(label).casefold()]
            if not shown:
                self.undo_layout.addWidget(heading(tr('Tidak ada entri yang cocok.' if query else 'Belum ada tindakan untuk diurungkan.',
                                                    'No matching entries.' if query else 'There are no actions to undo.'), 'workspaceStatus'))
            for index, token, label in shown:
                card = QFrame(); card.setObjectName('historyCard')
                row = QHBoxLayout(card); row.setContentsMargins(18, 14, 18, 14)
                glyph = QLabel()
                glyph.setObjectName('workspaceIcon'); glyph.setFixedSize(44, 44)
                glyph.setAlignment(Qt.AlignmentFlag.AlignCenter)
                glyph.setPixmap(icon('clock-3', '#73c1ff', 23).pixmap(QSize(23, 23)))
                row.addWidget(glyph)
                text = QVBoxLayout()
                name = heading(str(label), 'desktopCardTitle'); name.setWordWrap(True)
                text.addWidget(name)
                text.addWidget(heading(tr('Tersedia untuk diurungkan' if index == 0 else 'Setelah entri yang lebih baru',
                                           'Available to undo' if index == 0 else 'After newer entries'), 'desktopMuted'))
                row.addLayout(text, 1)
                button = QPushButton(tr('Urungkan', 'Undo'))
                button.setObjectName('workspaceButton')
                button.setEnabled(index == 0 and not self.busy and not self.loading)
                button.setToolTip(tr('Hanya entri terbaru yang dapat diurungkan.', 'Only the latest entry can be undone.'))
                button.clicked.connect(lambda checked=False, t=token: self.undo(t))
                row.addWidget(button)
                self.row_widgets.append((token, button))
                self.undo_layout.addWidget(card)
        audit = self.audit_rows
        if audit is None:
            self.audit_layout.addWidget(heading(tr('Audit tidak dapat dibaca.', 'Audit could not be read.'), 'workspaceStatus'))
        else:
            matched = [r for r in reversed(audit) if query in ' '.join(str(r.get(k) or '')
                       for k in ('at', 'tool', 'level', 'outcome', 'detail')).casefold()]
            if not matched:
                self.audit_layout.addWidget(heading(tr('Tidak ada catatan yang cocok.' if query else 'Belum ada catatan audit.',
                                                      'No matching records.' if query else 'There are no audit records.'), 'workspaceStatus'))
            for entry in matched:
                card = QFrame(); card.setObjectName('historyCard')
                layout = QVBoxLayout(card); layout.setContentsMargins(18, 12, 18, 12)
                title = heading(str(entry.get('tool') or '?'), 'desktopCardTitle'); title.setWordWrap(True)
                layout.addWidget(title)
                info = heading(' · '.join(str(entry.get(k) or '—') for k in ('at', 'level', 'outcome')), 'desktopMuted')
                info.setWordWrap(True); layout.addWidget(info)
                detail = str(entry.get('detail') or '')
                if detail:
                    note = heading(detail, 'desktopMuted'); note.setWordWrap(True); layout.addWidget(note)
                self.audit_layout.addWidget(card)

    def undo(self, token):
        if self.busy or self.loading or not self.undo_rows or self.undo_rows[0][0] is not token:
            return
        dialog = QMessageBox(self.dialog_parent)
        dialog.setIcon(QMessageBox.Icon.Warning)
        dialog.setTextFormat(Qt.TextFormat.PlainText)
        dialog.setWindowTitle(tr('Urungkan tindakan?', 'Undo action?'))
        dialog.setText(tr('Coba urungkan tindakan terbaru: ', 'Attempt to undo the latest action: ')
                       + str(self.undo_rows[0][1]) + tr('\nHasilnya belum tentu dapat dipastikan.',
                                                        '\nThe outcome may not be verifiable.'))
        dialog.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        dialog.button(QMessageBox.StandardButton.Yes).setText(tr('Urungkan', 'Undo'))
        dialog.button(QMessageBox.StandardButton.No).setText(tr('Batal', 'Cancel'))
        dialog.setDefaultButton(QMessageBox.StandardButton.No)
        if dialog.exec() != QMessageBox.StandardButton.Yes:
            return
        self.busy = True
        self.status.setText(tr('Mengurungkan…', 'Undoing…'))
        self.render()
        def run():
            from core import undo
            try:
                _, message = undo.undo_if_current(token)
            except Exception as exc:  # noqa: BLE001
                message = f'{type(exc).__name__}: {exc}'
            run_on_qt_thread(self.owner, lambda: self._finish_undo(message))
        try:
            threading.Thread(target=run, name='desktop-undo', daemon=True).start()
        except RuntimeError as exc:
            self._finish_undo(str(exc))

    def _finish_undo(self, message):
        self.busy = False
        self.notice = _t('ui.panel.history.changed') if message == 'changed' else str(message)
        self.refresh()

    def confirm_clear(self):
        if self.busy or self.loading or not self.undo_rows:
            return
        tokens = tuple(token for token, _ in self.undo_rows)
        dialog = QMessageBox(self.dialog_parent)
        dialog.setIcon(QMessageBox.Icon.Warning)
        dialog.setTextFormat(Qt.TextFormat.PlainText)
        dialog.setWindowTitle(_t('ui.panel.history.clear_title'))
        dialog.setText(_t('ui.panel.history.clear_confirm'))
        dialog.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        dialog.button(QMessageBox.StandardButton.Yes).setText(tr('Lupakan daftar', 'Forget list'))
        dialog.button(QMessageBox.StandardButton.No).setText(tr('Batal', 'Cancel'))
        dialog.setDefaultButton(QMessageBox.StandardButton.No)
        if dialog.exec() != QMessageBox.StandardButton.Yes:
            return
        from core import undo
        cleared = undo.clear_if_unchanged(tokens)
        self.notice = _t('ui.panel.history.cleared' if cleared else 'ui.panel.history.clear_changed')
        self.refresh()
