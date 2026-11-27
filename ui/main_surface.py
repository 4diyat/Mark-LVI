"""Desktop home: a two-zone ambient orb and a real session interaction panel."""
from __future__ import annotations

import math
import threading
import time
from datetime import datetime
from html import escape
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer, QSize
from PyQt6.QtGui import QColor, QFont, QFontDatabase, QPalette
from PyQt6.QtWidgets import (QApplication, QCheckBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QMenu,
                             QPushButton, QScrollArea, QStackedWidget, QTextBrowser, QVBoxLayout, QWidget)

from ui.hud_icons import icon
from ui.hud_metrics import MetricsSampler
from ui.hud_orb import MicButton, MiniOrb, OrbCore, Waveform
from ui.hud_pages import ModulesPage, QuickAction, SystemCard, heading, tr
from ui.hud_style import STYLE
from ui.tray_panel_model import _t


class MainWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.on_close = None
        self.on_resize = None

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        if self.on_resize:
            self.on_resize()

    def closeEvent(self, event):  # noqa: N802
        if self.on_close:
            self.on_close()
        super().closeEvent(event)


class MainSurface:
    def __init__(self, shell):
        self.shell = shell
        self.owner = threading.get_ident()
        self.messages = []
        self.message_times = []
        self.sending = False
        self._last_connection = None
        self.state = 'initialising'
        self.window = MainWindow()
        self.window.setObjectName('mainSurface')
        self.window.setWindowTitle(_t('ui.main.title'))
        self.window.resize(1440, 900)
        self.window.setMinimumSize(1000, 650)
        path = Path(__file__).resolve().parent.parent / 'assets/fonts/SpaceGrotesk-Variable.ttf'
        font_id = QFontDatabase.addApplicationFont(str(path))
        families = QFontDatabase.applicationFontFamilies(font_id) if font_id >= 0 else []
        if families:
            self.window.setFont(QFont(families[0], 10))
        self._build()
        self.window.on_resize = self._resize_view
        self.sampler = MetricsSampler(self.owner, self.update_metrics)
        self.window.on_close = self.sampler.stop
        self.sampler.start()
        self.mic_refresh = QTimer(self.window)
        self.mic_refresh.timeout.connect(self.refresh_mic)
        self.mic_refresh.start(500)
        self.set_state(getattr(shell, '_state', 'INITIALISING'))
        self._render_messages()

    def _build(self):
        root = QHBoxLayout(self.window)
        root.setContentsMargins(30, 24, 25, 24)
        root.setSpacing(22)
        left = QVBoxLayout()
        left.setSpacing(16)
        self.toast = self._make_toast()
        left.addWidget(self.toast, 0, Qt.AlignmentFlag.AlignLeft)
        panel = QFrame()
        panel.setObjectName('homePanel')
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(20, 18, 20, 20)
        panel_layout.setSpacing(14)
        header, brand = QHBoxLayout(), QVBoxLayout()
        brand.setSpacing(0)
        logo = heading(str(getattr(self.shell, '_assistant_name', '') or 'JARVIS'), 'brand')
        font_id = QFontDatabase.addApplicationFont(str(Path(__file__).resolve().parent.parent /
                                                   'assets/fonts/Orbitron-Variable.ttf'))
        families = QFontDatabase.applicationFontFamilies(font_id) if font_id >= 0 else []
        if families:
            logo.setFont(QFont(families[0], 16, QFont.Weight.Bold))
        brand.addWidget(logo)
        brand.addWidget(heading(tr('ASISTEN AI', 'AI ASSISTANT'), 'eyebrow'))
        header.addLayout(brand)
        header.addSpacing(18)
        self.segment = QFrame()
        self.segment.setObjectName('segmented')
        segment_layout = QHBoxLayout(self.segment)
        segment_layout.setContentsMargins(3, 3, 3, 3)
        segment_layout.setSpacing(0)
        self.nav_buttons = {}
        from ui.desktop_navigation import open_desktop
        for key, text, icon_name in (('orb', 'Orb', 'circle-dot'),
                                     ('history', tr('Riwayat', 'History'), 'clock-3'),
                                     ('memory', tr('Memori', 'Memory'), 'brain')):
            button = QPushButton(text)
            button.setIcon(icon(icon_name, '#a8d9ff', 20))
            button.setIconSize(QSize(19, 19))
            button.setObjectName('nav')
            button.setCheckable(True)
            button.setMinimumHeight(48)
            button.clicked.connect(lambda checked=False, page=key: self.navigate(page) if page == 'orb'
                                   else open_desktop(self.shell, page))
            segment_layout.addWidget(button, 1)
            self.nav_buttons[key] = button
        header.addWidget(self.segment, 1)
        panel_layout.addLayout(header)
        self.stack = QStackedWidget()
        self.modules = ModulesPage(self.module_draft, lambda: open_desktop(self.shell, 'memory'))
        module_scroll = QScrollArea()
        module_scroll.setWidgetResizable(True)
        module_scroll.setFrameShape(QFrame.Shape.NoFrame)
        module_scroll.setWidget(self.modules)
        self.home = self._home_page()
        self.pages = {'orb': self.home, 'modules': module_scroll}
        for page in self.pages.values():
            self.stack.addWidget(page)
        panel_layout.addWidget(self.stack, 1)
        left.addWidget(panel, 1)
        root.addLayout(left, 55)
        right = QVBoxLayout()
        right.setContentsMargins(0, 25, 0, 10)
        self.orb = OrbCore()
        self.orb.activated.connect(self.toggle_mic)
        right.addWidget(self.orb, 1)
        self.orb_state = heading('', 'orbState')
        self.orb_state.setAlignment(Qt.AlignmentFlag.AlignCenter)
        right.addWidget(self.orb_state)
        self.wave = Waveform()
        self.wave.setFixedWidth(230)
        right.addWidget(self.wave, 0, Qt.AlignmentFlag.AlignHCenter)
        self.reduce_motion = QCheckBox(tr('Kurangi gerak visual', 'Reduce visual motion'))
        self.reduce_motion.setToolTip(tr('Menghentikan animasi orb dan waveform.',
                                         'Stop the orb and waveform animation.'))
        self.reduce_motion.toggled.connect(self.set_reduced_motion)
        right.addWidget(self.reduce_motion, 0, Qt.AlignmentFlag.AlignHCenter)
        from ui.voice_mode_button import install; install(self, right)
        root.addLayout(right, 45)
        self.window.setStyleSheet(STYLE)
        self.navigate('orb')

    def _make_toast(self):
        toast = QFrame()
        toast.setObjectName('toast')
        toast.setMinimumWidth(470)
        toast.setMaximumWidth(470)
        toast.setMinimumHeight(112)
        row = QHBoxLayout(toast)
        row.setContentsMargins(22, 16, 18, 16)
        self.avatar = MiniOrb()
        row.addWidget(self.avatar)
        text = QVBoxLayout()
        text.setSpacing(2)
        text.addWidget(heading(tr('Status JARVIS', 'JARVIS status'), 'toastTitle'))
        self.status_label = heading('', 'state')
        text.addWidget(self.status_label)
        self.connection_label = heading('', 'connection')
        text.addWidget(self.connection_label)
        row.addLayout(text, 1)
        close = QPushButton()
        close.setIcon(icon('x', '#c0d1e5', 20))
        close.setIconSize(QSize(20, 20))
        close.setFixedSize(28, 28)
        close.setObjectName('closeToast')
        close.setAccessibleName(tr('Tutup notifikasi status', 'Close status notification'))
        close.clicked.connect(toast.hide)
        row.addWidget(close, 0, Qt.AlignmentFlag.AlignTop)
        return toast

    def _home_page(self):
        page = QWidget()
        outer = QVBoxLayout(page)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(10)
        self.home_content = QWidget()
        box = QVBoxLayout(self.home_content)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(10)
        self.home_scroll = QScrollArea()
        self.home_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.home_scroll.setWidgetResizable(True)
        self.home_scroll.setWidget(self.home_content)
        outer.addWidget(self.home_scroll, 1)
        cards = QHBoxLayout()
        cards.setSpacing(10)
        self.cards = {}
        for key, icon_name, color in (('summarize', 'file-text', '#55b7ff'), ('meeting', 'calendar-days', '#ff9c4a'),
                                 ('analyze', 'chart-no-axes-column-increasing', '#55d69c'), ('command', 'zap', '#a89aff')):
            card = QuickAction(_t(f'ui.main.card.{key}'), _t(f'ui.main.card.{key}.desc'),
                               icon_name, color, lambda checked=False, k=key: self.prepare(k))
            self.cards[key] = card
            cards.addWidget(card, 1)
        box.addLayout(cards, 0)
        row = QHBoxLayout()
        row.addWidget(heading(tr('PERCAKAPAN SESI', 'SESSION CONVERSATION'), 'eyebrow'))
        row.addStretch()
        status = QPushButton(tr('Status sistem', 'System status'))
        status.setObjectName('secondary')
        status.clicked.connect(self.show_system_card)
        row.addWidget(status)
        self.modules_button = QPushButton(tr('Modul', 'Modules'))
        self.modules_button.setObjectName('secondary')
        self.modules_button.clicked.connect(lambda: self.navigate('modules'))
        row.addWidget(self.modules_button)
        from ui.desktop_navigation import open_desktop
        self.workspace_button = QPushButton(tr('Ruang kerja', 'Workspace'))
        self.workspace_button.setObjectName('secondary')
        self.workspace_button.clicked.connect(lambda: open_desktop(self.shell))
        row.addWidget(self.workspace_button)
        box.addLayout(row)
        self.chat_stack = QStackedWidget()
        self.empty_panel = self._empty_chat()
        self.chat = QTextBrowser()
        self.chat.setOpenLinks(False)
        self.chat.setOpenExternalLinks(False)
        self.chat.setAccessibleName(_t('ui.panel.chat.title'))
        self.chat_stack.addWidget(self.empty_panel)
        self.chat_stack.addWidget(self.chat)
        self.chat_stack.setMinimumHeight(125)
        box.addWidget(self.chat_stack, 1)
        self.system_card = SystemCard()
        self.system_card.setMinimumHeight(170)
        self.system_card.later.clicked.connect(self.hide_system_card)
        self.system_card.hide()
        box.addWidget(self.system_card)
        self.feedback = heading('', 'feedback')
        self.feedback.setWordWrap(True)
        self.feedback.hide()
        box.addWidget(self.feedback)
        composer = QFrame()
        self.composer = composer
        composer.setMinimumHeight(78)
        composer.setObjectName('composer')
        input_row = QHBoxLayout(composer)
        input_row.setContentsMargins(8, 6, 8, 6)
        self.mic_button = MicButton()
        self.mic = self.mic_button
        self.mic.setObjectName('micSmall')
        self.mic.setFixedSize(42, 42)
        self.mic.clicked.connect(self.toggle_mic)
        input_row.addWidget(self.mic)
        divider = QFrame()
        divider.setObjectName('micDivider')
        divider.setFixedSize(1, 40)
        input_row.addWidget(divider)
        self.field = QLineEdit()
        palette = self.field.palette()
        palette.setColor(QPalette.ColorRole.PlaceholderText, QColor('#a6b6ca'))
        self.field.setPalette(palette)
        self.field.setPlaceholderText(_t('ui.main.placeholder'))
        self.field.setAccessibleName(_t('ui.main.placeholder'))
        self.field.returnPressed.connect(self.submit)
        input_row.addWidget(self.field, 1)
        self.sparkle_button = QPushButton()
        self.sparkle_button.setObjectName('sparkle')
        self.sparkle_button.setIcon(icon('sparkles', '#bdcfe4', 22))
        self.sparkle_button.setIconSize(QSize(22, 22))
        self.sparkle_button.setFixedSize(42, 42)
        self.sparkle_button.setAccessibleName(tr('Saran perintah', 'Prompt suggestions'))
        self.sparkle_button.setToolTip(tr('Pilih saran untuk mengisi draf', 'Choose a suggestion for your draft'))
        menu = QMenu(self.sparkle_button)
        for key in ('summarize', 'meeting', 'analyze', 'command'):
            action = menu.addAction(_t(f'ui.main.card.{key}'))
            action.triggered.connect(lambda checked=False, k=key: self.prepare(k))
        self.sparkle_button.setMenu(menu)
        input_row.addWidget(self.sparkle_button)
        self.send_button = QPushButton(_t('ui.main.send'))
        self.send_button.setIcon(icon('send', '#ffffff', 22))
        self.send_button.setIconSize(QSize(22, 22))
        self.send_button.setMinimumHeight(58)
        self.send_button.setObjectName('send')
        self.send_button.clicked.connect(self.submit)
        input_row.addWidget(self.send_button)
        self.retry_inline_panel = QFrame()
        self.retry_inline_panel.setObjectName('retryPanel')
        retry_row = QHBoxLayout(self.retry_inline_panel)
        retry_row.setContentsMargins(12, 5, 8, 5)
        self.retry_inline_text = heading('', 'emptyDescription')
        retry_row.addWidget(self.retry_inline_text, 1)
        self.retry_inline = QPushButton(tr('Coba lagi', 'Retry'))
        self.retry_inline.setIcon(icon('refresh-cw', '#cbe5ff', 18))
        self.retry_inline.setObjectName('secondary')
        self.retry_inline.clicked.connect(self.retry_connection)
        retry_row.addWidget(self.retry_inline)
        self.retry_inline_panel.hide()
        outer.addWidget(self.retry_inline_panel)
        outer.addWidget(composer)
        return page

    def _empty_chat(self):
        panel = QFrame()
        panel.setObjectName('emptyPanel')
        layout = QVBoxLayout(panel)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mark = QLabel()
        mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        mark.setPixmap(icon('message-circle', '#77bafa', 36).pixmap(QSize(36, 36)))
        layout.addWidget(mark)
        self.empty_title = heading('', 'emptyTitle')
        self.empty_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.empty_title)
        self.empty_description = heading('', 'emptyDescription')
        self.empty_description.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_description.setWordWrap(True)
        layout.addWidget(self.empty_description)
        self.countdown_label = heading('', 'muted')
        self.countdown_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.countdown_label)
        self.retry_button = QPushButton(tr('Coba lagi', 'Retry'))
        self.retry_button.setIcon(icon('refresh-cw', '#cbe5ff', 18))
        self.retry_button.setObjectName('secondary')
        self.retry_button.clicked.connect(self.retry_connection)
        layout.addWidget(self.retry_button, 0, Qt.AlignmentFlag.AlignHCenter)
        return panel

    def retry_connection(self):
        retry = getattr(self.shell, 'on_retry_connection', None)
        if callable(retry):
            try:
                retry()
            except Exception as exc:  # noqa: BLE001
                print(f'[JARVIS] Retry unavailable: {type(exc).__name__}: {exc}')
        self.refresh_mic()

    def _resize_view(self):
        if self._last_connection is False and not self.messages:
            QTimer.singleShot(0, lambda: self.home_scroll.verticalScrollBar().setValue(
                self.home_scroll.verticalScrollBar().maximum() if self.window.height() < 760 else 0))

    def current_page(self):
        return next(key for key, page in self.pages.items() if page is self.stack.currentWidget())

    def navigate(self, page):
        if page not in self.pages:
            return
        self.stack.setCurrentWidget(self.pages[page])
        self.nav_buttons['orb'].setChecked(page == 'orb')

    def show_system_card(self):
        self.home_content.setMinimumHeight(650)
        self.system_card.show()
        self.sampler.refresh()
        QTimer.singleShot(0, lambda: self.home_scroll.verticalScrollBar().setValue(
            self.home_scroll.verticalScrollBar().maximum()))

    def hide_system_card(self):
        self.home_content.setMinimumHeight(0)

    def update_metrics(self, cpu, ram):
        self.modules.update_values(cpu, ram)
        self.system_card.update_values(cpu, ram)

    def set_audio_level(self, level):
        if self.reduce_motion.isChecked():
            return
        self.orb.set_level(level)
        self.wave.add_level(level)

    def set_reduced_motion(self, reduced):
        self.orb.set_reduced_motion(reduced)
        self.wave.set_reduced_motion(reduced)
        overlay = getattr(self.shell, '_voice_overlay', None)
        if overlay is not None:
            from ui.voice_orb import set_reduced_motion
            set_reduced_motion(overlay, reduced)

    def set_state(self, state):
        key = str(state or '').strip().lower().replace(' ', '_')
        valid = {'initialising', 'idle', 'listening', 'thinking', 'processing', 'speaking', 'sleeping', 'no_mic'}
        self.state = key if key in valid else 'unknown'
        self.orb.set_state(self.state)
        self.refresh_mic()

    def refresh_mic(self):
        muted = bool(getattr(self.shell, 'muted', False))
        connection = None
        getter = getattr(self.shell, 'get_session_connected', None)
        if callable(getter):
            try:
                connection = bool(getter())
            except Exception:  # noqa: BLE001
                connection = None
        if connection != self._last_connection and not self.messages:
            if connection is False:
                QTimer.singleShot(0, lambda: self.home_scroll.verticalScrollBar().setValue(
                    self.home_scroll.verticalScrollBar().maximum()))
            elif connection is True:
                QTimer.singleShot(0, lambda: self.home_scroll.verticalScrollBar().setValue(0))
        self._last_connection = connection
        self.avatar.set_connected(connection)
        enabled = self.state in {'idle', 'listening', 'thinking', 'processing', 'speaking', 'sleeping'} and connection is not False
        if connection is False:
            label = tr('Menunggu sesi…', 'Waiting for session…')
        elif muted and enabled:
            label = tr('Mikrofon dibisukan', 'Microphone muted')
        elif self.state == 'listening' and connection is not False:
            label = tr('Siap mendengarkan…', 'Ready to listen…')
        else:
            label = _t('ui.main.state.' + self.state)
        self.status_label.setText(label)
        self.orb_state.setText(label)
        if connection is True:
            self.connection_label.setText(tr('●  Sesi aktif', '●  Session active'))
            self.connection_label.setStyleSheet('color:#67dca1;')
        elif connection is False:
            self.connection_label.setText(tr('●  Sesi tidak tersambung', '●  Session disconnected'))
            self.connection_label.setStyleSheet('color:#bdc9d5;')
        else:
            self.connection_label.setText(tr('●  Status sesi tidak diketahui', '●  Session status unknown'))
            self.connection_label.setStyleSheet('color:#bdc9d5;')
        connected_for_input = connection is not False
        self.field.setEnabled(connected_for_input)
        self.sparkle_button.setEnabled(connected_for_input)
        self.send_button.setEnabled(connected_for_input and not self.sending)
        for card in self.cards.values():
            card.setEnabled(connected_for_input)
        if connection is False:
            self.empty_title.setText(tr('Sesi belum tersambung', 'Session not connected'))
            self.empty_description.setText(tr('Percakapan akan muncul setelah sesi tersambung.',
                                              'Conversation will appear once the session connects.'))
        else:
            self.empty_title.setText(tr('Belum ada percakapan', 'No conversation yet'))
            self.empty_description.setText(tr('Mulai percakapan dengan suara atau teks.',
                                              'Start a conversation by voice or text.'))
        deadline, can_retry = None, False
        retry_state = getattr(self.shell, 'get_retry_state', None)
        if connection is False and callable(retry_state):
            try:
                deadline, can_retry = retry_state()
            except Exception as exc:  # noqa: BLE001
                print(f'[JARVIS] Retry status unavailable: {type(exc).__name__}: {exc}')
        remaining = max(0, math.ceil(deadline - time.monotonic())) if deadline is not None else None
        countdown = (tr(f'Mencoba lagi dalam {remaining} detik', f'Retrying in {remaining} seconds')
                     if remaining is not None else '')
        self.countdown_label.setText(countdown)
        self.retry_inline_text.setText(countdown or tr('Sesi tidak tersambung', 'Session disconnected'))
        self.retry_inline_panel.setVisible(bool(connection is False and self.messages))
        self.retry_inline.setEnabled(bool(can_retry and callable(getattr(self.shell, 'on_retry_connection', None))))
        self.retry_button.setVisible(connection is False)
        self.retry_button.setEnabled(bool(can_retry and callable(getattr(self.shell, 'on_retry_connection', None))))
        self.retry_button.setToolTip(tr('Tersedia saat menunggu percobaan ulang jaringan.',
                                        'Available during network retry backoff.'))
        action = tr('Aktifkan mikrofon', 'Unmute microphone') if muted else tr('Bisukan mikrofon', 'Mute microphone')
        if not enabled:
            action = tr('Mikrofon belum tersedia', 'Microphone not available yet')
        self.mic.setEnabled(enabled)
        self.mic.setAccessibleName(action)
        self.mic.setToolTip(action)
        self.orb.setAccessibleName(tr('Orb JARVIS. ', 'JARVIS orb. ') + label + '. ' + action)
        self.orb.setToolTip(action + tr(
            ' — akses suara mengikuti pengaturan sesi. Gelombang di dalam orb adalah ilustrasi; cincin luar menunjukkan level suara terbaru.',
            ' — voice access follows session settings. The inner wave is decorative; the outer ring shows recent audio levels.'))

    def toggle_mic(self):
        if not self.mic_button.isEnabled():
            return
        self.shell.muted = not bool(getattr(self.shell, 'muted', False))
        self.refresh_mic()

    def prepare(self, key):
        if key not in self.cards:
            return
        if not self.field.text().strip():
            self.field.setText(_t(f'ui.main.card.{key}.prompt'))
        self.field.setFocus()

    def module_draft(self, key):
        self.navigate('orb')
        prompts = {'agenda': tr('Bantu saya melihat agenda hari ini.', 'Help me review today’s schedule.'),
                   'code': tr('Bantu saya menulis kode: ', 'Help me write code: '),
                   'markets': tr('Bantu saya mencari informasi pasar terbaru.', 'Help me find the latest market information.'),
                   'search': tr('Bantu saya mencari informasi tentang: ', 'Help me find information about: ')}
        if not self.field.text().strip() and key in prompts:
            self.field.setText(prompts[key])
        self.field.setFocus()

    def show_feedback(self, text):
        if str(text).startswith('NET:'):
            self.refresh_mic()
            return
        self.feedback.setText(str(text))
        self.feedback.setVisible(bool(text))

    def submit(self):
        text = self.field.text().strip()
        if self.sending or not text or not self.field.isEnabled():
            return False
        callback = getattr(self.shell, 'on_text_command', None)
        if not callable(callback):
            self.show_feedback(_t('ui.main.send_unavailable'))
            return False
        self.sending = True
        self.send_button.setEnabled(False)
        self.show_feedback(_t('ui.main.sending'))
        from ui.command_delivery import dispatch, schedule_pending
        def run(): dispatch(callback, text, self.owner, self._sent)
        try:
            threading.Thread(target=run, name='main-command', daemon=True).start()
        except Exception as exc:  # noqa: BLE001
            print(f'[JARVIS] Command worker failed: {type(exc).__name__}: {exc}')
            self._sent(text, False)
            return False
        schedule_pending(self)
        return True

    def _sent(self, text, accepted):
        self.sending = False
        self.refresh_mic()
        if accepted is None:
            self.show_feedback(tr('Status pengiriman tidak pasti. Periksa sebelum mengirim ulang; draf dipertahankan.',
                                  'Delivery is uncertain. Check before retrying; the draft was kept.'))
            return
        if not accepted:
            if self.feedback.text() == _t('ui.main.sending'):
                self.show_feedback(_t('ui.main.send_failed'))
            return
        if self.field.text().strip() == text:
            self.field.clear()
        from ui.conversation_state import publish
        publish(self.shell, 'user', text)
        if self.feedback.text() in (_t('ui.main.sending'), tr(
                'Pengiriman masih menunggu; jangan kirim ulang sampai statusnya jelas.',
                'Send is still pending; do not retry until its status is known.')):
            self.show_feedback(tr('Dikirim ke sesi; tindakan belum tentu selesai.',
                                  'Sent to the session; an action is not necessarily complete.'))

    def add_message(self, role, text):
        if role not in ('user', 'assistant') or not str(text or '').strip():
            return
        self.messages.append((role, str(text).strip()))
        self.message_times.append(datetime.now().strftime('%H:%M'))
        del self.messages[:-100]
        del self.message_times[:-100]
        self._render_messages()

    def _render_messages(self):
        if not self.messages:
            html = f'<p style="color:#88a3a8">{escape(_t("ui.panel.chat.empty"))}</p>'
        else:
            rows = []
            for (role, value), when in zip(self.messages, self.message_times):
                align = 'right' if role == 'user' else 'left'
                color = '#164175' if role == 'user' else '#14202c'
                name = _t('ui.panel.chat.you') if role == 'user' else str(
                    getattr(self.shell, '_assistant_name', '') or 'JARVIS')
                rows.append(f'<table align="{align}" width="85%" cellpadding="10" '
                            f'bgcolor="{color}"><tr><td style="color:#eafafa">'
                            f'<b>{escape(name)}</b> &nbsp; <span style="color:#b8c7d7">{when}</span><br>{escape(value).replace(chr(10), "<br>")}'
                            '</td></tr></table><br>')
            html = ''.join(rows)
        self.chat_stack.setCurrentWidget(self.chat if self.messages else self.empty_panel)
        self.chat.setHtml(html)
        self.chat.verticalScrollBar().setValue(self.chat.verticalScrollBar().maximum())

    def show(self):
        self.window.show()
        self.window.raise_()
        self.window.activateWindow()

    def close(self):
        self.sampler.stop()
        self.window.close()


def open_main(shell):
    if QApplication.instance() is None:
        return False
    try:
        surface = getattr(shell, '_main_surface', None)
        if surface is None:
            surface = MainSurface(shell)
            shell._main_surface = surface
            from ui.conversation_state import hydrate
            hydrate(shell, surface)
        else:
            surface.sampler.start()
        surface.show()
        desktop = getattr(shell, '_desktop_workspace', None)
        if desktop is not None:
            desktop.hide()
        return True
    except Exception as exc:  # noqa: BLE001
        print(f'[JARVIS] Main surface unavailable: {type(exc).__name__}: {exc}')
        return False


def start_main(shell):
    if getattr(getattr(shell, '_launch', None), 'hidden', False):
        return False
    return open_main(shell)
