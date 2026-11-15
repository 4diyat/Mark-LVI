"""MT5 execution tests use fakes only. Never connect to a real terminal."""
from contextlib import contextmanager
from types import SimpleNamespace
import time

import pytest

from plugins import _mt5, _mt5_trade as trade, mt5_trade


class FakeMT5:
    ACCOUNT_TRADE_MODE_DEMO, ACCOUNT_TRADE_MODE_REAL = 0, 2
    ORDER_TYPE_BUY, ORDER_TYPE_SELL = 0, 1
    ORDER_TYPE_BUY_LIMIT, ORDER_TYPE_SELL_LIMIT = 2, 3
    ORDER_TYPE_BUY_STOP, ORDER_TYPE_SELL_STOP = 4, 5
    ORDER_TYPE_BUY_STOP_LIMIT, ORDER_TYPE_SELL_STOP_LIMIT = 6, 7
    TRADE_ACTION_DEAL, TRADE_ACTION_MODIFY = 1, 7
    ORDER_TIME_GTC, ORDER_FILLING_IOC = 0, 1
    TRADE_RETCODE_DONE, TRADE_RETCODE_PLACED, TRADE_RETCODE_DONE_PARTIAL = 10009, 10008, 10010

    def __init__(self):
        self.account = SimpleNamespace(login=123456, server="Broker-Demo", trade_mode=0,
                                       trade_allowed=True, trade_expert=True, currency="USD")
        self.terminal = SimpleNamespace(connected=True, trade_allowed=True)
        self.info = SimpleNamespace(volume_min=.01, volume_max=100.0, volume_step=.01, point=.00001)
        self.tick = SimpleNamespace(ask=1.1, bid=1.0999, time=time.time())
        self.pending = SimpleNamespace(ticket=77, symbol="EURUSD", type=2, volume_current=.01,
                                       price_open=1.09, sl=1.08, tp=1.12, type_time=0,
                                       time_expiration=0, price_stoplimit=0.0)
        self.profit = -10.0
        self.check_code = 0
        self.sent = []
        self.send_result = SimpleNamespace(retcode=10009, order=111, deal=222, comment="done")

    def terminal_info(self): return self.terminal
    def account_info(self): return self.account
    def symbol_info(self, _): return self.info
    def symbol_info_tick(self, _): return self.tick
    def order_calc_profit(self, *_): return self.profit
    def order_check(self, _): return SimpleNamespace(retcode=self.check_code, comment="check", margin=2.0)
    def order_send(self, request):
        self.sent.append(dict(request))
        return self.send_result
    def orders_get(self, ticket): return (self.pending,) if self.pending and ticket == 77 else ()


@pytest.fixture()
def mt5(monkeypatch):
    fake = FakeMT5()
    @contextmanager
    def connect():
        yield SimpleNamespace(mt5=fake, select=lambda _: None, symbol_info=fake.symbol_info)
    monkeypatch.setattr(_mt5, "connect", connect)
    return fake


def market():
    return {"kind": "market", "symbol": "EURUSD", "side": "buy", "volume": .01, "sl": 1.09, "tp": 1.12}


def test_plugin_opens_only_draft_and_never_trades():
    calls = []
    result = mt5_trade.run(market(), SimpleNamespace(show_code_job=calls.append))
    assert "no order has been sent" in result.lower()
    assert calls[0]["kind"] == "mt5_trade"
    assert "no order" in mt5_trade.run(market(), None).lower()


def test_market_needs_review_and_sends_once(mt5):
    preview = trade.prepare(market(), "DEMO", .01, 20)
    assert not mt5.sent
    assert "DEMO" in preview.summary and "**3456" in preview.summary and "Broker-Demo" in preview.summary
    assert "Estimated loss at stop" in preview.summary
    result = trade.execute(preview)
    assert len(mt5.sent) == 1 and "accepted" in result
    with pytest.raises(trade.TradeError, match="already been used"):
        trade.execute(preview)
    assert len(mt5.sent) == 1


