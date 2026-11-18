"""Opt-in local order review. All Qt objects remain on the main thread."""
from __future__ import annotations

import threading

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtWidgets import (QComboBox, QDialog, QGridLayout, QInputDialog, QLabel, QLineEdit,
                             QMessageBox, QPushButton, QVBoxLayout)

from core import trade_gate
from core.i18n import label as _t
from plugins import _mt5_trade as trade
from ui.theme import C, workspace_stylesheet
from ui.localization import TranslationBindings


class OrderDialog(QDialog):
    _prepared = pyqtSignal(object, str)
    _finished = pyqtSignal(str)

    def __init__(self, host, draft):
        super().__init__(host)
        self._host = host
        self._busy = False
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self._translations = TranslationBindings()
        self._translations.title(self, "trade.title")
        self.resize(640, 560)
        self.setStyleSheet(workspace_stylesheet())
        layout = QVBoxLayout(self)
        warning = self._translations.text(QLabel(), "trade.warning")
        warning.setWordWrap(True)
        layout.addWidget(warning)
        self.gate_status = QLabel()
        self.gate_status.setWordWrap(True)
        layout.addWidget(self.gate_status)
        self.stop_button = self._translations.text(QPushButton(), "trade.stop")
        self.stop_button.clicked.connect(self._emergency_stop)
        layout.addWidget(self.stop_button)
        self.resume_button = self._translations.text(QPushButton(), "trade.resume")
        self.resume_button.clicked.connect(self._resume_trading)
        layout.addWidget(self.resume_button)
        grid = QGridLayout()
        self.mode = QComboBox()
        for label, value in (("trade.off", "OFF"), ("trade.demo", "DEMO"), ("trade.live", "LIVE")):
            self.mode.addItem(_t(label), value)
            self._translations.choice(self.mode, self.mode.count() - 1, label)
        mode_label = self._translations.text(QLabel(), "trade.mode")
        mode_label.setBuddy(self.mode)
        grid.addWidget(mode_label, 0, 0)
        grid.addWidget(self.mode, 0, 1)
        self.kind = QComboBox()
        self.kind.addItem(_t("trade.market"), "market")
        self.kind.addItem(_t("trade.modify"), "modify_pending")
        self._translations.choice(self.kind, 0, "trade.market")
        self._translations.choice(self.kind, 1, "trade.modify")
        self.kind.setCurrentIndex(1 if draft.get("kind") == "modify_pending" else 0)
        kind_label = self._translations.text(QLabel(), "trade.kind")
        kind_label.setBuddy(self.kind)
        grid.addWidget(kind_label, 1, 0)
        grid.addWidget(self.kind, 1, 1)
        self.side = QComboBox()
        self.side.addItem(_t("trade.choose_side"), "")
        self.side.addItem(_t("trade.buy"), "buy")
        self.side.addItem(_t("trade.sell"), "sell")
        for index, key in enumerate(("trade.choose_side", "trade.buy", "trade.sell")):
            self._translations.choice(self.side, index, key)
        self.side.setCurrentIndex({"buy": 1, "sell": 2}.get(draft.get("side"), 0))
        side_label = self._translations.text(QLabel(), "trade.side")
        side_label.setBuddy(self.side)
        grid.addWidget(side_label, 2, 0)
        grid.addWidget(self.side, 2, 1)
        self.fields = {}
        for row, (key, label, fallback) in enumerate((
            ("symbol", "trade.symbol", ""), ("volume", "trade.volume", ""),
            ("ticket", "trade.ticket", ""), ("price", "trade.price", ""),
            ("sl", "trade.sl", ""), ("tp", "trade.tp", "0"),
            ("max_volume", "trade.max_volume", "0.01"), ("max_loss", "trade.max_loss", ""),
        ), start=3):
            field_label = self._translations.text(QLabel(), label)
            grid.addWidget(field_label, row, 0)
            # Maximum is always initialized locally, never taken from an AI draft.
            value = fallback if key in ("max_volume", "max_loss") else str(draft.get(key, fallback) or fallback)
            field = QLineEdit(value[:80])
            field_label.setBuddy(field)
            field.setAccessibleName(_t(label))
            self.fields[key] = field
            grid.addWidget(field, row, 1)
        layout.addLayout(grid)
        self.status = self._translations.text(QLabel(), "trade.not_sent", conditional=True)
        self.status.setWordWrap(True)
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        layout.addWidget(self.status)
        self.review = self._translations.text(QPushButton(), "trade.review")
        self.review.clicked.connect(self._prepare)
        layout.addWidget(self.review)
        self._prepared.connect(self._on_prepared)
        self._finished.connect(self._on_finished)
        self._gate_timer = QTimer(self)
        self._gate_timer.timeout.connect(self._refresh_gate)
        self._gate_timer.start(250)
        self._refresh_gate()

    def retranslate(self):
        self._translations.refresh()
        for key, label in (("symbol", "trade.symbol"), ("volume", "trade.volume"),
                           ("ticket", "trade.ticket"), ("price", "trade.price"),
                           ("sl", "trade.sl"), ("tp", "trade.tp"),
                           ("max_volume", "trade.max_volume"), ("max_loss", "trade.max_loss")):
            self.fields[key].setAccessibleName(_t(label))
        self._refresh_gate()

    def _refresh_gate(self):
        stopped = trade_gate.stopped()
        self.gate_status.setText(_t("trade.stopped" if stopped else "trade.stop_ready"))
        self.stop_button.setEnabled(not stopped)
        self.resume_button.setEnabled(stopped)
        self.review.setEnabled(not self._busy and not stopped)
        if stopped and self.mode.currentData() != "OFF":
            self.mode.setCurrentIndex(0)

    def _emergency_stop(self):
        trade_gate.stop()
        self._refresh_gate()

    def _resume_trading(self):
        if not trade_gate.stopped():
            return
        answer = QMessageBox.question(
            self, _t("trade.resume_title"), _t("trade.resume_detail"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if answer == QMessageBox.StandardButton.Yes:
            trade_gate.resume()
            self._refresh_gate()

    def _allowed(self):
        try:
            return any(r.get("name") == "mt5_trade" and r.get("valid") and r.get("enabled")
                       for r in self._host.get_plugins())
        except Exception:
            return False

    def _set_busy(self, value):
        self._busy = value
        self.review.setEnabled(not value and not trade_gate.stopped())
        self.mode.setEnabled(not value)
        self.kind.setEnabled(not value)
        self.side.setEnabled(not value)
        for widget in self.fields.values():
            widget.setEnabled(not value)

    def _prepare(self):
        if self._busy or not self._allowed() or trade_gate.stopped():
            self.status.setText(_t("trade.stopped" if trade_gate.stopped() else "trade.disabled"))
            return
        mode = self.mode.currentData()
        draft = {k: w.text().strip() for k, w in self.fields.items() if k not in ("max_volume", "max_loss")}
        draft.update(kind=self.kind.currentData(), side=self.side.currentData())
        maximum = self.fields["max_volume"].text().strip()
        max_loss = self.fields["max_loss"].text().strip()
        self._set_busy(True)
        self.status.setText(_t("trade.checking"))
        def worker():
            try:
                prepared, error = trade.prepare(draft, mode, maximum, max_loss), ""
            except Exception as exc:
                prepared, error = None, str(exc)
            try:
                self._prepared.emit(prepared, error)
            except RuntimeError:
                pass
        threading.Thread(target=worker, name="mt5-order-review", daemon=True).start()

    def _on_prepared(self, prepared, error):
        if error or not self._allowed() or not prepared or not trade_gate.valid(prepared.generation):
            self._set_busy(False)
            reason = error[:400] if error else _t("trade.stopped" if trade_gate.stopped() else "trade.cancelled")
            self.status.setText(_t("trade.error", error=reason))
            return
        # Disarm hand input before showing a local approval dialog. The order
        # cannot be approved by a tool argument or a remote dashboard request.
        controller = getattr(self._host, "_hand_controller", None)
        if controller is not None:
            controller.stop()
        if getattr(self._host, "_confirm_overlay", None) is not None:
            self._set_busy(False)
            self.status.setText(_t("trade.conflict"))
            return
        from core import trade_guard
        if not trade_guard.begin():
            self._set_busy(False)
            self.status.setText(_t("trade.conflict"))
            return
        self._host._hand_closing_confirm = True
        try:
            msg = QMessageBox(self)
            msg.setWindowTitle(_t("trade.confirm_title"))
            msg.setStyleSheet(f"QMessageBox {{ background: {C.PANEL}; color: {C.WHITE}; }} "
                              f"QLabel {{ color: {C.WHITE}; min-width: 500px; }} "
                              f"QPushButton {{ background: {C.PANEL2}; color: {C.WHITE}; "
                              f"border: 1px solid {C.BORDER_B}; border-radius: 6px; padding: 8px 20px; }} "
                              f"QPushButton:focus {{ border: 2px solid {C.PRI}; }}")
            msg.setTextFormat(Qt.TextFormat.PlainText)
            msg.setText(_t("trade.confirm_detail", summary=prepared.summary))
            msg.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
            msg.setDefaultButton(QMessageBox.StandardButton.No)
            msg.setWindowModality(Qt.WindowModality.ApplicationModal)
            accepted = msg.exec() == QMessageBox.StandardButton.Yes
            if accepted and prepared.mode == "LIVE":
                text, ok = QInputDialog.getText(self, _t("trade.live_confirm_title"),
                                                _t("trade.live_confirm_detail"))
                accepted = ok and text.strip() == "LIVE"
        finally:
            self._host._hand_closing_confirm = False
            trade_guard.end()
        if (not accepted or not self._allowed() or
                getattr(self._host, "_confirm_overlay", None) is not None):
            self._set_busy(False)
            self.status.setText(_t("trade.cancelled"))
            return
        self.status.setText(_t("trade.sending"))
        def worker():
            try:
                # Recheck revocation on the worker immediately before the call.
                from memory.config_manager import get_plugin_enabled
                if not get_plugin_enabled("mt5_trade", default=False):
                    result = _t("trade.disabled")
                else:
                    result = trade.execute(prepared)
            except Exception as exc:
                result = _t("trade.error", error=str(exc)[:400])
            # Logging is marshalled by MainWindow even if this dialog was closed.
            try:
                self._host.write_log(_t("trade.result_log", result=result[:350]))
                self._finished.emit(result)
            except RuntimeError:
                from core import logbook
                logbook.get("mt5_trade").warning("MT5 order result: %s", result[:350])
        threading.Thread(target=worker, name="mt5-order-submit", daemon=True).start()

    def _on_finished(self, result):
        self._set_busy(False)
        self.status.setText(result)


def open_trade(window, request):
    try:
        allowed = any(r.get("name") == "mt5_trade" and r.get("valid") and r.get("enabled")
                      for r in window.get_plugins())
    except Exception:
        allowed = False
    if not allowed:
        window.write_log(_t("trade.disabled"))
        return
    dialog = OrderDialog(window, request.get("draft") or {})
    if not hasattr(window, "_order_dialogs"):
        window._order_dialogs = set()
    window._order_dialogs.add(dialog)
    dialog.destroyed.connect(lambda: window._order_dialogs.discard(dialog))
    dialog.show()
    dialog.raise_()
