"""market_price — what a stock, coin or pair is worth right now, and where that
number came from.

WHY THIS PLUGIN
    "Berapa harga BBCA?" and "how much is bitcoin" are questions where a model's
    memory is not merely stale, it is confidently wrong — a price from training
    data is a number from an unknown date presented as today's. The rule here is
    the same one `currency_rates` follows: fetch it, date it, or say why not.

WHAT IT COVERS, FROM ONE ENDPOINT
    Jakarta (BBCA → BBCA.JK), US (AAPL), crypto (BTC-USD), forex (EURUSD=X),
    indices (^JKSE) and futures (GC=F) are all the same schema on Yahoo's v8
    chart endpoint, which needs no key. The `_market.py` helper holds the
    resolution table, the parser and the reasons each of those is subtler than
    it looks.

WHAT IT REFUSES TO DO
    * No forecast, no target price, no "should I buy". It reports the last print
      and the period return; the decision is not this app's.
    * It never substitutes a remembered price when the fetch fails. "About
      1,000" for a stock that is at 9,850 is the failure this exists to prevent,
      and it has no error message.
    * It does not pretend to be live: every answer says the data is typically
      delayed up to fifteen minutes.
"""
from __future__ import annotations

from plugins import _market

PLUGIN = {
    "name": "market_price",
    "description": (
        "Look up the current price of a stock, cryptocurrency, currency pair, "
        "index or commodity from Yahoo Finance, with the day's change and, on "
        "request, a period summary. Use for 'harga BBCA', 'berapa bitcoin', "
        "'EURUSD sekarang', 'how is gold doing'. Symbols: Jakarta listings are "
        "BBCA.JK (a bare four-letter code is tried as .JK first), crypto is "
        "BTC-USD, a pair is EURUSD=X, gold is GC=F. Never answer a price from "
        "memory. Data is delayed up to 15 minutes — say so, and never use this "
        "for order execution."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "symbol": {
                "type": "STRING",
                "description": ("Ticker or spoken name: BBCA, AAPL, BTC, bitcoin, "
                                "EURUSD, gold, IHSG."),
            },
            "kind": {
                "type": "STRING",
                "description": ("Optional hint when the ticker is ambiguous: "
                                "saham/stock, crypto, forex/fx, idx, or auto "
                                "(default)."),
            },
            "range": {
                "type": "STRING",
                "description": ("1d (default, the current quote), 5d, 1mo, 3mo, "
                                "6mo, 1y or 5y. Anything but 1d adds a period "
                                "summary and a sparkline."),
            },
        },
        "required": ["symbol"],
    },
    # A network round trip; the assistant keeps talking while it lands.
    "behavior": "NON_BLOCKING",
    "scheduling": "WHEN_IDLE",
    "tier": "core",
}


# A held instrument moves a fraction of a percent, or one percent on a bad day.
# Ten percent in a single session is an index, a leveraged product, or a wrong
# symbol — and printing it as "tomorrow's move" is how a user trades on the
# wrong company. The sentence says so instead.
LARGE_MOVE_PERCENT = 10.0


def _warn_if_extreme(quote) -> str:
    percent = quote.change_percent
    if percent is None or abs(percent) < LARGE_MOVE_PERCENT:
        return ""
    return (f" That is a {percent:+.0f}% session move — large enough that it is "
            "worth checking the symbol answered the instrument you meant.")


def _kind(parameters: dict) -> str:
    """`kind` and `market` are the same idea; accept whichever the model sent."""
    return str(parameters.get("kind") or parameters.get("market") or "auto")


def run(parameters: dict, player=None, session_memory=None) -> str:
    parameters = parameters or {}
    symbol = parameters.get("symbol", "")
    range_ = str(parameters.get("range") or "1d").strip().lower()
    try:
        quote = _market.fetch(symbol, range_, _kind(parameters))
    except ValueError as e:
        # A bad range or an empty symbol: the user's question, not the network.
        message = str(e)
        return f"Sir, {message[0].lower() + message[1:] if message else message}"
    except _market.MarketError as e:
        # No remembered fallback on purpose — see the module docstring.
        return (f"Sir, I could not get a price for {symbol!r} ({e}). "
                "I would rather tell you that than quote a number from memory.")
    except Exception as e:      # noqa: BLE001 — the network has many ways to fail
        return (f"Sir, I could not get a price for {symbol!r} ({e}) — the "
                "connection to the market data source failed. I would rather "
                "tell you that than quote a number from memory.")

    answer = _market.describe(quote, range_=range_) + _warn_if_extreme(quote)
    if range_ != "1d" and quote.closes:
        answer += " " + _market.history_summary(quote, range_)
    if player:
        try:
            player.write_log(f"JARVIS: {answer}")
        except Exception:
            pass          # a failed log line must not fail the price
    return answer