@pytest.mark.parametrize("mode", ["OFF", "LIVE", "UNKNOWN"])
def test_wrong_or_disabled_account_mode_never_sends(mt5, mode):
    with pytest.raises(trade.TradeError):
        trade.prepare(market(), mode, .01, 20)
    assert not mt5.sent


def test_live_account_can_only_be_reviewed_in_live_mode(mt5):
    mt5.account.trade_mode = 2
    with pytest.raises(trade.TradeError):
        trade.prepare(market(), "DEMO", .01, 20)
    preview = trade.prepare(market(), "LIVE", .01, 20)
    assert "LIVE" in preview.summary and not mt5.sent


@pytest.mark.parametrize("change", ["login", "server", "trade_mode", "trade_allowed", "currency"])
def test_changed_account_or_permissions_never_sends(mt5, change):
    preview = trade.prepare(market(), "DEMO", .01, 20)
    updates = {"login": 111, "server": "Other", "trade_mode": 2, "trade_allowed": False, "currency": "EUR"}
    setattr(mt5.account, change, updates[change])
    with pytest.raises(trade.TradeError):
        trade.execute(preview)
    assert not mt5.sent


def test_risk_limits_and_broker_rejection_never_send(mt5):
    with pytest.raises(trade.TradeError, match="maximum"):
        trade.prepare({**market(), "volume": .02}, "DEMO", .01, 20)
    with pytest.raises(trade.TradeError, match="Estimated loss"):
        trade.prepare(market(), "DEMO", .01, 5)
    with pytest.raises(trade.TradeError, match="stop loss"):
        trade.prepare({**market(), "sl": 0}, "DEMO", .01, 20)
    mt5.check_code = 10013
    with pytest.raises(trade.TradeError, match="rejected"):
        trade.prepare(market(), "DEMO", .01, 20)
    assert not mt5.sent


def test_price_movement_and_expired_quote_abort(mt5):
    preview = trade.prepare(market(), "DEMO", .01, 20)
    mt5.tick.ask = 1.2
    with pytest.raises(trade.TradeError, match="Price moved"):
        trade.execute(preview)
    assert not mt5.sent
    mt5.tick.time -= 100
    with pytest.raises(trade.TradeError, match="stale"):
        trade.prepare(market(), "DEMO", .01, 20)


def test_pending_order_change_is_checked_again_before_submission(mt5):
    draft = {"kind": "modify_pending", "ticket": 77, "price": 1.095, "sl": 1.085, "tp": 1.12}
    preview = trade.prepare(draft, "DEMO", .01, 20)
    assert "Existing order" in preview.summary and not mt5.sent
    mt5.pending.sl = 1.075
    with pytest.raises(trade.TradeError, match="changed"):
        trade.execute(preview)
    assert not mt5.sent
    mt5.pending.sl = 1.08
    preview = trade.prepare(draft, "DEMO", .01, 20)
    assert "accepted" in trade.execute(preview)
    assert mt5.sent[-1]["action"] == mt5.TRADE_ACTION_MODIFY


def test_unknown_result_never_retries(mt5):
    preview = trade.prepare(market(), "DEMO", .01, 20)
    mt5.send_result = None
    assert "UNKNOWN" in trade.execute(preview)
    assert len(mt5.sent) == 1
    with pytest.raises(trade.TradeError, match="already been used"):
        trade.execute(preview)
    assert len(mt5.sent) == 1


def test_review_expiry_and_risk_change_prevent_submission(mt5, monkeypatch):
    preview = trade.prepare(market(), "DEMO", .01, 20)
    monkeypatch.setattr(trade.time, "monotonic", lambda: preview.expires + 1)
    with pytest.raises(trade.TradeError, match="expired"):
        trade.execute(preview)
    assert not mt5.sent


