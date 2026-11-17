"""SSH tab close and consent logic without Qt, hardware or network."""
import ast
from enum import IntFlag
from pathlib import Path
from types import SimpleNamespace
from test_browser_ui_logic import Button, Layout, Signal, Tabs, Widget


class StandardButton(IntFlag):
    Yes = 1
    No = 2


class MessageBox:
    StandardButton = StandardButton
    answer = StandardButton.No
    @classmethod
    def question(cls, *args): return cls.answer


class Tab(Widget):
    def __init__(self, host):
        super().__init__()
        self.session, self.connected, self.state_changed, self.disconnects = None, False, Signal(), 0
        self.user = SimpleNamespace(text=lambda: 'alice')
        self.host = SimpleNamespace(text=lambda: 'server')
    def disconnect_session(self):
        self.disconnects += 1
        self.session = None
        self.state_changed.emit()


def window():
    tree = ast.parse(Path('ui/ssh_manager.py').read_text(encoding='utf-8'))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'SSHManagerWindow')
    module = ast.fix_missing_locations(ast.Module(body=[cls], type_ignores=[]))
    ns = {'QWidget': Widget, 'QVBoxLayout': Layout, 'QHBoxLayout': Layout, 'QPushButton': Button,
          'QTabWidget': Tabs, 'SSHTab': Tab, 'QMessageBox': MessageBox,
          '_t': lambda s: '{number}' if s == 'ssh.tab' else s, 'workspace_stylesheet': lambda: ''}
    exec(compile(module, 'ui/ssh_manager.py', 'exec'), ns)
    MessageBox.answer = StandardButton.No
    return ns['SSHManagerWindow'](object())


def test_close_requires_consent_and_does_not_disconnect_other_tabs():
    w = window()
    assert w.tabs.corner is w.new_tab and w.tabs.scroll_buttons
    first, second = w.tabs.widget(0), w.add_tab()
    first.session, second.session = object(), object()
    w.close_tab(1)
    assert w.tabs.count() == 2 and second.disconnects == 0
    MessageBox.answer = StandardButton.Yes
    w.close_tab(1)
    assert w.tabs.count() == 1 and second.disconnects == 1 and second.deleted
    assert first.session is not None and first.disconnects == 0


def test_close_all_and_cap():
    w = window()
    for _ in range(9): w.add_tab()
    assert w.tabs.count() == 10 and w.add_tab() is None and not w.new_tab.enabled
    first = w.tabs.widget(0)
    first.session = object()
    state = SimpleNamespace(ignored=False, accepted=False)
    state.ignore = lambda: setattr(state, 'ignored', True)
    state.accept = lambda: setattr(state, 'accepted', True)
    w.closeEvent(state)
    assert state.ignored and not first.disconnects
    MessageBox.answer = StandardButton.Yes
    w.closeEvent(state)
    assert state.accepted and first.disconnects == 1


def test_command_confirmation_does_not_transfer_to_reconnected_session():
    tree = ast.parse(Path('ui/ssh_manager.py').read_text(encoding='utf-8'))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'SSHTab')
    module = ast.fix_missing_locations(ast.Module(body=[cls], type_ignores=[]))
    tab = None
    class Dialog:
        StandardButton = StandardButton
        def __init__(self, *args): pass
        def setWindowTitle(self, *args): pass
        def setTextFormat(self, *args): pass
        def setText(self, *args): pass
        def setStandardButtons(self, *args): pass
        def setDefaultButton(self, *args): pass
        def exec(self):
            tab.session = object()
            tab.generation += 1
            return StandardButton.Yes
    ns = {'QWidget': Widget, 'pyqtSignal': Signal, 'QMessageBox': Dialog,
          'Qt': SimpleNamespace(TextFormat=SimpleNamespace(PlainText=0)),
          '_t': lambda key: '{user}@{host}:{port} {command}',
          'allowed': lambda host: True, 'validate_command': lambda command: command}
    exec(compile(module, 'ui/ssh_manager.py', 'exec'), ns)
    tab = ns['SSHTab'].__new__(ns['SSHTab'])
    tab.connected, tab.busy, tab.host_app, tab.session, tab.generation = True, False, object(), object(), 1
    tab.command = SimpleNamespace(text=lambda: 'whoami', clear=lambda: (_ for _ in ()).throw(AssertionError()))
    tab.user = SimpleNamespace(text=lambda: 'alice')
    tab.host = SimpleNamespace(text=lambda: 'server')
    tab.port = SimpleNamespace(value=lambda: 22)
    tab.send_command()
    assert not tab.busy


def test_auth_controls_match_session_and_method():
    tree = ast.parse(Path('ui/ssh_manager.py').read_text(encoding='utf-8'))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'SSHTab')
    module = ast.fix_missing_locations(ast.Module(body=[cls], type_ignores=[]))
    ns = {'QWidget': Widget, 'pyqtSignal': Signal}
    exec(compile(module, 'ui/ssh_manager.py', 'exec'), ns)
    tab = ns['SSHTab'].__new__(ns['SSHTab'])
    for name in ('connect_btn', 'disconnect_btn', 'send_btn', 'command', 'host', 'user', 'port',
                 'secret', 'key', 'pick_key', 'clear_key_btn'):
        setattr(tab, name, Button())
    tab.auth = Button()
    tab.auth.currentData = lambda: 'password'
    tab.busy, tab.connected, tab.session = False, False, None
    tab._sync()
    assert tab.connect_btn.enabled and tab.secret.enabled
    assert not tab.key.enabled and not tab.pick_key.enabled and not tab.clear_key_btn.enabled
    tab.auth.currentData = lambda: 'key'
    tab._sync()
    assert tab.key.enabled and tab.pick_key.enabled and tab.clear_key_btn.enabled
    tab.connected, tab.session = True, object()
    tab._sync()
    assert not tab.pick_key.enabled and not tab.connect_btn.enabled
    assert tab.disconnect_btn.enabled and tab.send_btn.enabled


def test_ssh_retranslation_preserves_authentication_and_status():
    tree = ast.parse(Path('ui/ssh_manager.py').read_text(encoding='utf-8'))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == 'SSHTab')
    ns = {'QWidget': Widget, 'pyqtSignal': Signal, '_t': lambda key: 'id:' + key}
    exec(compile(ast.fix_missing_locations(ast.Module(body=[cls], type_ignores=[])), 'ui/ssh_manager.py', 'exec'), ns)
    tab = ns['SSHTab'].__new__(ns['SSHTab'])
    class Text:
        def setText(self, text): self.text = text
        def setPlaceholderText(self, text): self.placeholder = text
    class Combo:
        def __init__(self): self.items = ['', '']; self.selected = 1
        def setItemText(self, i, text): self.items[i] = text
    for name in ('heading', 'known_hosts', 'output_heading', 'pick_key', 'clear_key_btn', 'connect_btn',
                 'disconnect_btn', 'send_btn', 'secret', 'command', 'status'):
        setattr(tab, name, Text())
    tab._form_labels, tab.auth, tab._status_key = [(Text(), 'ssh.host')], Combo(), 'ssh.connected'
    tab.retranslate()
    assert tab._form_labels[0][0].text == 'id:ssh.host'
    assert tab.auth.items == ['id:ssh.key_agent', 'id:ssh.password_method'] and tab.auth.selected == 1
    assert tab.status.text == 'id:ssh.connected'
