"""Security overview backed by policy and audit data, without fake permissions."""
import threading

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtWidgets import (QBoxLayout, QComboBox, QFileDialog, QFrame, QHBoxLayout,
                             QLabel, QMessageBox, QPushButton, QScrollArea, QVBoxLayout, QWidget)

from ui.hud_icons import icon
from ui.hud_pages import heading, tr
from ui.qt_thread import run_on_qt_thread


class SecurityPage(QWidget):
    def __init__(self, shell, window, open_memory):
        super().__init__()
        self.setObjectName('desktopPage')
        self.shell, self.dialog_parent = shell, window
        self.open_memory = open_memory
        self.owner = threading.get_ident()
        self.loading = self.exporting = self.reload_requested = False
        self.records = None
        self.audit_cards = []
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        self.columns = QBoxLayout(QBoxLayout.Direction.LeftToRight)
        self.columns.setSpacing(18)
        left = QFrame(); left.setObjectName('securityPanel')
        side = QVBoxLayout(left); side.setContentsMargins(20, 20, 20, 20); side.setSpacing(13)
        side.addWidget(heading(tr('Keamanan', 'Security'), 'desktopHeading'))
        intro = heading(tr('Tinjau kebijakan risiko dan keterbatasan izin aplikasi.',
                           'Review risk policy and the limits of application permissions.'), 'desktopMuted')
        intro.setWordWrap(True); side.addWidget(intro)
        side.addWidget(heading(tr('TINGKAT KEBIJAKAN', 'POLICY LEVELS'), 'desktopEyebrow'))
        self.risk_counts = {}
        for key, title, note, color in (
            ('safe', tr('Rendah', 'Low'), tr('Klasifikasi dasar kebijakan', 'Base policy classification'), '#64d59d'),
            ('medium', tr('Sedang', 'Medium'), tr('Perubahan; perlu dukungan urungkan', 'Changes; undo support required'), '#efb75d'),
            ('risky', tr('Berisiko', 'Risky'), tr('Memerlukan persetujuan manusia', 'Requires human approval'), '#f47e7e'),
        ):
            card = QFrame(); card.setObjectName('securityRisk')
            card.setProperty('risk', key)
            row = QHBoxLayout(card); row.setContentsMargins(14, 13, 14, 13)
            badge = QLabel(); badge.setFixedSize(40, 40); badge.setObjectName('workspaceIcon')
            badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            badge.setPixmap(icon('shield', color, 23).pixmap(QSize(23, 23))); row.addWidget(badge)
            text = QVBoxLayout()
            text.addWidget(heading(title, 'desktopCardTitle'))
            detail = heading(note, 'desktopMuted'); detail.setWordWrap(True); text.addWidget(detail)
            row.addLayout(text, 1)
            count = heading('—', 'securityCount'); count.setStyleSheet(f'color:{color};')
            count.setAccessibleName(title + ' · ' + tr('entri kebijakan', 'policy entries'))
            self.risk_counts[key] = count; row.addWidget(count)
            side.addWidget(card)
        explanation = heading(tr('Jumlah adalah entri kebijakan, bukan kemampuan aktif. Risiko akhir bergantung pada parameter; fitur lain tidak selalu memakai gerbang ini.',
                                 'Counts are policy entries, not active capabilities. Risk depends on parameters; other features do not necessarily use this gate.'), 'desktopHint')
        explanation.setWordWrap(True); side.addWidget(explanation)
        side.addWidget(heading(tr('IZIN DAN KONTROL', 'PERMISSIONS AND CONTROLS'), 'desktopEyebrow'))
        self._static_card(side, tr('Mode tamu', 'Guest mode'),
                          tr('Tidak tersedia; aplikasi tidak menjanjikan sesi tanpa penyimpanan.',
                             'Unavailable; the application does not promise a memory-free session.'), 'circle-dot')
        self._static_card(side, tr('Akses layar', 'Screen access'),
                          tr('Izin sistem tidak diketahui. Tidak ada sakelar umum; fitur tangkapan layar lain mungkin tetap dapat bekerja.',
                             'OS permission is unknown. No global switch is available; other screenshot features may still work.'), 'layout-grid')
        self._static_card(side, tr('Akses kamera', 'Camera access'),
                          tr('Izin sistem tidak diketahui. Tidak ada sakelar umum untuk semua fitur kamera.',
                             'OS permission is unknown. No global switch covers every camera feature.'), 'circle-dot')
        mic = QFrame(); mic.setObjectName('securityInfo')
        mbox = QVBoxLayout(mic); mbox.setContentsMargins(14, 12, 14, 12)
        mbox.addWidget(heading(tr('Mikrofon sesi', 'Session microphone'), 'desktopCardTitle'))
        self.mic_status = heading('', 'desktopMuted'); self.mic_status.setWordWrap(True); mbox.addWidget(self.mic_status)
        side.addWidget(mic)
        side.addStretch()
        self.columns.addWidget(left, 4)
        self.columns.setAlignment(left, Qt.AlignmentFlag.AlignTop)

        right = QFrame(); right.setObjectName('securityPanel'); right.setMinimumHeight(480)
        panel = QVBoxLayout(right); panel.setContentsMargins(20, 20, 20, 20); panel.setSpacing(12)
        header = QHBoxLayout(); header.addWidget(heading(tr('Log aktivitas', 'Activity log'), 'desktopSubheading'), 1)
        self.filter = QComboBox(); self.filter.setObjectName('securityFilter')
        self.filter.setAccessibleName(tr('Filter status audit', 'Filter audit outcome'))
        self.filter.currentIndexChanged.connect(self.render)
        header.addWidget(self.filter); panel.addLayout(header)
        help_text = heading(tr('Maksimal 50 catatan terbaru; log mungkin tidak lengkap. Waktu dan status ditampilkan sebagaimana dicatat, bukan verifikasi hasil.',
                               'Up to 50 recent records; the log may be incomplete. Times and outcomes are shown as recorded, not verified.'), 'desktopMuted')
        help_text.setWordWrap(True); panel.addWidget(help_text)
        self.audit_status = heading('', 'workspaceStatus'); self.audit_status.setWordWrap(True); panel.addWidget(self.audit_status)
        records_area = QScrollArea()
        records_area.setWidgetResizable(True)
        records_area.setFrameShape(QFrame.Shape.NoFrame)
        records_area.setMinimumHeight(180)
        records_area.setMaximumHeight(370)
        records_body = QWidget(); records_body.setObjectName('securityList')
        records_layout = QVBoxLayout(records_body)
        records_layout.setContentsMargins(0, 0, 0, 0)
        self.rows = QVBoxLayout(); self.rows.setSpacing(8); records_layout.addLayout(self.rows)
        records_layout.addStretch()
        records_area.setWidget(records_body)
        self.records_area = records_area
        panel.addWidget(records_area, 1)
        self.export_status = heading('', 'workspaceStatus'); self.export_status.setWordWrap(True); panel.addWidget(self.export_status)
        caution = heading(tr('Ekspor berisi seluruh log audit dan dapat memuat informasi sensitif.',
                             'Export includes the entire audit log and may contain sensitive information.'), 'desktopHint')
        caution.setWordWrap(True); panel.addWidget(caution)
        actions = QHBoxLayout()
        self.refresh_button = QPushButton(tr('Muat ulang', 'Refresh'))
        self.refresh_button.setObjectName('workspaceButton'); self.refresh_button.clicked.connect(self.refresh)
        actions.addWidget(self.refresh_button)
        self.export_button = QPushButton(tr('Ekspor log', 'Export log'))
        self.export_button.setObjectName('workspaceButton'); self.export_button.clicked.connect(self.choose_export)
        actions.addWidget(self.export_button)
        memory = QPushButton(tr('Kelola memori', 'Manage memory'))
        memory.setObjectName('workspaceButton'); memory.clicked.connect(self.open_memory)
        actions.addWidget(memory)
        panel.addLayout(actions)
        self.columns.addWidget(right, 6)
        self.columns.setAlignment(right, Qt.AlignmentFlag.AlignTop)
        root.addLayout(self.columns)
        self._reset_filter([])
        self.render()

    def _static_card(self, layout, title, description, glyph):
        card = QFrame(); card.setObjectName('securityInfo')
        row = QHBoxLayout(card); row.setContentsMargins(14, 12, 14, 12)
        badge = QLabel(); badge.setObjectName('workspaceIcon'); badge.setFixedSize(40, 40)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setPixmap(icon(glyph, '#73c1ff', 22).pixmap(QSize(22, 22))); row.addWidget(badge)
        text = QVBoxLayout(); text.addWidget(heading(title, 'desktopCardTitle'))
        subtitle = heading(description, 'desktopMuted'); subtitle.setWordWrap(True); text.addWidget(subtitle)
        unavailable = heading(tr('Kontrol belum tersedia', 'Control unavailable'), 'desktopHint')
        text.addWidget(unavailable)
        row.addLayout(text, 1)
        layout.addWidget(card)

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        direction = (QBoxLayout.Direction.TopToBottom if self.width() < 800
                     else QBoxLayout.Direction.LeftToRight)
        if self.columns.direction() != direction:
            self.columns.setDirection(direction)

    def _reset_filter(self, records):
        old = self.filter.currentData()
        self.filter.blockSignals(True); self.filter.clear()
        self.filter.addItem(tr('Semua status', 'All outcomes'), '')
        for outcome in sorted({str(row.get('outcome') or '') for row in records} - {''}):
            self.filter.addItem(outcome, outcome)
        idx = self.filter.findData(old)
        self.filter.setCurrentIndex(max(0, idx)); self.filter.blockSignals(False)

    def refresh(self):
        if self.loading:
            self.reload_requested = True
            return
        self.loading = True
        self.refresh_button.setEnabled(False); self.export_button.setEnabled(False)
        self.audit_status.setText(tr('Memuat log…', 'Loading log…'))
        muted = getattr(self.shell, 'muted', None)
        state = (tr('Dibisukan di aplikasi', 'Muted in the application') if muted is True else
                 tr('Tidak dibisukan di aplikasi', 'Not muted in the application') if muted is False else
                 tr('Status bisu tidak diketahui', 'Mute state unknown'))
        self.mic_status.setText(state + tr('. Ini bukan status izin OS atau bukti mikrofon sedang mendengar.',
                                          '. This is not an OS permission or proof the microphone is listening.'))
        def read():
            from core import audit_log, risk_policy
            try:
                table, policy_error = risk_policy.registered(), None
                counts = {key: sum(level == key for level in table.values()) for key in risk_policy.LEVELS}
            except Exception as exc:  # noqa: BLE001
                counts, policy_error = {}, str(exc)
            try:
                records, audit_error = audit_log.shared().entries(50, strict=True), None
            except Exception as exc:  # noqa: BLE001
                records, audit_error = None, str(exc)
            run_on_qt_thread(self.owner, lambda: self._loaded(counts, records, policy_error, audit_error))
        try:
            threading.Thread(target=read, name='desktop-security-read', daemon=True).start()
        except RuntimeError as exc:
            self._loaded({}, None, str(exc), str(exc))

    def _loaded(self, counts, records, policy_error, audit_error):
        self.loading = False
        self.records = records
        for key, label in self.risk_counts.items():
            label.setText(str(counts[key]) if key in counts else '—')
        if policy_error or audit_error:
            print(f'[JARVIS] Security read unavailable: policy={policy_error}, audit={audit_error}')
        self.refresh_button.setEnabled(True)
        self.export_button.setEnabled(records is not None and not self.exporting)
        self._reset_filter(records or [])
        self.render()
        if self.reload_requested:
            self.reload_requested = False
            self.refresh()

    def render(self):
        while self.rows.count():
            widget = self.rows.takeAt(0).widget()
            if widget:
                widget.deleteLater()
        self.audit_cards = []
        if self.records is None:
            self.audit_status.setText(tr('Log audit tidak dapat dibaca.', 'Audit log could not be read.'))
            return
        outcome = self.filter.currentData() or ''
        records = [r for r in reversed(self.records) if not outcome or r.get('outcome') == outcome]
        self.audit_status.setText('' if records else tr('Tidak ada catatan yang cocok.', 'No matching records.'))
        for record in records:
            card = QFrame(); card.setObjectName('securityEvent')
            box = QVBoxLayout(card); box.setContentsMargins(12, 10, 12, 10)
            title = heading(str(record.get('tool') or '—'), 'desktopCardTitle'); title.setWordWrap(True); box.addWidget(title)
            info = heading(' · '.join(str(record.get(k) or '—') for k in ('at', 'level', 'outcome')), 'desktopMuted')
            info.setWordWrap(True); box.addWidget(info)
            if record.get('detail'):
                detail = heading(str(record['detail']), 'desktopMuted'); detail.setWordWrap(True); box.addWidget(detail)
            self.rows.addWidget(card); self.audit_cards.append(card)

    def choose_export(self):
        if self.loading or self.exporting or self.records is None:
            return
        path, _ = QFileDialog.getSaveFileName(self.dialog_parent, tr('Ekspor log audit', 'Export audit log'),
                                             'jarvis-audit.json', 'JSON (*.json)')
        if not path:
            return
        dialog = QMessageBox(self.dialog_parent); dialog.setIcon(QMessageBox.Icon.Warning)
        dialog.setTextFormat(Qt.TextFormat.PlainText)
        dialog.setWindowTitle(tr('Ekspor log audit?', 'Export audit log?'))
        dialog.setText(tr('Ekspor seluruh log audit ke berkas baru ini? Log dapat berisi informasi sensitif.\n',
                          'Export the entire audit log to this new file? It may contain sensitive information.\n') + path)
        dialog.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        dialog.button(QMessageBox.StandardButton.Yes).setText(tr('Ekspor', 'Export'))
        dialog.button(QMessageBox.StandardButton.No).setText(tr('Batal', 'Cancel'))
        dialog.setDefaultButton(QMessageBox.StandardButton.No)
        if dialog.exec() == QMessageBox.StandardButton.Yes:
            self.export_to(path)

    def export_to(self, path):
        if self.loading or self.exporting or self.records is None:
            return
        self.exporting = True; self.export_button.setEnabled(False)
        self.export_status.setText(tr('Mengekspor…', 'Exporting…'))
        def work():
            try:
                from core.audit_export import export_new
                count, error = export_new(path), None
            except Exception as exc:  # noqa: BLE001
                count, error = None, f'{type(exc).__name__}: {exc}'
            run_on_qt_thread(self.owner, lambda: self._export_finished(path, count, error))
        try:
            threading.Thread(target=work, name='desktop-audit-export', daemon=True).start()
        except RuntimeError as exc:
            self._export_finished(path, None, str(exc))

    def _export_finished(self, path, count, error):
        self.exporting = False
        self.export_button.setEnabled(not self.loading and self.records is not None)
        if error:
            self.export_status.setText(tr('Ekspor gagal. Berkas yang baru dibuat mungkin tidak lengkap; berkas yang sudah ada tidak ditimpa.',
                                          'Export failed. A newly created file may be incomplete; an existing file was not overwritten.'))
            print(f'[JARVIS] Audit export failed: {error}')
        else:
            self.export_status.setText(tr(f'Log diekspor: {count} catatan ke {path}',
                                          f'Exported {count} records to {path}'))