def test_permissioned_plugin_is_disabled_by_default(isolated_config):
    from pathlib import Path
    from core import plugin_manifest
    from core.plugin_loader import discover_plugins
    root = Path(__file__).resolve().parents[1]
    manifest = plugin_manifest.verify(root / "plugins/mt5_trade.py", "mt5_trade")
    assert manifest.ok and manifest.permissions == ("network",)
    registry = discover_plugins(root / "plugins", set(), lambda _: None)
    row = next(r for r in registry.list_for_ui() if r["name"] == "mt5_trade")
    assert row["valid"] and not row["enabled"]


def test_failed_result_and_partial_fill_are_reported_without_retry(mt5):
    preview = trade.prepare(market(), "DEMO", .01, 20)
    mt5.send_result = SimpleNamespace(retcode=99999, comment="Rejected", order=0, deal=0)
    assert "did not confirm success" in trade.execute(preview)
    assert len(mt5.sent) == 1
    preview = trade.prepare(market(), "DEMO", .01, 20)
    mt5.send_result = SimpleNamespace(retcode=10010, comment="partial", order=1, deal=2, volume=.005)
    assert "partial fill" in trade.execute(preview)
    assert len(mt5.sent) == 2


def test_risk_is_recalculated_after_review(mt5):
    preview = trade.prepare(market(), "DEMO", .01, 20)
    mt5.profit = -11.0
    with pytest.raises(trade.TradeError, match="risk increased"):
        trade.execute(preview)
    assert not mt5.sent


def test_missing_trade_mode_and_no_automated_execution_permissions_rejected(mt5):
    del mt5.account.trade_mode
    with pytest.raises(trade.TradeError, match="unknown"):
        trade.prepare(market(), "DEMO", .01, 20)
    mt5.account.trade_mode = 0
    mt5.account.trade_expert = False
    with pytest.raises(trade.TradeError, match="disabled"):
        trade.prepare(market(), "DEMO", .01, 20)
    assert not mt5.sent


def test_account_changed_during_broker_check_never_sent(mt5):
    preview = trade.prepare(market(), "DEMO", .01, 20)
    def switch_account(_):
        mt5.account.server = "OtherBroker"
        return SimpleNamespace(retcode=0, comment="ok", margin=1)
    mt5.order_check = switch_account
    with pytest.raises(trade.TradeError, match="Account or server changed"):
        trade.execute(preview)
    assert not mt5.sent


def test_trade_review_guard_blocks_tool_dispatch():
    import ast
    import asyncio
    from pathlib import Path
    from core import trade_guard
    from types import SimpleNamespace
    source = Path(__file__).resolve().parents[1] / "main.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "JarvisLive")
    fn = next(node for node in cls.body if isinstance(node, ast.AsyncFunctionDef) and node.name == "_execute_tool")
    namespace = {"types": SimpleNamespace(FunctionResponse=lambda **kw: kw)}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), str(source), "exec"), namespace)
    fc = SimpleNamespace(name="computer_control", args={"action": "click"}, id="id")
    assert trade_guard.begin()
    try:
        result = asyncio.run(namespace["_execute_tool"](SimpleNamespace(), fc))
        assert "No tool was run" in result["response"]["result"]
        assert not trade_guard.begin()
    finally:
        trade_guard.end()
    assert not trade_guard.active()


def test_stop_limit_pending_orders_are_not_silently_underestimated(mt5):
    mt5.pending.type = mt5.ORDER_TYPE_BUY_STOP_LIMIT
    draft = {"kind": "modify_pending", "ticket": 77, "price": 1.095, "sl": 1.085, "tp": 1.12}
    with pytest.raises(trade.TradeError, match="Unsupported pending"):
        trade.prepare(draft, "DEMO", .01, 20)
    assert not mt5.sent


def test_review_can_expire_while_broker_checks(mt5, monkeypatch):
    preview = trade.prepare(market(), "DEMO", .01, 20)
    real_check = mt5.order_check
    def slow_check(request):
        monkeypatch.setattr(trade.time, "monotonic", lambda: preview.expires + 1)
        return real_check(request)
    mt5.order_check = slow_check
    with pytest.raises(trade.TradeError, match="expired before submission"):
        trade.execute(preview)
    assert not mt5.sent
