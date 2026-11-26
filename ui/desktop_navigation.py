"""Desktop navigation foundation, reusing the existing home and module surfaces.

Future sections are clearly disabled until their staged desktop implementations
exist. No tray page or memory operation is replaced by this navigation shell.
"""
from __future__ import annotations

import threading
from pathlib import Path

from PyQt6.QtCore import QSize, Qt, QTimer
from PyQt6.QtGui import QFont, QFontDatabase
from PyQt6.QtWidgets import (QApplication, QFrame, QHBoxLayout, QLabel, QPushButton,
                             QScrollArea, QStackedWidget, QVBoxLayout, QWidget)

from ui.hud_icons import icon
from ui.hud_metrics import MetricsSampler
from ui.hud_orb import MiniOrb
from ui.hud_pages import Metric, ModulesPage, heading, tr


class DesktopWindow(QWidget):
    def __init__(self, on_user_close):
        super().__init__()
        self.on_user_close = on_user_close
        self.closing_for_shutdown = False

    def closeEvent(self, event):  # noqa: N802
        super().closeEvent(event)
        if not self.closing_for_shutdown:
            QTimer.singleShot(0, self.on_user_close)


class DesktopWorkspace:
    """One reusable Qt desktop window with working, explicit navigation."""

    def __init__(self, shell):
        self.shell = shell
        self.owner = threading.get_ident()
        self.window = DesktopWindow(self.return_home)
        self.window.setObjectName('desktop')
        self.window.setWindowTitle(tr('JARVIS — Ruang kerja', 'JARVIS — Workspace'))
        self.window.resize(1360, 850)
        self.window.setMinimumSize(900, 600)
        font_path = Path(__file__).resolve().parent.parent / 'assets/fonts/SpaceGrotesk-Variable.ttf'
        font_id = QFontDatabase.addApplicationFont(str(font_path))
        families = QFontDatabase.applicationFontFamilies(font_id) if font_id >= 0 else []
        if families:
            self.window.setFont(QFont(families[0], 10))
        self._build()
        self.sampler = MetricsSampler(self.owner, self._update_metrics)
        self.status_timer = QTimer(self.window)
        self.status_timer.setInterval(1000)
        self.status_timer.timeout.connect(self._update_session)
        self._update_session()
        self.navigate('dashboard')

    def _build(self):
        root = QHBoxLayout(self.window)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(18)
        sidebar = QFrame()
        sidebar.setObjectName('desktopSide')
        sidebar.setFixedWidth(235)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(16, 20, 16, 16)
        side.setSpacing(10)
        brand_row = QHBoxLayout()
        self.brand_avatar = MiniOrb()
        brand_row.addWidget(self.brand_avatar)
        brand = QVBoxLayout()
        name = heading(str(getattr(self.shell, '_assistant_name', '') or 'JARVIS'), 'desktopBrand')
        brand.addWidget(name)
        brand.addWidget(heading(tr('ASISTEN AI', 'AI ASSISTANT'), 'desktopEyebrow'))
        brand_row.addLayout(brand, 1)
        side.addLayout(brand_row)
        side.addSpacing(18)
        nav_scroll = QScrollArea()
        nav_scroll.setWidgetResizable(True)
        nav_scroll.setFrameShape(QFrame.Shape.NoFrame)
        nav_body = QWidget()
        nav_body.setObjectName('navBody')
        nav = QVBoxLayout(nav_body)
        nav.setContentsMargins(0, 0, 0, 0)
        nav.setSpacing(5)
        self.buttons = {}
        specs = [
            ('dashboard', tr('Beranda', 'Home'), 'house', True),
            ('chat', tr('Obrolan', 'Chat'), 'message-circle', True),
            ('modules', tr('Modul', 'Modules'), 'layout-grid', True),
            ('history', tr('Riwayat', 'History'), 'clock-3', True),
            ('memory', tr('Memori', 'Memory'), 'brain', True),
            ('routines', tr('Rutinitas', 'Routines'), 'calendar', True),
            ('tools', tr('Alat', 'Tools'), 'wrench', True),
            ('security', tr('Keamanan', 'Security'), 'shield', True),
            ('settings', tr('Pengaturan', 'Settings'), 'settings', True),
        ]
        for key, label, symbol, available in specs:
            button = QPushButton(label)
            button.setObjectName('sideNav')
            button.setCheckable(True)
            button.setIcon(icon(symbol, '#9ebbd7', 20))
            button.setIconSize(QSize(20, 20))
            button.setMinimumHeight(45)
            button.clicked.connect(lambda checked=False, page=key: self.navigate(page))
            if not available:
                button.setEnabled(False)
                button.setToolTip(tr('Halaman desktop tersedia pada tahap berikutnya.',
                                     'This desktop page is available in a later stage.'))
            self.buttons[key] = button
            nav.addWidget(button)
        hint = heading(tr('Fitur panel dan pengaturan lanjut tetap dapat dibuka dari baki.',
                          'Panel features and advanced settings remain available from the tray.'), 'desktopHint')
        hint.setWordWrap(True)
        nav.addSpacing(12)
        nav.addWidget(hint)
        nav.addStretch()
        nav_scroll.setWidget(nav_body)
        side.addWidget(nav_scroll, 1)
        session_card = QFrame()
        session_card.setObjectName('sessionCard')
        session = QHBoxLayout(session_card)
        session.setContentsMargins(10, 10, 10, 10)
        self.avatar = MiniOrb()
        session.addWidget(self.avatar)
        session_text = QVBoxLayout()
        session_text.addWidget(heading(str(getattr(self.shell, '_assistant_name', '') or 'JARVIS'), 'sideTitle'))
        self.status = heading('', 'sideStatus')
        self.status.setWordWrap(True)
        session_text.addWidget(self.status)
        session.addLayout(session_text, 1)
        side.addWidget(session_card)
        root.addWidget(sidebar)

        frame = QFrame()
        frame.setObjectName('desktopContent')
        content = QVBoxLayout(frame)
        content.setContentsMargins(30, 26, 30, 26)
        self.stack = QStackedWidget()
        self.modules = ModulesPage(self._module_draft, lambda: self.navigate('memory'))
        self.modules.setObjectName('desktopPage')
        from ui.desktop_history import HistoryPage
        from ui.desktop_memory import MemoryPage
        from ui.desktop_security import SecurityPage
        from ui.desktop_routines import RoutinesPage
        from ui.desktop_tools import ToolsPage
        from ui.desktop_settings import SettingsPage
        from ui.desktop_welcome import WelcomePage
        self.history = HistoryPage(self.window)
        self.memory = MemoryPage(self.window)
        self.security = SecurityPage(self.shell, self.window, lambda: self.navigate('memory'))
        self.routines = RoutinesPage(self.window)
        self.tools = ToolsPage(self._tool_draft, self.open_chat)
        self.settings = SettingsPage(self.shell)
        self.welcome = WelcomePage(self.shell, lambda: self.navigate('dashboard'))
        self.pages = {'dashboard': self._dashboard(), 'modules': self.modules,
                      'history': self.history, 'memory': self.memory, 'security': self.security,
                      'routines': self.routines, 'tools': self.tools, 'settings': self.settings, 'welcome': self.welcome}
        for page in self.pages.values():
            scroll = QScrollArea()
            scroll.setObjectName('desktopScroll')
            scroll.setFrameShape(QFrame.Shape.NoFrame)
            scroll.setWidgetResizable(True)
            scroll.setWidget(page)
            self.stack.addWidget(scroll)
        content.addWidget(self.stack)
        root.addWidget(frame, 1)
        self.window.setStyleSheet(_STYLE)

    def _dashboard(self):
        page = QWidget()
        page.setObjectName('desktopPage')
        box = QVBoxLayout(page)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(18)
        box.addWidget(heading(tr('Ruang kerja', 'Workspace'), 'desktopHeading'))
        description = heading(tr('Akses percakapan dan ringkasan perangkat dari satu tempat.',
                                 'Access your conversation and device overview in one place.'), 'desktopMuted')
        description.setWordWrap(True)
        box.addWidget(description)
        box.addSpacing(12)
        box.addWidget(heading(tr('AKSES CEPAT', 'QUICK ACCESS'), 'desktopEyebrow'))
        cards = QHBoxLayout()
        cards.setSpacing(14)
        for title, description, glyph, callback in (
            (tr('Layar utama', 'Main screen'), tr('Kembali ke orb dan percakapan.', 'Return to the orb and conversation.'),
             'circle-dot', self.return_home),
            (tr('Obrolan', 'Chat'), tr('Buka percakapan sesi saat ini.', 'Open the current session conversation.'),
             'message-circle', self.open_chat),
            (tr('Modul', 'Modules'), tr('Lihat status perangkat dan modul inti.', 'View device status and core modules.'),
             'layout-grid', lambda: self.navigate('modules')),
        ):
            card = QPushButton()
            card.setObjectName('desktopAction')
            card.setAccessibleName(title)
            card.setMinimumHeight(150)
            card.clicked.connect(callback)
            layout = QVBoxLayout(card)
            layout.setContentsMargins(18, 18, 18, 18)
            glyph_label = QLabel()
            glyph_label.setPixmap(icon(glyph, '#70bdff', 26).pixmap(QSize(26, 26)))
            layout.addWidget(glyph_label)
            title_label = heading(title, 'desktopCardTitle')
            layout.addWidget(title_label)
            sub = heading(description, 'desktopMuted')
            sub.setWordWrap(True)
            layout.addWidget(sub)
            layout.addStretch()
            for widget in (glyph_label, title_label, sub):
                widget.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            cards.addWidget(card, 1)
        box.addLayout(cards)
        command = QPushButton(tr('Buka bar perintah', 'Open command bar'))
        command.setObjectName('workspaceButton')
        command.clicked.connect(self._open_command_bar)
        quick = QHBoxLayout(); quick.addWidget(command)
        guide = QPushButton(tr('Panduan awal', 'Getting started'))
        guide.setObjectName('workspaceButton'); guide.clicked.connect(lambda: self.navigate('welcome'))
        quick.addWidget(guide); quick.addStretch(); box.addLayout(quick)
        box.addSpacing(12)
        box.addWidget(heading(tr('RINGKASAN PERANGKAT', 'DEVICE OVERVIEW'), 'desktopEyebrow'))
        metrics = QHBoxLayout()
        self.cpu = Metric('CPU')
        self.ram = Metric('RAM')
        self.ping = Metric('PING')
        for metric in (self.cpu, self.ram, self.ping):
            metrics.addWidget(metric, 1)
        box.addLayout(metrics)
        info = heading(tr('CPU dan RAM dibaca dari perangkat ini. Ping tidak tersedia.',
                          'CPU and RAM are read from this device. Ping is unavailable.'), 'desktopMuted')
        info.setWordWrap(True)
        box.addWidget(info)
        box.addStretch(1)
        return page

    def _update_session(self):
        connected = None
        getter = getattr(self.shell, 'get_session_connected', None)
        if callable(getter):
            try:
                value = getter()
                connected = None if value is None else bool(value)
            except Exception as exc:  # noqa: BLE001
                print(f'[JARVIS] Session status unavailable: {type(exc).__name__}: {exc}')
        self.avatar.set_connected(connected)
        self.brand_avatar.set_connected(connected)
        if connected is True:
            text = tr('Sesi aktif', 'Session active')
        elif connected is False:
            text = tr('Sesi tidak tersambung', 'Session disconnected')
        else:
            text = tr('Status sesi tidak diketahui', 'Session status unknown')
        self.status.setText(text)

    def _update_metrics(self, cpu, ram):
        self.cpu.set_value(cpu)
        self.ram.set_value(ram)
        self.modules.update_values(cpu, ram)

    def current_page(self):
        return tuple(self.pages)[self.stack.currentIndex()]

    def navigate(self, page):
        if self.current_page() == 'tools' and page != 'tools':
            self.tools.leave()
        if page == 'chat':
            self.open_chat()
            return
        if page not in self.pages:
            return
        self.stack.setCurrentIndex(tuple(self.pages).index(page))
        if page in ('history', 'memory', 'security', 'routines', 'settings'):
            self.pages[page].refresh()
        for key, button in self.buttons.items():
            button.setChecked(key == page)

    def return_home(self):
        from ui.main_surface import open_main
        if open_main(self.shell):
            self.shell._main_surface.navigate('orb')
            self.hide()

    def open_chat(self):
        self.return_home()
        main = getattr(self.shell, '_main_surface', None)
        if main is not None and main.window.isVisible():
            main.field.setFocus()

    def _open_command_bar(self):
        from ui.ambient_shell import open_command_bar
        open_command_bar(self.shell)

    def _tool_draft(self, prompt):
        self.return_home()
        main = getattr(self.shell, '_main_surface', None)
        if main is not None and main.window.isVisible():
            main.navigate('orb')
            if not main.field.text().strip():
                main.field.setText(prompt)
            main.field.setFocus()

    def _module_draft(self, key):
        self.return_home()
        main = getattr(self.shell, '_main_surface', None)
        if main is not None and main.window.isVisible():
            main.module_draft(key)

    def show(self):
        self.window.closing_for_shutdown = False
        self.sampler.start()
        self._update_session()
        self.status_timer.start()
        self.window.show()
        self.window.raise_()
        self.window.activateWindow()

    def hide(self):
        if self.current_page() == 'tools':
            self.tools.leave()
        self.sampler.stop()
        self.status_timer.stop()
        self.window.hide()

    def close(self):
        if self.current_page() == 'tools':
            self.tools.leave()
        self.window.closing_for_shutdown = True
        self.sampler.stop()
        self.status_timer.stop()
        self.window.close()


