"""Selectable, bounded assistant conversation on the Qt main thread."""
from PyQt6.QtCore import QRectF, QTimer, Qt, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QFont, QPainter, QRadialGradient, QTextBlockFormat, QTextCursor
from PyQt6.QtWidgets import QTextEdit

from ui.theme import C, qcol


class LogWidget(QTextEdit):
    _sig = pyqtSignal(str)
    # A document-local marker allows bubble widths to follow a resized panel
    # without relying on user/model text or changing what can be copied.
    _bubble_property = 0x100001  # QTextFormat.UserProperty + 1
    _message_property = 0x100002
    _bubble_padding = 10

    @staticmethod
    def _bubble_margin(width):
        return max(0, min(round(width * .30), width - 150))

    @classmethod
    def _bubble_margins(cls, width, side):
        margin = cls._bubble_margin(width)
        # Reserve room for role markers only when the panel has enough width;
        # narrow windows retain the text area instead.
        near = 38 if width >= 280 else 8
        pad = cls._bubble_padding
        return ((margin + pad, near + pad) if side == 'you'
                else (near + pad, margin + pad))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if getattr(self, '_reflowing_bubbles', False):
            return
        self._reflowing_bubbles = True
        try:
            width = self.viewport().width()
            block = self.document().begin()
            while block.isValid():
                fmt = block.blockFormat()
                side = fmt.property(self._bubble_property)
                if side in ('you', 'ai'):
                    left, right = self._bubble_margins(width, side)
                    if fmt.leftMargin() != left or fmt.rightMargin() != right:
                        fmt.setLeftMargin(left)
                        fmt.setRightMargin(right)
                        QTextCursor(block).setBlockFormat(fmt)
                block = block.next()
        finally:
            self._reflowing_bubbles = False

    def _bubble_rects(self):
        """Return visible message backdrops in viewport coordinates.

        Message IDs combine consecutive paragraphs into one bubble while keeping
        separate messages distinct. Never inspect text as HTML or alter the
        document during painting.
        """
        document = self.document()
        layout = document.documentLayout()
        viewport = self.viewport()
        scroll_x = self.horizontalScrollBar().value()
        scroll_y = self.verticalScrollBar().value()
        doc_margin = document.documentMargin()
        result = []
        block = document.begin()
        while block.isValid():
            fmt = block.blockFormat()
            side, message = fmt.property(self._bubble_property), fmt.property(self._message_property)
            if side in ('you', 'ai') and message is not None and block.text():
                bounds = layout.blockBoundingRect(block).translated(-scroll_x, -scroll_y)
                pad = self._bubble_padding
                left = doc_margin + fmt.leftMargin() - pad - scroll_x
                right = viewport.width() - doc_margin - fmt.rightMargin() + pad - scroll_x
                rect = QRectF(left, bounds.top() - 4, max(1.0, right - left), bounds.height() + 8)
                if result and result[-1][2] == message:
                    previous, _, _ = result[-1]
                    result[-1] = (previous.united(rect), side, message)
                else:
                    result.append((rect, side, message))
            block = block.next()
        return [(rect, side) for rect, side, _ in result if rect.intersects(QRectF(viewport.rect()))]

    def paintEvent(self, event):
        painter = QPainter(self.viewport())
        painter.setClipRect(event.rect())
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        for rect, side in self._bubble_rects():
            painter.setBrush(QColor("#1c3a59" if side == "you" else "#192d41"))
            painter.drawRoundedRect(rect, 9, 9)
            if self.viewport().width() >= 280:
                # Non-interactive role markers are painted outside the text
                # document: copying, selection and streaming stay unchanged.
                x = rect.right() + 6 if side == "you" else rect.left() - 30
                icon = QRectF(x, rect.top() + 1, 24, 24)
                if side == "ai":
                    gradient = QRadialGradient(icon.center(), 12)
                    gradient.setColorAt(0, QColor("#164c83"))
                    gradient.setColorAt(.65, QColor("#127dd1"))
                    gradient.setColorAt(1, QColor("#7adfff"))
                    painter.setBrush(gradient)
                    painter.drawEllipse(icon)
                    painter.setBrush(QColor("#123251"))
                    painter.drawEllipse(icon.adjusted(5, 5, -5, -5))
                else:
                    painter.setBrush(QColor("#344d67"))
                    painter.drawEllipse(icon)
                    painter.setBrush(QColor("#bdcee1"))
                    painter.drawEllipse(QRectF(x + 8, icon.top() + 4, 8, 8))
                    painter.drawRoundedRect(QRectF(x + 5, icon.top() + 14, 14, 7), 4, 4)
        painter.end()
        # Let Qt draw the actual selectable document and selection on top.
        super().paintEvent(event)

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
        self._bubble_sequence = 0
        self._ai_name_lc = "jarvis"   # updated when assistant name changes
        self._tmr = QTimer(self)
        self._tmr.timeout.connect(self._step)
        self._sig.connect(self._enqueue)

    def append_log(self, text: str):
        self._sig.emit(text)
        self._remember(text)

    def _remember(self, text: str) -> None:
        """Keep the last assistant line, for the desktop notification.

        WHY HERE
            The notification needs the text of the answer, and this is the only
            place the program already holds it in one piece: `main.py` streams
            captions and logs them, so the log line IS the answer. Reading it
            back from the widget would mean walking a QTextDocument from a
            status callback on another thread; keeping the last line is a string
            assignment.

            Only assistant lines are kept, and only the last one: this exists to
            say "JARVIS finished, and here is what it said", not to become a
            second log.
        """
        line = (text or "").strip()
        if not line:
            return
        lower = line.lower()
        if lower.startswith("you:") or lower.startswith("file:"):
            return
        if lower.startswith(f"{self._ai_name_lc}:") or lower.startswith("jarvis:"):
            # Strip the speaker prefix: a notification repeats the name in its
            # title, and "J.A.R.V.I.S / JARVIS: It is done" reads as a stutter.
            _, _, body = line.partition(":")
            self.last_said = body.strip()[:180]

    @property
    def last_answer(self) -> str:
        """The last thing the assistant said, or '' — used by core.notify."""
        return getattr(self, "last_said", "")

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
        # Work on a cursor copy, not the widget's selection. Follow new output
        # only if the reader was already at the bottom and is not selecting.
        cur = self.textCursor()
        scrollbar = self.verticalScrollBar()
        follow = not cur.hasSelection() and scrollbar.value() >= scrollbar.maximum() - 2
        cur.movePosition(cur.MoveOperation.End)
        if self._pos < len(self._text):
            ch  = self._text[self._pos]
            if self._pos == 0:
                # Use native text blocks rather than inserting HTML: text from a model
                # or user remains inert and selectable, while chat messages get the
                # alignment and restrained blue surface of the desktop concept.
                block = QTextBlockFormat()
                block.setTopMargin(4)
                block.setBottomMargin(4)
                if self._tag in ("you", "ai"):
                    block.setAlignment(Qt.AlignmentFlag.AlignRight if self._tag == "you"
                                       else Qt.AlignmentFlag.AlignLeft)
                    left, right = self._bubble_margins(self.viewport().width(), self._tag)
                    block.setLeftMargin(left)
                    block.setRightMargin(right)
                    self._bubble_sequence += 1
                    block.setProperty(self._bubble_property, self._tag)
                    block.setProperty(self._message_property, self._bubble_sequence)
                else:
                    block.setLeftMargin(8)
                    block.setRightMargin(8)
                cur.setBlockFormat(block)
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
            cur.insertText(ch, fmt)
            self._pos += 1
            # Qt's small dirty text rectangle does not include rounded padding.
            self.viewport().update()
        else:
            self._tmr.stop()
            cur.insertText("\n")
            QTimer.singleShot(20, self._next)
        if follow:
            scrollbar.setValue(scrollbar.maximum())

