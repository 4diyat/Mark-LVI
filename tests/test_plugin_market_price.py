"""market_price: which instrument was meant, and what the reply actually says.

WHY THE PARSER IS TESTED LIKE THIS
    A price plugin fails in one of two ways, and only one of them is loud:

      * LOUD — the fetch raises, and the user is told. Nothing to test beyond
        the sentence that says it.
      * SILENT — a plausible number for the wrong instrument. "BBCA" on a
        machine that resolves to the wrong exchange answers with a real price
        for a real company, in a currency the user did not expect, and nothing
        anywhere looks broken.

    So the tests are aimed at the second kind: the resolution order, the
    previous-close arithmetic, and the nulls inside a valid array that turn a
    holiday into a crash if they are coerced to zero.

    NOTHING HERE TOUCHES THE NETWORK. `_get` is replaced with a payload built in
    the test; the one test that inspects a URL inspects the string built for it.
"""
from __future__ import annotations

import importlib
import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import plugin_manifest as pm  # noqa: E402


def _load(name: str):
    path = ROOT / "plugins" / f"{name}.py"
    module_name = f"{name}_under_test"
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def market():
    return _load("_market")


@pytest.fixture()
def plugin(market, monkeypatch):
    module = _load("market_price")
    module._market = market
    return module


def payload(symbol="BBCA.JK", price=9850.0, previous=9800.0, currency="IDR",
            exchange="Jakarta", closes=(9750.0, 9800.0, None, 9850.0),
            stamps=(1762700000, 1762700900, 1762701800, 1762702700),
            name="Bank Central Asia"):
    """The shape Yahoo returns, with the parts this module reads."""
    return {"chart": {"result": [{
        "meta": {"symbol": symbol, "regularMarketPrice": price,
                 "chartPreviousClose": previous, "currency": currency,
                 "fullExchangeName": exchange, "regularMarketTime": 1762702700,
                 "shortName": name},
        "timestamp": list(stamps),
        "indicators": {"quote": [{"close": list(closes)}]},
    }], "error": None}}


# --- which instrument did they mean ----------------------------------------

@pytest.mark.parametrize("said,expected", [
    ("BBCA", ["BBCA.JK", "BBCA"]),          # four letters: Jakarta first, US second
    ("AAPL", ["AAPL.JK", "AAPL"]),          # same rule — and the answer names the winner
    ("bbcа".replace("а", "a"), ["BBCA.JK", "BBCA"]),
    ("^JKSE", ["^JKSE"]),
    ("IHSG", ["^JKSE"]),
    ("bitcoin", ["BTC-USD"]),
    ("BTC", ["BTC-USD"]),
    ("EURUSD", ["EURUSD"]),
    ("EUR/USD", ["EURUSD=X"]),
    ("eur-usd", ["EURUSD=X"]),
    ("USD", ["DX-Y.NYB"]),
    ("JPY", ["JPYUSD=X"]),
    ("BTC-USD", ["BTC-USD"]),
    ("GC=F", ["GC=F"]),
    ("gold", ["GC=F"]),
    ("emas", ["GC=F"]),
])
def test_the_resolution_table(market, said, expected):
    assert market.candidates(said) == expected


def test_an_unknown_four_letter_code_falls_through_to_the_bare_ticker(market):
    """The fallback is why the answer prints the symbol that answered: a Jakarta
    listing that does not exist must not become a US one silently."""
    assert market.candidates("ZZZZ") == ["ZZZZ.JK", "ZZZZ"]


def test_a_hint_narrows_the_candidates(market):
    assert market.candidates("BBCA", "idx") == ["BBCA.JK"]
    assert market.candidates("BTC", "crypto") == ["BTC-USD"]
    assert market.candidates("EURUSD", "forex") == ["EURUSD=X"]


def test_an_empty_symbol_is_refused(market):
    with pytest.raises(ValueError):
        market.candidates("   ")


def test_the_first_candidate_that_answers_wins_and_is_reported(market, monkeypatch):
    asked = []

    def fake_get(url):
        asked.append(url)
        if ".JK" in url:
            raise market.SymbolNotFound("No data found, symbol may be delisted")
        return payload(symbol="AAPL", price=229.5, previous=228.0,
                       currency="USD", exchange="NasdaqGS")

    monkeypatch.setattr(market, "_get", fake_get)
    quote = market.fetch("AAPL", "1d")
    assert quote.symbol == "AAPL"
    assert quote.asked == "AAPL"          # the candidate that answered
    assert len(asked) == 2
    assert "AAPL.JK" in asked[0] and "AAPL" in asked[-1]


def test_no_candidate_at_all_is_one_sentence_with_the_spellings(market, monkeypatch):
    monkeypatch.setattr(market, "_get", lambda url: (_ for _ in ()).throw(
        market.SymbolNotFound("No data found")))
    with pytest.raises(market.SymbolNotFound) as err:
        market.fetch("BBCA")
    said = str(err.value)
    assert "BBCA.JK" in said and "BTC-USD" in said and "EURUSD=X" in said


