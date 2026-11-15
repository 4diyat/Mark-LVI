"""Explicitly reviewed MT5 orders. No order is submitted during preparation.

A single checked request is sent at most once after an on-device approval.
Broker results are not retried automatically: a missing response is UNKNOWN.
The separate _mt5 data helper remains strictly read-only.
"""
from __future__ import annotations

import math
import secrets
import threading
import time
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Mapping

from plugins import _mt5


_claimed = {}
_claim_lock = threading.Lock()


class TradeError(RuntimeError):
    pass


@dataclass(frozen=True)
class Prepared:
    token: str
    expires: float
    mode: str
    login: int
    server: str
    kind: str
    symbol: str
    volume: float
    side: str
    price: float
    sl: float
    tp: float
    ticket: int
    old_order: tuple | None
    max_volume: float
    max_loss: float
    estimated_loss: float
    currency: str
    request: tuple
    summary: str


def _number(value, name, *, allow_zero=False):
    try:
        n = float(value)
    except (TypeError, ValueError):
        raise TradeError(f"Invalid {name}.") from None
    if not math.isfinite(n) or n < 0 or (not allow_zero and n == 0):
        raise TradeError(f"Invalid {name}.")
    return n


def _identity(mt5, expected_mode):
    terminal, account = mt5.terminal_info(), mt5.account_info()
    if terminal is None or account is None or not getattr(terminal, "connected", False):
        raise TradeError("MT5 terminal is not connected to an account.")
    if not (getattr(terminal, "trade_allowed", False) and getattr(account, "trade_allowed", False)
            and getattr(account, "trade_expert", False)):
        raise TradeError("Trading is disabled by the terminal or account; check Algo Trading and broker permissions.")
    actual = getattr(account, "trade_mode", None)
    demo = getattr(mt5, "ACCOUNT_TRADE_MODE_DEMO", None)
    live = getattr(mt5, "ACCOUNT_TRADE_MODE_REAL", None)
    if actual is None or demo is None or live is None or demo == live:
        raise TradeError("Account type is unknown; no order can be sent.")
    mode = "DEMO" if actual == demo else "LIVE" if actual == live else None
    if mode not in {"DEMO", "LIVE"} or mode != expected_mode:
        raise TradeError("Account type is unknown or does not match the enabled mode.")
    login, server = int(getattr(account, "login", 0)), str(getattr(account, "server", "") or "")
    if login <= 0 or not server:
        raise TradeError("Could not verify account identity.")
    return mode, login, server


def _old_pending(mt5, ticket):
    orders = mt5.orders_get(ticket=ticket)
    if orders is None:
        raise TradeError("Could not retrieve the pending order from MT5.")
    if len(orders) != 1:
        raise TradeError("Pending order was not found or is no longer pending.")
    order = orders[0]
    # Price, volume, protection and lifetime are checked again after review.
    return (int(order.ticket), str(order.symbol), int(order.type), float(order.volume_current),
            float(order.price_open), float(order.sl), float(order.tp),
            int(order.type_time), int(order.time_expiration), float(getattr(order, "price_stoplimit", 0.0)))


def _check_volume(info, volume, max_volume):
    if volume > max_volume:
        raise TradeError("Volume exceeds the local maximum set in the trading dialog.")
    try:
        v, step = Decimal(str(volume)), Decimal(str(info.volume_step))
        vmin, vmax = Decimal(str(info.volume_min)), Decimal(str(info.volume_max))
        if step <= 0 or v < vmin or v > vmax or (v - vmin) % step != 0:
            raise TradeError("Volume does not match the broker's minimum, maximum or step.")
    except (InvalidOperation, ValueError, AttributeError):
        raise TradeError("Could not validate broker volume constraints.") from None


def _estimated_loss(mt5, side, symbol, volume, price, sl):
    if (side == "buy" and sl >= price) or (side == "sell" and sl <= price):
        raise TradeError("Stop loss is on the wrong side of the order price.")
    side_code = mt5.ORDER_TYPE_BUY if side == "buy" else mt5.ORDER_TYPE_SELL
    estimate = mt5.order_calc_profit(side_code, symbol, volume, price, sl)
    if estimate is None or not math.isfinite(float(estimate)) or float(estimate) >= 0:
        raise TradeError("Could not estimate a loss at the stop loss; no order was sent.")
    return -float(estimate)


def _pending_side(mt5, order_type):
    # Stop-limit orders have a distinct eventual entry price; do not estimate
    # their risk using the trigger price or silently modify them.
    buys = tuple(getattr(mt5, k, object()) for k in ("ORDER_TYPE_BUY_LIMIT", "ORDER_TYPE_BUY_STOP"))
    sells = tuple(getattr(mt5, k, object()) for k in ("ORDER_TYPE_SELL_LIMIT", "ORDER_TYPE_SELL_STOP"))
    if order_type in buys:
        return "buy"
    if order_type in sells:
        return "sell"
    raise TradeError("Unsupported pending order type; no order was sent.")


