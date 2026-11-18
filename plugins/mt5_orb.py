"""Read the Trading Terminal's configurable closed-M1 opening range."""
from datetime import timedelta
from pathlib import Path
import os
import tempfile

from plugins import _mt5, _orb

PLUGIN = {
    "name": "mt5_orb",
    "description": ("Read the same configurable closed-M1 opening range as Trading Terminal. "
                    "Requires MetaTrader 5 on Windows. Chart requests save a PNG and may open Trading Terminal; "
                    "it never places orders."),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "symbol": {
                "type": "STRING",
                "description": ("Broker symbol as the terminal spells it: EURUSD, "
                                "GBPUSD, XAUUSD. Some brokers add a suffix "
                                "(EURUSD.a, XAUUSDm) — if the first attempt says "
                                "the symbol is unknown, try the Market Watch name."),
            },
            "session": {"type": "STRING", "description": "Session: asia, london or new_york. Default london."},
            "draw": {
                "type": "BOOLEAN",
                "description": ("true (default) saves a PNG and requests the Trading Terminal chart; "
                                "false answers in words only, which is faster when "
                                "the user just wants the range and the breakout."),
            },
        },
        "required": ["symbol"],
    },
    # Drawing and reading a chart is a couple of seconds of local work, not a
    # network round trip; saying so lets the model keep talking.
    "behavior": "NON_BLOCKING",
    "scheduling": "WHEN_IDLE",
    "tier": "extra",
}


def _log(player, line):
    if player:
        try:
            player.write_log(line)
        except Exception:
            pass


def _save_snapshot_chart(snapshot, session):
    """Save a chart using only the same snapshot and levels as the answer."""
    item = snapshot["sessions"][session]
    settings = snapshot["settings"]
    analysis = _orb.Analysis(symbol=settings["symbol"], timeframe="M1", offset_hours=0)
    if item["high"] is not None and item["low"] is not None:
        analysis.range = _orb.Range(session=session, day=item["start"].date().isoformat(),
                                    high=item["high"], low=item["low"],
                                    bars=settings["range_minutes"], start=item["start"],
                                    end=item["range_end"] - timedelta(minutes=1))
    folder = Path.home() / "Desktop"
    if not folder.is_dir():
        folder = Path.home()
    fd, name = tempfile.mkstemp(prefix="jarvis_orb_", suffix=".png", dir=folder)
    os.close(fd)
    try:
        caption = (f"{session} state: {item['state']} | "
                   f"{'fresh' if snapshot['fresh'] else 'STALE'} | "
                   f"tick {snapshot['tick_time']:%Y-%m-%d %H:%M:%S} UTC")
        _orb.render_png(snapshot["bars"], analysis, name, caption=caption)
    except Exception:
        os.unlink(name)
        raise
    return name


def run(parameters: dict, player=None, session_memory=None) -> str:
    """Use exactly the same closed-M1 ORB and settings as Trading Terminal."""
    from memory.config_manager import get_plugin_config
    from plugins import _trading_terminal as terminal

    params = dict(parameters or {})
    session = str(params.get("session") or "london").strip().lower().replace(" ", "_")
    session = {"tokyo": "asia", "newyork": "new_york", "ny": "new_york", "us": "new_york"}.get(session, session)
    if session not in terminal.SESSIONS:
        return f"Unknown session {session!r}. Choose asia, london or new_york."
    if params.get("timeframe") and str(params["timeframe"]).upper() != "M1":
        return "ORB uses closed M1 candles, as in Trading Terminal; choose M1."
    if params.get("broker_utc_offset") is not None:
        return "ORB uses UTC timestamps and market time zones, not a broker UTC offset. Remove that parameter."
    if not params.get("symbol"):
        return "Sir, no symbol was given — which pair should I open?"
    settings = get_plugin_config("trading_terminal")
    if params.get("symbol"):
        settings["symbol"] = str(params["symbol"]).strip()
    try:
        snap = terminal.snapshot(settings)
        item = snap["sessions"][session]
        levels = (f"high {item['high']:.5f}, low {item['low']:.5f}"
                  if item['high'] is not None else "range unavailable")
        answer = (f"{snap['settings']['symbol']} {session} ORB: {item['state']}; {levels}. "
                  f"Range {item['start']:%Y-%m-%d %H:%M}–{item['range_end']:%H:%M} UTC "
                  f"({item['timezone']}), {snap['settings']['range_minutes']} minutes, closed M1. "
                  f"Tick {snap['tick_time']:%Y-%m-%d %H:%M:%S UTC}; "
                  f"{'fresh' if snap['fresh'] else 'STALE: no current signal'}. "
                  "Observations only; no order placed.")
        wants_chart = str(params.get("draw", True)).lower() not in ("no", "false", "0", "analysis", "text", "sentence")
        if wants_chart:
            try:
                path = _save_snapshot_chart(snap, session)
                answer += f" Chart saved to {path}."
            except Exception:
                answer += " PNG chart could not be saved; analysis remains available."
            # The terminal refreshes independently, using the same settings and algorithm.
            callback = getattr(player, "show_code_job", None) if player else None
            try:
                allowed = any(r.get("name") == "trading_terminal" and r.get("valid") and r.get("enabled")
                              for r in player.get_plugins()) if player else False
            except Exception:
                allowed = False
            if callable(callback) and allowed:
                callback({"kind": "trading_terminal", "symbol": snap['settings']['symbol'], "session": session})
                answer += " Requested the Trading Terminal chart; its data refreshes independently."
            else:
                answer += " Enable Trading Terminal and open it to view the chart."
        _log(player, f"JARVIS: {answer}")
        return answer
    except (ValueError, _mt5.MT5Unavailable) as exc:
        return f"Sir, I cannot read MetaTrader 5 here. {exc}"
