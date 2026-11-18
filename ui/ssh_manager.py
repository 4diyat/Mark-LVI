"""Manual multi-tab SSH manager. Workers never touch Qt widgets."""
import threading

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (QComboBox, QFileDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
                             QMessageBox, QPlainTextEdit, QPushButton, QSpinBox, QTabWidget, QVBoxLayout, QWidget)

from core.i18n import label as _t
from core.ssh_session import SSHSession, UnknownHostKey, validate_command, validate_connection
from ui.desktop_workspace import show_document
from ui.theme import workspace_stylesheet


def allowed(host):
    try:
        return any(r.get('name') == 'ssh_manager' and r.get('valid') and r.get('enabled') for r in host.get_plugins())
    except Exception:
        return False


class SSHTab(QWidget):
    connect_result = pyqtSignal(int, str)
    command_result = pyqtSignal(int, object)
    state_changed = pyqtSignal()

    def __init__(self, host):
        super().__init__()
        self.host_app, self.session = host, None
        self.generation, self.busy, self.connected = 0, False, False
        outer = QVBoxLayout(self)
        body = QHBoxLayout()
        outer.addLayout(body, 1)
        panel = QWidget()
        panel.setObjectName('WorkspaceSection')
        form = QFormLayout(panel)
        self.heading = QLabel(_t('ssh.connection_heading'))
        form.addRow(self.heading)
        self._status_key = 'ssh.disconnected'
        self.status = QLabel(_t(self._status_key))
        self.status.setWordWrap(True)
        self.host, self.user, self.key, self.secret = QLineEdit(), QLineEdit(), QLineEdit(), QLineEdit()
        self.port = QSpinBox()
        self.port.setRange(1, 65535)
        self.port.setValue(22)
        self.auth = QComboBox()
        self.auth.addItem(_t('ssh.key_agent'), 'key')
        self.auth.addItem(_t('ssh.password_method'), 'password')
        self.key.setReadOnly(True)
        self.secret.setEchoMode(QLineEdit.EchoMode.Password)
        self.secret.setPlaceholderText(_t('ssh.secret_hint'))
        key_row = QHBoxLayout()
        key_row.addWidget(self.key, 1)
        self.pick_key, self.clear_key_btn = QPushButton(_t('ssh.choose_key')), QPushButton(_t('ssh.clear_key'))
        self.pick_key.clicked.connect(self.choose_key)
        self.clear_key_btn.clicked.connect(self.clear_key)
        key_row.addWidget(self.pick_key)
        key_row.addWidget(self.clear_key_btn)
        self.auth.currentIndexChanged.connect(self._sync)
        self._form_labels = []
        for key, field in (('ssh.host', self.host), ('ssh.port', self.port), ('ssh.user', self.user),
                           ('ssh.authentication', self.auth), ('ssh.key_file', key_row), ('ssh.secret', self.secret)):
            label = QLabel(_t(key))
            self._form_labels.append((label, key))
            if isinstance(field, QWidget):
                label.setBuddy(field)
                field.setAccessibleName(_t(key))
            form.addRow(label, field)
        buttons = QHBoxLayout()
        self.connect_btn, self.disconnect_btn = QPushButton(_t('ssh.connect')), QPushButton(_t('ssh.disconnect'))
        self.connect_btn.setObjectName('WorkspacePrimary')
        self.connect_btn.clicked.connect(self.connect_session)
        self.disconnect_btn.clicked.connect(self.disconnect_session)
        buttons.addWidget(self.connect_btn)
        buttons.addWidget(self.disconnect_btn)
        form.addRow(buttons)
        form.addRow(self.status)
        self.known_hosts = QLabel(_t('ssh.known_hosts'))
        self.known_hosts.setWordWrap(True)
        form.addRow(self.known_hosts)
        body.addWidget(panel, 1)
        output_panel = QWidget()
        output_panel.setObjectName('WorkspaceSection')
        output = QVBoxLayout(output_panel)
        self.output_heading = QLabel(_t('ssh.output_hint'))
        output.addWidget(self.output_heading)
        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.output.document().setMaximumBlockCount(1500)
        cmdrow = QHBoxLayout()
        self.command = QLineEdit()
        self.command.setMaxLength(4096)
        self.command.setPlaceholderText(_t('ssh.command_hint'))
        self.command.setAccessibleName(_t('ssh.command_hint'))
        self.send_btn = QPushButton(_t('ssh.send'))
        self.send_btn.setObjectName('WorkspacePrimary')
        self.send_btn.clicked.connect(self.send_command)
        self.command.returnPressed.connect(self.send_command)
        cmdrow.addWidget(self.command, 1)
        cmdrow.addWidget(self.send_btn)
        output.addLayout(cmdrow)
        output.addWidget(self.output, 1)
        body.addWidget(output_panel, 2)
        self.connect_result.connect(self._on_connect)
        self.command_result.connect(self._on_command)
        self._sync()

    def _set_status(self, key):
        self._status_key = key
        self.status.setText(_t(key))

    def retranslate(self):
        for widget, key in ((self.heading, 'ssh.connection_heading'), (self.known_hosts, 'ssh.known_hosts'),
                            (self.output_heading, 'ssh.output_hint'), (self.pick_key, 'ssh.choose_key'),
                            (self.clear_key_btn, 'ssh.clear_key'), (self.connect_btn, 'ssh.connect'),
                            (self.disconnect_btn, 'ssh.disconnect'), (self.send_btn, 'ssh.send')):
            widget.setText(_t(key))
        for label, key in self._form_labels:
            label.setText(_t(key))
        self.auth.setItemText(0, _t('ssh.key_agent'))
        self.auth.setItemText(1, _t('ssh.password_method'))
        self.secret.setPlaceholderText(_t('ssh.secret_hint'))
        self.command.setPlaceholderText(_t('ssh.command_hint'))
        self.command.setAccessibleName(_t('ssh.command_hint'))
        self.status.setText(_t(self._status_key))

    def _sync(self, *_args):
        editable = not self.busy and not self.connected
        self.connect_btn.setEnabled(editable)
        self.disconnect_btn.setEnabled(self.session is not None)
        self.send_btn.setEnabled(self.connected and not self.busy)
        self.command.setEnabled(self.connected and not self.busy)
        for field in (self.host, self.user, self.port, self.auth, self.secret):
            field.setEnabled(editable)
        key_enabled = editable and self.auth.currentData() == 'key'
        for field in (self.key, self.pick_key, self.clear_key_btn):
            field.setEnabled(key_enabled)

    def choose_key(self):
        if self.busy or self.connected: return
        path, _ = QFileDialog.getOpenFileName(self, _t('ssh.choose_key'))
        if path: self.key.setText(path)

    def clear_key(self):
        if not self.busy and not self.connected: self.key.clear()

    @staticmethod
    def _emit(widget, name, *args):
        try: getattr(widget, name).emit(*args)
        except RuntimeError: pass

    def connect_session(self):
        if self.busy or self.connected or not allowed(self.host_app):
            self._set_status('ssh.disabled')
            return
        try:
            host, port, user = validate_connection(self.host.text(), self.port.value(), self.user.text())
            method, secret, key = self.auth.currentData(), self.secret.text(), self.key.text()
            if method == 'password' and not secret: raise ValueError('Missing password')
        except ValueError:
            self._set_status('ssh.invalid_fields')
            return
        self.secret.clear()
        self.generation += 1
        generation = self.generation
        session = self.session = SSHSession()
        self.busy = True
        self._set_status('ssh.connecting')
        self._sync()
        def worker():
            try: result = 'connected' if session.connect(host, port, user, method, secret, key) else 'disconnected'
            except UnknownHostKey: result = 'unknown_host'
            except Exception: result = 'connect_failed'
            self._emit(self, 'connect_result', generation, result)
        threading.Thread(target=worker, daemon=True, name='ssh-connect').start()

    def _on_connect(self, generation, result):
        if generation != self.generation: return
        self.busy = False
        self.connected = result == 'connected'
        if not self.connected:
            if self.session: self.session.request_close()
            self.session = None
        self._set_status('ssh.' + result)
        self._sync()
        self.state_changed.emit()

    def disconnect_session(self):
        self.generation += 1
        was_running = self.busy and self.connected
        session, self.session = self.session, None
        self.busy = self.connected = False
        self.secret.clear()
        if session: session.request_close()
        self._set_status('ssh.disconnect_busy' if was_running else 'ssh.disconnected')
        self._sync()
        self.state_changed.emit()

    def send_command(self):
        if not self.connected or self.busy or not allowed(self.host_app):
            self._set_status('ssh.disabled')
            return
        try: command = validate_command(self.command.text())
        except ValueError:
            self._set_status('ssh.invalid_command')
            return
        # A modal dialog runs a nested event loop: a disconnect/reconnect can
        # occur while it is open. Consent applies only to this exact session.
        session, generation = self.session, self.generation
        box = QMessageBox(self)
        box.setWindowTitle(_t('ssh.confirm_title'))
        box.setTextFormat(Qt.TextFormat.PlainText)
        box.setText(_t('ssh.confirm_detail').format(user=self.user.text(), host=self.host.text(),
                                                     port=self.port.value(), command=command))
        box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        box.setDefaultButton(QMessageBox.StandardButton.No)
        if box.exec() != QMessageBox.StandardButton.Yes: return
        if (not self.connected or self.busy or session is None or self.session is not session
                or self.generation != generation or not allowed(self.host_app)):
            return
        self.command.clear()
        self.busy = True
        self._set_status('ssh.running')
        self._sync()
        def worker():
            try: result = session.execute(command)
            except Exception: result = (b'', None, 'command_failed')
            self._emit(self, 'command_result', generation, result)
        threading.Thread(target=worker, daemon=True, name='ssh-command').start()

    def _on_command(self, generation, result):
        if generation != self.generation: return
        self.busy = False
        data, code, state = result
        text = data.decode('utf-8', errors='replace')
        text = ''.join(c for c in text if c in '\n\t' or c.isprintable())
        if text: self.output.appendPlainText(text)
        if code is not None: self.output.appendPlainText(_t('ssh.exit_status').format(code=code))
        visible = self.output.toPlainText()
        if len(visible) > 262144: self.output.setPlainText(visible[-262144:])
        self._set_status('ssh.' + state)
        self._sync()

    def closeEvent(self, event):
        self.disconnect_session()
        super().closeEvent(event)


