"""ui/overlays.py — the panels that float over the HUD and exist to set something.

WHY THESE THREE MOVED OUT OF ui/window.py
    The customise panel, the plugin list and its toggle rows are the first
    place a translation has to reach: they are all label and all instruction.
    Keeping them inside a 7,000-line module made the i18n work impossible to
    finish honestly — a panel that has to be re-rendered by hand cannot find its
    own labels, and `ui/window.py` was at its size ceiling with the language row
    still unwritten.

    They also have the smallest number of dependencies in that file: a palette,
    two config calls, and the catalogue. Nothing here needs the HUD, the
    session, the metrics sampler or the log — so this module imports no part of
    the window, and `ui/window.py` imports it, in that direction only.

WHAT A RETRANSLATION NEEDS, AND WHY THE HANDLES STAY
    CustomizeOverlay keeps a handle on each caption it writes, because changing
    the language must repaint the panel in place. A label built as
    `_lbl(text)` and not stored can never be updated — that was the reason the
    language row could not be added before the class was movable.
"""
from __future__ import annotations

import math
import threading

from PyQt6.QtCore import QPointF, Qt, QRectF, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QConicalGradient, QFont, QPainter, QPen
from PyQt6.QtWidgets import (
    QComboBox, QFrame, QHBoxLayout, QLabel, QLineEdit, QPushButton, QScrollArea,
    QVBoxLayout, QWidget,
)

from core.i18n import label as _t, set_locale
from ui.theme import C, DEFAULT_UI_COLOR, qcol


class HueWheel(QWidget):
    """
    Circular colour picker. The user drags the handle (small white circle)
    around the wheel to choose from ALL hues. The filled circle in the centre
    is a live preview of the selected colour.
    """

    hue_picked    = pyqtSignal(str)   # while dragging (live)
    hue_committed = pyqtSignal(str)   # when the handle is released

    _RING = 16   # ring thickness (px)

    def __init__(self, initial_hex: str = DEFAULT_UI_COLOR, parent=None):
        super().__init__(parent)
        self.setFixedSize(148, 148)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._hue  = 0.53
        self._drag = False
        self.set_color(initial_hex)

    # ── API ──────────────────────────────────────────────────────────────────
    def color(self) -> str:
        return QColor.fromHsvF(self._hue, 1.0, 1.0).name()

    def set_color(self, hex_str: str):
        c = QColor((hex_str or "").strip())
        if c.isValid() and c.hsvHueF() >= 0:
            self._hue = c.hsvHueF()
            self.update()

    # ── geometry helpers ─────────────────────────────────────────────────────
    def _ring_rect(self) -> QRectF:
        m = self._RING / 2 + 3
        return QRectF(self.rect()).adjusted(m, m, -m, -m)

    def _hue_from_pos(self, pos: QPointF) -> float:
        c  = QRectF(self.rect()).center()
        dx = pos.x() - c.x()
        dy = c.y() - pos.y()          # screen y goes down — flip to math axis
        ang = math.atan2(dy, dx)      # [-π, π], counter-clockwise
        return (ang / (2 * math.pi)) % 1.0

    # ── drawing ──────────────────────────────────────────────────────────────
    def paintEvent(self, _):
        p = QPainter(self)
        if not p.isActive():
            return
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect   = self._ring_rect()
        center = rect.center()

        grad = QConicalGradient(center, 0)
        for i in range(0, 361, 20):
            grad.setColorAt(i / 360.0, QColor.fromHsvF((i % 360) / 360.0, 1.0, 1.0))
        p.setPen(QPen(QBrush(grad), self._RING))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawEllipse(rect)

        # centre preview circle
        preview = QColor.fromHsvF(self._hue, 1.0, 1.0)
        inner   = rect.adjusted(30, 30, -30, -30)
        p.setPen(QPen(qcol(C.BORDER_B), 1))
        p.setBrush(QBrush(preview))
        p.drawEllipse(inner)

        # draggable handle
        r   = rect.width() / 2
        ang = self._hue * 2 * math.pi
        hx  = center.x() + r * math.cos(ang)
        hy  = center.y() - r * math.sin(ang)
        p.setPen(QPen(QColor("#00060a"), 2))
        p.setBrush(QBrush(QColor("#ffffff")))
        p.drawEllipse(QPointF(hx, hy), 7.5, 7.5)
        p.end()

    # ── fare ─────────────────────────────────────────────────────────────────
    def mousePressEvent(self, e):
        self._drag = True
        self._hue  = self._hue_from_pos(e.position())
        self.update()
        self.hue_picked.emit(self.color())

    def mouseMoveEvent(self, e):
        if self._drag:
            self._hue = self._hue_from_pos(e.position())
            self.update()
            self.hue_picked.emit(self.color())

    def mouseReleaseEvent(self, e):
        if self._drag:
            self._drag = False
            self.hue_committed.emit(self.color())




