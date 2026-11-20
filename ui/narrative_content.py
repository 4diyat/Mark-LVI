"""Interactive cards, process steps and timelines rendered as native Qt widgets."""
from __future__ import annotations

import json

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (QAbstractItemView, QDialog, QHBoxLayout, QLabel, QListWidget,
                             QListWidgetItem, QPlainTextEdit, QPushButton, QVBoxLayout, QWidget)

from core import outcome
from core.i18n import label as _t
from core.narrative_content import validate
from ui.theme import C, workspace_stylesheet


class NarrativeContent(QDialog):
    def __init__(self, host, payload):
        super().__init__(host)
        self.host = host
        self.data = validate(payload)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.setStyleSheet(workspace_stylesheet())
        self.setWindowTitle(self.data['title'])
        self.resize(820, 560)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 18, 22, 18)
        layout.setSpacing(10)
        self.heading = QLabel(self.data['title'])
        self.heading.setTextFormat(Qt.TextFormat.PlainText)
        self.heading.setWordWrap(True)
        self.heading.setFont(QFont('Arial', 17, QFont.Weight.Bold))
        layout.addWidget(self.heading)
        self.source = QLabel()
        self.source.setTextFormat(Qt.TextFormat.PlainText)
        self.source.setWordWrap(True)
        layout.addWidget(self.source)
        self.summary = QLabel(self.data['summary'])
        self.summary.setTextFormat(Qt.TextFormat.PlainText)
        self.summary.setWordWrap(True)
        self.summary.setVisible(bool(self.data['summary']))
        layout.addWidget(self.summary)
        self.kind_label = QLabel()
        self.kind_label.setFont(QFont('Arial', 11, QFont.Weight.Bold))
        layout.addWidget(self.kind_label)
        content = QHBoxLayout()
        self.items = QListWidget()
        self.items.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.items.setMinimumWidth(180)
        for i, item in enumerate(self.data['items']):
            prefix = f'{i + 1:02d}  ' if self.data['kind'] == 'steps' else '●  ' if self.data['kind'] == 'timeline' else '◇  '
            caption = prefix + item['label']
            if self.data['kind'] == 'timeline' and item['when']:
                caption += '  ·  ' + item['when']
            self.items.addItem(QListWidgetItem(caption))
        self.items.currentRowChanged.connect(self.select)
        content.addWidget(self.items, 2)
        panel = QWidget()
        panel.setObjectName('WorkspaceSection')
        right = QVBoxLayout(panel)
        right.setContentsMargins(16, 16, 16, 16)
        self.item_title = QLabel()
        self.item_title.setTextFormat(Qt.TextFormat.PlainText)
        self.item_title.setWordWrap(True)
        self.item_title.setFont(QFont('Arial', 13, QFont.Weight.Bold))
        right.addWidget(self.item_title)
        self.item_time = QLabel()
        self.item_time.setTextFormat(Qt.TextFormat.PlainText)
        self.item_time.setWordWrap(True)
        self.item_time.setStyleSheet(f'color: {C.DESKTOP_MUTED};')
        right.addWidget(self.item_time)
        self.detail = QPlainTextEdit()
        self.detail.setReadOnly(True)
        right.addWidget(self.detail, 1)
        self.ask = QPushButton()
        self.ask.clicked.connect(self.draft_question)
        right.addWidget(self.ask)
        self.notice = QLabel()
        self.notice.setTextFormat(Qt.TextFormat.PlainText)
        self.notice.setWordWrap(True)
        right.addWidget(self.notice)
        content.addWidget(panel, 3)
        layout.addLayout(content, 1)
        self.items.setCurrentRow(0)
        self.retranslate()

    def retranslate(self):
        self.kind_label.setText(_t('narrative.' + self.data['kind']))
        self.items.setAccessibleName(_t('narrative.select_item'))
        self.detail.setAccessibleName(_t('narrative.detail'))
        self.ask.setText(_t('narrative.ask'))
        observed = self.data['observed'] or _t('visual.unknown_time')
        self.source.setText(_t('visual.source', source=self.data['source']) + '  ·  '
                            + _t('visual.time', time=observed))
        self.select(self.items.currentRow())

    def select(self, row):
        if not 0 <= row < len(self.data['items']):
            return
        item = self.data['items'][row]
        self.item_title.setText(item['label'])
        self.item_time.setVisible(bool(item['when']))
        self.item_time.setText(item['when'])
        self.detail.setPlainText(item['detail'])

    def draft_question(self):
        row = self.items.currentRow()
        if not 0 <= row < len(self.data['items']):
            return
        if self.host._input.text().strip():
            self.notice.setText(_t('visual.draft_busy'))
            return
        context = json.dumps({'type': self.data['kind'], 'title': self.data['title'],
                              'source': self.data['source'], 'observed': self.data['observed'],
                              'selected': self.data['items'][row]}, ensure_ascii=False)
        self.host._input.setText(_t('narrative.question') + ' '
                                 + outcome.untrusted('content', context).replace('\n', ' '))
        self.notice.setText(_t('visual.drafted'))
        assistant = self.host._desktop_windows['assistant']
        assistant.showNormal()
        self.host._desktop_mdi.setActiveSubWindow(assistant)
        self.host._input.setFocus()
