"""Native, non-executable interactive chart and table for the JARVIS workspace."""
from __future__ import annotations

from PyQt6.QtCore import QPointF, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PyQt6.QtWidgets import (QAbstractItemView, QDialog, QHBoxLayout, QLabel, QPushButton,
                             QStackedWidget, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget)

from core.i18n import label as _t
from core.visual_content import positions, validate
from ui.theme import workspace_stylesheet
from ui.visual_followup import draft, question_input, retranslate_input


def number(value, unit):
    return f"{value:.15g}" + (f" {unit}" if unit else "")


class Chart(QWidget):
    selected = pyqtSignal(int)

    def __init__(self, data):
        super().__init__()
        self.data = data
        self.index = 0
        self.setMinimumSize(260, 180)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAccessibleName(_t("visual.chart_accessible"))

    def points(self):
        return positions(self.data['points'], 70, 28, max(1, self.width() - 100),
                         max(1, self.height() - 75))

    def paintEvent(self, event):
        del event
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.fillRect(self.rect(), QColor('#0b1827'))
        coords = self.points()
        values = [item['value'] for item in self.data['points']]
        lo, hi = min(0.0, min(values)), max(0.0, max(values))
        if lo == hi:
            hi = lo + 1
        p.setFont(QFont('Arial', 9))
        for i in range(4):
            y = 28 + (self.height() - 75) * i / 3
            p.setPen(QPen(QColor('#263c51'), 1))
            p.drawLine(QPointF(70, y), QPointF(self.width() - 30, y))
            p.setPen(QColor('#adc0d4'))
            p.drawText(QRectF(0, y - 10, 62, 20), Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                       number(hi - (hi - lo) * i / 3, ''))
        path = QPainterPath(QPointF(*coords[0]))
        for point in coords[1:]:
            path.lineTo(QPointF(*point))
        p.setPen(QPen(QColor('#54aaff'), 2))
        p.drawPath(path)
        for i, (x, y) in enumerate(coords):
            p.setPen(QPen(QColor('#a5d9ff'), 2) if i == self.index else Qt.PenStyle.NoPen)
            p.setBrush(QColor('#3f9cec'))
            p.drawEllipse(QPointF(x, y), 6 if i == self.index else 4, 6 if i == self.index else 4)
        # Labels stay readable for small series; the table always exposes all labels.
        if len(coords) <= 8:
            p.setPen(QColor('#adc0d4'))
            for (x, _), item in zip(coords, self.data['points']):
                p.drawText(QRectF(x - 38, self.height() - 34, 76, 22),
                           Qt.AlignmentFlag.AlignCenter, item['label'][:12])
        p.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            pos = event.position()
            points = self.points()
            nearest = min(range(len(points)), key=lambda i: (points[i][0] - pos.x()) ** 2 + (points[i][1] - pos.y()) ** 2)
            if (points[nearest][0] - pos.x()) ** 2 + (points[nearest][1] - pos.y()) ** 2 <= 14 ** 2:
                self.selected.emit(nearest)
                self.setFocus()
                return
        super().mousePressEvent(event)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Left, Qt.Key.Key_Right):
            change = -1 if event.key() == Qt.Key.Key_Left else 1
            self.selected.emit(max(0, min(len(self.data['points']) - 1, self.index + change)))
            return
        super().keyPressEvent(event)


class VisualContent(QDialog):
    def __init__(self, host, payload):
        super().__init__(host)
        self.host = host
        self.data = validate(payload)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.setStyleSheet(workspace_stylesheet())
        self.setWindowTitle(self.data['title'])
        self.resize(760, 550)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 18, 22, 18)
        title = QLabel(self.data['title'])
        title.setTextFormat(Qt.TextFormat.PlainText)
        title.setWordWrap(True)
        title.setFont(QFont('Arial', 17, QFont.Weight.Bold))
        layout.addWidget(title)
        self.source = QLabel()
        self.source.setTextFormat(Qt.TextFormat.PlainText)
        self.source.setWordWrap(True)
        layout.addWidget(self.source)
        bar = QHBoxLayout()
        self.graph_button, self.table_button = QPushButton(), QPushButton()
        bar.addWidget(self.graph_button)
        bar.addWidget(self.table_button)
        bar.addStretch()
        layout.addLayout(bar)
        self.stack = QStackedWidget()
        self.chart = Chart(self.data)
        self.chart.selected.connect(self.select)
        self.stack.addWidget(self.chart)
        self.table = QTableWidget(len(self.data['points']), 2)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.horizontalHeader().setStretchLastSection(True)
        for row, item in enumerate(self.data['points']):
            self.table.setItem(row, 0, QTableWidgetItem(item['label']))
            self.table.setItem(row, 1, QTableWidgetItem(number(item['value'], self.data['unit'])))
        self.table.currentCellChanged.connect(lambda row, *_: self.select(row))
        self.stack.addWidget(self.table)
        layout.addWidget(self.stack, 1)
        self.selection = QLabel()
        self.selection.setTextFormat(Qt.TextFormat.PlainText)
        self.selection.setWordWrap(True)
        layout.addWidget(self.selection)
        self.followup_input = question_input(self)
        self.followup_input.textChanged.connect(lambda: self.notice.clear())
        layout.addWidget(self.followup_input)
        self.ask = QPushButton()
        self.ask.clicked.connect(self.draft_question)
        layout.addWidget(self.ask)
        self.notice = QLabel()
        self.notice.setWordWrap(True)
        self.notice.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.notice)
        self.graph_button.clicked.connect(lambda: self.stack.setCurrentIndex(0))
        self.table_button.clicked.connect(lambda: self.stack.setCurrentIndex(1))
        self.retranslate()
        self.select(0)

    def retranslate(self):
        self.graph_button.setText(_t('visual.graph'))
        self.table_button.setText(_t('visual.table'))
        self.ask.setText(_t('visual.ask'))
        retranslate_input(self.followup_input)
        self.table.setHorizontalHeaderLabels([_t('visual.label'), _t('visual.value')])
        source = _t('visual.source', source=self.data['source'])
        observed = self.data['observed'] or _t('visual.unknown_time')
        self.source.setText(source + '  ·  ' + _t('visual.time', time=observed))
        self.chart.setAccessibleName(_t('visual.chart_accessible'))
        self.select(self.chart.index)

    def select(self, index):
        if not 0 <= index < len(self.data['points']):
            return
        if self.chart.index != index:
            self.notice.clear()
        self.chart.index = index
        self.chart.update()
        if self.table.currentRow() != index:
            self.table.selectRow(index)
        item = self.data['points'][index]
        self.selection.setText(_t('visual.selected', label=item['label'],
                                  value=number(item['value'], self.data['unit'])))

    def draft_question(self):
        from core.visual_followup import chart_snapshot
        draft(self.host, self.notice, _t('visual.question'), 'chart',
              chart_snapshot(self.data, self.chart.index), self.followup_input.text())