def _checked(mt5, request):
    checked = mt5.order_check(request)
    if checked is None:
        raise TradeError("MT5 order check failed; no order was sent.")
    if getattr(checked, "retcode", None) != 0:
        raise TradeError(f"MT5 order check rejected the request: {getattr(checked, 'comment', '')} (code {getattr(checked, 'retcode', '?')}).")
    return checked


def prepare(draft: Mapping, mode: str, max_volume: float, max_loss: float) -> Prepared:
    """Build and check a new market order or modify a pending order; never send."""
    if mode not in {"DEMO", "LIVE"}:
        raise TradeError("Trading is off. Choose DEMO or LIVE in the desktop dialog.")
    max_volume = _number(max_volume, "maximum volume")
    max_loss = _number(max_loss, "maximum estimated loss")
    if max_volume > 1.0:
        raise TradeError("Local maximum volume cannot exceed 1.0 lot per order.")
    kind = str(draft.get("kind", ""))
    if kind not in {"market", "modify_pending"}:
        raise TradeError("Only market orders and pending-order modifications are supported.")
    symbol = str(draft.get("symbol", "")).strip()
    if len(symbol) > 80 or any(ord(c) < 32 for c in symbol):
        raise TradeError("Invalid symbol.")
    sl = _number(draft.get("sl"), "stop loss")
    tp = _number(draft.get("tp", 0), "take profit", allow_zero=True)
    with _mt5.connect() as session:
        mt5 = session.mt5
        actual_mode, login, server = _identity(mt5, mode)
        ticket, old, side = 0, None, ""
        if kind == "market":
            if not symbol:
                raise TradeError("A broker symbol is required.")
            side = str(draft.get("side", "")).lower()
            if side not in {"buy", "sell"}:
                raise TradeError("Choose buy or sell.")
            volume = _number(draft.get("volume"), "volume")
            session.select(symbol)
            info = session.symbol_info(symbol)
            _check_volume(info, volume, max_volume)
            tick = mt5.symbol_info_tick(symbol)
            if tick is None:
                raise TradeError("No current quote is available.")
            age = time.time() - float(getattr(tick, "time", 0))
            if not 0 <= age <= 10:
                raise TradeError("Quote is stale; review again with a current quote.")
            price = _number(tick.ask if side == "buy" else tick.bid, "quote")
            if (side == "buy" and (sl >= price or (tp and tp <= price))) or (side == "sell" and (sl <= price or (tp and tp >= price))):
                raise TradeError("Stop loss or take profit is on the wrong side of the quote.")
            request = {"action": mt5.TRADE_ACTION_DEAL, "symbol": symbol, "volume": volume,
                       "type": mt5.ORDER_TYPE_BUY if side == "buy" else mt5.ORDER_TYPE_SELL,
                       "price": price, "sl": sl, "tp": tp, "deviation": 10,
                       "type_time": mt5.ORDER_TIME_GTC, "type_filling": mt5.ORDER_FILLING_IOC,
                       "comment": "JARVIS reviewed"}
        else:
            try:
                ticket = int(draft.get("ticket", 0))
            except (ValueError, TypeError):
                raise TradeError("Invalid pending-order ticket.") from None
            if ticket <= 0:
                raise TradeError("A pending-order ticket is required.")
            old = _old_pending(mt5, ticket)
            symbol, volume = old[1], old[3]
            side = _pending_side(mt5, old[2])
            _check_volume(session.symbol_info(symbol), volume, max_volume)
            price = _number(draft.get("price"), "pending order price")
            # Preserve expiration and stop-limit attributes, never alter volume/type.
            request = {"action": mt5.TRADE_ACTION_MODIFY, "order": ticket, "symbol": symbol,
                       "price": price, "sl": sl, "tp": tp, "type_time": old[7],
                       "expiration": old[8], "stoplimit": old[9]}
        estimated_loss = _estimated_loss(mt5, side, symbol, volume, price, sl)
        if estimated_loss > max_loss:
            raise TradeError("Estimated loss at stop loss exceeds the local limit; no order was sent.")
        currency = str(getattr(mt5.account_info(), "currency", "") or "")
        if not currency:
            raise TradeError("Account currency could not be verified; no order was sent.")
        check = _checked(mt5, request)
        # A malicious or changing broker must not cause an unchecked account switch.
        if _identity(mt5, mode) != (actual_mode, login, server):
            raise TradeError("Account changed during order preparation.")
        masked = "*" * max(0, len(str(login)) - 4) + str(login)[-4:]
        summary = (f"{actual_mode} | account {masked} | server {server}\n"
                   f"{kind.upper()} {side.upper()} | {symbol} | volume {volume:g} lots\n"
                   f"Price {price:g} | SL {sl:g} | TP {tp:g} | ticket {ticket or 'new'}\n"
                   f"Maximum {max_volume:g} lots | requested market deviation 10 points\n"
                   f"Estimated loss at stop: {estimated_loss:.2f} {currency} (limit {max_loss:.2f} {currency})\n"
                   f"Actual loss can exceed this estimate due to slippage, gaps, fees or failed stops.\n"
                   f"Estimated margin: {getattr(check, 'margin', 'unavailable')} (broker order check)\n"
                   + (f"Existing order: price {old[4]:g}, SL {old[5]:g}, TP {old[6]:g}, type {old[2]}, "
                      f"time type {old[7]}, expiration {old[8]}, stop-limit {old[9]:g}\n" if old else "")
                   + "Review expires in 45 seconds. LIVE accounts risk real funds.")
        return Prepared(secrets.token_hex(16), time.monotonic() + 45, actual_mode, login, server, kind, symbol, volume, side, price, sl, tp,
                        ticket, old, max_volume, max_loss, estimated_loss, currency, tuple(request.items()), summary)


