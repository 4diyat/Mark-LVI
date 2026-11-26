"""Settings and integration overview; delegate existing edits to the tray panel."""
import threading
from collections import Counter

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (QCheckBox, QFrame, QGridLayout, QHBoxLayout, QPushButton,
                             QStackedWidget, QVBoxLayout, QWidget)

from ui.hud_pages import heading, tr
from ui.qt_thread import run_on_qt_thread


class SettingsPage(QWidget):
    def __init__(self, shell):
        super().__init__()
        self.setObjectName('desktopPage')
        self.shell = shell
        self.owner = threading.get_ident()
        self.loading = self.reload_requested = False
        self.records = None
        self.cards = []
        self.page_index = 0
        root = QVBoxLayout(self); root.setContentsMargins(0, 0, 0, 0); root.setSpacing(14)
        root.addWidget(heading(tr('Pengaturan', 'Settings'), 'desktopHeading'))
        nav = QGridLayout()
        self.access_button = self.button(tr('Aksesibilitas', 'Accessibility'), lambda: self.show_tab(0))
        self.plugins_button = self.button(tr('Plugin dan perangkat', 'Plugins and devices'), lambda: self.show_tab(1))
        self.gesture_button = self.button(tr('Panduan gestur', 'Gesture guide'), lambda: self.show_tab(2))
        self.appearance_button = self.button(tr('Tampilan panel', 'Tray appearance'), lambda: self.show_tab(3))
        for i, b in enumerate((self.access_button, self.plugins_button, self.gesture_button, self.appearance_button)):
            nav.addWidget(b, i // 2, i % 2)
        nav.setColumnStretch(2, 1); root.addLayout(nav)
        self.tabs = QStackedWidget(); root.addWidget(self.tabs)
        self.tabs.addWidget(self._access()); self.tabs.addWidget(self._plugins()); self.tabs.addWidget(self._gesture())
        from ui.desktop_appearance import AppearancePage
        self.appearance = AppearancePage(self.shell); self.tabs.addWidget(self.appearance)
        root.addStretch()
        self.show_tab(0)

    @staticmethod
    def button(text, callback):
        button = QPushButton(text); button.setObjectName('workspaceButton'); button.clicked.connect(callback)
        return button

    @staticmethod
    def panel(title, description):
        card = QFrame(); card.setObjectName('settingsCard')
        box = QVBoxLayout(card); box.setContentsMargins(20, 18, 20, 18); box.setSpacing(9)
        box.addWidget(heading(title, 'desktopCardTitle'))
        note = heading(description, 'desktopMuted'); note.setWordWrap(True); box.addWidget(note)
        return card, box

    def _access(self):
        page = QWidget(); page.setObjectName('desktopPage')
        box = QVBoxLayout(page); box.setContentsMargins(0, 0, 0, 0); box.setSpacing(12)
        intro = heading(tr('Beberapa pilihan berlaku hanya pada panel baki atau layar utama, bukan seluruh aplikasi.',
                           'Some choices apply only to the tray panel or home screen, not the entire application.'), 'desktopMuted')
        intro.setWordWrap(True); box.addWidget(intro)
        card, content = self.panel(tr('Bahasa antarmuka', 'Interface language'),
            tr('Bahasa proses saat ini ditampilkan di bawah. Penggantian tersedia di panel baki; label yang sudah dibuat mungkin tidak langsung berubah dan pilihan tidak disimpan untuk peluncuran berikutnya.',
               'The current process language appears below. Change it in the tray panel; existing labels may not update immediately and the choice is not saved for the next launch.'))
        self.locale = heading('', 'routineTime'); content.addWidget(self.locale)
        content.addWidget(self.button(tr('Buka pengaturan bahasa dan kontras panel', 'Open tray language and contrast settings'),
                                      lambda: self.open_tray('access')), 0, Qt.AlignmentFlag.AlignLeft)
        box.addWidget(card)
        card, content = self.panel(tr('Kontras', 'Contrast'),
            tr('Pilihan kontras yang ada berlaku untuk panel baki, bukan ruang kerja ini.',
               'The existing contrast choice applies to the tray panel, not this workspace.'))
        box.addWidget(card)
        card, content = self.panel(tr('Kurangi gerak pada layar utama', 'Reduce motion on the home screen'),
            tr('Mengurangi animasi orb dan waveform layar utama selama sesi ini; bukan pengaturan seluruh aplikasi dan tidak disimpan.',
               'Reduces the home orb and waveform animation for this session; not an application-wide or persisted setting.'))
        self.motion = QCheckBox(tr('Kurangi gerak layar utama', 'Reduce home-screen motion'))
        self.motion.toggled.connect(self.set_motion); content.addWidget(self.motion); box.addWidget(card)
        card, content = self.panel(tr('Ukuran teks & gestur kustom', 'Text size & custom gestures'),
            tr('Pengaturan ukuran teks dan pemetaan gestur kustom belum tersedia di ruang kerja ini.',
               'Text size and custom gesture mapping are not available in this workspace.'))
        box.addWidget(card)
        self.access_status = heading('', 'workspaceStatus'); self.access_status.setWordWrap(True); box.addWidget(self.access_status)
        box.addStretch(); return page

    def _plugins(self):
        page = QWidget(); page.setObjectName('desktopPage')
        box = QVBoxLayout(page); box.setContentsMargins(0, 0, 0, 0); box.setSpacing(12)
        top = QHBoxLayout(); top.addWidget(heading(tr('Plugin', 'Plugins'), 'desktopSubheading'), 1)
        self.reload_button = self.button(tr('Muat ulang', 'Refresh'), self.refresh_plugins); top.addWidget(self.reload_button)
        top.addWidget(self.button(tr('Kelola di panel baki', 'Manage in tray panel'), lambda: self.open_tray('plugins')))
        box.addLayout(top)
        intro = heading(tr('Status adalah konfigurasi registri, bukan bukti koneksi layanan. Kelola dan tinjau izin di panel baki. Deklarasi izin bukan sandbox; plugin berjalan dengan hak proses aplikasi.',
                           'Status is registry configuration, not proof a service is connected. Manage and review permissions in the tray panel. Declared permissions are not a sandbox; plugins run with application process privileges.'), 'desktopMuted')
        intro.setWordWrap(True); box.addWidget(intro)
        self.plugin_status = heading('', 'workspaceStatus'); self.plugin_status.setWordWrap(True); box.addWidget(self.plugin_status)
        self.list_layout = QVBoxLayout(); self.list_layout.setSpacing(9); box.addLayout(self.list_layout)
        pagination = QHBoxLayout()
        self.prev = self.button(tr('Sebelumnya', 'Previous'), lambda: self.move_page(-1)); pagination.addWidget(self.prev)
        self.page_label = heading('', 'desktopHint'); pagination.addWidget(self.page_label, 1, Qt.AlignmentFlag.AlignCenter)
        self.next = self.button(tr('Berikutnya', 'Next'), lambda: self.move_page(1)); pagination.addWidget(self.next)
        box.addLayout(pagination)
        card, content = self.panel(tr('Penyandingan ponsel', 'Phone pairing'),
            tr('Belum tersedia di halaman ini. Kode dan status perangkat tidak ditampilkan karena belum terhubung ke layanan penyandingan yang terverifikasi.',
               'Unavailable on this page. Codes and device status are not shown because no verified pairing service is connected.'))
        disabled = self.button(tr('Belum tersedia', 'Unavailable'), lambda: None); disabled.setEnabled(False); content.addWidget(disabled, 0, Qt.AlignmentFlag.AlignLeft)
        box.addWidget(card)
        self.integration_status = heading('', 'workspaceStatus'); self.integration_status.setWordWrap(True); box.addWidget(self.integration_status)
        box.addStretch(); self._render_plugins(); return page

    def _gesture(self):
        page = QWidget(); page.setObjectName('desktopPage')
        box = QVBoxLayout(page); box.setContentsMargins(0, 0, 0, 0); box.setSpacing(12)
        intro = heading(tr('Panduan kebijakan, bukan indikator bahwa kamera atau kontrol OS aktif. Pelacakan ruang kerja saat ini memerlukan Windows dan perangkat yang didukung.',
                           'Policy guide, not an indicator that camera or OS control is active. Workspace tracking currently requires Windows and supported hardware.'), 'desktopMuted')
        intro.setWordWrap(True); box.addWidget(intro)
        for title, note in (
            (tr('Penunjuk tangan', 'Hand pointer'), tr('Posisi tangan dapat menggerakkan penunjuk saat jalur kontrol yang sesuai aktif.', 'Hand position can move a pointer when the applicable control path is active.')),
            (tr('Jepit', 'Pinch'), tr('Dalam kontrol OS, jepit yang ditahan dapat menekan tombol mouse; melepaskan atau kehilangan tangan melepaskannya.', 'In OS control, a held pinch can press the mouse button; release or tracking loss releases it.')),
            (tr('Dua jari', 'Two fingers'), tr('Pose gulir dapat menghasilkan gulir pada jalur yang mendukungnya.', 'The scroll pose can produce scrolling on a supported path.')),
        ):
            card, _ = self.panel(title, note); box.addWidget(card)
        note = heading(tr('Kontrol OS terpisah dan membutuhkan persetujuan fisik. Konfirmasi tidak boleh dilakukan dengan gestur; pengikatan gestur kustom belum tersedia.',
                          'OS control is separate and requires physical approval. Gestures must not approve confirmations; custom bindings are not available.'), 'desktopHint')
        note.setWordWrap(True); box.addWidget(note); box.addStretch(); return page

    def show_tab(self, index):
        self.tabs.setCurrentIndex(index)
        for n, b in enumerate((self.access_button, self.plugins_button, self.gesture_button, self.appearance_button)):
            b.setCheckable(True); b.setChecked(n == index)
        if index == 0:
            self.refresh_access()
        elif index == 1:
            self.refresh_plugins()
        elif index == 3:
            self.appearance.refresh()

    def refresh(self):
        if self.tabs.currentIndex() == 0: self.refresh_access()
        if self.tabs.currentIndex() == 1: self.refresh_plugins()
        if self.tabs.currentIndex() == 3: self.appearance.refresh()

    def refresh_access(self):
        from core import i18n
        self.locale.setText(tr('Bahasa proses: ', 'Process language: ') + i18n.active_locale())
        home = getattr(self.shell, '_main_surface', None)
        control = getattr(home, 'reduce_motion', None)
        self.motion.blockSignals(True)
        self.motion.setEnabled(control is not None)
        self.motion.setChecked(control.isChecked() if control is not None else False)
        self.motion.blockSignals(False)

    def set_motion(self, enabled):
        home = getattr(self.shell, '_main_surface', None)
        control = getattr(home, 'reduce_motion', None)
        if control is None:
            self.refresh_access()
            return
        control.setChecked(bool(enabled))

    def open_tray(self, page):
        target = self.integration_status if page == 'plugins' else self.access_status
        try:
            from ui.tray_panel_wiring import open_panel
            if not open_panel(self.shell) or not self.shell._panel.set_page(page):
                raise RuntimeError('tray page unavailable')
        except Exception as exc:  # noqa: BLE001
            print(f'[JARVIS] Tray settings unavailable: {type(exc).__name__}: {exc}')
            target.setText(tr('Panel baki tidak dapat dibuka.', 'Could not open the tray panel.'))
            return
        target.setText(tr('Panel baki dibuka. Muat ulang halaman ini setelah perubahan.',
                          'Tray panel opened. Refresh this page after making changes.'))

    def refresh_plugins(self):
        if self.loading:
            self.reload_requested = True
            return
        self.loading = True; self.reload_button.setEnabled(False)
        self.plugin_status.setText(tr('Memuat registri…', 'Loading registry…'))
        def work():
            try:
                provider = getattr(self.shell, 'get_plugins', None)
                rows = provider() if callable(provider) else None
                if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
                    raise ValueError('Registry unavailable')
                rows = [dict(row) for row in rows]
                error = None
            except Exception as exc:  # noqa: BLE001
                rows, error = None, f'{type(exc).__name__}: {exc}'
            run_on_qt_thread(self.owner, lambda: self._loaded_plugins(rows, error))
        try:
            threading.Thread(target=work, name='desktop-plugin-registry', daemon=True).start()
        except RuntimeError as exc:
            self._loaded_plugins(None, str(exc))

    def _loaded_plugins(self, rows, error):
        self.loading = False; self.records = rows; self.reload_button.setEnabled(True)
        if error:
            print(f'[JARVIS] Plugin registry unavailable: {error}')
            self.plugin_status.setText(tr('Registri plugin tidak dapat dibaca.', 'Plugin registry could not be read.'))
        else:
            self.plugin_status.setText(tr('Tidak ada plugin terdaftar.', 'No plugins registered.') if not rows else '')
        self._render_plugins()
        if self.reload_requested:
            self.reload_requested = False; self.refresh_plugins()

    def move_page(self, delta):
        if not self.loading and self.records is not None:
            self.page_index += delta; self._render_plugins()

    def _render_plugins(self):
        while self.list_layout.count():
            widget = self.list_layout.takeAt(0).widget()
            if widget: widget.deleteLater()
        self.cards = []
        rows = self.records or []
        pages = max(1, (len(rows) + 3) // 4)
        self.page_index = max(0, min(self.page_index, pages - 1))
        counts = Counter(str(row.get('name') or '') for row in rows)
        for row in rows[self.page_index*4:(self.page_index+1)*4]:
            name = str(row.get('name') or '')
            permissions = row.get('permissions')
            valid = bool(name and counts[name] == 1 and row.get('valid') is True and isinstance(row.get('enabled'), bool) and
                         isinstance(permissions, (list, tuple)) and all(isinstance(p, str) for p in permissions))
            state = (tr('Diaktifkan dalam konfigurasi', 'Enabled in configuration') if row.get('enabled') else
                     tr('Dinonaktifkan dalam konfigurasi', 'Disabled in configuration')) if valid else tr('Tidak dapat dikelola', 'Cannot be managed')
            declared = ', '.join(permissions) if valid and permissions else tr('Tidak ada yang dideklarasikan', 'None declared') if valid else str(row.get('error') or tr('Data registri tidak valid atau nama ganda', 'Invalid registry data or duplicate name'))
            card, content = self.panel(name or '—', str(row.get('description') or ''))
            prefix = tr('Izin dideklarasikan: ', 'Declared permissions: ') if valid else ''
            label = heading(state + ' · ' + prefix + declared, 'desktopHint'); label.setWordWrap(True); content.addWidget(label)
            if row.get('manifest_note'):
                note = heading(str(row['manifest_note']), 'desktopHint'); note.setWordWrap(True); content.addWidget(note)
            self.list_layout.addWidget(card); self.cards.append(card)
        self.page_label.setText(tr(f'Halaman {self.page_index+1} / {pages} · {len(rows)} plugin',
                                   f'Page {self.page_index+1} / {pages} · {len(rows)} plugins') if self.records is not None else tr('Jumlah tidak diketahui', 'Count unknown'))
        self.prev.setEnabled(not self.loading and self.records is not None and self.page_index > 0)
        self.next.setEnabled(not self.loading and self.records is not None and self.page_index+1 < pages)
