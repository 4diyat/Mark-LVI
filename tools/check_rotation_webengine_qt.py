"""Offline feasibility test for a rotated Qt WebEngine view in a proxy.

Uses synthetic HTML only, no external sites, credentials or workspace changes.
"""
import faulthandler
import os
import sys
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PyQt6.QtCore import QCoreApplication, QEventLoop, QPoint, QPointF, QTimer, Qt  # noqa: E402
QCoreApplication.setAttribute(Qt.ApplicationAttribute.AA_ShareOpenGLContexts)
from PyQt6.QtTest import QTest  # noqa: E402
from PyQt6.QtWebEngineWidgets import QWebEngineView  # noqa: E402
from PyQt6.QtWidgets import QApplication, QGraphicsScene, QGraphicsView, QVBoxLayout, QWidget  # noqa: E402


def main():
    faulthandler.dump_traceback_later(40, exit=True)
    app = QApplication([sys.argv[0]])
    scene = QGraphicsScene(0, 0, 1000, 800)
    view = QGraphicsView(scene)
    view.setSceneRect(scene.sceneRect())
    view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    view.resize(1020, 820)
    root = QWidget()
    root.resize(400, 300)
    layout = QVBoxLayout(root)
    layout.setContentsMargins(0, 0, 0, 0)
    web = QWebEngineView(root)
    layout.addWidget(web)
    proxy = scene.addWidget(root)
    assert proxy is not None
    proxy.setPos(300, 200)
    proxy.setTransformOriginPoint(proxy.boundingRect().center())
    view.show()
    QTest.qWait(100)

    def wait_for(register):
        loop = QEventLoop()
        results = []
        timer = QTimer()
        timer.setSingleShot(True)
        timer.timeout.connect(loop.quit)
        def done(result):
            results.append(result)
            loop.quit()
        register(done)
        timer.start(8000)
        loop.exec()
        timer.stop()
        assert results, 'WebEngine callback timed out'
        return results[0]

    def load(done):
        web.loadFinished.connect(done)
        web.setHtml('''<!doctype html><html><body style="margin:0;background:rgb(30,190,80)">
          <input id="entry" style="position:absolute;left:20px;top:20px;width:180px;height:35px">
          <button id="go" style="position:absolute;left:20px;top:90px;width:180px;height:35px"
            onclick="document.body.dataset.clicked='yes'">Press</button>
          </body></html>''')
    assert wait_for(load) is True
    QTest.qWait(700)

    def js(script):
        return wait_for(lambda done: web.page().runJavaScript(script, done))

    def mapped(local):
        point = web.mapTo(root, local)
        target = view.mapFromScene(proxy.mapToScene(QPointF(point)))
        assert view.viewport().rect().contains(target)
        return target

    for angle in (0, 30):
        print(f'webengine proof angle {angle}: rendering', flush=True)
        proxy.setRotation(angle)
        QTest.qWait(300)
        app.processEvents()
        # A visible solid patch checks actual pixels, not merely DOM readiness.
        pixel = view.viewport().grab().toImage().pixelColor(mapped(QPoint(300, 200)))
        assert pixel.green() > 130 and pixel.red() < 100, (angle, pixel.name())
        print(f'webengine proof angle {angle}: typing', flush=True)
        QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, pos=mapped(QPoint(80, 38)))
        QTest.keyClick(view.viewport(), Qt.Key.Key_A, Qt.KeyboardModifier.ControlModifier)
        QTest.keyClicks(view.viewport(), f'angle{angle}')
        assert js("document.getElementById('entry').value") == f'angle{angle}'
        print(f'webengine proof angle {angle}: button', flush=True)
        js("document.body.dataset.clicked='no'")
        QTest.mouseClick(view.viewport(), Qt.MouseButton.LeftButton, pos=mapped(QPoint(80, 108)))
        assert js("document.body.dataset.clicked") == 'yes'
    view.close()
    faulthandler.cancel_dump_traceback_later()
    print('Offline WebEngine proxy feasibility proof passed; not integrated into JARVIS.')


if __name__ == '__main__':
    main()
