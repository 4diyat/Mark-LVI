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

# ── board 25's tokens, declared here rather than borrowed ───────────────────
#
# THE HUD PALETTE IS NOT THIS DIALOG'S PALETTE. `ui.theme.C` still carries the
# #171719 / #ff6b00 look of the full-screen window that ambient mode replaced.
# Every ambient surface that draws (`orb_paint`, `toast_card`, `tray_pages`,
# `voice_paint`, `face_canvas`) declares the design system's numbers directly,
# and this module was the last one reading `C` — which is exactly why it was
# the one surface that looked nothing like its artboard.
#
# Values are copied from `docs/mockups/build.py`, not invented: BASE, TEXT,
# MUTED, AMBER and LINE are the sheet's tokens, and #0C1B26 is the artboard's
# own card fill for the risk dialog.
BASE = "#04080D"
PANEL = "#0A1722"
LINE = "#17323F"
LINE_ACC = "#2A6477"
AMBER = "#F5A524"
TEXT = "#E6F4F8"
MUTED = "#8FA9B5"
AMBER_BG = "#0C1B26"
#: `FONT` in the sheet is 'Space Grotesk','Segoe UI',Arial — a fallback chain,
#: because Space Grotesk is not installed on every machine.
FONT = "Space Grotesk, Segoe UI, Arial"

# ── board 25's two constants ────────────────────────────────────────────────
#
# BOTH ARE FIXED TEXT RATHER THAN CATALOGUE KEYS, AND THAT IS DELIBERATE.
#
# `CANNOT_UNDO` is a statement about THIS dialog: the action behind it cannot be
# taken back, which is the entire reason the dialog exists. A translation that
# softened it would be a translation that changed a safety fact.
#
# `KEYS_HINT` is a keyboard legend. "Enter" and "Esc" are the names printed on
# every keyboard that has them; translating them produces a legend for keys the
# user does not own. The artboard writes them in a monospace face for the same
# reason: they are key names, not prose.
CANNOT_UNDO = "Tindakan ini tidak bisa diurungkan."
KEYS_HINT = "Enter · Esc"

# WHERE THE COMMAND CAME FROM LIVES IN `core/input_source`, not here.
#
# The two callers are in `main.py`'s audio loop and its text handler, and this
# module imports PyQt6 at module level — an import that needs a display has no
# business running inside an audio callback on a machine with no Qt. The store
# therefore lives in a module that imports nothing, and this module only
# FORMATS what it recorded.