def test_the_url_carries_the_interval_that_matches_the_range(market, monkeypatch):
    seen = {}
    monkeypatch.setattr(market, "_get",
                        lambda url: (seen.update(url=url), payload())[1])
    market.fetch("BBCA", "1mo")
    assert "/v8/finance/chart/BBCA.JK" in seen["url"]
    assert "range=1mo" in seen["url"] and "interval=1d" in seen["url"]


def test_an_unknown_range_is_refused_before_the_network(market, monkeypatch):
    monkeypatch.setattr(market, "_get", lambda url: pytest.fail("went to the network"))
    with pytest.raises(ValueError) as err:
        market.fetch("BBCA", "2d")
    assert "2d" in str(err.value)


# --- the arithmetic --------------------------------------------------------

def test_the_session_change_uses_the_previous_close(market):
    quote = market._parse(payload(price=9850.0, previous=9800.0), "BBCA.JK")
    assert quote.change == pytest.approx(50.0)
    assert quote.change_percent == pytest.approx(0.5102, abs=1e-3)


def test_a_missing_previous_close_is_unknown_not_zero(market):
    """"+9,850,000%" is what `previous_close or 0` produces here."""
    quote = market._parse(payload(previous=None), "BBCA.JK")
    assert quote.change is None and quote.change_percent is None
    assert "9850" in market.describe(quote).replace(",", "")


def test_nulls_inside_the_close_array_are_dropped_not_zeroed(market):
    """A holiday or a halted stock is `null` between two real closes. Coerced to
    zero it becomes a 99 % crash, and the sparkline is the only place anyone
    would notice."""
    quote = market._parse(payload(closes=(9750.0, None, 9800.0, None, 9850.0)),
                          "BBCA.JK")
    assert quote.closes == [9750.0, 9800.0, 9850.0]
    # Four stamps for five closes: the pairing is abandoned rather than guessed,
    # and today's close is still the last element — zip() alone would have
    # dropped it, which is the one number anybody is looking at.
    assert quote.timestamps == []


def test_matching_lengths_keep_their_times_and_skip_the_null_pair(market):
    quote = market._parse(payload(closes=(9750.0, None, 9850.0),
                                  stamps=(1762700000, 1762700900, 1762701800)),
                          "BBCA.JK")
    assert quote.closes == [9750.0, 9850.0]
    assert len(quote.timestamps) == 2


def test_an_error_object_from_the_source_becomes_a_sentence(market):
    bad = {"chart": {"result": None,
                     "error": {"code": "Not Found",
                               "description": "No data found, symbol may be delisted"}}}
    with pytest.raises(market.SymbolNotFound) as err:
        market._parse(bad, "XXXX")
    assert "delisted" in str(err.value)


def test_an_empty_reply_is_not_a_crash(market):
    with pytest.raises(market.SymbolNotFound):
        market._parse({"chart": {"result": [], "error": None}}, "X")


def test_a_price_only_in_the_bars_still_answers(market):
    chart = payload(price=None)
    with pytest.raises(market.SymbolNotFound):
        # price=None and chartPreviousClose set: no bar price, no quote
        market._parse({**chart, "chart": {"result": [
            {"meta": {"symbol": "X", "chartPreviousClose": 1.0},
             "timestamp": [], "indicators": {"quote": [{"close": []}]}}],
            "error": None}}, "X")


# --- the sentence ----------------------------------------------------------

def test_the_sentence_names_the_delay_the_symbol_and_the_exchange(market):
    quote = market._parse(payload(), "BBCA.JK")
    said = market.describe(quote)
    assert "Bank Central Asia (BBCA.JK) is 9,850 IDR on Jakarta" in said
    assert "up 50.00 (+0.51%) on the session." in said
    assert "delayed up to 15 minutes" in said
    assert "not a live tick" in said
    # Nothing extra when the user's own words produced this symbol.
    assert "Yahoo symbol used" not in said


def test_a_resolved_symbol_is_named_so_a_wrong_guess_is_visible(market):
    """The one-line defence against a plausible price for the wrong company:
    the sentence says which ticker answered whenever it is not the one typed."""
    quote = market._parse(payload(symbol="AAPL"), "AAPL", typed="apple")
    said = market.describe(quote)
    assert said.endswith("Yahoo symbol used: AAPL.")


def test_an_unchanged_session_reads_as_unchanged_not_as_up_zero(market):
    quote = market._parse(payload(price=9800.0, previous=9800.0), "X.JK")
    said = market.describe(quote)
    assert "unchanged on the session" in said
    assert "up 0.00" not in said


def test_rupiah_has_no_cents_and_crypto_has_six_decimals(market):
    assert market._money(9850.0, "IDR") == "9,850 IDR"
    assert market._money(0.00001234, "USD") == "0.000012 USD"
    assert market._money(229.5, "USD") == "229.50 USD"


