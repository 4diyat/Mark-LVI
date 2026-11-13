"""currency_rates — convert between currencies at a real, dated rate.

WHY THIS IS IN THE REPOSITORY
    It is the example that proves the whole third-party chain end to end: a
    manifest beside the plugin, the loader checking the file against it, the
    declared permission reaching the toggle, and the consent question appearing
    before the plugin can make a request. A feature whose only users are
    hypothetical is a feature nobody has run.

    It is also a plugin somebody would actually install. "How much is 50 dollars
    in rupiah" is a thing people ask an assistant, and answering it from the
    model's memory produces a number that was right at some point in 2023.

WHY A PUBLIC API WITH NO KEY
    A plugin example that needs an API key is an example nobody can run. The
    Frankfurter API (frankfurter.dev) is the ECB's reference rates, needs no
    account, no key and no terms form — and it returns the DATE of the rate,
    which is the part that matters: an exchange rate without a date is a rumour.

WHAT IT DOES NOT DO
    * It does not guess a currency from a word. "50 dollars in rupiah" arrives
      as two ISO codes from the model, and anything it cannot parse it says so
      rather than converting to something plausible.
    * It does not cache. A rate cached for a day is a wrong answer with extra
      steps; the API is fast and this is called maybe twice a week.
    * It does not import `urllib.request` at module scope. The import scan reads
      `from urllib import request` (see core/plugin_manifest.py), and keeping the
      import inside `run()` means a failed request can never be a failed plugin
      import.
"""
from urllib import request as _urlrequest

TIMEOUT_S = 8

# The API is versioned by URL, and this is the one that answers without a key.
_ENDPOINT = "https://api.frankfurter.dev/v1/latest?base={base}&symbols={symbols}"

# Spoken names people actually use, mapped to ISO 4217. The model is asked to
# send codes, but it will send "dollars" often enough that guessing the common
# ones is worth four lines — and only the common ones, because a wrong guess
# about "peso" is worse than asking.
_ALIASES = {
    "dollar": "USD", "dollars": "USD", "usd": "USD", "buck": "USD",
    "euro": "EUR", "euros": "EUR", "eur": "EUR",
    "pound": "GBP", "pounds": "GBP", "gbp": "GBP", "sterling": "GBP",
    "rupiah": "IDR", "idr": "IDR", "perak": "IDR",
    "yen": "JPY", "jpy": "JPY",
    "rupee": "INR", "rupees": "INR", "inr": "INR",
    "ringgit": "MYR", "myr": "MYR",
    "singapore dollar": "SGD", "sgd": "SGD",
    "franc": "CHF", "chf": "CHF",
    "yuan": "CNY", "rmb": "CNY", "cny": "CNY",
    "won": "KRW", "krw": "KRW",
    "baht": "THB", "thb": "THB",
    "real": "BRL", "brl": "BRL",
    "rand": "ZAR", "zar": "ZAR",
    "australian dollar": "AUD", "aud": "AUD",
    "canadian dollar": "CAD", "cad": "CAD",
}

PLUGIN = {
    "name": "currency_rates",
    "description": (
        "Convert an amount of money between two currencies at the European "
        "Central Bank's reference rate, and say the date the rate is from. Use "
        "this whenever the user asks what something costs in another currency "
        "or how much an amount is worth elsewhere — never answer an exchange "
        "rate from memory, because it will be stale. Two ISO codes: USD, EUR, "
        "IDR, GBP, JPY, SGD and so on."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "amount": {"type": "NUMBER",
                       "description": "How much to convert, in the source currency."},
            "from_currency": {"type": "STRING",
                              "description": "Source currency, e.g. USD."},
            "to_currency": {"type": "STRING",
                            "description": "Currency to convert into, e.g. IDR."},
        },
        "required": ["amount", "from_currency", "to_currency"],
    },
}


def _code(value) -> str:
    """ISO code from whatever the model sent. Empty string when unknown."""
    text = str(value or "").strip().lower()
    if not text:
        return ""
    if text in _ALIASES:
        return _ALIASES[text]
    if len(text) == 3 and text.isalpha():
        return text.upper()
    # "US dollars", "euros." — the last word is usually the noun.
    word = text.replace(".", "").split()[-1] if text.split() else ""
    return _ALIASES.get(word, "")


def _fetch_rate(base: str, quote: str) -> tuple[float, str]:
    """(rate, date). Raises on anything unexpected — run() turns it into a
    sentence, because this is where the network lives."""
    import json as _json
    url = _ENDPOINT.format(base=base, symbols=quote)
    with _urlrequest.urlopen(url, timeout=TIMEOUT_S) as response:   # noqa: S310
        payload = _json.loads(response.read().decode("utf-8"))
    rates = payload.get("rates") or {}
    if quote not in rates:
        raise LookupError(f"no rate for {quote}")
    return float(rates[quote]), str(payload.get("date") or "")


def _say(amount: float, base: str, quote: str, rate: float, date: str) -> str:
    """The sentence that is spoken. A rounded conversion plus the rate and the
    date, because those are the two things that let the user judge it."""
    converted = amount * rate
    # Two decimals for anything of a size where cents exist, none for the
    # currencies where they do not (IDR, JPY, KRW) — "Rp 812.345,67" is 1984,
    # not precision.
    whole = quote in ("IDR", "JPY", "KRW", "VND", "CLP")
    shown = f"{converted:,.0f}" if whole else f"{converted:,.2f}"
    when = f" on {date}" if date else ""
    return (f"{amount:,.2f} {base} is {shown} {quote} "
            f"at {rate:,.6g}{when}.")


def run(parameters: dict, player=None, session_memory=None) -> str:
    amount_raw = parameters.get("amount", 0)
    try:
        amount = float(amount_raw)
    except (TypeError, ValueError):
        return f"Sir, I could not read {amount_raw!r} as an amount."

    base = _code(parameters.get("from_currency"))
    quote = _code(parameters.get("to_currency"))
    if not base or not quote:
        return ("Sir, tell me both currencies as three-letter codes — "
                f"I could not read {parameters.get('from_currency')!r} to "
                f"{parameters.get('to_currency')!r}.")
    if base == quote:
        return f"That is already {base}, sir."
    if amount < 0:
        return "Sir, a negative amount is not something I can convert."

    try:
        rate, date = _fetch_rate(base, quote)
    except LookupError:
        # The API knows its own currency list; an unknown code is a user error,
        # not a network failure, and saying which is which matters.
        return (f"Sir, {base} to {quote} is not a pair the reference rates "
                "carry — check the currency codes.")
    except Exception as e:
        # No silent fallback to a remembered rate. A number from memory is
        # exactly the failure this plugin exists to avoid.
        return (f"Sir, I could not reach the exchange-rate service ({e}). "
                "I would rather tell you that than guess a rate.")

    answer = _say(amount, base, quote, rate, date)
    if player:
        try:
            player.write_log(f"JARVIS: {answer}")
        except Exception:
            pass          # a failed log line must not fail the conversion
    return answer
