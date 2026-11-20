"""Native, keyboard-accessible list presentation for explanatory content.

Items retain their full accessible text in the model; the painted preview is
bounded, while the selected detail pane exposes the complete information.
"""
from PyQt6.QtCore import QRect, QSize, Qt
from PyQt6.QtGui import QColor, QFont, QPen
from PyQt6.QtWidgets import QStyle, QStyledItemDelegate

from core.i18n import label as _t
from ui.theme import C


class NarrativeItemDelegate(QStyledItemDelegate):
    def __init__(self, kind, parent=None):
        super().__init__(parent)
        self.kind = kind

    def sizeHint(self, option, index):
        del option, index
        return QSize(180, 112 if self.kind == 'cards' else 90)

    def paint(self, painter, option, index):
        item = index.data(Qt.ItemDataRole.UserRole)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        focused = bool(option.state & QStyle.StateFlag.State_HasFocus)
        painter.save()
        painter.setRenderHint(painter.RenderHint.Antialiasing)
        rect = option.rect.adjusted(5, 4, -5, -4)
        color = QColor(C.DESKTOP_DOCK if selected else C.DESKTOP_SIDEBAR)
        border = QColor('#70b7ff' if focused else '#4b9fff' if selected else C.DESKTOP_BORDER)
        painter.setPen(QPen(border, 2 if focused else 1))
        painter.setBrush(color)
        painter.drawRoundedRect(rect, 9, 9)

        left = rect.left() + 12
        if self.kind != 'cards':
            x = rect.left() + 24
            y = rect.top() + 24
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor('#4b9fff' if selected else C.DESKTOP_BORDER))
            painter.drawEllipse(x - 14, y - 14, 28, 28)
            painter.setPen(QColor(C.DESKTOP_TEXT))
            badge = str(index.row() + 1) if self.kind == 'steps' else '•'
            painter.drawText(QRect(x - 14, y - 14, 28, 28), Qt.AlignmentFlag.AlignCenter, badge)
            if self.kind == 'timeline' and index.row() + 1 < index.model().rowCount():
                painter.setPen(QPen(QColor(C.DESKTOP_BORDER), 2))
                painter.drawLine(x, y + 17, x, rect.bottom() - 3)
            left = rect.left() + 48

        width = max(1, rect.right() - left - 10)
        painter.setPen(QColor(C.DESKTOP_TEXT))
        font = QFont(option.font)
        font.setBold(True)
        painter.setFont(font)
        title = painter.fontMetrics().elidedText(item['label'], Qt.TextElideMode.ElideRight, width)
        painter.drawText(QRect(left, rect.top() + 10, width, 23), Qt.AlignmentFlag.AlignVCenter, title)
        painter.setPen(QColor(C.DESKTOP_MUTED))
        font.setBold(False)
        painter.setFont(font)
        if self.kind == 'timeline':
            subtitle = item['when'] or _t('visual.unknown_time')
        else:
            subtitle = ' '.join(item['detail'].split())
        subtitle = painter.fontMetrics().elidedText(subtitle, Qt.TextElideMode.ElideRight, width)
        painter.drawText(QRect(left, rect.top() + 38, width, 23), Qt.AlignmentFlag.AlignVCenter, subtitle)
        painter.restore()