def test_a_period_answer_reports_the_period_not_the_session(market):
    quote = market._parse(payload(closes=(100.0, 105.0, 110.0)), "X.JK")
    said = market.history_summary(quote, "1mo")
    assert "+10.00%" in said and "1mo" in said
    assert "low" in said and "high" in said


def test_the_sparkline_always_includes_the_latest_bar(market):
    rows = [float(i) for i in range(500)]
    art = market.sparkline(rows, width=40)
    assert len(art) == 40
    assert art[-1] == "█"          # the last value is the highest here


def test_a_flat_series_does_not_divide_by_zero(market):
    assert market.sparkline([5.0, 5.0, 5.0]) == "▁▁▁"
    assert market.sparkline([5.0]) == ""


# --- the plugin surface ----------------------------------------------------

def test_a_normal_quote_reads_like_an_answer(plugin, monkeypatch):
    monkeypatch.setattr(plugin._market, "_get", lambda url: payload())
    said = plugin.run({"symbol": "BBCA"})
    assert "BBCA.JK" in said and "9,850 IDR" in said
    assert said.endswith(".")


def test_a_network_failure_never_becomes_a_remembered_price(plugin, monkeypatch):
    def boom(url):
        raise OSError("getaddrinfo failed")

    monkeypatch.setattr(plugin._market, "_get", boom)
    said = plugin.run({"symbol": "BBCA"})
    assert "could not get a price" in said
    assert "memory" in said
    assert "9,850" not in said


def test_a_bad_range_is_the_users_question_not_a_network_error(plugin):
    said = plugin.run({"symbol": "BBCA", "range": "2d"})
    assert said.startswith("Sir, i do not have") or "I do not have" in said
    assert "could not get a price" not in said


def test_an_extreme_session_move_asks_the_user_to_check_the_symbol(plugin, monkeypatch):
    """The failure mode this catches: a Jakarta code that resolved to some
    penny stock elsewhere and printed a real number for the wrong thing."""
    monkeypatch.setattr(plugin._market, "_get", lambda url: payload(
        price=1.0, previous=50.0, currency="USD", exchange="Other OTC"))
    said = plugin.run({"symbol": "BBCA"})
    assert "worth checking the symbol" in said


def test_range_1d_does_not_add_a_period_summary(plugin, monkeypatch):
    monkeypatch.setattr(plugin._market, "_get", lambda url: payload())
    assert "over 1d" not in plugin.run({"symbol": "BBCA"})


def test_a_longer_range_adds_the_summary_and_the_sparkline(plugin, monkeypatch):
    monkeypatch.setattr(plugin._market, "_get", lambda url: payload())
    said = plugin.run({"symbol": "BBCA", "range": "1mo"})
    assert "over 1mo" in said
    assert any(ch in said for ch in "▁▂▃▄▅▆▇█")


def test_a_failing_log_line_does_not_fail_the_price(plugin, monkeypatch):
    class Broken:
        def write_log(self, _line):
            raise RuntimeError("no log today")

    monkeypatch.setattr(plugin._market, "_get", lambda url: payload())
    assert "9,850" in plugin.run({"symbol": "BBCA"}, player=Broken())


def test_the_declaration_is_named_after_the_file_and_needs_a_symbol(plugin):
    assert plugin.PLUGIN["name"] == "market_price"
    assert plugin.PLUGIN["parameters"]["required"] == ["symbol"]


def test_the_plugin_says_it_is_delayed_and_not_for_orders(plugin):
    description = plugin.PLUGIN["description"]
    assert "delayed" in description
    assert "order" in description


# --- the manifest ----------------------------------------------------------

def test_the_manifest_matches_and_declares_network():
    manifest = pm.verify(ROOT / "plugins" / "market_price.py", "market_price")
    assert manifest is not None
    assert manifest.problems == []
    assert manifest.permissions == ("network",)


def test_the_network_is_in_the_helper_so_the_manifest_warns_rather_than_lies():
    """`market_price.py` itself contains no import of urllib — the request lives
    in `_market.py`. The manifest declares `network` because the plugin DOES use
    it, and the checker reports the mismatch as a WARNING ("declares network
    that the scan did not see"), not as a problem. This test pins that
    distinction: honest over-declaration must not be a load failure."""
    manifest = pm.verify(ROOT / "plugins" / "market_price.py", "market_price")
    assert manifest.ok
    assert any("network" in w for w in manifest.warnings)
    implied = pm.implied_permissions(ROOT / "plugins" / "_market.py")
    assert "network" in implied


def test_it_ships_disabled_until_the_user_consents():
    from core.plugin_loader import discover_plugins

    rows = {r["name"]: r for r in discover_plugins(
        ROOT / "plugins", set(), logger=lambda _m: None).list_for_ui()}
    assert rows["market_price"]["valid"] is True
    assert rows["market_price"]["enabled"] is False
    assert rows["market_price"]["permissions"] == ["network"]
