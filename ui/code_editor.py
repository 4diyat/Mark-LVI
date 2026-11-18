"""Qt code surface: line-number gutter and lightweight syntax colouring."""
from PyQt6.QtCore import QRect, QSize, Qt
from PyQt6.QtGui import QColor, QPainter, QSyntaxHighlighter, QTextCharFormat
from PyQt6.QtWidgets import QPlainTextEdit, QWidget

from core.code_syntax import spans


class SyntaxHighlighter(QSyntaxHighlighter):
    def __init__(self, document):
        super().__init__(document)
        self.language = 'text'
        self.formats = {}
        for name, color in (('keyword', '#bd9bea'), ('string', '#b5d98b'),
                            ('comment', '#7592a9'), ('number', '#e3c386')):
            fmt = QTextCharFormat()
            fmt.setForeground(QColor(color))
            self.formats[name] = fmt

    def highlightBlock(self, text):
        for start, length, kind in spans(text, self.language):
            self.setFormat(start, length, self.formats[kind])

    def set_language(self, language):
        if self.language != language:
            self.language = language
            self.rehighlight()


class LineNumberArea(QWidget):
    def __init__(self, editor):
        super().__init__(editor)
        self.editor = editor

    def sizeHint(self):
        return QSize(self.editor.line_number_width(), 0)

    def paintEvent(self, event):
        self.editor.paint_line_numbers(event)


class CodeEditor(QPlainTextEdit):
    def __init__(self):
        super().__init__()
        self._gutter = LineNumberArea(self)
        self.blockCountChanged.connect(self._update_gutter_width)
        self.updateRequest.connect(self._update_gutter)
        self._update_gutter_width()
        self.highlighter = SyntaxHighlighter(self.document())
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.setStyleSheet('QPlainTextEdit { background: #0b1928; color: #d7e9f6; '
                           'border: 1px solid #294157; selection-background-color: #315b80; }')

    def line_number_width(self):
        return 12 + self.fontMetrics().horizontalAdvance('9') * len(str(max(1, self.blockCount())))

    def _update_gutter_width(self, *_args):
        self.setViewportMargins(self.line_number_width(), 0, 0, 0)

    def _update_gutter(self, rect, dy):
        if dy:
            self._gutter.scroll(0, dy)
        else:
            self._gutter.update(0, rect.y(), self._gutter.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self._update_gutter_width()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        rect = self.contentsRect()
        self._gutter.setGeometry(QRect(rect.left(), rect.top(), self.line_number_width(), rect.height()))

    def paint_line_numbers(self, event):
        painter = QPainter(self._gutter)
        painter.fillRect(event.rect(), QColor('#101e2c'))
        painter.setPen(QColor('#6f8ba3'))
        block = self.firstVisibleBlock()
        number = block.blockNumber()
        top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + round(self.blockBoundingRect(block).height())
        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                painter.drawText(0, top, self._gutter.width() - 5, self.fontMetrics().height(),
                                 Qt.AlignmentFlag.AlignRight, str(number + 1))
            block = block.next()
            top, number = bottom, number + 1
            bottom = top + round(self.blockBoundingRect(block).height())
        painter.end()
