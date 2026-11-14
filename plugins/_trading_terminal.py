"""Read-only MT5 data and configurable, closed-M1 session ORB analysis.

MT5 bar timestamps are Unix epoch seconds in UTC. Session starts use IANA
market time zones, including DST. No order APIs are called by this module.
"""
from __future__ import annotations

import math
import threading
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from plugins import _mt5

SESSIONS = {
    "asia": ("Asia/Tokyo", "09:00", 480),
    "london": ("Europe/London", "08:00", 480),
    "new_york": ("America/New_York", "09:30", 390),
}
DEFAULTS = {"symbol": "EURUSD", "asia_start": "09:00", "london_start": "08:00",
            "new_york_start": "09:30", "range_minutes": "15"}
_LOCK = threading.Lock()
STALE_TICK_SECONDS = 60
STALE_BAR_SECONDS = 120


def parse_settings(values: dict | None) -> dict:
    raw = dict(DEFAULTS)
    raw.update(values or {})
    symbol = str(raw["symbol"]).strip()
    if not symbol or len(symbol) > 80 or any(ord(c) < 32 for c in symbol):
        raise ValueError("Enter a valid broker symbol from Market Watch.")
    try:
        minutes = int(str(raw["range_minutes"]).strip())
    except (TypeError, ValueError):
        raise ValueError("Opening range must be an integer from 1 to 120 minutes.") from None
    if not 1 <= minutes <= 120:
        raise ValueError("Opening range must be an integer from 1 to 120 minutes.")
    out = {"symbol": symbol, "range_minutes": minutes}
    for name in SESSIONS:
        val = str(raw.get(f"{name}_start") or "").strip()
        try:
            start = datetime.strptime(val, "%H:%M").time()
        except ValueError:
            raise ValueError(f"{name}: use a local start time in HH:MM format.") from None
        out[f"{name}_start"] = start.strftime("%H:%M")
    return out


def _market_start(now: datetime, name: str, start_text: str) -> tuple[datetime, datetime]:
    zone_name, _, length = SESSIONS[name]
    try:
        zone = ZoneInfo(zone_name)
    except ZoneInfoNotFoundError:
        raise ValueError("Time zone database missing; install tzdata.") from None
    local_now = now.astimezone(zone)
    h, m = (int(x) for x in start_text.split(":"))
    day = local_now.date()
    start = datetime.combine(day, time(h, m), zone)
    if start.astimezone(timezone.utc) > now:
        start = datetime.combine(day - timedelta(days=1), time(h, m), zone)
    # Refuse ambiguous/nonexistent local times rather than guessing across DST.
    if start.replace(fold=0).utcoffset() != start.replace(fold=1).utcoffset():
        raise ValueError(f"{name} start falls in a daylight-saving transition; choose another time.")
    start_utc = start.astimezone(timezone.utc)
    return start_utc, start_utc + timedelta(minutes=length)


def _valid_bar(bar) -> bool:
    try:
        op, high, low, close = (float(v) for v in (bar.open, bar.high, bar.low, bar.close))
        return all(math.isfinite(v) for v in (op, high, low, close)) and low <= min(op, close) <= max(op, close) <= high
    except (TypeError, ValueError, AttributeError):
        return False


