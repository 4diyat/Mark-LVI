"""Read-only MetaTrader 5 chart and ORB information, owned by the Qt thread."""
from __future__ import annotations

import threading
from datetime import datetime, timezone

from PyQt6.QtCore import Qt, QTimer, pyqtSignal
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import (QCheckBox, QComboBox, QDialog, QGridLayout, QHBoxLayout,
                             QLabel, QLineEdit, QPushButton, QSpinBox, QVBoxLayout, QWidget)

from core.i18n import label as _t
from memory.config_manager import get_plugin_config, save_plugin_config
from plugins import _trading_terminal as terminal
from ui.theme import C


class CandleChart(QWidget):
    """Draw closed M1 candles and the selected session's calculated range."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumHeight(260)
        self._snapshot = None
        self._session = "asia"

    def set_data(self, snapshot, session):
        self._snapshot, self._session = snapshot, session
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#07141c"))
        snapshot = self._snapshot
        if not snapshot:
            painter.setPen(QColor(C.TEXT_DIM))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, _t("trading.no_chart"))
            return
        bars = snapshot["bars"]
        if not bars:
            return
        prices = [float(v) for b in bars for v in (b.high, b.low)]
        result = snapshot["sessions"].get(self._session, {})
        prices.extend(v for v in (result.get("high"), result.get("low")) if v is not None)
        lo, hi = min(prices), max(prices)
        margin = max((hi - lo) * 0.06, max(abs(hi), 1.0) * 1e-7)
        lo, hi = lo - margin, hi + margin
        left, right, top, bottom = 10, max(11, self.width() - 85), 15, max(16, self.height() - 32)
        plot_height = bottom - top
        def y(price):
            return top + (hi - price) / (hi - lo) * plot_height
        painter.setPen(QPen(QColor("#253742"), 1))
        for i in range(5):
            yy = top + i * plot_height / 4
            painter.drawLine(int(left), int(yy), int(right), int(yy))
            painter.drawText(right + 4, int(yy + 4), f"{hi - i * (hi - lo) / 4:.5f}")
        step = (right - left) / len(bars)
        for i, bar in enumerate(bars):
            x = left + (i + 0.5) * step
            color = QColor("#4ed397" if bar.close >= bar.open else "#ff6b6b")
            painter.setPen(QPen(color, 1))
            painter.drawLine(int(x), int(y(bar.high)), int(x), int(y(bar.low)))
            painter.setBrush(color)
            y1, y2 = y(max(bar.open, bar.close)), y(min(bar.open, bar.close))
            painter.drawRect(int(x - max(1, step * .3)), int(y1), max(1, int(step * .6)), max(1, int(y2 - y1)))
        for key, color in (("high", "#ffd166"), ("low", "#a78bfa")):
            price = result.get(key)
            if price is not None:
                painter.setPen(QPen(QColor(color), 1, Qt.PenStyle.DashLine))
                painter.drawLine(left, int(y(price)), right, int(y(price)))
                painter.drawText(left + 4, int(y(price) - 3), f"{key.upper()} {price:.5f}")
        first = datetime.fromtimestamp(int(bars[0].time), timezone.utc)
        last = datetime.fromtimestamp(int(bars[-1].time), timezone.utc)
        painter.setPen(QColor(C.TEXT_DIM))
        painter.drawText(left, self.height() - 8, f"{first:%Y-%m-%d %H:%M} → {last:%m-%d %H:%M} UTC | M1")


class TradingTerminal(QDialog):
    _data_ready = pyqtSignal(object, str)

    def __init__(self, parent, request):
        super().__init__(parent)
        self._host = parent
        self._busy = False
        self._snapshot = None
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.setWindowTitle(_t("trading.title"))
        self.resize(1000, 750)
        self.setStyleSheet(f"QDialog, QWidget {{ background:#001018; color:{C.TEXT}; }} "
                           f"QLineEdit, QSpinBox, QComboBox, QPushButton {{ background:#001c25; "
                           f"color:{C.TEXT}; border:1px solid {C.BORDER}; padding:4px; }}")
        self._data_ready.connect(self._on_data)
        settings = dict(terminal.DEFAULTS)
        settings.update(get_plugin_config("trading_terminal"))
        if request.get("symbol"):
            settings["symbol"] = str(request["symbol"])[:80]
        layout = QVBoxLayout(self)
        warning = QLabel(_t("trading.disclaimer"))
        warning.setWordWrap(True)
        layout.addWidget(warning)
        form = QGridLayout()
        self._symbol = QLineEdit(str(settings.get("symbol") or ""))
        form.addWidget(QLabel(_t("trading.symbol")), 0, 0)
        form.addWidget(self._symbol, 0, 1)
        self._inputs = {}
        for i, key in enumerate(("asia", "london", "new_york")):
            form.addWidget(QLabel(_t(f"trading.{key}_start")), i + 1, 0)
            inp = QLineEdit(str(settings.get(f"{key}_start") or ""))
            self._inputs[key] = inp
            form.addWidget(inp, i + 1, 1)
        self._duration = QSpinBox()
        self._duration.setRange(1, 120)
        try:
            self._duration.setValue(int(settings.get("range_minutes", 15)))
        except (TypeError, ValueError):
            self._duration.setValue(15)
        form.addWidget(QLabel(_t("trading.range_minutes")), 0, 2)
        form.addWidget(self._duration, 0, 3)
        layout.addLayout(form)
        row = QHBoxLayout()
        self._refresh = QPushButton(_t("trading.refresh"))
        self._refresh.clicked.connect(self._request)
        row.addWidget(self._refresh)
        self._auto = QCheckBox(_t("trading.auto_refresh"))
        self._auto.toggled.connect(self._toggle_auto)
        row.addWidget(self._auto)
        row.addWidget(QLabel(_t("trading.chart_session")))
        self._session = QComboBox()
        for key in terminal.SESSIONS:
            self._session.addItem(_t(f"trading.session_{key}"), key)
        self._session.currentIndexChanged.connect(self._chart_changed)
        row.addWidget(self._session)
        layout.addLayout(row)
        self._status = QLabel(_t("trading.connecting"))
        self._status.setWordWrap(True)
        layout.addWidget(self._status)
        self._chart = CandleChart()
        layout.addWidget(self._chart, 1)
        self._results = QLabel(_t("trading.no_data"))
        self._results.setTextFormat(Qt.TextFormat.PlainText)
        self._results.setWordWrap(True)
        self._results.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(self._results)
        self._timer = QTimer(self)
        self._timer.setInterval(15_000)
        self._timer.timeout.connect(self._request)
        self._age_timer = QTimer(self)
        self._age_timer.setInterval(5000)
        self._age_timer.timeout.connect(self._mark_stale)
        self._age_timer.start()
        QTimer.singleShot(0, self._request)

    def _allowed(self):
        try:
            return any(r.get("name") == "trading_terminal" and r.get("valid") and r.get("enabled")
                       for r in self._host.get_plugins())
        except Exception:
            return False

    def _toggle_auto(self, enabled):
        if enabled:
            self._timer.start()
        else:
            self._timer.stop()

    def _request(self):
        if self._busy:
            return
        if not self._allowed():
            self._auto.setChecked(False)
            self._snapshot = None
            self._chart.set_data(None, self._session.currentData())
            self._results.setText(_t("trading.no_data"))
            self._status.setText(_t("trading.disabled"))
            return
        raw = {"symbol": self._symbol.text(), "range_minutes": str(self._duration.value())}
        raw.update({f"{name}_start": widget.text() for name, widget in self._inputs.items()})
        try:
            settings = terminal.parse_settings(raw)
        except ValueError as exc:
            self._status.setText(_t("trading.error", error=str(exc)))
            return
        if not save_plugin_config("trading_terminal", raw):
            self._status.setText(_t("trading.save_error"))
            return
        self._busy = True
        self._refresh.setEnabled(False)
        self._status.setText(_t("trading.connecting"))
        def worker():
            try:
                data, error = terminal.snapshot(settings), ""
            except Exception as exc:
                data, error = None, str(exc)
            try:
                self._data_ready.emit(data, error)
            except RuntimeError:
                pass
        threading.Thread(target=worker, daemon=True, name="mt5-terminal").start()

    def _on_data(self, data, error):
        self._busy = False
        self._refresh.setEnabled(True)
        if error:
            self._snapshot = None
            self._chart.set_data(None, self._session.currentData())
            self._results.setText(_t("trading.no_data"))
            self._status.setText(_t("trading.error", error=error[:500]))
            return
        self._snapshot = data
        self._render_data(data)

    def _mark_stale(self):
        data = self._snapshot
        if not data or not data["fresh"]:
            return
        now = datetime.now(timezone.utc)
        if any(not 0 <= (now - data[key]).total_seconds() <= limit for key, limit in (
                ("tick_time", terminal.STALE_TICK_SECONDS),
                ("last_bar_close", terminal.STALE_BAR_SECONDS))):
            data["fresh"] = False
            for item in data["sessions"].values():
                item["data_stale"] = True
                if item["state"] in ("up", "down", "inside"):
                    item["state"] = "stale"
            self._render_data(data)

    def _render_data(self, data):
        status = _t("trading.live") if data["fresh"] else _t("trading.stale")
        self._status.setText(_t("trading.quote", symbol=data["settings"]["symbol"],
                                bid=f"{data['bid']:.5f}", ask=f"{data['ask']:.5f}",
                                time=data["tick_time"].strftime("%Y-%m-%d %H:%M:%S UTC"), status=status)
                             + " | " + _t("trading.account", account=data["account"], server=data["server"]))
        lines = []
        for name, item in data["sessions"].items():
            state = _t("trading.state_" + item["state"])
            if item.get("data_stale"):
                state += " — " + _t("trading.stale")
            levels = (f"H {item['high']:.5f} / L {item['low']:.5f}"
                      if item["high"] is not None else "—")
            detail = (f" | {_t('trading.break_time')}: {item['breakout_time']:%H:%M UTC}"
                      if item["breakout_time"] else "")
            if item["state"] == "incomplete":
                detail += f" | {_t('trading.missing')}: {item['missing']}"
            lines.append(f"{_t('trading.session_' + name)} | {state} | {levels} | "
                         f"{item['start']:%Y-%m-%d %H:%M}–{item['range_end']:%H:%M} UTC "
                         f"({item['timezone']}){detail}")
        self._results.setText("\n".join(lines))
        self._chart_changed()

    def _chart_changed(self, *_):
        self._chart.set_data(self._snapshot, self._session.currentData())


def open_terminal(window, request):
    try:
        allowed = any(row.get("name") == "trading_terminal" and row.get("valid") and row.get("enabled")
                      for row in window.get_plugins())
    except Exception:
        allowed = False
    if not allowed:
        window.write_log(_t("trading.disabled"))
        return
    dialog = TradingTerminal(window, request)
    if not hasattr(window, "_trading_dialogs"):
        window._trading_dialogs = set()
    window._trading_dialogs.add(dialog)
    dialog.destroyed.connect(lambda: window._trading_dialogs.discard(dialog))
    dialog.show()
    dialog.raise_()
