"""Exercise browser tabs and WebEngine policies offscreen, without network."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PyQt6.QtCore import QCoreApplication, Qt, QUrl  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402
QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
from ui.workspace_browser import BrowserWindow  # noqa: E402


def main():
    app = QApplication([])
    class Host:
        enabled = True
        def get_plugins(self):
            return [{'name': 'workspace_browser', 'valid': True, 'enabled': self.enabled}]
    host = Host()
    window = BrowserWindow(host)
    window.show()
    first = window.tabs.widget(0)
    second = window.add_tab()
    assert window.tabs.cornerWidget() is window.new_tab
    assert first.fill_btn.objectName() == 'WorkspacePrimary'
    from core import i18n
    i18n.set_locale('id')
    window.retranslate()
    assert window.new_tab.text() == i18n.label('browser.new_tab')
    assert first.fill_btn.text() == i18n.label('browser.fill')
    assert window.tabs.count() == 2 and first.profile is not second.profile
    assert first.profile.isOffTheRecord() and second.profile.isOffTheRecord()
    assert first.page.acceptNavigationRequest(QUrl('https://example.com'), None, True)
    assert not first.page.acceptNavigationRequest(QUrl('file:///tmp/secret'), None, True)
    assert first.page.createWindow(None) is None and first.page.chooseFiles(None, [], []) == []
    host.enabled = False
    assert not first.page.acceptNavigationRequest(QUrl('https://example.com'), None, True)
    window.close_tab(1)
    assert not second._live and first._live and window.tabs.count() == 1
    window.close()
    assert not first._live
    app.processEvents()
    print('Real Qt browser policies passed without network.')


if __name__ == '__main__':
    main()
