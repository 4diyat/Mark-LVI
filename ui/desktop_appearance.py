"""Tray-only appearance controls, with asynchronous checked persistence."""
import threading

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QPushButton, QVBoxLayout, QWidget

from ui.hud_pages import heading, tr
from ui.qt_thread import run_on_qt_thread


class AppearancePage(QWidget):
    def __init__(self, shell):
        super().__init__(); self.shell = shell; self.owner = threading.get_ident(); self.busy = False
        self.setObjectName('desktopPage')
        root = QVBoxLayout(self); root.setContentsMargins(0, 0, 0, 0); root.setSpacing(14)
        root.addWidget(heading(tr('Tema panel baki', 'Tray panel theme'), 'desktopSubheading'))
        desc = heading(tr('Pilihan ini hanya mengubah panel baki. Ruang kerja, layar utama, dan overlay tetap gelap.',
                          'This changes the tray panel only. The workspace, home screen and overlays remain dark.'), 'desktopMuted')
        desc.setWordWrap(True); root.addWidget(desc)
        card = QFrame(); card.setObjectName('settingsCard')
        box = QVBoxLayout(card); box.setContentsMargins(20, 18, 20, 18); box.setSpacing(12)
        box.addWidget(heading(tr('Pilih tampilan', 'Choose appearance'), 'desktopCardTitle'))
        buttons = QHBoxLayout(); self.buttons = {}
        for value, label in (('dark', tr('Gelap', 'Dark')), ('light', tr('Terang', 'Light')), ('auto', tr('Otomatis', 'Auto'))):
            b = QPushButton(label); b.setObjectName('workspaceButton'); b.setCheckable(True)
            b.clicked.connect(lambda checked=False, name=value: self.save(name))
            self.buttons[value] = b; buttons.addWidget(b)
        buttons.addStretch(); box.addLayout(buttons)
        self.current = heading('', 'routineTime'); self.current.setWordWrap(True); box.addWidget(self.current)
        note = heading(tr('Otomatis memakai preferensi tema yang tersimpan di konfigurasi; jika tidak ada, gelap. Bukan deteksi langsung tema sistem. Kontras tinggi panel dapat mengesampingkan warna tema.',
                          'Auto uses a stored system-theme preference; if absent it uses dark. It is not live OS theme detection. Tray high contrast may override theme colors.'), 'desktopMuted')
        note.setWordWrap(True); box.addWidget(note); root.addWidget(card)
        self.status = heading('', 'workspaceStatus'); self.status.setWordWrap(True); root.addWidget(self.status)
        self.open_button = QPushButton(tr('Buka panel baki', 'Open tray panel'))
        self.open_button.setObjectName('workspaceButton'); self.open_button.clicked.connect(self.open_panel)
        root.addWidget(self.open_button, 0, Qt.AlignmentFlag.AlignLeft); root.addStretch()

    def _enable(self, value):
        self.busy = not value
        for button in self.buttons.values(): button.setEnabled(value)

    def refresh(self):
        if self.busy: return
        self._enable(False); self.status.setText(tr('Memuat tema…', 'Loading theme…'))
        def work():
            try:
                from memory.config_manager import get_ui_theme, get_high_contrast
                from ui.tray_theme import resolve_theme
                name = get_ui_theme(); resolved = resolve_theme(name); high = get_high_contrast()
                error = None
            except Exception as exc:  # noqa: BLE001
                name, resolved, high, error = None, None, False, str(exc)
            run_on_qt_thread(self.owner, lambda: self._loaded(name, resolved, high, error))
        self._start(work)

    def _start(self, work):
        try:
            threading.Thread(target=work, name='tray-theme-setting', daemon=True).start()
        except RuntimeError as exc:
            self._enable(True); self.status.setText(tr('Pekerja tema tidak tersedia.', 'Theme worker unavailable.'))
            print(f'[JARVIS] Theme worker unavailable: {exc}')

    def _loaded(self, name, resolved, high, error):
        self._enable(True)
        if error:
            self.status.setText(tr('Tema tidak dapat dibaca.', 'Could not read theme.'))
            for b in self.buttons.values(): b.setChecked(False)
            return
        for value, b in self.buttons.items(): b.setChecked(value == name)
        names = {'dark': tr('Gelap', 'Dark'), 'light': tr('Terang', 'Light'), 'auto': tr('Otomatis', 'Auto')}
        self.current.setText(tr('Tersimpan: ', 'Saved: ') + names[name] + ' · ' + tr('Palet: ', 'Palette: ') +
                             (tr('Kontras tinggi', 'High contrast') if high else names[resolved]))
        self.status.clear()

    def save(self, name):
        if self.busy or name not in self.buttons: return
        self._enable(False); self.status.setText(tr('Menyimpan…', 'Saving…'))
        def work():
            try:
                from memory.config_manager import set_config_values, get_ui_theme, get_high_contrast
                from ui.tray_theme import resolve_theme
                ok = bool(set_config_values(ui_theme=name))
                actual = get_ui_theme(); resolved = resolve_theme(actual); high = get_high_contrast()
                error = None
            except Exception as exc:  # noqa: BLE001
                ok, actual, resolved, high, error = False, None, None, False, str(exc)
            run_on_qt_thread(self.owner, lambda: self._saved(name, ok, actual, resolved, high, error))
        self._start(work)

    def _saved(self, requested, ok, actual, resolved, high, error):
        self._loaded(actual, resolved, high, error)
        if not ok or actual != requested or error:
            self.status.setText(tr('Tema tidak tersimpan; periksa konfigurasi.', 'Theme was not saved; check configuration.'))
            return
        panel = getattr(self.shell, '_panel', None)
        if panel is not None:
            try:
                if not panel.set_theme(actual):
                    raise RuntimeError('tray refused the theme')
            except Exception as exc:  # noqa: BLE001
                print(f'[JARVIS] Tray theme not applied: {exc}')
                self.status.setText(tr('Tema tersimpan; panel tidak dapat diperbarui.', 'Theme saved; tray panel could not be updated.'))
                return
        self.status.setText(tr('Tema panel tersimpan.', 'Tray theme saved.'))

    def open_panel(self):
        from ui.tray_panel_wiring import open_panel
        if not open_panel(self.shell):
            self.status.setText(tr('Panel baki tidak dapat dibuka.', 'Could not open the tray panel.'))