class CustomizeOverlay(QWidget):
    """Floating overlay — change assistant name, user name, UI colour and voice."""

    # assistant_name, user_name, ui_colour, voice, ui_language
    saved = pyqtSignal(str, str, str, str, str)
    _OW, _OH = 400, 588

    def __init__(self, assistant_name="JARVIS", user_name="",
                 ui_color=DEFAULT_UI_COLOR, voice="", parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            CustomizeOverlay {{
                background: rgba(0, 6, 10, 245);
                border: 1px solid {C.BORDER_B};
                border-radius: 6px;
            }}
        """)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 18, 24, 18)
        lay.setSpacing(8)

        def _lbl(txt, fs=9, bold=False, color=C.PRI, align=Qt.AlignmentFlag.AlignCenter):
            w = QLabel(txt); w.setAlignment(align)
            w.setFont(QFont("Courier New", fs,
                            QFont.Weight.Bold if bold else QFont.Weight.Normal))
            w.setStyleSheet(f"color: {color}; background: transparent;")
            return w

        _fs = (f"QLineEdit {{ background: #000d12; color: {C.TEXT}; "
               f"border: 1px solid {C.BORDER}; border-radius: 3px; padding: 4px 8px; }}"
               f"QLineEdit:focus {{ border: 1px solid {C.PRI}; }}")

        self._head_lbl = _lbl(_t("setup.customise"), 12, True)
        lay.addWidget(self._head_lbl)
        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {C.BORDER}; margin: 2px 0;")
        lay.addWidget(sep)

        self._name_cap = _lbl(_t("setup.name"), 8, color=C.TEXT_DIM,
                              align=Qt.AlignmentFlag.AlignLeft)
        lay.addWidget(self._name_cap)
        self._name_input = QLineEdit(assistant_name)
        self._name_input.setFont(QFont("Courier New", 10))
        self._name_input.setFixedHeight(32)
        self._name_input.setStyleSheet(_fs)
        lay.addWidget(self._name_input)

        lay.addSpacing(4)
        self._user_cap = _lbl(_t("setup.user_name"), 8, color=C.TEXT_DIM,
                              align=Qt.AlignmentFlag.AlignLeft)
        lay.addWidget(self._user_cap)
        self._user_input = QLineEdit(user_name)
        self._user_input.setPlaceholderText(_t("ui.placeholder.user_name"))
        self._user_input.setFont(QFont("Courier New", 10))
        self._user_input.setFixedHeight(32)
        self._user_input.setStyleSheet(_fs)
        lay.addWidget(self._user_input)

        # ── Assistant voice — Gemini prebuilt voices ─────────────────────────
        # Names are language-neutral proper nouns, so the row reads the same in
        # every locale. Selecting one and applying rebuilds the Live session.
        from memory.config_manager import AVAILABLE_VOICES, DEFAULT_VOICE
        lay.addSpacing(4)
        self._voice_cap = _lbl(_t("setup.voice"), 8, color=C.TEXT_DIM,
                              align=Qt.AlignmentFlag.AlignLeft)
        lay.addWidget(self._voice_cap)
        self._sel_voice   = (voice or DEFAULT_VOICE)
        if self._sel_voice not in AVAILABLE_VOICES:
            self._sel_voice = DEFAULT_VOICE
        self._voice_btns: dict[str, QPushButton] = {}
        voice_row = QHBoxLayout(); voice_row.setSpacing(4)
        for _v in AVAILABLE_VOICES:
            b = QPushButton(_v)
            b.setCheckable(True)
            b.setFixedHeight(28)
            b.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _=False, name=_v: self._on_voice_pick(name))
            self._voice_btns[_v] = b
            voice_row.addWidget(b)
        lay.addLayout(voice_row)
        self._refresh_voice_btns()

        # ── Interface language ───────────────────────────────────────────────
        # LAST in the panel on purpose: changing it re-renders every label, and
        # a row that moves under the pointer is worse than one at the bottom.
        # The names of the languages are written in the languages themselves —
        # a user who cannot read the current UI still recognises their own.
        lay.addSpacing(4)
        self._lang_cap = _lbl(_t("setup.language"), 8, color=C.TEXT_DIM,
                              align=Qt.AlignmentFlag.AlignLeft)
        lay.addWidget(self._lang_cap)
        from core.i18n import LOCALES, resolve
        from memory.config_manager import get_ui_language
        self._auto_lang = resolve(None)          # what "auto" currently means
        self._sel_lang  = get_ui_language()      # 'auto' or a locale
        self._initial_lang = self._sel_lang      # for _cancel
        self._lang_btns: dict[str, QPushButton] = {}
        lang_row = QHBoxLayout(); lang_row.setSpacing(4)
        options = [("auto", _t("setup.language.auto", locale=self._auto_lang.upper()))] + [
            (code, code.upper()) for code in LOCALES]
        for code, caption in options:
            b = QPushButton(caption)
            b.setCheckable(True)
            b.setFixedHeight(24)
            b.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _=False, c=code: self._pick_language(c))
            self._lang_btns[code] = b
            lang_row.addWidget(b)
        lang_row.addStretch()
        lay.addLayout(lang_row)
        self._refresh_lang_btns()

        # ── UI colour — colour wheel ─────────────────────────────────────────
        lay.addSpacing(4)
        clr_hdr = QHBoxLayout()
        self._colour_cap = _lbl(_t("setup.colour"), 8, color=C.TEXT_DIM,
                                align=Qt.AlignmentFlag.AlignLeft)
        clr_hdr.addWidget(self._colour_cap)
        clr_hdr.addStretch()
        self._default_btn = df_btn = QPushButton(_t("ui.default_btn"))
        df_btn.setFixedSize(64, 20)
        df_btn.setFont(QFont("Courier New", 7, QFont.Weight.Bold))
        df_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        df_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {C.TEXT_MED};
                border: 1px solid {C.BORDER}; border-radius: 3px;
            }}
            QPushButton:hover {{ color: {C.TEXT}; border-color: {C.BORDER_B}; }}
        """)
        df_btn.clicked.connect(lambda: self._set_color(DEFAULT_UI_COLOR))
        clr_hdr.addWidget(df_btn)
        lay.addLayout(clr_hdr)

        self._initial_color = (ui_color or DEFAULT_UI_COLOR).strip().lower()
        self._sel_color     = self._initial_color
        self.on_preview     = None   # callable(hex) — live preview; MainWindow wires it

        self._wheel = HueWheel(self._sel_color)
        wheel_row = QHBoxLayout()
        wheel_row.addStretch(); wheel_row.addWidget(self._wheel); wheel_row.addStretch()
        lay.addLayout(wheel_row)
        self._wheel.hue_picked.connect(self._on_wheel_pick)
        self._wheel.hue_committed.connect(self._on_wheel_commit)

        self._hex_input = QLineEdit(self._sel_color)
        self._hex_input.setPlaceholderText(_t("ui.placeholder.hex"))
        self._hex_input.setFont(QFont("Courier New", 10))
        self._hex_input.setFixedHeight(28)
        self._hex_input.setStyleSheet(_fs)
        self._hex_input.textEdited.connect(self._on_hex_edited)
        lay.addWidget(self._hex_input)

        lay.addSpacing(6)
        btn_row = QHBoxLayout(); btn_row.setSpacing(8)

        self._save_btn = save_btn = QPushButton(_t("ui.apply_changes"))
        save_btn.setFixedHeight(34)
        save_btn.setFont(QFont("Courier New", 9, QFont.Weight.Bold))
        save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        save_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {C.PRI};
                border: 1px solid {C.PRI_DIM}; border-radius: 3px;
            }}
            QPushButton:hover {{ background: {C.PRI_GHO}; border: 1px solid {C.PRI}; }}
        """)
        save_btn.clicked.connect(self._save)
        btn_row.addWidget(save_btn)

        self._cancel_btn = cancel_btn = QPushButton(_t("ui.cancel"))
        cancel_btn.setFixedHeight(34)
        cancel_btn.setFont(QFont("Courier New", 9))
        cancel_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        cancel_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {C.TEXT_MED};
                border: 1px solid {C.BORDER}; border-radius: 3px;
            }}
            QPushButton:hover {{ color: {C.TEXT}; border-color: {C.BORDER_B}; }}
        """)
        cancel_btn.clicked.connect(self._cancel)
        btn_row.addWidget(cancel_btn)
        lay.addLayout(btn_row)

    # ── interface language ───────────────────────────────────────────────────
    def _pick_language(self, code: str) -> None:
        """Choose a language and show it at once, without writing the config.

        The panel is rebuilt from the new catalogue in place (cheaper and less
        surprising than closing it), and the choice is only persisted on APPLY.
        Cancelling therefore leaves both the setting and the window as they were
        — the alternative, switching live and cancelling later, is a window that
        no longer matches its own config file.
        """
        self._sel_lang = code
        set_locale(code if code != "auto" else None)
        self._retranslate()

    def _refresh_lang_btns(self) -> None:
        palette_on = (f"QPushButton {{ background: {C.PRI_GHO}; color: {C.PRI};"
                      f" border: 1px solid {C.PRI}; border-radius: 3px; }}")
        palette_off = (f"QPushButton {{ background: transparent; color: {C.TEXT_MED};"
                       f" border: 1px solid {C.BORDER}; border-radius: 3px; }}")
        for code, btn in self._lang_btns.items():
            btn.setChecked(code == self._sel_lang)
            btn.setStyleSheet(palette_on if code == self._sel_lang else palette_off)

    def _retranslate(self) -> None:
        """Re-read every label in this overlay from the active catalogue.

        Only the texts are touched; the widgets keep their positions, so nothing
        jumps and nothing loses focus. Handles are kept for exactly this reason:
        a label that was built with `_lbl(...)` and never stored cannot be
        retranslated, and would be the one row left in the old language.
        """
        self._head_lbl.setText(_t("setup.customise"))
        self._name_cap.setText(_t("setup.name"))
        self._user_cap.setText(_t("setup.user_name"))
        self._voice_cap.setText(_t("setup.voice"))
        self._colour_cap.setText(_t("setup.colour"))
        self._lang_cap.setText(_t("setup.language"))
        self._user_input.setPlaceholderText(_t("ui.placeholder.user_name"))
        self._hex_input.setPlaceholderText(_t("ui.placeholder.hex"))
        self._default_btn.setText(_t("ui.default_btn"))
        self._save_btn.setText(_t("ui.apply_changes"))
        self._cancel_btn.setText(_t("ui.cancel"))
        for code, btn in self._lang_btns.items():
            btn.setText(_t("setup.language.auto", locale=self._auto_lang.upper())
                        if code == "auto" else code.upper())
        self._refresh_lang_btns()

    # ── voice selection ──────────────────────────────────────────────────────
    def _on_voice_pick(self, name: str):
        self._sel_voice = name
        self._refresh_voice_btns()

    def _refresh_voice_btns(self):
        """Highlight the selected voice pill; dim the rest."""
        for name, b in self._voice_btns.items():
            on = (name == self._sel_voice)
            b.setChecked(on)
            if on:
                b.setStyleSheet(f"""
                    QPushButton {{ background: {C.PRI_GHO}; color: {C.PRI};
                        border: 1px solid {C.PRI}; border-radius: 3px; }}
                """)
            else:
                b.setStyleSheet(f"""
                    QPushButton {{ background: transparent; color: {C.TEXT_MED};
                        border: 1px solid {C.BORDER}; border-radius: 3px; }}
                    QPushButton:hover {{ color: {C.TEXT}; border-color: {C.BORDER_B}; }}
                """)

    # ── colour flow ──────────────────────────────────────────────────────────
    def _set_color(self, hx: str, update_wheel: bool = True, preview: bool = True):
        """Updates the selected colour; hex box + wheel stay in sync, theme is live-previewed."""
        self._sel_color = hx.strip().lower()
        self._hex_input.blockSignals(True)
        self._hex_input.setText(self._sel_color)
        self._hex_input.blockSignals(False)
        if update_wheel:
            self._wheel.set_color(self._sel_color)
        if preview and self.on_preview:
            self.on_preview(self._sel_color)

    def _on_wheel_pick(self, hx: str):
        # While dragging: update the hex box, don't apply the theme yet
        self._sel_color = hx
        self._hex_input.blockSignals(True)
        self._hex_input.setText(hx)
        self._hex_input.blockSignals(False)

    def _on_wheel_commit(self, hx: str):
        # Handle released → live-preview the whole interface
        self._set_color(hx, update_wheel=False)

    def _on_hex_edited(self, text: str):
        t = text.strip().lower()
        if t.startswith("#") and len(t) == 7:
            try:
                int(t[1:], 16)
            except ValueError:
                return
            self._set_color(t, update_wheel=True, preview=True)

    def _cancel(self):
        # If a preview was applied, revert to the colour from launch
        if self.on_preview and self._sel_color != self._initial_color:
            self.on_preview(self._initial_color)
        # The language preview is reverted the same way, and for the same
        # reason: this panel may preview, but only APPLY may decide.
        set_locale(self._initial_lang if self._initial_lang != "auto" else None)
        self.hide()

    def _save(self):
        name = self._name_input.text().strip() or "JARVIS"
        user = self._user_input.text().strip()
        self.saved.emit(name, user, self._sel_color or DEFAULT_UI_COLOR,
                        self._sel_voice, self._sel_lang)
        self.hide()




