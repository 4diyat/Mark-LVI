"""The pass-through overlay base and the confirmation banner.

WHY THIS MOVED OUT OF ui/window.py
    `window.py` is 6,900 lines and `MainWindow` alone is 3,066 of them. The
    modules already in `ui/` (audio, overlays, theme) prove the pattern; these
    two classes are the next honest cut, and they depend on nothing but Qt, the
    palette and the translation helper — no `self.` from the window reaches into
    them, so moving them cannot change behaviour.

    `_HudOverlay` is here rather than left behind because every overlay placed
    with `_centre_overlay` needs its repaint-on-hide, and it is the base both
    this banner and the panels in ui/overlays.py sit on.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (
    QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget,
)

from core.i18n import label as _t
from ui.theme import C


class _HudOverlay(QWidget):
    """Base for the floating panels placed by hand over the HUD.

    They are children of the central widget but sit in no layout, so Qt never
    invalidates the region they occupy when they hide or shrink: the HUD keeps
    painting around them and their last frame stays on screen as a ghost. Any
    overlay positioned with _centre_overlay needs this."""

    def hideEvent(self, e):
        p = self.parentWidget()
        if p is not None:
            # Repaint exactly what we were covering, before we stop covering it.
            p.update(self.geometry())
        super().hideEvent(e)

    def closeEvent(self, e):
        p = self.parentWidget()
        if p is not None:
            p.update(self.geometry())
        super().closeEvent(e)

class ConfirmBanner(_HudOverlay):
    """The gate in front of an action that cannot be taken back.

    The old confirmation was a tool parameter the model filled in itself, which
    means it confirmed its own shutdown requests. This is the interface asking,
    and the answer travels from a human finger to core/confirm.py without the
    model in the loop. Nothing blocks while it is up: the assistant keeps
    talking, so this costs no latency — unlike the old gate, which spent two
    tool round trips on every power command."""

    answered = pyqtSignal(bool)
    _OW = 430

    def __init__(self, title: str = "", detail: str = "", parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            ConfirmBanner {{
                background: rgba(14, 3, 0, 250);
                border: 1px solid {C.ACC};
                border-radius: 6px;
            }}
        """)
        self.setFixedWidth(self._OW)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(8)

        hdr = QLabel(_t("ui.confirm.heading"))
        hdr.setFont(QFont("Courier New", 11, QFont.Weight.Bold))
        hdr.setStyleSheet(f"color: {C.ACC}; background: transparent;")
        lay.addWidget(hdr)

        ttl = QLabel(title)
        ttl.setTextFormat(Qt.TextFormat.PlainText)
        ttl.setWordWrap(True)
        ttl.setFont(QFont("Courier New", 10, QFont.Weight.Bold))
        ttl.setStyleSheet(f"color: {C.TEXT}; background: transparent;")
        lay.addWidget(ttl)
        self._title_label = ttl

        if detail:
            dtl = QLabel(detail)
            dtl.setTextFormat(Qt.TextFormat.PlainText)
            dtl.setWordWrap(True)
            dtl.setFont(QFont("Courier New", 8))
            dtl.setStyleSheet(f"color: {C.TEXT_MED}; background: transparent;")
            lay.addWidget(dtl)
        self._detail_label = dtl if detail else None

        row = QHBoxLayout(); row.setSpacing(8)

        yes = QPushButton(_t("ui.confirm.button"))
        yes.setFixedHeight(32)
        yes.setFont(QFont("Courier New", 9, QFont.Weight.Bold))
        yes.setCursor(Qt.CursorShape.PointingHandCursor)
        yes.setStyleSheet(f"""
            QPushButton {{ background: transparent; color: {C.ACC};
                border: 1px solid {C.ACC}; border-radius: 3px; }}
            QPushButton:hover {{ background: rgba(255,107,0,40); }}
        """)
        yes.clicked.connect(lambda: self.answered.emit(True))
        row.addWidget(yes)

        no = QPushButton(_t("ui.cancel"))
        no.setFixedHeight(32)
        no.setFont(QFont("Courier New", 9))
        no.setCursor(Qt.CursorShape.PointingHandCursor)
        no.setStyleSheet(f"""
            QPushButton {{ background: transparent; color: {C.TEXT_MED};
                border: 1px solid {C.BORDER}; border-radius: 3px; }}
            QPushButton:hover {{ color: {C.TEXT}; border-color: {C.BORDER_B}; }}
        """)
        no.clicked.connect(lambda: self.answered.emit(False))
        row.addWidget(no)
        lay.addLayout(row)

        # Default focus on CANCEL: if someone hits Enter without reading, the
        # safe answer wins.
        no.setDefault(True)
        no.setFocus()

    def set_title(self, title: str, detail: str = "") -> None:
        """Reuse this banner for a second question.

        A new window per question would flicker `hide` then `show` on a desktop
        with nothing else on it, which reads as a glitch rather than as a new
        question. Reusing one widget also means the focus rule (CANCEL first)
        is only written once.
        """
        self._title_label.setText(str(title or ""))
        detail_label = self._detail_label
        if detail_label is None:
            return
        detail_label.setText(str(detail or ""))
        detail_label.setVisible(bool(detail))
        self.adjustSize()


def build_confirm_window(parent=None) -> "ConfirmBanner":
    """A `ConfirmBanner` that is its own always-on-top window.

    WHY NOT A CHILD OF THE ORB
        The orb is 28-56 px. A 430 px banner parented to it is clipped to the
        orb's own geometry, so the user is told to confirm something that is not
        on screen — and `core/confirm` refuses the action 90 seconds later with
        nothing to explain why. Artboard 25 draws this banner bottom-centre over
        whatever the user is doing, which is a window, not a child widget.

    Tool + WindowStaysOnTop + Frameless is the same trio the face bubble uses
    (`ui/face_bubble.window_flags`), so the two floating surfaces cannot drift
    apart in how they ask the window manager for the same thing.
    """
    from PyQt6.QtCore import Qt

    banner = ConfirmBanner("", "", parent)
    banner.setWindowFlags(banner.windowFlags()
                          | Qt.WindowType.Tool
                          | Qt.WindowType.FramelessWindowHint
                          | Qt.WindowType.WindowStaysOnTopHint)
    banner.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, False)
    _place_bottom_centre(banner)
    return banner


def _place_bottom_centre(banner) -> None:
    """Put the banner where artboard 25 puts it, on whichever screen has focus.

    Not the primary screen: a user with two monitors confirms on the one they
    are looking at. A missing screen (headless, or before the first window) is
    not an error — Qt will place the window itself.
    """
    try:
        from PyQt6.QtGui import QCursor, QGuiApplication

        screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        if screen is None:
            return
        area = screen.availableGeometry()
        banner.adjustSize()
        width, height = banner.width(), banner.height()
        banner.move(area.x() + (area.width() - width) // 2,
                    area.y() + area.height() - height - 64)
    except Exception as e:                          # noqa: BLE001
        # Placement is cosmetic; the banner is still on top and still modal in
        # the only sense that matters (it holds the answer). `show_confirm`
        # reports failures to show, so nothing is lost here.
        print(f"[JARVIS] Confirm: placement skipped — {type(e).__name__}: {e}")
