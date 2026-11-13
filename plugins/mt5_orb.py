"""mt5_orb — draw a MetaTrader 5 chart and read the market-session ORB on M30.

WHAT IT ANSWERS
    "Show me EURUSD" and "is there an opening-range breakout on gold" are the
    same job twice: pull the closed M30 bars from a running MetaTrader 5
    terminal, work out the session's opening range, and say whether a bar has
    CLOSED beyond it. `mt5_orb_chart` draws it as a PNG beside your Desktop and
    returns the file path; `mt5_orb_analysis` returns the sentence.

WHAT IT IS HONEST ABOUT
    * It cannot work off Windows. The `MetaTrader5` package ships Windows wheels
      only, so this plugin is offered on every platform and answers with the
      reason instead of vanishing — a tool that silently disappears is a bug
      report waiting to happen.
    * It needs the terminal running and logged in. There is no public MT5 data
      feed; the Python package is a bridge to the desktop terminal.
    * Bar times are the BROKER's, not UTC. Every answer repeats the offset it
      assumed (default GMT+2, which is what most FX brokers run), because two
      hours of error turns the London window into the Asian one.
    * It trades nothing. Reading a chart and sending an order are different
      kinds of decision, and this app's confirmation gate is built for the
      reversible ones.

WHY THE LOGIC IS NOT IN THIS FILE
    `plugins/_orb.py` holds the strategy and the renderer, `plugins/_mt5.py` the
    terminal bridge. Both are pure enough to test with injected bars, which is
    how this plugin was verified on a machine that cannot install MetaTrader5 at
    all. This file is only the tool surface: parameters in, sentence or path out.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from plugins import _mt5, _orb

# Enough for several sessions at M30 (48 bars a day) without asking the terminal
# for history it may not keep; "Max. bars in chart" caps this anyway.
BAR_COUNT = 400

PLUGIN = {
    "name": "mt5_orb",
    "description": (
        "Read a MetaTrader 5 chart and analyse the market-session opening range "
        "breakout (ORB) on M30. Leave draw=true when the user asks to SEE a pair "
        "('show me EURUSD', 'gambar chart gold') and it saves a PNG chart; set "
        "draw=false when they only ask whether a range broke, where the levels "
        "are, or what the session did. Requires the MetaTrader 5 terminal running "
        "and logged in on Windows; on any other operating system it explains why "
        "it cannot. Never use this for live prices or for placing an order."
    ),
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
            "session": {
                "type": "STRING",
                "description": ("Which session's opening range: london (07-11 UTC), "
                                "newyork (12-16 UTC) or tokyo (00-04 UTC). Default "
                                "london."),
            },
            "broker_utc_offset": {
                "type": "INTEGER",
                "description": ("The broker's server time zone as hours from UTC — 2 "
                                "for GMT+2, the usual FX default, 3 in summer for "
                                "many brokers. Bar timestamps arrive in this zone, so "
                                "guessing wrong shifts the session window."),
            },
            "timeframe": {
                "type": "STRING",
                "description": "Chart timeframe. Default M30 — the strategy is built for it.",
            },
            "draw": {
                "type": "BOOLEAN",
                "description": ("true (default) saves a PNG chart of the pair; "
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


def _settings(parameters: dict) -> tuple[str, str, str, int]:
    """(symbol, session, timeframe, offset) with the defaults filled in.

    The offset is read from the user's plugin settings when the model did not
    supply one, because a broker's time zone is a property of their account and
    should not be re-guessed on every call. The setting is a string in the
    settings UI, hence the int() with a fallback to the documented default.
    """
    symbol = str(parameters.get("symbol") or "").strip().upper()
    session = str(parameters.get("session") or "london").strip().lower()
    timeframe = str(parameters.get("timeframe") or "M30").strip().upper()
    raw = parameters.get("broker_utc_offset", _orb.DEFAULT_BROKER_UTC_OFFSET_H)
    try:
        offset = int(float(raw))
    except (TypeError, ValueError):
        offset = _orb.DEFAULT_BROKER_UTC_OFFSET_H
    return symbol, session, timeframe, offset


def _read(parameters: dict):
    """(bars, analysis, symbol) — raises MT5Unavailable or ValueError with a
    sentence the caller can speak as-is."""
    symbol, session, timeframe, offset = _settings(parameters)
    if not symbol:
        raise ValueError("no symbol was given — which pair should I open?")
    if timeframe not in _mt5.TIMEFRAMES:
        raise ValueError(
            f"there is no {timeframe} timeframe; I have "
            f"{', '.join(_mt5.TIMEFRAMES)}.")
    _orb.session_window(session)     # validate the name before touching MT5

    with _mt5.connect() as terminal:
        terminal.select(symbol)
        bars = terminal.bars(symbol, timeframe, BAR_COUNT, closed_only=True)
    analysis = _orb.analyse(bars, symbol, session, offset_hours=offset,
                            timeframe=timeframe)
    return bars, analysis, symbol


def _chart_path(symbol: str) -> Path:
    """Somewhere the user will find it. The Desktop is where this app already
    puts screenshots (actions/computer_control.py), so it is where a chart is
    looked for too; the home directory is the fallback when there is no Desktop
    (a fresh Windows profile, or a non-Windows machine)."""
    desktop = Path.home() / "Desktop"
    folder = desktop if desktop.is_dir() else Path.home()
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe = "".join(c for c in symbol if c.isalnum() or c in "-_") or "chart"
    return folder / f"mt5_{safe}_{stamp}.png"


def _log(player, line: str) -> None:
    if not player:
        return
    try:
        player.write_log(line)
    except Exception:
        pass      # a failed log line must not fail the chart the user asked for


def chart(parameters: dict, player=None) -> str:
    bars, analysis, symbol = _read(parameters)
    path = _chart_path(symbol)
    try:
        _orb.render_png(bars, analysis, path)
        drawn = f"Chart saved to {path}."
    except ImportError:
        # Pillow absent: still answer, in the transcript, rather than failing.
        return (_orb.summary(analysis) + "\n\n"
                + _orb.render_text(bars, analysis) + "\n\n"
                "Pillow is not installed, so this is a text chart instead of a PNG "
                "(pip install pillow for the picture).")
    _log(player, f"JARVIS: {drawn}")
    return (f"{drawn}\n\n{_orb.summary(analysis)}\n\n"
            f"{_orb.render_text(bars, analysis)}")


def analysis_only(parameters: dict, player=None) -> str:
    _bars, analysis, _symbol = _read(parameters)
    answer = _orb.summary(analysis)
    _log(player, f"JARVIS: {answer}")
    return answer


def run(parameters: dict, player=None, session_memory=None) -> str:
    """One tool, two jobs: `draw` decides. The tool declaration is a single
    `mt5_orb` entry because two entries with near-identical descriptions is how
    a model picks the wrong one; the description says which verb to use."""
    parameters = dict(parameters or {})
    wants_chart = str(parameters.pop("draw", "chart")).strip().lower()
    if wants_chart in ("no", "false", "0", "analysis", "text", "sentence"):
        job = analysis_only
    else:
        job = chart
    try:
        return job(parameters, player=player)
    except _mt5.MT5Unavailable as e:
        # Not a failure to hide: the user needs to know it is the machine, and
        # what to do about it.
        return f"Sir, I cannot read MetaTrader 5 here. {e}"
    except ValueError as e:
        # _read()'s messages are written to follow "Sir, " — the one raised by
        # _orb.session_window starts with "Unknown", so lower the first letter
        # rather than letting the sentence start twice.
        text = str(e)
        return f"Sir, {text[0].lower() + text[1:] if text else text}"
