"""Market data from Yahoo's chart endpoint — and the four places it can mislead.

WHY THIS ENDPOINT
    `query1.finance.yahoo.com/v8/finance/chart/<symbol>` needs no key, no
    account and no crumb/cookie dance, and it returns the current price in the
    same JSON as the history. The obvious-looking `/v7/finance/quote` has
    required a minted crumb since 2024, so it is not used here even once — a
    "free" API that needs an auth handshake is how a plugin ends up broken three
    months after it was written.

    What that buys: Jakarta (`.JK`), US (`AAPL`), crypto (`BTC-USD`), forex
    (`EURUSD=X`), indices (`^JKSE`) and futures (`GC=F`) all come from the same
    schema.

THE FOUR TRAPS, EACH ONE HANDLED AND EACH ONE SAID OUT LOUD IN THE ANSWER
    1. IT IS DELAYED. Most exchanges arrive 15 minutes late; crypto is closer to
       live. A price that looks current and is a quarter of an hour old is
       exactly what somebody would trade on, so every answer says so.
    2. THE SYMBOL IS A GUESS. The user says "BBCA", "bitcoin", "EURUSD", "emas"
       — none of which is a Yahoo symbol. Resolution is a stated order of
       candidates (BBCA → BBCA.JK → BBCA), and the answer prints the symbol
       that actually answered, so a wrong guess is visible in one line instead
       of being a number from a different company.
    3. THE CHANGE IS NOT ONE NUMBER. `regularMarketPrice` against
       `chartPreviousClose` is the day's move; against a bar three weeks ago it
       is a period return. The two are computed separately and labelled.
    4. A NULL CLOSE IS NORMAL. Holidays and halted stocks come back as `null`
       inside an otherwise valid array. Treating `None` as 0 turns a gap into a
       99 % crash, so nulls are dropped, never coerced.

WHAT THIS IS NOT
    Not a trading feed and not advice. No prediction, no "buy", no target price:
    the module reports what the last print was and when, and the sentence says
    which delay applies.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from urllib import request as _urlrequest

TIMEOUT_S = 8
ENDPOINT = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"

# Yahoo answers 429 to the default urllib agent often enough that a browser
# string is not optional.
_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

# Ranges Yahoo accepts, and the interval that makes sense for each. `1d` is the
# quote case: one bar, and `chartPreviousClose` is yesterday's close.
RANGES = {
    "1d": "5m",
    "5d": "15m",
    "1mo": "1d",
    "3mo": "1d",
    "6mo": "1d",
    "1y": "1wk",
    "5y": "1mo",
}

# Spoken names → symbols. Short on purpose: an alias that is wrong is worse than
# no alias, because it answers with a real price for the wrong instrument.
ALIASES = {
    "ihsg": "^JKSE", "jkse": "^JKSE", "indeks harga saham gabungan": "^JKSE",
    "s&p": "^GSPC", "s&p 500": "^GSPC", "sp500": "^GSPC", "spx": "^GSPC",
    "nasdaq": "^IXIC", "dow": "^DJI", "dow jones": "^DJI", "djia": "^DJI",
    "nikkei": "^N225", "hang seng": "^HSI", "hangseng": "^HSI",
    "emis": "^N225",
    "gold": "GC=F", "emas": "GC=F", "silver": "SI=F", "perak": "SI=F",
    "oil": "CL=F", "minyak": "CL=F", "brent": "BZ=F",
    "bitcoin": "BTC-USD", "btc": "BTC-USD",
    "ethereum": "ETH-USD", "eth": "ETH-USD",
    "solana": "SOL-USD", "sol": "SOL-USD",
    "dogecoin": "DOGE-USD", "doge": "DOGE-USD",
    "ripple": "XRP-USD", "xrp": "XRP-USD",
    "cardano": "ADA-USD", "ada": "ADA-USD",
    "binance coin": "BNB-USD", "bnb": "BNB-USD",
    "usd": "USD", "dollar": "USD", "rupiah": "IDR",
}

CURRENCY_CODES = {
    "USD", "EUR", "GBP", "JPY", "CHF", "AUD", "NZD", "CAD", "CNY", "HKD",
    "SGD", "IDR", "KRW", "INR", "THB", "MYR", "SEK", "NOK", "MXN", "ZAR",
    "BRL", "TRY", "RUB", "PLN", "DKK", "PHP", "TWD", "SAR", "AED",
}

# A bare four-letter code is an Indonesian listing far more often than it is a
# US one on a machine in Jakarta. The order below is what makes that a stated
# guess (`.JK` is tried first, the answer names whichever answered) rather than
# a silent one.
_IDX_LENGTH = 4


class MarketError(RuntimeError):
    """A sentence for a person: the symbol is wrong, the network is not there,
    or the reply was not the shape this module understands."""


class SymbolNotFound(MarketError):
    """Yahoo knows the request and has no such instrument."""


@dataclass
class Quote:
    symbol: str                 # the Yahoo symbol that answered
    asked: str                  # what the user's words resolved to before the fallback
    input: str = ""             # what the user actually typed
    name: str = ""
    price: float | None = None
    previous_close: float | None = None
    currency: str = ""
    exchange: str = ""
    market_time: datetime | None = None
    closes: list[float] = field(default_factory=list)
    timestamps: list[datetime] = field(default_factory=list)

    @property
    def change(self) -> float | None:
        if self.price is None or not self.previous_close:
            return None
        return self.price - self.previous_close

    @property
    def change_percent(self) -> float | None:
        if self.price is None or not self.previous_close:
            return None
        return (self.price - self.previous_close) / self.previous_close * 100.0


def _slug(text: str) -> str:
    return " ".join(str(text or "").strip().lower().replace("_", " ").split())


# Yahoo has no bare "USD" ticker. A currency on its own is quoted against the
# dollar (or, for the dollar itself, as the index that measures it).
_DOLLAR_INDEX = "DX-Y.NYB"
_CRYPTO = {"BTC", "ETH", "SOL", "XRP", "ADA", "DOGE", "BNB", "USDT"}


def _for_code(code: str) -> list[str]:
    code = code.strip().upper()
    if code == "USD":
        return [_DOLLAR_INDEX]
    return [f"{code}USD=X"]


def candidates(symbol: str, market: str = "auto") -> list[str]:
    """The symbols to try, in order. The first one that answers is reported.

    Nothing here reaches the network, which is what makes it testable; the
    decision table is the entire "which instrument did they mean" question.
    """
    raw = str(symbol or "").strip()
    if not raw:
        raise ValueError("no symbol was given — which stock, coin or pair?")
    key = _slug(raw)
    if key in ALIASES:
        target = ALIASES[key]
        # "rupiah" and "dollar" resolve to CODES, which still need the pair rule
        # below — returning ["IDR"] would ask Yahoo for a ticker that does not
        # exist and call the user's question unanswerable.
        return _for_code(target) if target in CURRENCY_CODES else [target]

    # "btc usd", "eur/usd", "eur-usd" — a pair with a separator.
    for sep in ("/", "-", " "):
        if sep in key:
            left, _, right = key.partition(sep)
            pair = (left.strip().upper(), right.strip().upper())
            if all(code in CURRENCY_CODES for code in pair):
                # A crypto pair keeps Yahoo's dash; a currency pair needs '=X'.
                if pair[0] in _CRYPTO or pair[1] in _CRYPTO:
                    return [f"{pair[0]}-{pair[1]}"]
                return [f"{pair[0]}{pair[1]}=X"]

    upper = raw.upper().replace(" ", "")
    if upper.startswith("^") or upper.endswith(("=X", "=F", "-USD", ".JK")):
        return [upper]
    if upper in CURRENCY_CODES:
        return _for_code(upper)

    market = _slug(market)
    if market in ("crypto", "koin", "kripto"):
        return [f"{upper}-USD"]
    if market in ("forex", "fx", "valas", "kurs"):
        # "EURUSD" and "EUR" both land here; a bare code pairs with the dollar.
        # Deduped because EURUSD would otherwise produce "EURUSD=X" twice.
        return list(dict.fromkeys([f"{upper}=X", f"{upper}USD=X"]
                                  if len(upper) == 3 else [f"{upper}=X"]))
    if market in ("idx", "saham", "saham indonesia", "indonesia", "id"):
        return [f"{upper}.JK"]
    if len(upper) == _IDX_LENGTH and upper.isalpha():
        return [f"{upper}.JK", upper]
    return [upper]


def _get(url: str) -> dict:
    """One HTTP GET. Kept tiny so the tests can replace exactly this."""
    req = _urlrequest.Request(url, headers={"User-Agent": _UA,
                                           "Accept": "application/json"})
    with _urlrequest.urlopen(req, timeout=TIMEOUT_S) as response:   # noqa: S310
        return json.loads(response.read().decode("utf-8", "replace"))


def _parse(payload: dict, asked: str, typed: str = "") -> Quote:
    """The chart JSON → a Quote, or MarketError with Yahoo's own reason."""
    chart = payload.get("chart") or {}
    error = chart.get("error")
    if error:
        description = str(error.get("description") or error.get("code") or error)
        raise SymbolNotFound(description)
    results = chart.get("result") or []
    if not results:
        raise SymbolNotFound("the data source returned no rows")
    result = results[0]
    meta = result.get("meta") or {}
    price = meta.get("regularMarketPrice")
    if price is None:
        # Some listings only carry the last close inside the bars.
        closes = _closes(result)
        price = closes[-1] if closes else None
    if price is None:
        raise SymbolNotFound("no price in the reply")

    quote = Quote(
        symbol=str(meta.get("symbol") or asked),
        asked=asked,
        input=typed,
        name=str(meta.get("shortName") or meta.get("longName") or ""),
        price=float(price),
        previous_close=_as_float(meta.get("chartPreviousClose")
                                 or meta.get("previousClose")),
        currency=str(meta.get("currency") or ""),
        exchange=str(meta.get("fullExchangeName") or meta.get("exchangeName") or ""),
        market_time=_as_time(meta.get("regularMarketTime")),
    )
    # zip() stops at the shorter array — so a reply with four closes and three
    # stamps would silently drop today's price, which is the one number anybody
    # is looking at. The pairing is explicit, and the last close is taken from
    # the full array when the two lengths disagree.
    closes = _closes(result)
    stamps = result.get("timestamp") or []
    if closes and (not stamps or len(closes) != len(stamps)):
        keep = [(None, close) for close in closes if close is not None]
    else:
        keep = [(stamp, close) for stamp, close in zip(stamps, closes)
                if close is not None]
    quote.closes = [close for _t, close in keep]
    quote.timestamps = [_as_time(t) for t, _c in keep if _as_time(t) is not None]
    return quote


