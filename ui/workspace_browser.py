"""Tabbed embedded browser. All web content is untrusted."""
import threading

from PyQt6.QtCore import Qt, QUrl, pyqtSignal
from PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile, QWebEngineScript, QWebEngineSettings
from PyQt6.QtWebEngineWidgets import QWebEngineView
from PyQt6.QtWidgets import (QComboBox, QDialog, QFormLayout, QHBoxLayout, QLabel, QLineEdit,
                             QMessageBox, QPushButton, QTabWidget, QVBoxLayout, QWidget)

from core.browser_autofill import fill_script
from core.browser_url import https_origin, validate_browser_url
from core.browser_vault import BrowserVault
from core.i18n import label as _t
from ui.desktop_workspace import show_document
from ui.theme import workspace_stylesheet


def plugin_allowed(host):
    try:
        return any(r.get('name') == 'workspace_browser' and r.get('valid') and r.get('enabled')
                   for r in host.get_plugins())
    except Exception:
        return False


class BrowserPage(QWebEnginePage):
    def __init__(self, profile, view, host):
        super().__init__(profile, view)
        self._host = host
        self.featurePermissionRequested.connect(self._deny_feature)
        if hasattr(self, 'permissionRequested'):
            self.permissionRequested.connect(lambda permission: permission.deny())

    def _deny_feature(self, origin, feature):
        self.setFeaturePermission(origin, feature, self.PermissionPolicy.PermissionDeniedByUser)

    def acceptNavigationRequest(self, url, navigation_type, is_main_frame):
        del navigation_type, is_main_frame
        if not plugin_allowed(self._host):
            return False
        try:
            validate_browser_url(url.toString())
            return True
        except ValueError:
            return False

    def createWindow(self, window_type):
        del window_type
        return None

    def chooseFiles(self, mode, old_files, accepted_mime_types):
        del mode, old_files, accepted_mime_types
        return []


