"""Read-only MT5 session ORB and desktop routing, with no trading or network."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from core import plugin_manifest
from core.plugin_loader import discover_plugins
from plugins import _mt5, _trading_terminal as backend, trading_terminal

UTC = timezone.utc
ROOT = Path(__file__).resolve().parents[1]


def bar(at, close=100, high=101, low=99):
    return _mt5.Bar(int(at.timestamp()), 100.0, float(high), float(low), float(close), 1)


def make_bars(start, count):
    return [bar(start + timedelta(minutes=i)) for i in range(count)]


def settings(**kw):
    return backend.parse_settings(kw)


def test_london_15_minute_range_and_closed_candle_breakout():
    start = datetime(2026, 1, 5, 8, tzinfo=UTC)
    rows = make_bars(start, 16)
    rows[-1] = bar(start + timedelta(minutes=15), close=102, high=103)
    # A still-forming candle is not eligible.
    rows.append(bar(start + timedelta(minutes=16), close=98, low=97))
    result = backend.analyse_session(rows, "london", settings(), start + timedelta(minutes=16))
    assert result["high"] == 101 and result["low"] == 99
    assert result["state"] == "up" and result["breakout"] == "up"
    assert result["breakout_time"] == start + timedelta(minutes=16)


def test_wick_not_breakout_and_incomplete_range_never_signals():
    start = datetime(2026, 1, 5, 8, tzinfo=UTC)
    rows = make_bars(start, 16)
    rows[-1] = bar(start + timedelta(minutes=15), close=100, high=103)
    now = start + timedelta(minutes=16)
    assert backend.analyse_session(rows, "london", settings(), now)["state"] == "inside"
    del rows[5]
    result = backend.analyse_session(rows, "london", settings(), now)
    assert result["state"] == "incomplete" and result["high"] is None


def test_missing_post_range_candle_does_not_misidentify_first_breakout():
    start = datetime(2026, 1, 5, 8, tzinfo=UTC)
    rows = make_bars(start, 18)
    rows.pop(15)
    rows[-1] = bar(start + timedelta(minutes=17), close=102, high=103)
    result = backend.analyse_session(rows, "london", settings(), start + timedelta(minutes=18))
    assert result["state"] == "incomplete" and result["breakout"] is None


def test_dst_changes_market_open_and_no_broker_offset_is_applied():
    winter = datetime(2026, 1, 5, 9, tzinfo=UTC)
    summer = datetime(2026, 7, 6, 9, tzinfo=UTC)
    cfg = settings()
    assert backend.analyse_session([], "london", cfg, winter)["start"].hour == 8
    assert backend.analyse_session([], "london", cfg, summer)["start"].hour == 7
    assert backend.analyse_session([], "new_york", cfg, datetime(2026, 1, 5, 16, tzinfo=UTC))["start"].hour == 14
    assert backend.analyse_session([], "new_york", cfg, datetime(2026, 7, 6, 16, tzinfo=UTC))["start"].hour == 13
    assert backend.analyse_session([], "asia", cfg, winter)["start"].hour == 0


def test_configurable_minutes_and_session_hours():
    start = datetime(2026, 1, 5, 8, 30, tzinfo=UTC)
    cfg = settings(london_start="08:30", range_minutes="3")
    rows = make_bars(start, 4)
    rows[-1] = bar(start + timedelta(minutes=3), close=98, low=97)
    result = backend.analyse_session(rows, "london", cfg, start + timedelta(minutes=4))
    assert result["state"] == "down" and result["start"] == start
    assert result["range_end"] == start + timedelta(minutes=3)
    with pytest.raises(ValueError):
        settings(range_minutes="0")
    with pytest.raises(ValueError):
        settings(asia_start="25:00")


def test_session_end_does_not_scan_the_next_session():
    start = datetime(2026, 1, 5, 8, tzinfo=UTC)
    rows = make_bars(start, 480)
    rows.append(bar(start + timedelta(minutes=480), close=102, high=103))
    result = backend.analyse_session(rows, "london", settings(), start + timedelta(minutes=481))
    assert result["state"] == "closed" and result["breakout"] is None


def test_dst_ambiguous_start_is_not_guessed():
    cfg = settings(london_start="01:30")
    with pytest.raises(ValueError, match="daylight-saving"):
        backend.analyse_session([], "london", cfg, datetime(2026, 10, 25, 5, tzinfo=UTC))


class FakeTerminal:
    def __init__(self, rows, tick):
        self.rows, self.tick, self.calls = rows, tick, []
        self.mt5 = self
    def __enter__(self):
        return self
    def __exit__(self, *_):
        self.calls.append("closed")
    def select(self, symbol):
        self.calls.append(("select", symbol))
    def bars(self, symbol, tf, count, closed_only):
        self.calls.append(("bars", symbol, tf, closed_only))
        return self.rows
    def symbol_info_tick(self, symbol):
        return self.tick
    def terminal_info(self):
        return SimpleNamespace(connected=True)
    def account_info(self):
        return SimpleNamespace(login=12345678, server="Demo-Broker")


def test_snapshot_uses_closed_bars_and_suppresses_stale_signals():
    start = datetime(2026, 1, 5, 8, tzinfo=UTC)
    now = start + timedelta(minutes=16)
    rows = make_bars(start, 16)
    rows[-1] = bar(start + timedelta(minutes=15), close=102, high=103)
    tick = SimpleNamespace(bid=100.0, ask=100.1, time=int(now.timestamp()))
    fake = FakeTerminal(rows, tick)
    out = backend.snapshot({"symbol": "EURUSDm"}, now=now, connect=lambda **_: fake)
    assert out["fresh"] and out["sessions"]["london"]["state"] == "up"
    assert out["account"] == "***5678" and out["server"] == "Demo-Broker"
    assert ("bars", "EURUSDm", "M1", True) in fake.calls and fake.calls[-1] == "closed"
    stale = backend.snapshot({}, now=now + timedelta(minutes=10), connect=lambda **_: fake)
    assert not stale["fresh"] and stale["sessions"]["london"]["data_stale"]
    assert stale["sessions"]["london"]["state"] not in ("up", "down")


def test_manifest_and_entry_are_read_only(isolated_config):
    manifest = plugin_manifest.verify(ROOT / "plugins/trading_terminal.py", "trading_terminal")
    assert manifest.ok and manifest.permissions == ("network",)
    registry = discover_plugins(ROOT / "plugins", set(), lambda _: None)
    row = next(r for r in registry.list_for_ui() if r["name"] == "trading_terminal")
    assert row["valid"] and not row["enabled"]
    calls = []
    player = SimpleNamespace(show_code_job=calls.append)
    assert "does not place orders" in trading_terminal.run({"symbol": "XAUUSDm"}, player)
    assert calls == [{"kind": "trading_terminal", "symbol": "XAUUSDm"}]
    assert "desktop" in trading_terminal.run({}, None)
    for path in (ROOT / "plugins/_trading_terminal.py", ROOT / "ui/trading_terminal.py"):
        assert "order_send" not in path.read_text(encoding="utf-8")


def test_no_account_or_invalid_tick_is_not_reported_as_connected():
    start = datetime(2026, 1, 5, 8, tzinfo=UTC)
    now = start + timedelta(minutes=16)
    tick = SimpleNamespace(bid=100.0, ask=100.1, time=int(now.timestamp()))
    fake = FakeTerminal(make_bars(start, 16), tick)
    fake.account_info = lambda: None
    with pytest.raises(_mt5.MT5Unavailable, match="no logged-in"):
        backend.snapshot({}, now=now, connect=lambda **_: fake)
    assert fake.calls[-1] == "closed"
    fake.account_info = lambda: SimpleNamespace(login=42, server="Demo")
    fake.tick = SimpleNamespace(bid=100, ask=99, time=int(now.timestamp()))
    with pytest.raises(_mt5.MT5Unavailable, match="invalid bid/ask"):
        backend.snapshot({}, now=now, connect=lambda **_: fake)


def test_shared_mt5_connection_does_not_shutdown_another_request(monkeypatch):
    import threading
    import time
    events = []
    class MT5:
        def initialize(self, **kwargs):
            events.append("initialize")
            return True
        def terminal_info(self):
            return SimpleNamespace(name="Demo")
        def shutdown(self):
            events.append("shutdown")
    fake = MT5()
    monkeypatch.setattr(_mt5, "_module", lambda: fake)
    first = _mt5.connect()
    started, finished = threading.Event(), threading.Event()
    def second():
        started.set()
        with _mt5.connect():
            events.append("second used")
        finished.set()
    thread = threading.Thread(target=second)
    thread.start()
    assert started.wait(1)
    time.sleep(.05)
    assert events == ["initialize"] and not finished.is_set()
    first.close()
    assert finished.wait(1)
    thread.join()
    assert events == ["initialize", "shutdown", "initialize", "second used", "shutdown"]


def test_ui_routes_terminal_and_displays_stale_data():
    window = (ROOT / "ui/window.py").read_text(encoding="utf-8")
    router = (ROOT / "ui/workspace_router.py").read_text(encoding="utf-8")
    gui = (ROOT / "ui/trading_terminal.py").read_text(encoding="utf-8")
    assert '"creative_workspace", "trading_terminal"' in window
    assert '"trading_terminal"' in router and 'open_terminal(window, job)' in router
    assert 'trading.stale' in gui and 'def _mark_stale' in gui
    assert 'self._allowed()' in gui


def test_mt5_session_close_is_idempotent():
    calls = []
    session = _mt5.Session(SimpleNamespace(shutdown=lambda: calls.append("closed")))
    session.close()
    session.close()
    assert calls == ["closed"]


def test_invalid_ohlc_candle_cannot_produce_a_signal():
    start = datetime(2026, 1, 5, 8, tzinfo=UTC)
    rows = make_bars(start, 16)
    # Close above the candle's own high is malformed, not a breakout.
    rows[-1] = bar(start + timedelta(minutes=15), close=105, high=101)
    result = backend.analyse_session(rows, "london", settings(), start + timedelta(minutes=16))
    assert result["state"] == "incomplete" and result["breakout"] is None
