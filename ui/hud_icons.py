"""Bundled Lucide SVG icons, rendered in the requested state colour."""
from pathlib import Path

from PyQt6.QtCore import QByteArray, QSize, Qt
from PyQt6.QtGui import QIcon, QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer

_ROOT = Path(__file__).resolve().parent.parent / 'assets/icons/lucide'


def icon(name, color='#b8dfff', size=24):
    path = _ROOT / (name + '.svg')
    try:
        svg = path.read_text(encoding='utf-8').replace('currentColor', color)
        renderer = QSvgRenderer(QByteArray(svg.encode('utf-8')))
        if not renderer.isValid():
            return QIcon()
        pixmap = QPixmap(QSize(size * 2, size * 2))
        pixmap.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pixmap)
        renderer.render(painter)
        painter.end()
        pixmap.setDevicePixelRatio(2)
        return QIcon(pixmap)
    except OSError as exc:
        print(f'[JARVIS] Icon unavailable: {name}: {exc}')
        return QIcon()