class BrowserTab(QWidget):
    _vault_done = pyqtSignal(int, str, str, object)
    page_changed = pyqtSignal()

    def __init__(self, host, initial_url=''):
        super().__init__()
        self._host, self._vault = host, BrowserVault()
        self._generation, self._loaded, self._live, self._busy = 0, False, True, False
        layout = QVBoxLayout(self)
        controls = QHBoxLayout()
        self.back, self.forward, self.reload_btn = (QPushButton(_t(k)) for k in ('browser.back', 'browser.forward', 'browser.reload'))
        self.address = QLineEdit()
        self.address.setPlaceholderText(_t('browser.address_hint'))
        self.address.setAccessibleName(_t('browser.address_hint'))
        self.go = QPushButton(_t('browser.go'))
        self.go.setObjectName('WorkspacePrimary')
        for b in (self.back, self.forward, self.reload_btn):
            controls.addWidget(b)
        controls.addWidget(self.address, 1)
        controls.addWidget(self.go)
        layout.addLayout(controls)
        row = QHBoxLayout()
        self.offer = QComboBox()
        self.offer.setAccessibleName(_t('browser.saved_available'))
        self.offer.addItem(_t('browser.no_saved'), '')
        self.fill_btn, self.save_btn, self.delete_btn = (QPushButton(_t(k)) for k in ('browser.fill', 'browser.save', 'browser.delete'))
        self.fill_btn.setObjectName('WorkspacePrimary')
        row.addWidget(self.offer, 1)
        for b in (self.fill_btn, self.save_btn, self.delete_btn):
            row.addWidget(b)
        layout.addLayout(row)
        self._status_key = 'browser.privacy'
        self.status = QLabel(_t(self._status_key))
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.view = QWebEngineView(self)
        self.profile = QWebEngineProfile(self)  # unnamed = off-the-record, per tab
        self.profile.downloadRequested.connect(lambda item: item.cancel())
        self.page = BrowserPage(self.profile, self.view, host)
        self.view.setPage(self.page)
        for name in ('JavascriptCanOpenWindows', 'JavascriptCanAccessClipboard',
                     'LocalContentCanAccessFileUrls', 'LocalContentCanAccessRemoteUrls', 'ScreenCaptureEnabled'):
            attribute = getattr(QWebEngineSettings.WebAttribute, name, None)
            if attribute is not None:
                self.page.settings().setAttribute(attribute, False)
        layout.addWidget(self.view, 1)
        self.back.clicked.connect(self.view.back)
        self.forward.clicked.connect(self.view.forward)
        self.reload_btn.clicked.connect(self.view.reload)
        self.go.clicked.connect(self.navigate)
        self.address.returnPressed.connect(self.navigate)
        self.view.urlChanged.connect(self._url_changed)
        self.view.loadStarted.connect(self._invalidate)
        self.view.loadFinished.connect(self._load_finished)
        self._vault_done.connect(self._vault_result)
        self.offer.currentIndexChanged.connect(lambda _: self._buttons())
        self.fill_btn.clicked.connect(self.fill_login)
        self.save_btn.clicked.connect(self.save_login)
        self.delete_btn.clicked.connect(self.delete_login)
        self._buttons()
        if initial_url:
            self.address.setText(initial_url)
            self.navigate()

    def _set_status(self, key):
        self._status_key = key
        self.status.setText(_t(key))

    def retranslate(self):
        for widget, key in ((self.back, 'browser.back'), (self.forward, 'browser.forward'),
                            (self.reload_btn, 'browser.reload'), (self.go, 'browser.go'),
                            (self.fill_btn, 'browser.fill'), (self.save_btn, 'browser.save'),
                            (self.delete_btn, 'browser.delete')):
            widget.setText(_t(key))
        self.address.setPlaceholderText(_t('browser.address_hint'))
        self.address.setAccessibleName(_t('browser.address_hint'))
        self.status.setText(_t(self._status_key))
        # Only the empty sentinel is localized; usernames and selection stay intact.
        for index in range(self.offer.count()):
            if self.offer.itemData(index) == '':
                self.offer.setItemText(index, _t('browser.no_saved'))

    def _origin(self):
        if not self._live or not self._loaded or not plugin_allowed(self._host):
            return None
        try:
            return https_origin(self.view.url().toString())
        except ValueError:
            return None

    def _buttons(self):
        origin = self._origin()
        user = self.offer.currentData()
        self.save_btn.setEnabled(bool(origin) and not self._busy)
        self.fill_btn.setEnabled(bool(origin and user) and not self._busy)
        self.delete_btn.setEnabled(bool(origin and user) and not self._busy)

    def _invalidate(self):
        self._generation += 1
        self._loaded = self._busy = False
        self._set_status('browser.privacy')
        self.offer.clear()
        self.offer.addItem(_t('browser.no_saved'), '')
        self._buttons()

    def _url_changed(self, url):
        self._invalidate()
        self.address.setText(url.toString())
        self.page_changed.emit()

    def _load_finished(self, ok):
        self._loaded = bool(ok)
        self._set_status('browser.privacy' if ok else 'browser.load_failed')
        self._buttons()
        origin = self._origin()
        if origin:
            self._work('list', origin)

    def navigate(self):
        if not plugin_allowed(self._host):
            self._set_status('browser.disabled')
            return
        try:
            url = validate_browser_url(self.address.text())
        except ValueError:
            self._set_status('browser.invalid')
            return
        self.view.setUrl(QUrl(url))

    def _work(self, operation, origin, user='', secret=''):
        if self._busy:
            return
        self._busy = True
        self._buttons()
        generation, vault = self._generation, self._vault
        def worker():
            try:
                if operation == 'list':
                    value = vault.list_usernames(origin)
                elif operation == 'save':
                    value = vault.save(origin, user, secret)
                elif operation == 'get':
                    value = (user, vault.get(origin, user))
                else:
                    value = vault.delete(origin, user)
                result = (True, value)
            except Exception:
                result = (False, None)
            try:
                self._vault_done.emit(generation, operation, origin, result)
            except RuntimeError:
                pass
        threading.Thread(target=worker, daemon=True, name='browser-vault').start()

    def _vault_result(self, generation, operation, origin, result):
        if generation != self._generation or self._origin() != origin:
            return
        self._busy = False
        ok, value = result
        if not ok:
            self._set_status('browser.vault_failed')
        elif operation == 'list':
            self.offer.clear()
            if value:
                for user in value:
                    self.offer.addItem(user, user)
                self._set_status('browser.saved_available')
            else:
                self.offer.addItem(_t('browser.no_saved'), '')
        elif operation in ('save', 'delete'):
            self._set_status('browser.saved' if operation == 'save' else 'browser.deleted')
            self._work('list', origin)
        elif operation == 'get' and value[1] is not None:
            user, password = value
            script = fill_script(origin, user, password)
            try:
                self.page.runJavaScript(script, int(QWebEngineScript.ScriptWorldId.ApplicationWorld),
                    lambda result: self._fill_result(generation, origin, result))
            except RuntimeError:
                pass
        else:
            self._set_status('browser.no_saved')
        self._buttons()

    def _fill_result(self, generation, origin, result):
        if generation == self._generation and self._origin() == origin:
            self._set_status('browser.filled' if result == 'filled' else 'browser.fill_failed')

    def _confirm(self, title, text):
        box = QMessageBox(self)
        box.setWindowTitle(_t(title))
        box.setTextFormat(Qt.TextFormat.PlainText)
        box.setText(text)
        box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        box.setDefaultButton(QMessageBox.StandardButton.No)
        return box.exec() == QMessageBox.StandardButton.Yes

    def save_login(self):
        origin = self._origin()
        if not origin or self._busy:
            return
        generation = self._generation
        dialog = QDialog(self)
        dialog.setWindowTitle(_t('browser.save'))
        form = QFormLayout(dialog)
        form.addRow(_t('browser.site'), QLabel(origin))
        user, password = QLineEdit(), QLineEdit()
        user.setMaxLength(512)
        password.setMaxLength(4096)
        password.setEchoMode(QLineEdit.EchoMode.Password)
        form.addRow(_t('browser.user'), user)
        form.addRow(_t('browser.password'), password)
        form.addRow(QLabel(_t('browser.replace')))
        controls = QHBoxLayout()
        save, cancel = QPushButton(_t('browser.save')), QPushButton(_t('browser.cancel'))
        save.clicked.connect(dialog.accept)
        cancel.clicked.connect(dialog.reject)
        controls.addWidget(save)
        controls.addWidget(cancel)
        form.addRow(controls)
        accepted = dialog.exec() == QDialog.DialogCode.Accepted
        name, secret = user.text(), password.text()
        password.clear()
        dialog.deleteLater()
        if accepted and generation == self._generation and self._origin() == origin and name and secret:
            self._work('save', origin, name, secret)

    def fill_login(self):
        origin, user, generation = self._origin(), self.offer.currentData(), self._generation
        if (origin and user and not self._busy
                and self._confirm('browser.fill', _t('browser.fill_confirm').format(origin=origin, username=user))
                and generation == self._generation and self._origin() == origin):
            self._work('get', origin, user)

    def delete_login(self):
        origin, user, generation = self._origin(), self.offer.currentData(), self._generation
        if (origin and user and not self._busy
                and self._confirm('browser.delete', _t('browser.delete_confirm').format(origin=origin, username=user))
                and generation == self._generation and self._origin() == origin):
            self._work('delete', origin, user)

    def closeEvent(self, event):
        self._live = False
        self._invalidate()
        self.view.stop()
        super().closeEvent(event)