def analyse_session(bars, name: str, settings: dict, now: datetime) -> dict:
    if name not in SESSIONS:
        raise ValueError("Unknown market session.")
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("An aware UTC timestamp is required.")
    now = now.astimezone(timezone.utc)
    start, end = _market_start(now, name, settings[f"{name}_start"])
    range_end = start + timedelta(minutes=settings["range_minutes"])
    expected = [int((start + timedelta(minutes=i)).timestamp())
                for i in range(settings["range_minutes"])]
    # Ignore incomplete or future candles even if a mock/terminal returns one.
    closed = {int(bar.time): bar for bar in bars
              if int(bar.time) + 60 <= int(now.timestamp()) and _valid_bar(bar)}
    missing = [stamp for stamp in expected if stamp not in closed]
    result = {"session": name, "timezone": SESSIONS[name][0], "start": start,
              "range_end": range_end, "end": end, "high": None, "low": None,
              "breakout": None, "breakout_time": None, "state": "waiting",
              "missing": len(missing)}
    if now < range_end:
        return result
    if missing:
        result["state"] = "incomplete"
        return result
    window = [closed[stamp] for stamp in expected]
    result["high"] = max(float(b.high) for b in window)
    result["low"] = min(float(b.low) for b in window)
    # Missing closed candles after the range could hide an earlier breakout;
    # never present a later candle as the first signal in that case.
    cutoff = min(int(now.timestamp()) // 60 * 60, int(end.timestamp()))
    post_expected = range(int(range_end.timestamp()), cutoff, 60)
    missing_post = sum(1 for stamp in post_expected if stamp not in closed)
    if missing_post:
        result["missing"] = missing_post
        result["state"] = "incomplete"
        return result
    # Only examine completed candles after the range and before this session ends.
    for stamp, bar in sorted(closed.items()):
        if not (range_end.timestamp() <= stamp and stamp + 60 <= end.timestamp()):
            continue
        close = float(bar.close)
        if not math.isfinite(close):
            result["state"] = "incomplete"
            result["missing"] += 1
            return result
        if close > result["high"] or close < result["low"]:
            result["breakout"] = "up" if close > result["high"] else "down"
            result["breakout_time"] = datetime.fromtimestamp(stamp + 60, timezone.utc)
            break
    result["state"] = "closed" if now >= end else (result["breakout"] or "inside")
    return result


def snapshot(values: dict | None = None, *, now=None, connect=None) -> dict:
    """Read M1 bars and a tick; does not modify account or send any trade."""
    settings = parse_settings(values)
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("An aware UTC timestamp is required.")
    now = now.astimezone(timezone.utc)
    with _LOCK:
        with (connect or _mt5.connect)(timeout_ms=10_000) as terminal:
            terminal.select(settings["symbol"])
            bars = terminal.bars(settings["symbol"], "M1", 2000, closed_only=True)
            tick = terminal.mt5.symbol_info_tick(settings["symbol"])
            info = terminal.mt5.terminal_info()
            account = terminal.mt5.account_info()
            if account is None:
                raise _mt5.MT5Unavailable("The MT5 terminal has no logged-in account.")
            if info is not None and not getattr(info, "connected", True):
                raise _mt5.MT5Unavailable("The terminal is disconnected from its broker.")
            if tick is None:
                raise _mt5.MT5Unavailable("No tick is available for this symbol.")
            bid, ask = float(tick.bid), float(tick.ask)
            tick_time = datetime.fromtimestamp(int(tick.time), timezone.utc)
            login = str(getattr(account, "login", "") or "")
            masked_login = ("***" + login[-4:]) if login else "—"
            server = str(getattr(account, "server", "") or "—")[:120]
    rows = sorted((b for b in bars if int(b.time) + 60 <= int(now.timestamp())
                   and _valid_bar(b)), key=lambda b: b.time)
    if not rows:
        raise _mt5.MT5Unavailable("No closed one-minute bars were returned.")
    if not (math.isfinite(bid) and math.isfinite(ask) and bid > 0 and ask >= bid):
        raise _mt5.MT5Unavailable("The terminal returned invalid bid/ask prices.")
    last_close = datetime.fromtimestamp(int(rows[-1].time) + 60, timezone.utc)
    age = (now - last_close).total_seconds()
    tick_age = (now - tick_time).total_seconds()
    fresh = 0 <= age <= STALE_BAR_SECONDS and 0 <= tick_age <= STALE_TICK_SECONDS
    analyses = {name: analyse_session(rows, name, settings, now) for name in SESSIONS}
    if not fresh:
        for value in analyses.values():
            value["data_stale"] = True
            # A stale feed must never be shown as a current signal.
            if value["state"] in ("up", "down", "inside"):
                value["state"] = "stale"
    return {"settings": settings, "bars": rows[-180:], "sessions": analyses,
            "bid": bid, "ask": ask, "tick_time": tick_time,
            "last_bar_close": last_close, "as_of": now, "fresh": fresh,
            "account": masked_login, "server": server}
