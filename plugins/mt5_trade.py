"""Open an explicitly approved MT5 order dialog; never submit from plugin code."""
PLUGIN = {
    "name": "mt5_trade",
    "description": ("Open a desktop order draft for a market buy/sell or pending-order modification. "
                    "The person must choose DEMO/LIVE and approve the reviewed order in the desktop UI. "
                    "Never claim an order was placed just because the draft opened. No automatic orders."),
    "parameters": {"type": "OBJECT", "properties": {
        "kind": {"type": "STRING", "description": "market or modify_pending"},
        "symbol": {"type": "STRING", "description": "Exact broker symbol for a market order"},
        "side": {"type": "STRING", "description": "buy or sell for a market order"},
        "volume": {"type": "NUMBER", "description": "Lots for a market order"},
        "ticket": {"type": "INTEGER", "description": "Existing pending-order ticket to modify"},
        "price": {"type": "NUMBER", "description": "New pending-order price"},
        "sl": {"type": "NUMBER", "description": "Required stop-loss price"},
        "tp": {"type": "NUMBER", "description": "Optional take-profit price; zero means none"},
    }, "required": ["kind"]},
    "behavior": "NON_BLOCKING", "scheduling": "WHEN_IDLE", "tier": "extra",
}


def run(parameters: dict, player=None, session_memory=None) -> str:
    if player is None or not callable(getattr(player, "show_code_job", None)):
        return "The MT5 order draft requires the desktop interface; no order was sent."
    draft = dict(parameters or {})
    kind = draft.get("kind")
    if kind not in ("market", "modify_pending"):
        return "Choose a market order or modification of an existing pending order; no order was sent."
    allowed = {key: draft[key] for key in ("kind", "symbol", "side", "volume", "ticket", "price", "sl", "tp") if key in draft}
    try:
        player.show_code_job({"kind": "mt5_trade", "draft": allowed})
        return "Opening an order draft for your review. Trading is off by default; no order has been sent."
    except Exception as exc:
        return f"Could not open the order draft: {exc}. No order was sent."