class BrowserWindow(QWidget):
    MAX_TABS = 10
    def __init__(self, host, url=''):
        super().__init__()
        self._host, self._next = host, 1
        self.setWindowTitle(_t('browser.title'))
        self.resize(1000, 720)
        self.setStyleSheet(workspace_stylesheet())
        layout = QVBoxLayout(self)
        self.tabs = QTabWidget()
        self.new_tab = QPushButton(_t('browser.new_tab'))
        self.new_tab.clicked.connect(self.add_tab)
        self.tabs.setCornerWidget(self.new_tab)
        self.tabs.setTabsClosable(True)
        self.tabs.setMovable(True)
        self.tabs.setUsesScrollButtons(True)
        self.tabs.tabCloseRequested.connect(self.close_tab)
        layout.addWidget(self.tabs, 1)
        self.add_tab(url)

    def add_tab(self, url=''):
        if self.tabs.count() >= self.MAX_TABS:
            return None
        if not isinstance(url, str):
            url = ''
        tab = BrowserTab(self._host, url)
        tab.number = self._next
        self._next += 1
        idx = self.tabs.addTab(tab, _t('browser.tab').format(number=tab.number))
        tab.page_changed.connect(lambda: self._title(tab))
        self.tabs.setCurrentIndex(idx)
        self.new_tab.setEnabled(self.tabs.count() < self.MAX_TABS)
        self._title(tab)
        return tab

    def retranslate(self):
        self.setWindowTitle(_t('browser.title'))
        self.new_tab.setText(_t('browser.new_tab'))
        for index in range(self.tabs.count()):
            tab = self.tabs.widget(index)
            tab.retranslate()
            self._title(tab)

    def _title(self, tab):
        index = self.tabs.indexOf(tab)
        if index >= 0:
            title = _t('browser.tab').format(number=tab.number)
            host = tab.view.url().host()
            self.tabs.setTabText(index, title + (' — ' + host[:45] if host else ''))

    def close_tab(self, index):
        if not 0 <= index < self.tabs.count():
            return
        tab = self.tabs.widget(index)
        tab.close()
        self.tabs.removeTab(index)
        tab.deleteLater()
        if not self.tabs.count():
            self.add_tab()
        self.new_tab.setEnabled(self.tabs.count() < self.MAX_TABS)

    def closeEvent(self, event):
        for idx in range(self.tabs.count()):
            self.tabs.widget(idx).close()
        super().closeEvent(event)


def open_browser(window, job):
    if not plugin_allowed(window):
        window.write_log(_t('browser.disabled'))
        return None
    return show_document(window, BrowserWindow(window, job.get('url', '')), 'workspace_browser')