def open_desktop(shell, page=None):
    """Open the workspace, keeping the existing home alive and its draft intact."""
    if QApplication.instance() is None:
        return False
    try:
        from ui.qt_thread import init_dispatcher
        init_dispatcher()
        workspace = getattr(shell, '_desktop_workspace', None)
        if workspace is None:
            workspace = DesktopWorkspace(shell)
            shell._desktop_workspace = workspace
        workspace.show()
        if page is not None:
            workspace.navigate(page)
        home = getattr(shell, '_main_surface', None)
        if home is not None:
            home.sampler.stop()
            home.window.hide()
        return True
    except Exception as exc:  # noqa: BLE001
        print(f'[JARVIS] Workspace unavailable: {type(exc).__name__}: {exc}')
        return False


_STYLE = '''
QWidget#desktop { background:#050a12; color:#f1f6fd; }
QFrame#desktopSide, QFrame#desktopContent { background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #111c29,stop:1 #080e17); border:1px solid #344458; border-radius:18px; }
QWidget#navBody, QWidget#desktopPage, QWidget#securityList, QScrollArea { background:transparent; border:0; }
QLabel { color:#e9f3ff; background:transparent; }
QLabel#desktopBrand { color:#74c2ff; font-size:21px; font-weight:700; letter-spacing:3px; }
QLabel#desktopEyebrow { color:#a9bbce; font-size:11px; font-weight:600; letter-spacing:1px; }
QLabel#desktopHeading, QLabel#pageTitle { color:#f3f8ff; font-size:32px; font-weight:700; }
QLabel#desktopHint { color:#a4b5c7; font-size:12px; }
QLabel#desktopMuted, QLabel#muted { color:#b9c8d9; font-size:14px; }
QLabel#desktopCardTitle, QLabel#cardTitle { color:#ecf6ff; font-size:17px; font-weight:600; }
QLabel#sideTitle { font-size:14px; font-weight:600; }
QLabel#sideStatus { color:#b5c7d8; font-size:12px; }
QLabel#accentIcon { color:#70bfff; font-size:22px; }
QLabel#eyebrow { color:#aebfd0; font-size:11px; }
QLabel#metricValue { color:#d5edff; font-size:15px; font-weight:600; }
QFrame#settingsCard, QFrame#toolPanel, QFrame#routineCard, QFrame#routineBuilder { background:#111f2e; border:1px solid #3b5065; border-radius:12px; }
QLabel#routineTime { color:#8ccfff; font-size:14px; }
QLineEdit#routineInput { background:#0b1623; color:#e9f3ff; border:1px solid #46627c; border-radius:8px; padding:10px; }
QFrame#securityPanel { background:#0d1824; border:1px solid #354a60; border-radius:14px; }
QFrame#securityRisk, QFrame#securityInfo, QFrame#securityEvent { background:#142231; border:1px solid #3c5267; border-radius:10px; }
QFrame#securityRisk[risk="safe"] { border-color:#386e5b; background:#132a29; }
QFrame#securityRisk[risk="medium"] { border-color:#776344; background:#29281f; }
QFrame#securityRisk[risk="risky"] { border-color:#754b51; background:#2a2027; }
QLabel#securityCount { font-size:24px; font-weight:700; }
QLabel#desktopSubheading { font-size:23px; font-weight:700; }
QComboBox#securityFilter { color:#deecf9; background:#162435; border:1px solid #405b75; border-radius:8px; padding:7px 12px; }
QFrame#historyCard, QFrame#memoryCard { background:#111e2c; border:1px solid #354a60; border-radius:12px; }
QLabel#memoryCategory, QLabel#workspaceCount { color:#88caff; border:1px solid #385f82; border-radius:10px; padding:7px 10px; }
QLabel#memoryValue { color:#ecf6ff; font-size:15px; }
QLabel#memoryDetails, QLabel#workspaceStatus { color:#c0d0e0; font-size:14px; }
QLabel#memoryDetails { background:#0b1723; border:1px solid #30485d; border-radius:10px; padding:14px; }
QLabel#workspaceIcon { background:#142b41; border:1px solid #2a4c6c; border-radius:10px; }
QPushButton#workspaceButton, QPushButton#expand, QPushButton#danger { color:#d3e8fa; background:#15283c; border:1px solid #456887; border-radius:9px; padding:9px 14px; }
QPushButton#workspaceButton:hover, QPushButton#expand:hover { border-color:#78bfff; }
QPushButton#workspaceButton:checked { color:#edf7ff; background:#1d4e7d; border-color:#69bfff; }
QCheckBox { color:#d1e5f6; font-size:14px; spacing:8px; }
QCheckBox::indicator { width:16px; height:16px; border:1px solid #7392ae; border-radius:4px; background:#101b2b; }
QCheckBox::indicator:checked { background:#328ee9; border-color:#8dd0ff; }
QPushButton#danger { color:#ffb27d; border-color:#966244; background:#291e1a; }
QPushButton#workspaceButton:disabled, QPushButton#danger:disabled { color:#75889c; border-color:#344253; background:#121d29; }
QMessageBox { background:#101c2b; color:#edf6ff; }
QMessageBox QPushButton { color:#edf6ff; background:#1c344d; border:1px solid #587693; border-radius:8px; padding:8px 18px; }
QMessageBox QPushButton:hover { border-color:#81c9ff; }
QLineEdit#workspaceSearch { color:#edf6ff; background:#0c1724; border:1px solid #3a536d; border-radius:10px; padding:9px 14px; min-width:220px; }
QFrame#sessionCard { background:#101b29; border:1px solid #334b63; border-radius:12px; }
QPushButton#sideNav { background:transparent; border:1px solid transparent; border-radius:10px; color:#c3d1df; text-align:left; padding:8px 13px; font-size:14px; }
QPushButton#sideNav:hover { background:#14283e; }
QPushButton#sideNav:checked { background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #16457b,stop:1 #112235); border:1px solid #3d8bd0; color:#e1f3ff; }
QPushButton#sideNav:disabled { color:#748498; }
QPushButton#desktopAction, QPushButton#moduleCard, QFrame#metric { background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 #162536,stop:1 #0c1520); border:1px solid #354a60; border-radius:12px; text-align:left; }
QPushButton#desktopAction:hover, QPushButton#moduleCard:hover { border-color:#5ab5ff; background:#182f48; }
QPushButton#moduleCard:disabled { background:#0d1721; border-color:#293948; }
QProgressBar { background:#253d51; border:0; border-radius:3px; }
QProgressBar::chunk { background:#52b7ff; border-radius:3px; }
QScrollBar:vertical { background:#101b28; width:8px; margin:0; }
QScrollBar::handle:vertical { background:#526d88; border-radius:4px; min-height:30px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0; }
'''