class SSHManagerWindow(QWidget):
    MAX_TABS = 10
    def __init__(self, host):
        super().__init__()
        self._host, self._next = host, 1
        self.setWindowTitle(_t('ssh.title'))
        self.resize(1050, 720)
        self.setStyleSheet(workspace_stylesheet())
        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        self.new_tab = QPushButton(_t('ssh.new_tab'))
        self.new_tab.clicked.connect(self.add_tab)
        self.tabs.setCornerWidget(self.new_tab)
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        self.tabs.setUsesScrollButtons(True)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        layout.addWidget(self.tabs, 1)
        self.add_tab()

    def add_tab(self):
        if self.tabs.count() >= self.MAX_TABS: return None
        tab = SSHTab(self._host)
        tab.number = self._next
        self._next += 1
        idx = self.tabs.addTab(tab, _t('ssh.tab').format(number=tab.number))
        tab.state_changed.connect(lambda: self._title(tab))
        self.tabs.setCurrentIndex(idx)
        self.new_tab.setEnabled(self.tabs.count() < self.MAX_TABS)
        return tab

    def retranslate(self):
        self.setWindowTitle(_t('ssh.title'))
        self.new_tab.setText(_t('ssh.new_tab'))
        for index in range(self.tabs.count()):
            tab = self.tabs.widget(index)
            tab.retranslate()
            self._title(tab)

    def _title(self, tab):
        idx = self.tabs.indexOf(tab)
        if idx >= 0:
            title = _t('ssh.tab').format(number=tab.number)
            if tab.connected: title += ' — ' + tab.user.text()[:24] + '@' + tab.host.text()[:40]
            self.tabs.setTabText(idx, title)

    def _confirm_close(self, panels):
        if not any(panel.session is not None for panel in panels): return True
        result = QMessageBox.question(self, _t('ssh.close_title'), _t('ssh.close_warning'),
                                      QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                      QMessageBox.StandardButton.No)
        return result == QMessageBox.StandardButton.Yes

    def close_tab(self, index):
        if not 0 <= index < self.tabs.count(): return
        tab = self.tabs.widget(index)
        if not self._confirm_close([tab]): return
        tab.disconnect_session()
        self.tabs.removeTab(index)
        tab.deleteLater()
        if not self.tabs.count(): self.add_tab()
        self.new_tab.setEnabled(self.tabs.count() < self.MAX_TABS)

    def shutdown_panels(self):
        """Snapshot sessions for the desktop's two-phase shutdown check."""
        return [self.tabs.widget(i) for i in range(self.tabs.count())]

    def closeEvent(self, event):
        panels = self.shutdown_panels()
        if not self._confirm_close(panels):
            event.ignore()
            return
        for tab in panels: tab.disconnect_session()
        super().closeEvent(event)


def open_ssh_manager(window, job):
    del job
    if not allowed(window):
        window.write_log(_t('ssh.disabled'))
        return None
    return show_document(window, SSHManagerWindow(window), 'ssh_manager')