def origin_text(source: str | None = None) -> str:
    """The origin line's first half — spoken, typed, or honestly unknown.

    Unknown is a real answer, not a failure: a plugin, a timer, or a deeplink
    can start an action with no human input in the last minute. Saying "spoken
    command" for those is how the caption becomes untrustworthy everywhere.
    """
    if source is None:
        from core import input_source

        source = input_source.current()
    key = str(source or "").strip().lower()
    if key == "voice":
        return _t("ui.confirm.origin.voice")
    if key == "typed":
        return _t("ui.confirm.origin.typed")
    return _t("ui.confirm.origin.unknown")


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

    def resizeEvent(self, event):                   # noqa: N802 — Qt's name
        """Keep the risk bar against the left edge, inset like the artboard.

        Board 25 insets it 18 px from the dialog's top and bottom, so it reads
        as a marker rather than a frame. Pinned here rather than in the layout
        because it must not take part in the column: it is an edge decoration,
        and a layout row would push the 28 px text inset sideways.
        """
        # `super()` is guarded because `resizeEvent` is not on every Qt binding
        # this project can be run against, and a decoration failing to place
        # itself must never be the reason the dialog cannot be shown at all.
        try:
            super().resizeEvent(event)
        except AttributeError:
            pass
        bar = getattr(self, "_risk_bar", None)
        if bar is not None:
            bar.setGeometry(1, 18, 3, max(0, self.height() - 36))
    #: Board 25's dialog is 520 px wide. This used to be 430, which is 90 px
    #: narrower than the artboard — the title wrapped earlier than the drawing
    #: and the two buttons sat closer together than the sheet shows.
    _OW = 520

    def __init__(self, title: str = "", detail: str = "", parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        # BOARD 25'S OWN TOKENS, not the legacy HUD palette.
        #
        # This used `rgba(14, 3, 0, 250)` — near-black with a red cast — a
        # `AMBER` (#ff6b00) orange border and a 6 px radius. The artboard draws
        # #0C1B26, an AMBER border, a 16 px radius and a 3 px amber bar inset
        # 18 px down the left edge. Four differences at once is not a shade
        # apart, it is a different dialog: the HUD palette belongs to the
        # window that no longer exists, and this is the one surface a user is
        # asked to trust with an irreversible action.
        # The 3 px risk bar is NOT a CSS `border-left`. Qt's stylesheet engine
        # only paints per-side borders on some widget classes, and a
        # `QWidget` with `WA_StyledBackground` is one of the ones where it
        # silently draws nothing — `ASSUMPTIONS` A5 makes that bar load-bearing
        # ("bahaya dibedakan lewat bentuk: garis kiri 3 px"), so it is a real
        # widget pinned to the left edge instead of a hope about the renderer.
        self.setStyleSheet(f"""
            ConfirmBanner {{
                background: {AMBER_BG};
                border: 1px solid {AMBER};
                border-radius: 16px;
            }}
        """)
        self.setFixedWidth(self._OW)

        self._risk_bar = QWidget(self)
        self._risk_bar.setFixedWidth(3)
        self._risk_bar.setStyleSheet(
            f"background: {AMBER}; border-radius: 1.5px;")

        lay = QVBoxLayout(self)
        # Artboard 25: every element is inset 28 px from the dialog edge, and
        # the rows are 20–24 px apart. The old 20/16 padding drew the title 8 px
        # left of where the sheet puts it and pulled the whole column up.
        lay.setContentsMargins(28, 22, 28, 22)
        lay.setSpacing(10)

        hdr = QLabel(_t("ui.confirm.heading"))
        hdr.setFont(QFont(FONT, 10, QFont.Weight.DemiBold))
        hdr.setStyleSheet(f"color: {AMBER}; background: transparent;")
        lay.addWidget(hdr)

        ttl = QLabel(title)
        ttl.setTextFormat(Qt.TextFormat.PlainText)
        ttl.setWordWrap(True)
        ttl.setFont(QFont(FONT, 13, QFont.Weight.Medium))
        ttl.setStyleSheet(f"color: {TEXT}; background: transparent;")
        lay.addWidget(ttl)
        self._title_label = ttl

        # "Tindakan ini tidak bisa diurungkan." — artboard 25 prints it under
        # the title as a standing sentence, so the user reads WHY they are being
        # asked before they read what they are being asked about.
        never = QLabel(CANNOT_UNDO)
        never.setTextFormat(Qt.TextFormat.PlainText)
        never.setWordWrap(True)
        never.setFont(QFont(FONT, 7))
        never.setStyleSheet(f"color: {MUTED}; background: transparent;")
        lay.addWidget(never)
        self._never_label = never

        # ALWAYS BUILT, HIDDEN WHILE EMPTY. Building it only when the
        # constructor was handed a detail made the artboard's line impossible to
        # reach: `build_confirm_window()` passes "" and the real detail arrives
        # later through `set_title`, so on the live path this label never
        # existed and "Lampiran: anggaran.xlsx · 3 penerima" could never appear.
        dtl = QLabel(detail)
        dtl.setTextFormat(Qt.TextFormat.PlainText)
        dtl.setWordWrap(True)
        dtl.setFont(QFont(FONT, 7))
        dtl.setStyleSheet(f"color: {MUTED}; background: transparent;")
        dtl.setVisible(bool(detail))
        lay.addWidget(dtl)
        self._detail_label = dtl

        # ── ASAL PERMINTAAN ─────────────────────────────────────────────
        # Artboard 25 has this field and the banner did not. It answers the
        # question a user actually has in front of an irreversible action:
        # "who asked for this?" — not "what is JARVIS about to do", which the
        # title already says.
        self._origin_header = QLabel(_t("ui.confirm.origin").upper())
        self._origin_header.setFont(QFont(FONT, 7, QFont.Weight.DemiBold))
        self._origin_header.setStyleSheet(
            f"color: {MUTED}; background: transparent;")
        lay.addWidget(self._origin_header)

        self._origin_label = QLabel("")
        self._origin_label.setTextFormat(Qt.TextFormat.PlainText)
        self._origin_label.setWordWrap(True)
        self._origin_label.setFont(QFont(FONT, 7))
        self._origin_label.setStyleSheet(
            f"color: {TEXT}; background: transparent;")
        lay.addWidget(self._origin_label)

        row = QHBoxLayout(); row.setSpacing(8)

        yes = QPushButton(_t("ui.confirm.button"))
        # ARTBOARD 25's PILL: 150×40, radius h/2, FILLED with the accent and
        # dark text on it (`pill_btn(..., primary=True)`). The old button was
        # 32 px tall with a transparent body and a 3 px radius, so the one
        # action the dialog exists for was drawn like a secondary one.
        yes.setFixedHeight(40)
        yes.setMinimumWidth(150)
        yes.setFont(QFont(FONT, 9, QFont.Weight.DemiBold))
        yes.setCursor(Qt.CursorShape.PointingHandCursor)
        yes.setStyleSheet(f"""
            QPushButton {{ background: {AMBER}; color: {BASE};
                border: 1px solid {AMBER}; border-radius: 20px; }}
            QPushButton:hover {{ background: #FFB944; border-color: #FFB944; }}
            QPushButton:focus {{ border: 1px solid {TEXT}; }}
        """)
        yes.clicked.connect(lambda: self.answered.emit(True))
        row.addWidget(yes)

        no = QPushButton(_t("ui.cancel"))
        # The artboard's secondary pill: 130×40, transparent, hairline border.
        no.setFixedHeight(40)
        no.setMinimumWidth(130)
        no.setFont(QFont(FONT, 9))
        no.setCursor(Qt.CursorShape.PointingHandCursor)
        no.setStyleSheet(f"""
            QPushButton {{ background: transparent; color: {TEXT};
                border: 1px solid {LINE_ACC}; border-radius: 20px; }}
            QPushButton:hover {{ background: {PANEL}; border-color: {TEXT}; }}
            QPushButton:focus {{ border: 1px solid {TEXT}; }}
        """)
        no.clicked.connect(lambda: self.answered.emit(False))
        row.addWidget(no)
        self._confirm_button = yes
        self._cancel_button = no
        lay.addLayout(row)

        # ── "Enter · Esc" ───────────────────────────────────────────────────
        # In the artboard's corner, right-aligned, monospace — a keyboard
        # legend rather than prose. `setAlignment` on a label inside a vertical
        # layout is enough: no second row of buttons to hang it off.
        self._keys_label = QLabel(KEYS_HINT)
        self._keys_label.setFont(QFont(FONT, 7))
        self._keys_label.setAlignment(Qt.AlignmentFlag.AlignRight)
        self._keys_label.setStyleSheet(
            f"color: {MUTED}; background: transparent;")
        lay.addWidget(self._keys_label)

        # Default focus on CANCEL: if someone hits Enter without reading, the
        # safe answer wins.
        no.setDefault(True)
        no.setFocus()

    # ── the two keys the artboard names ─────────────────────────────────────
    #
    # THE OWNER'S RULING REVERSED THE OLD ONE. `test_cancel_has_the_focus_so_a
    # _stray_enter_is_safe` pinned CANCEL as default so an unread Enter could
    # never confirm. Board 25 writes "Enter · Esc" in the corner, so the dialog
    # answers to both — AND THE INITIAL FOCUS STILL STARTS ON CANCEL, which is
    # what keeps the old safety property: Enter pressed without touching
    # anything confirms nothing, because the focused widget swallows it. Enter
    # confirms once the user has moved to Konfirmasi.
    def keyPressEvent(self, event):                 # noqa: N802 — Qt's name
        from PyQt6.QtCore import Qt as _Qt

        key = event.key()
        if key == _Qt.Key.Key_Escape:
            self.answered.emit(False)
            event.accept()
            return
        if key in (_Qt.Key.Key_Return, _Qt.Key.Key_Enter):
            self.answered.emit(True)
            event.accept()
            return
        # Every other key belongs to whatever has focus — including the Tab
        # that moves focus to Konfirmasi. Guarded because the base class may not
        # have the method at all (a widget built on a stub, or a future base
        # that is not a QWidget): an unhandled key must not raise out of a
        # dialog that is waiting for an answer.
        handler = getattr(super(), "keyPressEvent", None)
        if callable(handler):
            handler(event)
        else:
            event.ignore()

    def set_origin(self, when: str = "", source: str | None = None) -> None:
        """The caption under "ASAL PERMINTAAN": who asked, when, and whether it
        is on the record.

        THREE FACTS, AND EACH ONE IS TRUE. The source comes from what the entry
        points recorded, the time from the request itself, and "tercatat di
        audit log" from `core/confirm._audit`, which writes every decision. A
        line that guessed any of the three would be worse than no line.
        """
        parts = [origin_text(source)]
        if when:
            parts.append(str(when))
        parts.append(_t("ui.confirm.logged"))
        self._origin_label.setText(" · ".join(parts))

    def set_title(self, title: str, detail: str = "") -> None:
        """Reuse this banner for a second question.

        A new window per question would flicker `hide` then `show` on a desktop
        with nothing else on it, which reads as a glitch rather than as a new
        question. Reusing one widget also means the focus rule (CANCEL first)
        is only written once.
        """
        self._title_label.setText(str(title or ""))
        detail_label = self._detail_label
        if detail_label is not None:
            detail_label.setText(str(detail or ""))
            detail_label.setVisible(bool(detail))
        # NOT AN EARLY RETURN when there is no detail. The banner with no detail
        # line is the common case, and the first version returned here — so a
        # reused banner kept the PREVIOUS question's origin and time, which is
        # the one line on this dialog that is a lie when it is stale.
        # A reused banner must not keep the previous question's origin — that
        # is the one line on this dialog that would then be a lie. The TIME is
        # refreshed too, and this first version refreshed only the source: the
        # test that reuses the banner went from "14:31" to no time at all.
        from datetime import datetime

        self.set_origin(when=datetime.now().strftime("%H:%M"))
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
