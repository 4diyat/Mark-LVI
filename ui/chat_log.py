"""Selectable, bounded assistant conversation on the Qt main thread."""
from PyQt6.QtCore import QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QFont, QTextBlockFormat, QTextCursor
from PyQt6.QtWidgets import QTextEdit

from ui.theme import C, qcol


class LogWidget(QTextEdit):
    _sig = pyqtSignal(str)
    # A document-local marker allows bubble widths to follow a resized panel
    # without relying on user/model text or changing what can be copied.
    _bubble_property = 0x100001  # QTextFormat.UserProperty + 1

    @staticmethod
    def _bubble_margin(width):
        return max(0, min(round(width * .30), width - 150))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if getattr(self, '_reflowing_bubbles', False):
            return
        self._reflowing_bubbles = True
        try:
            margin = self._bubble_margin(self.viewport().width())
            block = self.document().begin()
            while block.isValid():
                fmt = block.blockFormat()
                side = fmt.property(self._bubble_property)
                if side in ('you', 'ai'):
                    left, right = (margin, 8) if side == 'you' else (8, margin)
                    if fmt.leftMargin() != left or fmt.rightMargin() != right:
                        fmt.setLeftMargin(left)
                        fmt.setRightMargin(right)
                        QTextCursor(block).setBlockFormat(fmt)
                block = block.next()
        finally:
            self._reflowing_bubbles = False

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        # Cap scrollback so an hours-long session can't grow the document
        # without bound — keeps memory flat and every insert cheap. Oldest
        # lines drop off the top automatically.
        self.document().setMaximumBlockCount(600)
        self.setFont(QFont("Courier New", 9))
        self.setStyleSheet(f"""
            QTextEdit {{
                background: {C.PANEL};
                color: {C.TEXT};
                border: 1px solid {C.BORDER};
                border-radius: 4px;
                padding: 6px;
                selection-background-color: {C.PRI_GHO};
            }}
            QScrollBar:vertical {{
                background: {C.BG};
                width: 8px;
                border: none;
            }}
            QScrollBar::handle:vertical {{
                background: {C.BORDER_B};
                border-radius: 4px;
                min-height: 20px;
            }}
        """)
        self._queue: list[str] = []
        self._typing  = False
        self._text    = ""
        self._pos     = 0
        self._tag     = "sys"
        self._ai_name_lc = "jarvis"   # updated when assistant name changes
        self._tmr = QTimer(self)
        self._tmr.timeout.connect(self._step)
        self._sig.connect(self._enqueue)

    def append_log(self, text: str):
        self._sig.emit(text)

    def _enqueue(self, text: str):
        self._queue.append(text)
        if not self._typing:
            self._next()

    def _next(self):
        if not self._queue:
            self._typing = False
            return
        self._typing = True
        self._text   = self._queue.pop(0)
        self._pos    = 0
        tl = self._text.lower()
        _ai_pfx = f"{self._ai_name_lc}:"
        if   tl.startswith("you:"):                              self._tag = "you"
        elif tl.startswith(_ai_pfx) or tl.startswith("jarvis:"): self._tag = "ai"
        elif tl.startswith("file:"):                             self._tag = "file"
        elif "err" in tl:                                        self._tag = "err"
        else:                                                    self._tag = "sys"
        self._tmr.start(6)

    def _step(self):
        if self._pos < len(self._text):
            ch  = self._text[self._pos]
            cur = self.textCursor()
            if self._pos == 0:
                # Use native text blocks rather than inserting HTML: text from a model
                # or user remains inert and selectable, while chat messages get the
                # alignment and restrained blue surface of the desktop concept.
                cur.movePosition(cur.MoveOperation.End)
                block = QTextBlockFormat()
                block.setTopMargin(4)
                block.setBottomMargin(4)
                if self._tag in ("you", "ai"):
                    block.setAlignment(Qt.AlignmentFlag.AlignRight if self._tag == "you"
                                       else Qt.AlignmentFlag.AlignLeft)
                    margin = self._bubble_margin(self.viewport().width())
                    block.setLeftMargin(margin if self._tag == "you" else 8)
                    block.setRightMargin(8 if self._tag == "you" else margin)
                    block.setProperty(self._bubble_property, self._tag)
                    block.setBackground(QBrush(QColor("#1c3a59" if self._tag == "you" else "#192d41")))
                else:
                    block.setLeftMargin(8)
                    block.setRightMargin(8)
                cur.setBlockFormat(block)
                self.setTextCursor(cur)
            fmt = cur.charFormat()
            col = {
                "you":  qcol(C.WHITE),
                "ai":   qcol(C.DESKTOP_TEXT),
                "err":  qcol(C.RED),
                "file": qcol(C.GREEN),
                # SYS lines are the bulk of the log. Amber fought the cyan HUD
                # and, being a fixed status colour rather than a hue-linked one,
                # stayed amber even after the accent picker retinted everything
                # else. TEXT_MED follows the theme and drops the contrast to a
                # level you can read past.
                "sys":  qcol(C.TEXT_MED),
            }.get(self._tag, qcol(C.TEXT))
            fmt.setForeground(QBrush(col))
            cur.movePosition(cur.MoveOperation.End)
            cur.insertText(ch, fmt)
            self.setTextCursor(cur)
            self.ensureCursorVisible()
            self._pos += 1
        else:
            self._tmr.stop()
            cur = self.textCursor()
            cur.movePosition(cur.MoveOperation.End)
            cur.insertText("\n")
            self.setTextCursor(cur)
            self.ensureCursorVisible()
            QTimer.singleShot(20, self._next)

