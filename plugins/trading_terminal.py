"""Open the read-only MetaTrader 5 session-ORB chart workspace."""
PLUGIN = {
    "name": "trading_terminal",
    "description": ("Open a read-only MetaTrader 5 trading terminal with live bid/ask, M1 chart, "
                    "and configurable Asia, London and New York opening-range breakouts. "
                    "Signals only; never places, changes, or closes orders. Requires a "
                    "running logged-in MT5 terminal and the Windows MetaTrader5 package."),
    "parameters": {"type": "OBJECT", "properties": {
        "symbol": {"type": "STRING", "description": "Optional exact broker Market Watch symbol, e.g. EURUSD or XAUUSDm."},
    }, "required": []},
    "behavior": "NON_BLOCKING", "scheduling": "WHEN_IDLE", "tier": "extra",
}

PLUGIN_SETTINGS = {
    "namespace": "trading_terminal", "title": "MT5 Trading Terminal — ORB",
    "fields": [
        {"key": "symbol", "label": "Broker symbol", "type": "text", "default": "EURUSD"},
        {"key": "asia_start", "label": "Asia start (Asia/Tokyo local HH:MM)", "type": "text", "default": "09:00"},
        {"key": "london_start", "label": "London start (Europe/London local HH:MM)", "type": "text", "default": "08:00"},
        {"key": "new_york_start", "label": "New York start (America/New_York local HH:MM)", "type": "text", "default": "09:30"},
        {"key": "range_minutes", "label": "Opening range minutes (1–120)", "type": "text", "default": "15"},
    ],
}


def run(parameters: dict, player=None, session_memory=None) -> str:
    if player is None or not callable(getattr(player, "show_code_job", None)):
        return "The MT5 trading terminal needs the desktop interface."
    symbol = str((parameters or {}).get("symbol") or "").strip()
    if len(symbol) > 80 or any(ord(c) < 32 for c in symbol):
        return "Please provide a valid Market Watch symbol."
    try:
        player.show_code_job({"kind": "trading_terminal", "symbol": symbol})
        return "Opening the read-only MT5 terminal. It displays signals only and does not place orders."
    except Exception as exc:
        return f"Could not open the MT5 terminal: {exc}"