class PluginManagerOverlay(QWidget):
    """Floating overlay — lists discovered plugins with per-plugin ON/OFF toggles."""

    _OW = 420

    def __init__(self, plugins: list[dict], parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            PluginManagerOverlay {{
                background: rgba(0, 6, 10, 245);
                border: 1px solid {C.BORDER_B};
                border-radius: 6px;
            }}
        """)
        self.setFixedWidth(self._OW)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(6)

        hdr = QLabel(_t("ui.plugins.heading"))
        hdr.setFont(QFont("Courier New", 12, QFont.Weight.Bold))
        hdr.setStyleSheet(f"color: {C.PRI}; background: transparent;")
        lay.addWidget(hdr)
        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {C.BORDER}; margin: 2px 0;")
        lay.addWidget(sep)

        if not plugins:
            empty = QLabel(_t("ui.plugins.none"))
            empty.setFont(QFont("Courier New", 8))
            empty.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")
            lay.addWidget(empty)

        for p in plugins:
            lay.addLayout(self._build_row(p))

        lay.addSpacing(4)
        close_btn = QPushButton(_t("ui.close"))
        close_btn.setFixedHeight(30)
        close_btn.setFont(QFont("Courier New", 9))
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(f"""
            QPushButton {{
                background: transparent; color: {C.TEXT_MED};
                border: 1px solid {C.BORDER}; border-radius: 3px;
            }}
            QPushButton:hover {{ color: {C.TEXT}; border-color: {C.BORDER_B}; }}
        """)
        close_btn.clicked.connect(self.hide)
        lay.addWidget(close_btn)
        self.adjustSize()

    def _build_row(self, p: dict) -> QHBoxLayout:
        row = QHBoxLayout(); row.setSpacing(6)

        label_text = p["name"] if p["valid"] else f"{p['name']}  (⚠ {p['file']})"
        lbl = QLabel(label_text)
        lbl.setFont(QFont("Courier New", 8))
        lbl.setStyleSheet(f"color: {C.TEXT if p['valid'] else C.TEXT_DIM}; background: transparent;")
        # The tooltip is where a third-party plugin's declaration is read
        # BEFORE the toggle is pressed. `permissions` is empty for every plugin
        # in this repository, so their tooltips are unchanged.
        perms = p.get("permissions") or []
        tip = p["description"] if p["valid"] else p["error"]
        if p["valid"] and perms:
            tip = (tip + "\n\n"
                   + _t("ui.plugins.permissions", list=", ".join(perms)))
        elif p["valid"] and p.get("manifest_note"):
            tip = tip + "\n\n" + p["manifest_note"]
        lbl.setToolTip(tip)
        lbl.setWordWrap(False)
        row.addWidget(lbl, stretch=1)

        btn = QPushButton()
        btn.setFixedSize(72, 24)
        btn.setFont(QFont("Courier New", 7, QFont.Weight.Bold))
        if not p["valid"]:
            btn.setText(_t("ui.broken"))
            btn.setEnabled(False)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent; color: {C.TEXT_DIM};
                    border: 1px solid {C.BORDER}; border-radius: 3px;
                }}
            """)
        elif perms and not p["enabled"]:
            # CONSENT, ONCE, BEFORE THE PLUGIN RUNS. The button says what it is
            # asking for rather than "OFF", and pressing it opens a question.
            # Only for a plugin that DECLARED a permission: this repository's
            # own plugins mostly have no manifest and keep their plain toggle,
            # so the dialog cannot train people to click through it.
            btn.setText(_t("ui.plugins.ask"))
            btn.setToolTip(_t("ui.plugins.consent", list=", ".join(perms)))
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self._style_toggle(btn, False)
            btn.clicked.connect(lambda _, name=p["name"], b=btn,
                                list_=tuple(perms): self._ask_and_toggle(name, b, list_))
        else:
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            self._style_toggle(btn, p["enabled"])
            btn.clicked.connect(lambda _, name=p["name"], b=btn: self._toggle(name, b))
        row.addWidget(btn)
        return row

    def _style_toggle(self, btn: QPushButton, enabled: bool):
        if enabled:
            btn.setText(_t("ui.on"))
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: #001a08; color: {C.GREEN};
                    border: 1px solid {C.GREEN_D}; border-radius: 3px;
                }}
                QPushButton:hover {{ background: #002010; }}
            """)
        else:
            btn.setText(_t("ui.off"))
            btn.setStyleSheet(f"""
                QPushButton {{
                    background: transparent; color: {C.TEXT_DIM};
                    border: 1px solid {C.BORDER}; border-radius: 3px;
                }}
                QPushButton:hover {{ color: {C.TEXT}; border-color: {C.BORDER_B}; }}
            """)

    def _ask_and_toggle(self, name: str, btn: QPushButton, perms: tuple) -> None:
        """Say what the plugin needs, and only run it if the user agrees.

        Deliberately a Qt question box and not a custom panel: it is the one
        dialog every desktop user already knows how to read, it blocks until
        answered, and it cannot be dismissed by accident in a way that leaves
        the plugin switched on. The default button is NO.
        """
        from PyQt6.QtWidgets import QMessageBox
        box = QMessageBox(self)
        box.setWindowTitle(name)
        box.setText(_t("ui.plugins.consent", list=", ".join(perms)))
        box.setIcon(QMessageBox.Icon.Warning)
        box.setStandardButtons(QMessageBox.StandardButton.Yes
                               | QMessageBox.StandardButton.No)
        box.setDefaultButton(QMessageBox.StandardButton.No)
        if box.exec() == QMessageBox.StandardButton.Yes:
            self._toggle(name, btn)
        else:
            # The button never said ON, so there is nothing to put back.
            btn.setText(_t("ui.plugins.ask"))

    def _toggle(self, name: str, btn: QPushButton):
        from memory.config_manager import get_plugin_enabled, save_plugin_enabled
        new_val = not get_plugin_enabled(name)
        save_plugin_enabled(name, new_val)
        self._style_toggle(btn, new_val)


class PluginSettingsOverlay(QWidget):
    """Floating overlay — one row per installed plugin, a form where there is one.

    Fully generic: it draws what PluginRegistry.settings_schemas() hands it and
    knows NOTHING about any specific plugin, so the core stays clean and plugins
    remain pure drop-in.

    EVERY plugin is listed, in three shapes:
      * has a schema and is enabled   → the fields, editable, with SAVE;
      * has a schema but is disabled  → the fields, greyed out, plus why;
      * no schema at all              → a line saying it needs no settings.

    That third shape is not padding. Four of the five plugins this repository
    ships declare no PLUGIN_SETTINGS, and this panel used to render ONLY plugins
    that declared one — so it listed nothing and called the feature broken, two
    buttons away from a manager listing all five. A plugin that takes no
    settings still has to prove it exists.
    """

    _test_done = pyqtSignal(str, bool, str)   # namespace, ok, message
    _OW = 460

    # Set by the window: opens the plugin manager. A callable rather than an
    # import of the overlay, so this panel keeps knowing nothing about it.
    on_open_manager = None

    def __init__(self, sections: list[dict], parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setStyleSheet(f"""
            PluginSettingsOverlay {{
                background: rgba(0, 6, 10, 245);
                border: 1px solid {C.BORDER_B};
                border-radius: 6px;
            }}
        """)
        self._sections = sections or []
        self._widgets: dict[tuple, object] = {}    # (namespace, key) -> input widget
        self._types:   dict[tuple, str]    = {}     # (namespace, key) -> field type
        self._status_labels: dict[str, QLabel] = {} # namespace -> status QLabel
        self._test_done.connect(self._on_test_done)

        self._fs = (f"QLineEdit {{ background: #000d12; color: {C.TEXT}; "
                    f"border: 1px solid {C.BORDER}; border-radius: 3px; padding: 4px 8px; }}"
                    f"QLineEdit:focus {{ border: 1px solid {C.PRI}; }}")

        root = QVBoxLayout(self)
        root.setContentsMargins(22, 16, 22, 16)
        root.setSpacing(8)

        root.addWidget(self._lbl(_t("plugins.heading"), 12, True))
        sep = QFrame(); sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {C.BORDER}; margin: 2px 0;")
        root.addWidget(sep)

        if not self._sections:
            root.addWidget(self._lbl(_t("plugins.empty"), 9, color=C.TEXT_DIM))
            # A panel that says "nothing here" and offers no way forward is a
            # dead end. The plugins the user expects to configure are listed in
            # the manager, which is one button away from this message.
            if self.on_open_manager:
                man_btn = QPushButton(_t("ui.plugins.heading"))
                man_btn.setFixedHeight(32)
                man_btn.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
                man_btn.setCursor(Qt.CursorShape.PointingHandCursor)
                man_btn.setStyleSheet(f"""
                    QPushButton {{ background: transparent; color: {C.PRI};
                        border: 1px solid {C.PRI_DIM}; border-radius: 3px; }}
                    QPushButton:hover {{ background: {C.PRI_GHO}; border-color: {C.PRI}; }}
                """)
                man_btn.clicked.connect(self.on_open_manager)
                root.addWidget(man_btn)
        else:
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QFrame.Shape.NoFrame)
            scroll.setStyleSheet("QScrollArea { background: transparent; }")
            inner = QWidget()
            inner.setStyleSheet("background: transparent;")
            form = QVBoxLayout(inner)
            form.setContentsMargins(0, 0, 6, 0)
            form.setSpacing(6)
            for sec in self._sections:
                self._build_section(form, sec)
            form.addStretch(1)
            scroll.setWidget(inner)
            root.addWidget(scroll, 1)

        # ── bottom buttons ───────────────────────────────────────────────────
        btn_row = QHBoxLayout(); btn_row.setSpacing(8)
        if self._sections:
            save_btn = QPushButton(_t("ui.save"))
            save_btn.setFixedHeight(34)
            save_btn.setFont(QFont("Courier New", 9, QFont.Weight.Bold))
            save_btn.setCursor(Qt.CursorShape.PointingHandCursor)
            save_btn.setStyleSheet(f"""
                QPushButton {{ background: transparent; color: {C.PRI};
                    border: 1px solid {C.PRI_DIM}; border-radius: 3px; }}
                QPushButton:hover {{ background: {C.PRI_GHO}; border: 1px solid {C.PRI}; }}
            """)
            save_btn.clicked.connect(self._save_all)
            btn_row.addWidget(save_btn)

        close_btn = QPushButton(_t("ui.close"))
        close_btn.setFixedHeight(34)
        close_btn.setFont(QFont("Courier New", 9))
        close_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        close_btn.setStyleSheet(f"""
            QPushButton {{ background: transparent; color: {C.TEXT_MED};
                border: 1px solid {C.BORDER}; border-radius: 3px; }}
            QPushButton:hover {{ color: {C.TEXT}; border-color: {C.BORDER_B}; }}
        """)
        close_btn.clicked.connect(self.hide)
        btn_row.addWidget(close_btn)
        root.addLayout(btn_row)

    # ── helpers ───────────────────────────────────────────────────────────────
    def _lbl(self, txt, fs=9, bold=False, color=C.PRI,
             align=Qt.AlignmentFlag.AlignLeft):
        w = QLabel(txt); w.setAlignment(align); w.setWordWrap(True)
        w.setFont(QFont("Courier New", fs,
                        QFont.Weight.Bold if bold else QFont.Weight.Normal))
        w.setStyleSheet(f"color: {color}; background: transparent;")
        return w

    def _build_section(self, form: QVBoxLayout, sec: dict):
        ns     = sec.get("namespace") or sec.get("plugin") or "plugin"
        title  = sec.get("title") or ns
        fields = sec.get("fields") or []
        values = sec.get("values") or {}

        form.addSpacing(4)
        form.addWidget(self._lbl(title, 10, True, C.PRI))

        # Why this form cannot be used yet. A plugin that declared a permission
        # arrives switched OFF until the user consents (see _enabled), and its
        # settings are still worth showing: the form is how the user finds out
        # what the plugin wants configured before saying yes.
        locked = not sec.get("enabled", True)
        if locked:
            form.addWidget(self._lbl(_t("plugins.locked", plugin=sec.get("plugin") or ns),
                                     8, color=C.ACC2))

        # No schema, no fields — but still a row, because "this plugin takes no
        # settings" is the answer the user came for, and a plugin missing from
        # the list looks exactly like a plugin that failed to load.
        if not fields:
            form.addWidget(self._lbl(
                _t("plugins.no_fields") if not locked else _t("plugins.no_fields_locked"),
                8, color=C.TEXT_DIM))

        for field in fields:
            if not isinstance(field, dict) or not field.get("key"):
                continue
            key   = field["key"]
            ftype = (field.get("type") or "text").lower()
            label = field.get("label") or key
            default = field.get("default")
            stored  = values.get(key, default)

            form.addWidget(self._lbl(label.upper(), 8, color=C.TEXT_DIM))

            if ftype == "choice":
                w = QComboBox()
                w.addItems([str(o) for o in field.get("options", [])])
                w.setFont(QFont("Courier New", 9))
                w.setFixedHeight(30)
                w.setStyleSheet(
                    f"QComboBox {{ background: #000d12; color: {C.TEXT}; "
                    f"border: 1px solid {C.BORDER}; border-radius: 3px; padding: 2px 8px; }}"
                    f"QComboBox QAbstractItemView {{ background: #000d12; color: {C.TEXT}; "
                    f"selection-background-color: {C.PRI_GHO}; }}")
                if stored is not None:
                    w.setCurrentText(str(stored))
            elif ftype == "toggle":
                w = QPushButton()
                w.setCheckable(True)
                w.setChecked(bool(stored))
                w.setFixedHeight(28)
                w.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
                w.setCursor(Qt.CursorShape.PointingHandCursor)
                self._style_toggle(w)
                w.toggled.connect(lambda _=False, b=w: self._style_toggle(b))
            else:  # text / password
                w = QLineEdit("" if stored is None else str(stored))
                w.setFont(QFont("Courier New", 10))
                w.setFixedHeight(30)
                w.setStyleSheet(self._fs)
                if field.get("placeholder"):
                    w.setPlaceholderText(str(field["placeholder"]))
                if ftype == "password":
                    w.setEchoMode(QLineEdit.EchoMode.Password)

            if locked:
                # Readable, just not editable: greying out beats hiding, because
                # the values the user typed before the plugin was switched off
                # are still theirs to look at.
                w.setEnabled(False)
            self._widgets[(ns, key)] = w
            self._types[(ns, key)]   = ftype
            form.addWidget(w)

        # optional test/connect action button + status line
        action = sec.get("action")
        if isinstance(action, dict) and callable(action.get("run")):
            form.addSpacing(2)
            ab = QPushButton(str(action.get("label") or "TEST"))
            ab.setFixedHeight(30)
            ab.setFont(QFont("Courier New", 8, QFont.Weight.Bold))
            ab.setCursor(Qt.CursorShape.PointingHandCursor)
            ab.setStyleSheet(f"""
                QPushButton {{ background: #00091a; color: {C.PRI};
                    border: 1px solid {C.PRI_DIM}; border-radius: 3px; }}
                QPushButton:hover {{ background: {C.PRI_GHO}; border-color: {C.PRI}; }}
            """)
            ab.clicked.connect(lambda _=False, n=ns: self._run_action(n))
            form.addWidget(ab)

        status = self._lbl("", 8, color=C.TEXT_DIM)
        self._status_labels[ns] = status
        form.addWidget(status)

        line = QFrame(); line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet(f"color: {C.BORDER}; margin: 4px 0;")
        form.addWidget(line)

    def _style_toggle(self, btn: QPushButton):
        on = btn.isChecked()
        btn.setText(_t("ui.on") if on else _t("ui.off"))
        if on:
            btn.setStyleSheet(f"QPushButton {{ background: {C.PRI_GHO}; color: {C.PRI}; "
                              f"border: 1px solid {C.PRI}; border-radius: 3px; }}")
        else:
            btn.setStyleSheet(f"QPushButton {{ background: transparent; color: {C.TEXT_MED}; "
                              f"border: 1px solid {C.BORDER}; border-radius: 3px; }}")

    # ── data ──────────────────────────────────────────────────────────────────
    def _gather(self, ns: str) -> dict:
        out = {}
        for (n, key), w in self._widgets.items():
            if n != ns:
                continue
            t = self._types.get((n, key), "text")
            if t == "choice":
                out[key] = w.currentText()
            elif t == "toggle":
                out[key] = w.isChecked()
            else:
                out[key] = w.text().strip()
        return out

    def _save_ns(self, ns: str):
        from memory.config_manager import save_plugin_config
        save_plugin_config(ns, self._gather(ns))

    def _save_all(self):
        for sec in self._sections:
            ns = sec.get("namespace") or sec.get("plugin")
            # Nothing to save in a section with no fields, and a locked one
            # cannot be written: a "SAVED" that wrote nothing is a lie the user
            # has no way to check.
            if ns and sec.get("enabled", True) and sec.get("fields"):
                self._save_ns(ns)
                lbl = self._status_labels.get(ns)
                if lbl:
                    lbl.setText(_t("ui.saved"))
                    lbl.setStyleSheet(f"color: {C.PRI}; background: transparent;")

    def _run_action(self, ns: str):
        sec = next((s for s in self._sections
                    if (s.get("namespace") or s.get("plugin")) == ns), None)
        if not sec:
            return
        run_fn = (sec.get("action") or {}).get("run")
        if not callable(run_fn):
            return
        if not sec.get("enabled", True):
            return                        # locked section: nothing to test
        self._save_ns(ns)                 # persist what the user typed before testing
        values = self._gather(ns)
        lbl = self._status_labels.get(ns)
        if lbl:
            lbl.setText(_t("ui.testing"))
            lbl.setStyleSheet(f"color: {C.TEXT_DIM}; background: transparent;")

        def worker():
            try:
                res = run_fn(values)
                if isinstance(res, tuple) and len(res) == 2:
                    ok, msg = bool(res[0]), str(res[1])
                else:
                    ok, msg = bool(res), str(res)
            except Exception as e:
                ok, msg = False, str(e)
            self._test_done.emit(ns, ok, msg)

        threading.Thread(target=worker, daemon=True).start()

    def _on_test_done(self, ns: str, ok: bool, msg: str):
        lbl = self._status_labels.get(ns)
        if not lbl:
            return
        lbl.setText(msg)
        color = C.PRI if ok else "#ff6b6b"
        lbl.setStyleSheet(f"color: {color}; background: transparent;")