def _closes(result: dict) -> list[float | None]:
    indicators = result.get("indicators") or {}
    quotes = indicators.get("quote") or [{}]
    return list(quotes[0].get("close") or [])


def _as_float(value) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _as_time(value) -> datetime | None:
    try:
        return datetime.fromtimestamp(int(value), tz=timezone.utc)
    except (TypeError, ValueError, OSError):
        return None


def fetch(symbol: str, range_: str = "1d", market: str = "auto") -> Quote:
    """Quote (and bars) for one symbol, trying the candidate list in order.

    A `.JK` guess that fails falls through to the bare ticker, and the answer
    carries the symbol that actually answered — so the fallback is visible
    rather than silent.
    """
    range_ = str(range_ or "1d").strip().lower()
    if range_ not in RANGES:
        raise ValueError(
            f"I do not have {range_!r}; I can do {', '.join(RANGES)}.")
    errors: list[str] = []
    for candidate in candidates(symbol, market):
        url = (ENDPOINT.format(symbol=candidate)
               + f"?range={range_}&interval={RANGES[range_]}&includePrePost=false")
        try:
            return _parse(_get(url), candidate, str(symbol).strip())
        except SymbolNotFound as e:
            errors.append(f"{candidate}: {e}")
    raise SymbolNotFound(
        f"no data for {symbol!r} — tried {' and '.join(errors)}. Broker and "
        "exchange spellings differ: BBCA on Jakarta is BBCA.JK, the US listing "
        "is just AAPL, crypto is BTC-USD, a currency pair is EURUSD=X.")


