"""Exercise browser tab ownership and stale-result guards without Qt or network."""
import ast
import types
from pathlib import Path


class Signal:
    def __init__(self, *args): self.slots = []
    def connect(self, fn): self.slots.append(fn)
    def emit(self, *args):
        for fn in self.slots: fn(*args)


class Widget:
    def __init__(self, *args): self.deleted = False
    def setWindowTitle(self, *args): pass
    def setStyleSheet(self, *args): pass
    def resize(self, *args): pass
    def deleteLater(self): self.deleted = True
    def closeEvent(self, event): event.accept()


class Layout:
    def __init__(self, *args): pass
    def addWidget(self, *args): pass
    def addLayout(self, *args): pass
    def addStretch(self, *args): pass


class Button:
    def __init__(self, *args): self.clicked, self.enabled = Signal(), True
    def setEnabled(self, value): self.enabled = value


class Tabs:
    def __init__(self): self.pages, self.labels, self.tabCloseRequested = [], [], Signal()
    def setTabsClosable(self, value): pass
    def setMovable(self, value): pass
    def setUsesScrollButtons(self, value): self.scroll_buttons = value
    def setCornerWidget(self, widget): self.corner = widget
    def count(self): return len(self.pages)
    def addTab(self, panel, label): self.pages.append(panel); self.labels.append(label); return len(self.pages) - 1
    def setCurrentIndex(self, index): self.current = index
    def indexOf(self, panel): return self.pages.index(panel) if panel in self.pages else -1
    def setTabText(self, index, text): self.labels[index] = text
    def widget(self, index): return self.pages[index]
    def removeTab(self, index): self.pages.pop(index); self.labels.pop(index)


class FakeTab(Widget):
    def __init__(self, host, url):
        super().__init__()
        self.url, self.page_changed, self.profile, self.closed = url, Signal(), object(), False
        self.view = types.SimpleNamespace(url=lambda: types.SimpleNamespace(host=lambda: 'example.com'))
    def close(self): self.closed = True


def load_class(name, namespace):
    tree = ast.parse(Path('ui/workspace_browser.py').read_text(encoding='utf-8'))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == name)
    module = ast.fix_missing_locations(ast.Module(body=[cls], type_ignores=[]))
    exec(compile(module, 'ui/workspace_browser.py', 'exec'), namespace)
    return namespace[name]


def test_tabs_independent_and_bounded():
    ns = {'QWidget': Widget, 'QVBoxLayout': Layout, 'QHBoxLayout': Layout, 'QPushButton': Button,
          'QTabWidget': Tabs, 'BrowserTab': FakeTab, '_t': lambda s: '{number}' if s == 'browser.tab' else s,
          'workspace_stylesheet': lambda: ''}
    window = load_class('BrowserWindow', ns)(object(), 'https://example.com')
    assert window.tabs.corner is window.new_tab and window.tabs.scroll_buttons
    first = window.tabs.widget(0)
    second = window.add_tab(False)
    assert first.url == 'https://example.com' and second.url == '' and first.profile is not second.profile
    window.close_tab(1)
    assert second.closed and second.deleted and not first.closed
    for _ in range(9): window.add_tab()
    assert window.tabs.count() == 10 and not window.new_tab.enabled and window.add_tab() is None
    window.close_tab(1)
    assert window.new_tab.enabled


def test_stale_vault_result_never_injects_password():
    ns = {'QWidget': Widget, 'pyqtSignal': Signal}
    cls = load_class('BrowserTab', ns)
    tab = cls.__new__(cls)
    tab._generation = 2
    tab._origin = lambda: 'https://example.com'
    calls = []
    tab.page = types.SimpleNamespace(runJavaScript=lambda *a: calls.append(a))
    tab._vault_result(1, 'get', 'https://example.com', (True, ('user', 'secret')))
    tab._origin = lambda: 'https://other.example'
    tab._vault_result(2, 'get', 'https://example.com', (True, ('user', 'secret')))
    assert not calls


def test_confirmation_does_not_apply_after_same_origin_navigation():
    cls = load_class('BrowserTab', {'QWidget': Widget, 'pyqtSignal': Signal, '_t': lambda key: '{origin} {username}'})
    tab = cls.__new__(cls)
    tab._origin = lambda: 'https://example.com'
    tab.offer = types.SimpleNamespace(currentData=lambda: 'alice')
    tab._busy, tab._generation = False, 1
    operations = []
    tab._work = lambda *args: operations.append(args)
    def confirm(*args):
        tab._generation += 1  # Navigation while the modal dialog is open.
        return True
    tab._confirm = confirm
    tab.fill_login()
    tab.delete_login()
    assert not operations


def test_browser_retranslation_preserves_selected_login_and_current_status():
    cls = load_class('BrowserTab', {'QWidget': Widget, 'pyqtSignal': Signal, '_t': lambda key: 'id:' + key})
    tab = cls.__new__(cls)
    class Text:
        def setText(self, text): self.text = text
        def setPlaceholderText(self, text): self.placeholder = text
    class Combo:
        def __init__(self): self.items = [('', 'old no saved'), ('alice', 'alice')]; self.selected = 1
        def count(self): return len(self.items)
        def itemData(self, i): return self.items[i][0]
        def setItemText(self, i, text): self.items[i] = (self.items[i][0], text)
    for name in ('back', 'forward', 'reload_btn', 'go', 'fill_btn', 'save_btn', 'delete_btn', 'address', 'status'):
        setattr(tab, name, Text())
    tab.offer = Combo()
    tab._status_key = 'browser.filled'
    tab.retranslate()
    assert tab.status.text == 'id:browser.filled'
    assert tab.address.placeholder == 'id:browser.address_hint'
    assert tab.offer.items == [('', 'id:browser.no_saved'), ('alice', 'alice')]
    assert tab.offer.selected == 1


def test_navigation_clears_previous_fill_status_and_saved_selection():
    cls = load_class('BrowserTab', {'QWidget': Widget, 'pyqtSignal': Signal, '_t': lambda key: key})
    tab = cls.__new__(cls)
    class Status:
        def setText(self, value): self.text = value
    class Offer:
        def clear(self): self.items = []
        def addItem(self, label, data): self.items.append((label, data))
    tab._generation, tab._loaded, tab._busy = 2, True, True
    tab.status, tab.offer = Status(), Offer()
    tab._buttons = lambda: None
    tab._invalidate()
    assert tab._generation == 3 and not tab._loaded and not tab._busy
    assert tab.status.text == 'browser.privacy'
    assert tab.offer.items == [('browser.no_saved', '')]