def execute(prepared: Prepared):
    """Send the reviewed immutable request once, after desktop approval only."""
    if not isinstance(prepared, Prepared):
        raise TradeError("A reviewed order is required.")
    with _claim_lock:
        now = time.monotonic()
        for token, expiry in list(_claimed.items()):
            if expiry < now:
                del _claimed[token]
        if prepared.token in _claimed:
            raise TradeError("This review has already been used; prepare a new one.")
        _claimed[prepared.token] = prepared.expires
    if time.monotonic() > prepared.expires:
        raise TradeError("The review expired; no order was sent.")
    with _mt5.connect() as session:
        mt5 = session.mt5
        if _identity(mt5, prepared.mode) != (prepared.mode, prepared.login, prepared.server):
            raise TradeError("Account or server changed after review; no order was sent.")
        if prepared.old_order is not None and _old_pending(mt5, prepared.ticket) != prepared.old_order:
            raise TradeError("The pending order changed after review; no order was sent.")
        if prepared.kind == "market":
            tick = mt5.symbol_info_tick(prepared.symbol)
            info = session.symbol_info(prepared.symbol)
            if tick is None or not 0 <= time.time() - float(getattr(tick, "time", 0)) <= 10:
                raise TradeError("Quote is stale; no order was sent.")
            current = _number(tick.ask if prepared.side == "buy" else tick.bid, "quote")
            point = _number(getattr(info, "point", 0), "broker point")
            if abs(current - prepared.price) > 10 * point:
                raise TradeError("Price moved beyond 10 points after review; no order was sent.")
        account = mt5.account_info()
        if account is None or str(getattr(account, "currency", "") or "") != prepared.currency:
            raise TradeError("Account currency changed; no order was sent.")
        _check_volume(session.symbol_info(prepared.symbol), prepared.volume, prepared.max_volume)
        loss = _estimated_loss(mt5, prepared.side, prepared.symbol, prepared.volume, prepared.price, prepared.sl)
        if loss > prepared.max_loss or loss > prepared.estimated_loss * 1.01:
            raise TradeError("Estimated risk increased after review; no order was sent. Prepare again.")
        request = dict(prepared.request)
        _checked(mt5, request)
        if _identity(mt5, prepared.mode) != (prepared.mode, prepared.login, prepared.server):
            raise TradeError("Account or server changed before submission; no order was sent.")
        if prepared.old_order is not None and _old_pending(mt5, prepared.ticket) != prepared.old_order:
            raise TradeError("The pending order changed before submission; no order was sent.")
        if time.monotonic() > prepared.expires:
            raise TradeError("The review expired before submission; no order was sent.")
        if prepared.kind == "market":
            tick = mt5.symbol_info_tick(prepared.symbol)
            if tick is None or not 0 <= time.time() - float(getattr(tick, "time", 0)) <= 10:
                raise TradeError("Quote is stale; no order was sent.")
            current = _number(tick.ask if prepared.side == "buy" else tick.bid, "quote")
            if abs(current - prepared.price) > 10 * point:
                raise TradeError("Price moved beyond 10 points before submission; no order was sent.")
        try:
            result = mt5.order_send(request)  # exactly one attempt; never retry an unknown result
        except Exception as exc:
            return f"UNKNOWN: MT5 did not return a result ({exc}). Check the terminal before trying again."
        if result is None:
            return "UNKNOWN: MT5 did not return a result. Check the terminal before trying again."
        code = getattr(result, "retcode", None)
        if code in {getattr(mt5, "TRADE_RETCODE_DONE", None), getattr(mt5, "TRADE_RETCODE_PLACED", None),
                    getattr(mt5, "TRADE_RETCODE_DONE_PARTIAL", None)} and code is not None:
            status = ("partial fill" if code == getattr(mt5, "TRADE_RETCODE_DONE_PARTIAL", None)
                      else "placed" if code == getattr(mt5, "TRADE_RETCODE_PLACED", None) else "completed")
            return (f"MT5 accepted ({status}): code {code}, order {getattr(result, 'order', 0)}, "
                    f"deal {getattr(result, 'deal', 0)}, volume {getattr(result, 'volume', 'unknown')}; "
                    f"{getattr(result, 'comment', '')}. Verify the terminal.")
        return f"MT5 did not confirm success: code {code}, {getattr(result, 'comment', '')}. Check the terminal."
