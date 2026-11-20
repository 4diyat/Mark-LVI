"""Exercise browser tabs and WebEngine policies offscreen, without network."""
import os
import sys
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PyQt6.QtCore import QCoreApplication, Qt, QUrl  # noqa: E402
from PyQt6.QtWidgets import QApplication  # noqa: E402
from PyQt6.QtTest import QSignalSpy, QTest  # noqa: E402
QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
from ui.workspace_browser import BrowserWindow  # noqa: E402


def main():
    app = QApplication([sys.argv[0]])
    class Host:
        enabled = True
        def get_plugins(self):
            return [{'name': 'workspace_browser', 'valid': True, 'enabled': self.enabled}]
    host = Host()
    window = BrowserWindow(host)
    window.show()
    first = window.tabs.widget(0)
    assert window.tabs.tabText(0) == 'Tab 1'
    for button, key in ((first.back, 'browser.back'), (first.forward, 'browser.forward'),
                        (first.reload_btn, 'browser.reload')):
        from core.i18n import label
        assert not button.icon().isNull() and button.text() == ''
        assert button.toolTip() == button.accessibleName() == label(key)
        pixmap = button.icon().pixmap(20, 20).toImage()
        assert any(pixmap.pixelColor(x, y).alpha() for x in range(pixmap.width()) for y in range(pixmap.height()))
    click = QSignalSpy(first.back.clicked)
    first.back.setFocus()
    QTest.keyClick(first.back, Qt.Key.Key_Space)
    assert len(click) == 1
    second = window.add_tab()
    assert window.tabs.cornerWidget() is window.new_tab
    assert first.fill_btn.objectName() == 'WorkspacePrimary'
    from core import i18n
    i18n.set_locale('id')
    window.retranslate()
    assert window.new_tab.text() == i18n.label('browser.new_tab')
    assert first._close_button.accessibleName() == i18n.label('browser.close_tab', number=1)
    assert second._close_button.toolTip() == i18n.label('browser.close_tab', number=2)
    assert not first._close_button.icon().isNull()
    assert first.fill_btn.text() == i18n.label('browser.fill')
    assert first.back.accessibleName() == first.back.toolTip() == i18n.label('browser.back')
    assert window.tabs.tabText(0) == i18n.label('browser.tab', number=1)
    assert window.tabs.count() == 2 and first.profile is not second.profile
    assert first.profile.isOffTheRecord() and second.profile.isOffTheRecord()
    assert first.page.acceptNavigationRequest(QUrl('https://example.com'), None, True)
    assert not first.page.acceptNavigationRequest(QUrl('file:///tmp/secret'), None, True)
    assert first.page.createWindow(None) is None and first.page.chooseFiles(None, [], []) == []
    host.enabled = False
    assert not first.page.acceptNavigationRequest(QUrl('https://example.com'), None, True)
    # A moved tab must retain its own close action and session ownership.
    window.tabs.tabBar().moveTab(1, 0)
    assert window.tabs.widget(0) is second and window.tabs.widget(1) is first
    second._close_button.setFocus()
    QTest.keyClick(second._close_button, Qt.Key.Key_Space)
    assert not second._live and first._live and window.tabs.count() == 1
    assert window.tabs.widget(0) is first
    window.close()
    assert not first._live
    app.processEvents()
    print('Real Qt browser policies passed without network.')


if __name__ == '__main__':
    main()