def _money(value: float, currency: str) -> str:
    """A price a person reads. Rupiah has no cents worth printing and six
    decimals are how crypto is quoted; everything else is two."""
    code = (currency or "").upper()
    if code == "IDR":
        return f"{value:,.0f} IDR"
    if value < 1:
        return f"{value:,.6f} {code}".strip()
    return f"{value:,.2f} {code}".strip()


def describe(quote: Quote, *, range_: str = "1d") -> str:
    """The sentence: what it is worth, how it moved, and the two things that make
    the number usable — which exchange it is, and how old it is.

    Written as sentences rather than joined fragments: this is read aloud, and
    "is 9,850 IDR. up 130.00. on Jakarta." is what a list of parts sounds like.
    """
    if quote.price is None:
        return f"No price came back for {quote.symbol}."
    label = f"{quote.name} ({quote.symbol})" if quote.name else quote.symbol
    where = f" on {quote.exchange}" if quote.exchange else ""
    said = f"{label} is {_money(quote.price, quote.currency)}{where}"

    change, percent = quote.change, quote.change_percent
    if change is not None and percent is not None:
        direction = "up" if change > 0 else "down" if change < 0 else "unchanged,"
        if direction == "unchanged,":
            said += ", unchanged on the session"
        else:
            said += f", {direction} {abs(change):,.2f} ({percent:+.2f}%) on the session"
    elif range_ != "1d" and quote.closes and quote.closes[0]:
        said += f", {(quote.price - quote.closes[0]) / quote.closes[0] * 100.0:+.2f}% over {range_}"
    said += "."

    when = (f"Last print {quote.market_time:%Y-%m-%d %H:%M} UTC"
            if quote.market_time else "Print time unknown")
    said += (f" {when}; Yahoo data is typically delayed up to 15 minutes, "
             "so this is not a live tick.")

    typed = (quote.input or "").strip().upper().replace(" ", "")
    if typed and typed != quote.symbol.upper().replace(" ", ""):
        said += f" Yahoo symbol used: {quote.symbol}."
    return said


