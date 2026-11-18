"""Exercise SSH tabs with real offscreen Qt and fake transport only."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PyQt6.QtCore import QTimer  # noqa: E402
from PyQt6.QtTest import QTest  # noqa: E402
from PyQt6.QtWidgets import QApplication, QMessageBox, QWidget  # noqa: E402
from types import SimpleNamespace  # noqa: E402
import ui.ssh_manager as ssh_ui  # noqa: E402


def main():
    app = QApplication([])
    class Host:
        def get_plugins(self):
            return [{'name': 'ssh_manager', 'valid': True, 'enabled': True}]
    class FakeSession:
        def __init__(self): self.commands, self.closed = [], False
        def connect(self, *args): self.args = args; return True
        def execute(self, command): self.commands.append(command); return b'hello', 0, 'finished'
        def request_close(self): self.closed = True
    ssh_ui.SSHSession = FakeSession
    window = ssh_ui.SSHManagerWindow(Host())
    window.show()
    first, second = window.tabs.widget(0), window.add_tab()
    assert window.tabs.cornerWidget() is window.new_tab
    assert first.connect_btn.objectName() == first.send_btn.objectName() == 'WorkspacePrimary'
    assert first.pick_key.isEnabled() and first.clear_key_btn.isEnabled()
    first.auth.setCurrentIndex(1)
    assert not first.pick_key.isEnabled() and not first.clear_key_btn.isEnabled()
    first.auth.setCurrentIndex(0)
    assert first.pick_key.isEnabled() and first.clear_key_btn.isEnabled()
    for tab, hostname in ((first, 'one.invalid'), (second, 'two.invalid')):
        tab.host.setText(hostname)
        tab.user.setText('alice')
        tab.auth.setCurrentIndex(1)
        tab.secret.setText('fake-secret')
        tab.connect_session()
    for _ in range(100):
        QTest.qWait(10)
        if first.connected and second.connected: break
    assert first.connected and second.connected and not first.secret.text() and not second.secret.text()
    assert not first.pick_key.isEnabled() and not first.clear_key_btn.isEnabled()
    from core import i18n
    i18n.set_locale('id')
    window.retranslate()
    assert first.connected and second.connected and first.auth.currentData() == 'password'
    assert first.connect_btn.text() == i18n.label('ssh.connect')
    assert window.new_tab.text() == i18n.label('ssh.new_tab')
    a, b = first.session, second.session
    assert a is not b
    def confirm():
        active = QApplication.activeModalWidget()
        assert isinstance(active, QMessageBox)
        active.button(QMessageBox.StandardButton.Yes).click()
    second.command.setText('echo hello')
    QTimer.singleShot(0, confirm)
    second.send_command()
    for _ in range(100):
        QTest.qWait(10)
        if not second.busy: break
    assert b.commands == ['echo hello'] and a.commands == []
    assert 'hello' in second.output.toPlainText() and not first.output.toPlainText()
    # Session sharing is explicit, excludes previous output and can be revoked.
    QTimer.singleShot(0, confirm)
    second.toggle_sharing()
    assert second._share_output and not second._shared_output and not first._share_output
    from core.ssh_assist import SSHAssistRequest
    from ui.ssh_assist import execute
    host = QWidget()
    host.get_plugins = lambda: [{'name': 'ssh_manager', 'valid': True, 'enabled': True}]
    sub = SimpleNamespace(_document=window, isHidden=lambda: False, isMinimized=lambda: False)
    host._workspace_documents = {'doc-1': ('ssh_manager', sub)}
    host._desktop_mdi = SimpleNamespace(activeSubWindow=lambda: sub)
    host._confirm_overlay = None
    host._hand_closing_confirm = False
    inspect = SSHAssistRequest({'action': 'inspect', 'target': 'doc-1'})
    execute(host, inspect)
    result = inspect.wait(0)
    assert result['ok'] and result['sharing'] and result['output'] == ''
    request = SSHAssistRequest({'action': 'execute', 'target': 'doc-1',
                                'session': result['session'], 'command': 'pwd'})
    QTimer.singleShot(0, confirm)
    execute(host, request)
    assert request.wait(0)['ok']
    for _ in range(100):
        QTest.qWait(10)
        if not second.busy: break
    assert b.commands == ['echo hello', 'pwd'] and 'hello' in second._shared_output
    second.toggle_sharing()
    assert not second._share_output and not second._shared_output
    host.close()
    QTimer.singleShot(0, confirm)
    window.close_tab(window.tabs.indexOf(second))
    assert b.closed and not a.closed
    QTimer.singleShot(0, confirm)
    assert window.close() and a.closed
    app.processEvents()
    print('Real Qt SSH tabs passed with fake transport.')


if __name__ == '__main__':
    main()
