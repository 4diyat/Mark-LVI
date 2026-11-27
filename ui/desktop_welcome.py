"""Optional first-use guide: information only, not a microphone permission gate."""
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ui.hud_pages import heading, tr


class WelcomePage(QWidget):
    def __init__(self, shell, finish):
        super().__init__()
        self.shell, self.finish = shell, finish
        self.index = 0
        self.setObjectName('desktopPage')
        root = QVBoxLayout(self); root.setContentsMargins(0, 0, 0, 0); root.setSpacing(14)
        brand = QHBoxLayout()
        art = QLabel()
        from ui.brand_art import brand_pixmap
        art.setPixmap(brand_pixmap(100))
        brand.addWidget(art)
        titles = QVBoxLayout()
        titles.addWidget(heading(str(getattr(shell, '_assistant_name', '') or 'JARVIS'), 'desktopBrand'))
        titles.addWidget(heading(tr('PANDUAN AWAL', 'GETTING STARTED'), 'desktopEyebrow'))
        brand.addLayout(titles); brand.addStretch(); root.addLayout(brand)
        self.progress = heading('', 'routineTime'); root.addWidget(self.progress)
        card = QFrame(); card.setObjectName('settingsCard')
        body = QVBoxLayout(card); body.setContentsMargins(24, 22, 24, 22); body.setSpacing(15)
        self.title = heading('', 'desktopSubheading'); body.addWidget(self.title)
        self.intro = heading('', 'desktopMuted'); self.intro.setWordWrap(True); body.addWidget(self.intro)
        self.points = []
        for _ in range(3):
            label = heading('', 'desktopMuted'); label.setWordWrap(True); body.addWidget(label); self.points.append(label)
        self.action = QPushButton(); self.action.setObjectName('workspaceButton'); self.action.clicked.connect(self.open_related)
        body.addWidget(self.action, 0, Qt.AlignmentFlag.AlignLeft)
        root.addWidget(card)
        self.status = heading('', 'workspaceStatus'); self.status.setWordWrap(True); root.addWidget(self.status)
        nav = QHBoxLayout()
        self.back = QPushButton(tr('Kembali', 'Back')); self.back.setObjectName('workspaceButton'); self.back.clicked.connect(self.previous)
        self.next = QPushButton(); self.next.setObjectName('workspaceButton'); self.next.clicked.connect(self.advance)
        nav.addWidget(self.back); nav.addStretch(); nav.addWidget(self.next); root.addLayout(nav)
        root.addStretch(); self.render()

    def render(self):
        steps = [
            (tr('Selamat datang', 'Welcome'),
             tr('Panduan ini dapat dibuka kapan saja dan tidak mengubah izin secara otomatis.', 'This guide can be reopened and does not change permissions automatically.'),
             [tr('Kunci API dikonfigurasi melalui layar setup terpisah.', 'The API key is configured in the separate setup screen.'),
              tr('Koneksi dan kemampuan perangkat bergantung pada sesi dan sistem Anda.', 'Connections and device capabilities depend on your session and system.'),
              tr('Lanjutkan untuk mengenal suara, presensi, dan pengaturan.', 'Continue to learn about voice, presence and settings.')]),
            (tr('Mikrofon dan suara', 'Microphone and voice'),
             tr('Aplikasi tidak dapat memastikan atau mengubah izin mikrofon sistem dari panduan ini.', 'This guide cannot determine or change system microphone permission.'),
             [tr('Periksa izin mikrofon di pengaturan sistem operasi Anda.', 'Check microphone permissions in your operating system settings.'),
              tr('Input suara dapat dikirim ke layanan AI saat sesi tersambung.', 'Voice input may be sent to the AI service while a session is connected.'),
              tr('Melewati halaman ini tidak mematikan mikrofon aplikasi.', 'Skipping this page does not turn off the application microphone.')]),
            (tr('Mode presensi', 'Presence mode'),
             tr('Aktif, Fokus, dan Senyap mengatur cara aplikasi menampilkan kehadiran dan saran; bukan izin mikrofon.', 'Active, Focus and Quiet affect presence and suggestions; they are not microphone permissions.'),
             [tr('Aktif menampilkan saran; Fokus menahan saran.', 'Active shows suggestions; Focus holds suggestions.'),
              tr('Senyap menekan banner, tetapi tidak mematikan sesi.', 'Quiet suppresses banners but does not turn off the session.'),
              tr('Pilih mode melalui panel baki, jika tersedia.', 'Choose a mode in the tray panel, when available.')]),
            (tr('Siap menjelajah', 'Ready to explore'),
             tr('Panduan selesai. Ini bukan konfirmasi bahwa izin atau koneksi telah berhasil.', 'Guide complete. This is not confirmation of permissions or a successful connection.'),
             [tr('Pengaturan menyediakan pilihan panel dan aksesibilitas.', 'Settings provides panel and accessibility options.'),
              tr('Keamanan menampilkan kebijakan dan catatan yang tersedia.', 'Security displays available policies and records.'),
              tr('Anda dapat kembali ke panduan ini dari ruang kerja.', 'You can return to this guide from the workspace.')]),
        ]
        title, intro, points = steps[self.index]
        self.progress.setText(tr(f'LANGKAH {self.index + 1} / 4', f'STEP {self.index + 1} / 4'))
        self.title.setText(title); self.intro.setText(intro)
        for label, text in zip(self.points, points): label.setText('•  ' + text)
        self.back.setEnabled(self.index > 0)
        self.next.setText(tr('Selesai', 'Finish') if self.index == 3 else tr('Lanjut', 'Next'))
        self.action.setVisible(self.index == 2)
        self.action.setText(tr('Buka panel presensi', 'Open presence panel'))
        self.status.clear()

    def advance(self):
        if self.index == 3:
            self.finish(); return
        self.index += 1; self.render()

    def previous(self):
        if self.index:
            self.index -= 1; self.render()

    def open_related(self):
        from ui.tray_panel_wiring import open_panel
        if not open_panel(self.shell):
            self.status.setText(tr('Panel presensi tidak dapat dibuka.', 'Could not open presence panel.'))
        else:
            self.status.setText(tr('Panel dibuka; pilih mode di sana.', 'Panel opened; choose a mode there.'))
