"""Tools and help without invented clipboard, search, or accessibility powers."""
import threading

from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtWidgets import (QFrame, QGridLayout, QHBoxLayout, QLineEdit,
                             QPushButton, QStackedWidget, QVBoxLayout, QWidget)

from ui.hud_pages import heading, tr
from ui.panel_target import PanelTarget
from ui.qt_thread import run_on_qt_thread
from ui.tray_panel_model import _t


class ToolsPage(QWidget):
    def __init__(self, prepare_draft, open_chat):
        super().__init__()
        self.setObjectName('desktopPage')
        self.owner = threading.get_ident()
        self.prepare_draft, self.open_chat = prepare_draft, open_chat
        self.search_view = PanelTarget()
        self.clip_running = False
        self.clip_generation = 0
        self.timer = QTimer(self); self.timer.setInterval(100); self.timer.timeout.connect(self.poll_search)
        root = QVBoxLayout(self); root.setContentsMargins(0, 0, 0, 0)
        self.tabs = QStackedWidget(); root.addWidget(self.tabs)
        self.tabs.addWidget(self._tools())
        self.tabs.addWidget(self._help())

    @staticmethod
    def _panel():
        card = QFrame(); card.setObjectName('toolPanel')
        layout = QVBoxLayout(card); layout.setContentsMargins(20, 18, 20, 18); layout.setSpacing(10)
        return card, layout

    @staticmethod
    def _button(text, action):
        button = QPushButton(text); button.setObjectName('workspaceButton'); button.clicked.connect(action)
        return button

    def _tools(self):
        page = QWidget(); page.setObjectName('desktopPage')
        box = QVBoxLayout(page); box.setContentsMargins(0, 0, 0, 0); box.setSpacing(14)
        head = QHBoxLayout(); head.addWidget(heading(tr('Alat', 'Tools'), 'desktopHeading'), 1)
        self.help_button = self._button(tr('Pusat bantuan', 'Help center'), self.show_help)
        head.addWidget(self.help_button); box.addLayout(head)
        intro = heading(tr('Siapkan draf, lihat clipboard saat diminta, atau cari nama berkas lokal.',
                           'Prepare a draft, inspect the clipboard on request, or search local file names.'), 'desktopMuted')
        intro.setWordWrap(True); box.addWidget(intro)
        card, layout = self._panel(); layout.addWidget(heading(tr('Alat cepat', 'Quick tools'), 'desktopSubheading'))
        hint = heading(tr('Tombol hanya menyiapkan draf di Obrolan; tidak mengirim otomatis dan tidak mengganti draf yang ada.',
                          'Buttons only prepare a draft in Chat; they never send automatically or replace an existing draft.'), 'desktopHint')
        hint.setWordWrap(True); layout.addWidget(hint)
        grid = QGridLayout(); grid.setSpacing(10)
        for index, (title, prompt) in enumerate((
            (tr('Ringkas teks', 'Summarize text'), tr('Bantu saya meringkas teks berikut: ', 'Help me summarize the following text: ')),
            (tr('Buat konten', 'Create content'), tr('Bantu saya membuat konten tentang: ', 'Help me create content about: ')),
            (tr('Terjemahkan', 'Translate'), tr('Bantu saya menerjemahkan teks berikut: ', 'Help me translate the following text: ')),
        )):
            button = self._button(title, lambda checked=False, p=prompt: self.prepare_draft(p))
            button.setMinimumHeight(58); grid.addWidget(button, 0, index)
        layout.addLayout(grid); box.addWidget(card)

        card, layout = self._panel(); title = QHBoxLayout()
        title.addWidget(heading(tr('Clipboard', 'Clipboard'), 'desktopSubheading'), 1)
        self.clip_button = self._button(tr('Lihat clipboard', 'View clipboard'), self.read_clipboard)
        title.addWidget(self.clip_button); layout.addLayout(title)
        note = heading(tr('Dibaca hanya setelah diminta. Pratinjau teks dibatasi; informasi sensitif bisa terlihat di layar. Tidak ada riwayat clipboard di halaman ini.',
                          'Read only on request. The text preview is limited; sensitive information may be visible. This page has no clipboard history.'), 'desktopHint')
        note.setWordWrap(True); layout.addWidget(note)
        self.clip_text = heading(tr('Belum dibaca.', 'Not read.'), 'desktopMuted'); self.clip_text.setWordWrap(True); layout.addWidget(self.clip_text)
        self.clip_kind = heading('', 'desktopHint'); self.clip_kind.setWordWrap(True); layout.addWidget(self.clip_kind)
        box.addWidget(card)

        card, layout = self._panel(); layout.addWidget(heading(tr('Cari berkas', 'Find files'), 'desktopSubheading'))
        note = heading(tr('Mencocokkan kata minimal 3 karakter di nama berkas dalam Documents, Downloads, dan Desktop; kata pendek diabaikan. Maksimal 3 hasil; isi dan folder tidak dicari.',
                          'Matches words of at least 3 characters in file names under Documents, Downloads, and Desktop; shorter words are ignored. Up to 3 results; contents and folders are not searched.'), 'desktopHint')
        note.setWordWrap(True); layout.addWidget(note)
        row = QHBoxLayout(); self.query = QLineEdit(); self.query.setObjectName('routineInput')
        self.query.setPlaceholderText(tr('Kata dalam nama berkas', 'Words in a file name'))
        self.query.setAccessibleName(tr('Cari nama berkas', 'Search file names'))
        self.query.textChanged.connect(self.invalidate_search); self.query.returnPressed.connect(self.start_search)
        row.addWidget(self.query, 1)
        self.search_button = self._button(tr('Cari', 'Search'), self.start_search); row.addWidget(self.search_button)
        self.cancel_button = self._button(tr('Batal', 'Cancel'), self.cancel_search); self.cancel_button.setEnabled(False); row.addWidget(self.cancel_button)
        layout.addLayout(row)
        self.search_status = heading('', 'workspaceStatus'); self.search_status.setWordWrap(True); layout.addWidget(self.search_status)
        self.result_labels = []
        for _ in range(3):
            label = heading('', 'desktopMuted'); label.setWordWrap(True); label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            label.hide(); self.result_labels.append(label); layout.addWidget(label)
        box.addWidget(card); box.addStretch()
        return page

    def _help(self):
        page = QWidget(); page.setObjectName('desktopPage')
        box = QVBoxLayout(page); box.setContentsMargins(0, 0, 0, 0); box.setSpacing(14)
        header = QHBoxLayout(); header.addWidget(heading(tr('Pusat Bantuan', 'Help center'), 'desktopHeading'), 1)
        header.addWidget(self._button(tr('Kembali ke Alat', 'Back to Tools'), lambda: self.tabs.setCurrentIndex(0)))
        box.addLayout(header)
        subtitle = heading(tr('Kemampuan yang tersedia dan batasannya.', 'Available capabilities and their limits.'), 'desktopMuted')
        subtitle.setWordWrap(True); box.addWidget(subtitle)
        card, content = self._panel()
        content.addWidget(heading(tr('Masukan suara ke asisten', 'Voice input to the assistant'), 'desktopSubheading'))
        note = heading(tr('Suara ditujukan ke sesi asisten, bukan dikte ke aplikasi lain. Mikrofon, izin OS, koneksi dan pengaturan sesi dapat memengaruhi apakah suara diterima.',
                          'Voice goes to the assistant session, not dictation into other applications. The microphone, OS permission, connection and session settings can affect whether audio is received.'), 'desktopMuted')
        note.setWordWrap(True); content.addWidget(note)
        content.addWidget(self._button(tr('Buka Obrolan', 'Open Chat'), self.open_chat), 0, Qt.AlignmentFlag.AlignLeft)
        box.addWidget(card)
        for title, description in (
            (tr('Baca layar', 'Read screen'), tr('Kontrol pembacaan layar pada halaman ini belum tersedia. Fitur tangkapan layar lain mungkin tetap tersedia.',
                                                'This page has no screen-reading control. Other screenshot features may still be available.')),
            (tr('Isi formulir', 'Fill forms'), tr('Pengisian formulir otomatis belum tersedia: tujuan dan kolom belum dapat diverifikasi dengan aman.',
                                                'Automatic form filling is unavailable: the destination and fields cannot yet be verified safely.')),
        ):
            card, content = self._panel(); content.addWidget(heading(title, 'desktopSubheading'))
            note = heading(description, 'desktopMuted'); note.setWordWrap(True); content.addWidget(note)
            unavailable = self._button(tr('Belum tersedia', 'Unavailable'), lambda: None); unavailable.setEnabled(False)
            content.addWidget(unavailable, 0, Qt.AlignmentFlag.AlignLeft); box.addWidget(card)
        card, content = self._panel(); content.addWidget(heading(tr('Privasi dan koneksi', 'Privacy and connection'), 'desktopSubheading'))
        note = heading(tr('Perintah dan audio dapat dikirim ke layanan model. Jangan masukkan informasi sensitif tanpa mempertimbangkan tujuan pengiriman.',
                          'Commands and audio may be sent to the model service. Consider the destination before entering sensitive information.'), 'desktopMuted')
        note.setWordWrap(True); content.addWidget(note); box.addWidget(card); box.addStretch()
        return page

    def show_help(self):
        self.leave()
        self.tabs.setCurrentIndex(1)

    def read_clipboard(self):
        if self.clip_running:
            return
        self.clip_running = True; self.clip_button.setEnabled(False)
        self.clip_generation += 1; generation = self.clip_generation
        self.clip_text.setText(tr('Membaca clipboard…', 'Reading clipboard…')); self.clip_kind.setText('')
        def work():
            try:
                from ui.pages_people import clipboard_text, sensitive_kind
                text = clipboard_text()
                kind = sensitive_kind(text) if text else ''
            except Exception as exc:  # noqa: BLE001
                print(f'[JARVIS] Clipboard read failed: {type(exc).__name__}: {exc}')
                text, kind = None, ''
            run_on_qt_thread(self.owner, lambda: self._clipboard_done(generation, text, kind))
        try:
            threading.Thread(target=work, name='desktop-clipboard-read', daemon=True).start()
        except RuntimeError as exc:
            print(f'[JARVIS] Clipboard worker failed: {exc}')
            self._clipboard_done(generation, None, '')

    def _clipboard_done(self, generation, text, kind):
        self.clip_running = False; self.clip_button.setEnabled(True)
        if generation != self.clip_generation:
            return
        if text is None:
            self.clip_text.setText(tr('Clipboard tidak dapat dibaca.', 'Clipboard could not be read.'))
        elif not text:
            self.clip_text.setText(tr('Clipboard teks kosong.', 'Clipboard text is empty.'))
        else:
            preview = ' '.join(text.splitlines())[:160] + ('…' if len(text) > 160 else '')
            self.clip_text.setText(preview)
            self.clip_kind.setText(tr('Pola terdeteksi: ', 'Pattern detected: ') + _t(kind)
                                   + tr(' · bukan pemeriksaan keamanan.', ' · not a security check.') if kind
                                   else _t('ui.page.tools.not_sensitive'))

    def start_search(self):
        self.search_view.start_search(self.query.text())
        self._paint_search()
        if self.search_view.search_status == 'searching':
            self.timer.start()

    def invalidate_search(self):
        self.cancel_search()

    def cancel_search(self):
        self.search_view.cancel_search(); self.timer.stop(); self._paint_search()

    def poll_search(self):
        if self.search_view.poll_search():
            self._paint_search()
        if self.search_view.search_status != 'searching':
            self.timer.stop()

    def _paint_search(self):
        state = self.search_view.search_status
        texts = {
            'idle': '',
            'invalid': tr('Masukkan setidaknya satu kata dengan 3 huruf.', 'Enter at least one word of 3 characters.'),
            'searching': tr('Mencari… Hasil dibatalkan akan diabaikan; operasi sistem berkas mungkin masih berjalan.', 'Searching… Cancelled results are ignored; a filesystem call may still be running.'),
            'error': tr('Pencarian gagal; hasil tidak diketahui.', 'Search failed; results are unknown.'),
            'done': '' if self.search_view.hits else tr('Tidak ada hasil yang cocok di lokasi yang diperiksa.', 'No matches in the locations checked.'),
        }
        self.search_status.setText(texts[state]); self.cancel_button.setEnabled(state == 'searching')
        for index, label in enumerate(self.result_labels):
            hits = self.search_view.hits
            label.setText(str(hits[index]) if index < len(hits) else '')
            label.setVisible(index < len(hits))

    def leave(self):
        self.cancel_search()
        self.clip_generation += 1
        self.clip_text.setText(tr('Belum dibaca.', 'Not read.')); self.clip_kind.setText('')
