"""Local consent and asynchronous read of the active embedded browser tab."""
from urllib.parse import urlsplit

from PyQt6.QtCore import QTimer, Qt
from PyQt6.QtWebEngineCore import QWebEngineScript
from PyQt6.QtWidgets import QMessageBox

from core.browser_read import MAX_TEXT, read_script, scope_allows
from core.browser_url import validate_browser_url
from core.i18n import label as _t
from ui.workspace_browser import plugin_allowed


def execute(window, request):
    """Called on the Qt thread; only the active visible browser is eligible."""
    if not request.claim():
        return
    try:
        if not plugin_allowed(window):
            request.finish({'ok': False, 'message': 'Browser plugin is disabled.'})
            return
        sub = window._desktop_mdi.activeSubWindow()
        entry = next(((kind, widget) for kind, widget in window._workspace_documents.values()
                      if widget is sub and kind == 'workspace_browser'), None)
        if not entry or sub.isHidden() or sub.isMinimized():
            request.finish({'ok': False, 'message': 'Focus the internal browser window and the tab to read first.'})
            return
        browser = sub._document
        tab = browser.tabs.currentWidget()
        if not tab or not tab._live or not tab._loaded:
            request.finish({'ok': False, 'message': 'The selected browser tab is not loaded.'})
            return
        url = validate_browser_url(tab.view.url().toString())
        if not scope_allows(url, request.scope):
            request.finish({'ok': False, 'message': 'Focus the requested Google Flights page in the internal browser first.'})
            return
        generation = tab._generation
        origin = urlsplit(url).scheme + '://' + urlsplit(url).netloc
        if getattr(window, '_confirm_overlay', None) is not None or getattr(window, '_hand_closing_confirm', False):
            request.finish({'ok': False, 'message': 'Another confirmation is already open.'})
            return
        box = QMessageBox(window)
        box.setWindowTitle(_t('browser.read_confirm_title'))
        box.setTextFormat(Qt.TextFormat.PlainText)
        box.setText(_t('browser.read_confirm_detail', origin=origin))
        box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        box.setDefaultButton(QMessageBox.StandardButton.No)
        window._hand_closing_confirm = True
        try:
            QTimer.singleShot(45000, box.reject)
            approved = box.exec() == QMessageBox.StandardButton.Yes
        finally:
            window._hand_closing_confirm = False
        if not request.active():
            return
        if not approved:
            request.finish({'ok': False, 'message': 'Browser read was not approved.'})
            return

        def unchanged():
            return (request.active() and plugin_allowed(window) and tab._live and tab._loaded
                    and tab._generation == generation and browser.tabs.currentWidget() is tab
                    and window._desktop_mdi.activeSubWindow() is sub
                    and not sub.isHidden() and not sub.isMinimized()
                    and tab.view.url().toString() == url)

        if not unchanged():
            request.finish({'ok': False, 'message': 'Browser tab changed; read cancelled.'})
            return

        def complete(value):
            try:
                if not unchanged():
                    request.finish({'ok': False, 'message': 'Browser tab changed; read cancelled.'})
                elif not isinstance(value, str):
                    request.finish({'ok': False, 'message': 'Could not read the browser page.'})
                else:
                    request.finish({'ok': True, 'text': value[:MAX_TEXT]})
            except RuntimeError:
                request.finish({'ok': False, 'message': 'Browser tab was closed.'})
        tab.page.runJavaScript(read_script(url), int(QWebEngineScript.ScriptWorldId.ApplicationWorld), complete)
    except Exception:
        request.finish({'ok': False, 'message': 'Browser read could not be completed.'})