def sparkline(values: list[float], width: int = 40) -> str:
    """Ten levels of block, so a month of closes fits in a transcript."""
    blocks = "▁▂▃▄▅▆▇█"
    rows = [v for v in values if v is not None]
    if len(rows) < 2:
        return ""
    if len(rows) > width:
        # Even spacing across the whole range, always including the last bar —
        # a chart that silently stops two weeks early is worse than none.
        step = (len(rows) - 1) / (width - 1)
        rows = [rows[round(i * step)] for i in range(width)]
    low, high = min(rows), max(rows)
    span = (high - low) or 1.0
    return "".join(blocks[int((v - low) / span * (len(blocks) - 1))] for v in rows)


def history_summary(quote: Quote, range_: str) -> str:
    """Period return, the extremes, and the shape. No forecast."""
    rows = quote.closes
    if len(rows) < 2:
        return "Not enough bars came back to summarise that period."
    first, last = rows[0], rows[-1]
    low, high = min(rows), max(rows)
    percent = (last - first) / first * 100.0 if first else 0.0
    direction = "up" if percent > 0 else "down" if percent < 0 else "flat"
    return (f"{quote.symbol} over {range_}: {percent:+.2f}% ({direction}), "
            f"{len(rows)} bars, low {_money(low, quote.currency)}, "
            f"high {_money(high, quote.currency)}. "
            f"{sparkline(rows)}")
