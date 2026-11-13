"""The example plugin: the conversion, and the sentences it refuses to say.

WHY THIS IS TESTED LIKE AN ACTION AND NOT LIKE A DEMO
    This plugin exists to prove the third-party chain — manifest, loader,
    permission, consent — but it is also a plugin the user will talk to, and a
    plugin that answers confidently and wrongly is worse than one that is
    missing. The two failures that matter are both about refusing clearly:

      * a rate it could not fetch must never be replaced by a remembered one.
        "About 16,000 rupiah" from a model's memory is exactly what this plugin
        was written to prevent, and the failure has no error message.
      * a currency it could not read must be reported as unreadable, not
        guessed. "peso" is ARS, CLP, COP, MXN, UYU or PHP depending on who is
        talking.

    Nothing here touches the network: `_fetch_rate` is replaced, and the one
    test that runs the real HTTP code asserts on the URL it builds rather than
    on an answer.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import plugin_manifest as pm  # noqa: E402


def _load_plugin():
    """The plugin as the loader loads it — from its file, by path, with a name
    that is not a package. Importing `plugins.currency_rates` would work here
    and would not be what the app does."""
    path = ROOT / "plugins" / "currency_rates.py"
    spec = importlib.util.spec_from_file_location("currency_rates_under_test", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def plugin():
    return _load_plugin()


@pytest.fixture()
def rates(plugin, monkeypatch):
    """Pin the rate and the date; record what was asked for."""
    asked = {}

    def fake_fetch(base, quote):
        asked["base"], asked["quote"] = base, quote
        return 16_250.0, "2026-11-11"

    monkeypatch.setattr(plugin, "_fetch_rate", fake_fetch)
    return asked


# ── the chain this file exists to prove ────────────────────────────────────

def test_the_plugin_carries_a_manifest_that_verifies():
    """The whole point of the example: a plugin with a declaration, checked
    against the file it describes."""
    manifest = pm.verify(ROOT / "plugins" / "currency_rates.py", "currency_rates")
    assert manifest is not None
    assert manifest.ok, manifest.problems
    assert manifest.permissions == ("network",)
    assert manifest.version and manifest.author


def test_the_manifest_hash_matches_the_file_on_disk():
    """Spelled out separately, because the failure message in CI should name the
    command that fixes it rather than just 'sha256 does not match'."""
    import hashlib
    py = ROOT / "plugins" / "currency_rates.py"
    stored = json.loads((ROOT / "plugins" / "currency_rates.json")
                        .read_text(encoding="utf-8"))["sha256"]
    assert stored == hashlib.sha256(py.read_bytes()).hexdigest(), (
        "the plugin changed without its manifest — update plugins/"
        "currency_rates.json (tests/test_plugin_currency.py fails on purpose)")


def test_the_plugin_name_matches_its_metadata(plugin):
    assert plugin.PLUGIN["name"] == "currency_rates"
    assert plugin.PLUGIN["description"].strip()


def test_the_declared_permission_is_the_one_the_source_uses(plugin):
    """`network` is declared and `urllib` is imported. If somebody adds `open()`
    or `subprocess` later without updating the manifest, the loader refuses the
    plugin — and this test says so before that happens in the field."""
    implied = pm.implied_permissions(ROOT / "plugins" / "currency_rates.py")
    assert implied == {"network"}


def test_the_loader_accepts_it_and_starts_it_off(monkeypatch):
    """A plugin that declared permissions is OFF until the user answers the
    consent question — that is what makes the question worth asking."""
    from core.plugin_loader import discover_plugins
    from memory import config_manager as cm

    monkeypatch.setattr(cm, "CONFIG_FILE", Path("/nonexistent/api_keys.json"))
    monkeypatch.setattr(cm, "CONFIG_DIR", Path("/nonexistent"))
    monkeypatch.setattr(cm, "_LAST_GOOD", {}, raising=False)

    registry = discover_plugins(ROOT / "plugins", set(), lambda _m: None)
    assert registry.has("currency_rates")
    row = next(r for r in registry.list_for_ui() if r["name"] == "currency_rates")
    assert row["valid"] is True
    assert row["permissions"] == ["network"]
    assert row["enabled"] is False, "a declared plugin must not start enabled"
    assert "disabled" in registry.run("currency_rates", {}).lower()


def test_answering_yes_starts_it(monkeypatch, tmp_path):
    """And the answer is what turns it on — nothing else."""
    from core.plugin_loader import discover_plugins
    from memory import config_manager as cm

    monkeypatch.setattr(cm, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(cm, "CONFIG_FILE", tmp_path / "api_keys.json")
    monkeypatch.setattr(cm, "_LAST_GOOD", {}, raising=False)

    registry = discover_plugins(ROOT / "plugins", set(), lambda _m: None)
    cm.save_plugin_enabled("currency_rates", True)
    row = next(r for r in registry.list_for_ui() if r["name"] == "currency_rates")
    assert row["enabled"] is True


# ── the conversion ─────────────────────────────────────────────────────────

def test_the_answer_carries_the_rate_the_date_and_the_amount(plugin, rates):
    reply = plugin.run({"amount": 50, "from_currency": "USD", "to_currency": "IDR"})
    assert "50.00 USD" in reply
    assert "812,500" in reply              # 50 × 16,250, no decimals for IDR
    assert "2026-11-11" in reply           # the date is not optional
    assert (rates["base"], rates["quote"]) == ("USD", "IDR")


def test_a_currency_without_cents_is_not_given_two_decimals(plugin, rates):
    """"Rp 812.500,00" is not precision, it is a number the user has to
    un-read."""
    assert "," in plugin.run({"amount": 50, "from_currency": "USD",
                              "to_currency": "IDR"})
    assert "812,500.00" not in plugin.run({"amount": 50, "from_currency": "USD",
                                           "to_currency": "IDR"})


def test_a_currency_with_cents_keeps_them(plugin, rates):
    reply = plugin.run({"amount": 10, "from_currency": "USD", "to_currency": "EUR"})
    assert "EUR" in reply and "." in reply.split("EUR")[0][-4:]


def test_spoken_names_are_understood(plugin, rates):
    reply = plugin.run({"amount": 1, "from_currency": "dollars",
                        "to_currency": "rupiah"})
    assert (rates["base"], rates["quote"]) == ("USD", "IDR")
    assert "16,250 IDR" in reply


def test_an_amount_that_is_a_string_still_works(plugin, rates):
    """The model sends JSON, and JSON numbers sometimes arrive as strings."""
    assert "USD" in plugin.run({"amount": "50", "from_currency": "USD",
                                "to_currency": "IDR"})


def test_same_currency_is_not_a_conversion(plugin, rates):
    reply = plugin.run({"amount": 5, "from_currency": "USD", "to_currency": "USD"})
    assert "already USD" in reply
    assert not rates, "no request should be made for USD to USD"


# ── the refusals ───────────────────────────────────────────────────────────

def test_a_currency_it_cannot_read_is_reported_not_guessed(plugin, rates):
    reply = plugin.run({"amount": 1, "from_currency": "peso", "to_currency": "USD"})
    assert "could not read" in reply
    assert not rates, "an unreadable currency must not reach the network"


def test_a_failed_request_never_becomes_a_remembered_rate(plugin, monkeypatch):
    """The failure this plugin exists to prevent, pinned."""
    def boom(base, quote):
        raise OSError("network is unreachable")

    monkeypatch.setattr(plugin, "_fetch_rate", boom)
    reply = plugin.run({"amount": 50, "from_currency": "USD", "to_currency": "IDR"})
    assert "could not reach" in reply
    assert "rather tell you that than guess" in reply
    assert "16,250" not in reply and "16250" not in reply


def test_an_unknown_pair_is_told_apart_from_a_network_failure(plugin, monkeypatch):
    """"Not a pair we carry" and "cannot reach the service" are different
    problems with different fixes."""
    def missing(base, quote):
        raise LookupError("no rate")

    monkeypatch.setattr(plugin, "_fetch_rate", missing)
    reply = plugin.run({"amount": 1, "from_currency": "USD", "to_currency": "XTS"})
    assert "not a pair" in reply and "could not reach" not in reply


def test_a_nonsense_amount_is_refused(plugin, rates):
    reply = plugin.run({"amount": "a lot", "from_currency": "USD",
                        "to_currency": "IDR"})
    assert "could not read" in reply
    assert not rates


def test_a_negative_amount_is_refused(plugin, rates):
    reply = plugin.run({"amount": -5, "from_currency": "USD", "to_currency": "IDR"})
    assert "negative" in reply
    assert not rates


def test_a_missing_parameter_does_not_raise(plugin, rates):
    """run() is called from a worker thread by the model's choosing; an
    exception there is a traceback in the console instead of a sentence."""
    assert plugin.run({})                                   # no crash
    assert "could not read" in plugin.run({"amount": 1})


# ── the request it builds ─────────────────────────────────────────────────

def test_the_request_url_is_the_documented_one(plugin, monkeypatch):
    """Runs the real `_fetch_rate` with the transport replaced, so the URL and
    the timeout are checked without a network round trip."""
    seen = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return b'{"amount": 1.0, "base": "USD", "date": "2026-11-11", ' \
                   b'"rates": {"IDR": 16250.0}}'

    def fake_urlopen(url, timeout=None):
        seen["url"], seen["timeout"] = url, timeout
        return FakeResponse()

    monkeypatch.setattr(plugin._urlrequest, "urlopen", fake_urlopen)
    rate, date = plugin._fetch_rate("USD", "IDR")
    assert rate == 16250.0 and date == "2026-11-11"
    assert seen["url"] == "https://api.frankfurter.dev/v1/latest?base=USD&symbols=IDR"
    assert seen["timeout"] == plugin.TIMEOUT_S, (
        "an un-timed request in a tool is a hung conversation")


def test_a_response_without_the_rate_raises_rather_than_returning_one(plugin, monkeypatch):
    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return b'{"base": "USD", "rates": {}}'

    monkeypatch.setattr(plugin._urlrequest, "urlopen",
                        lambda url, timeout=None: FakeResponse())
    with pytest.raises(LookupError):
        plugin._fetch_rate("USD", "IDR")


def test_the_log_line_is_optional(plugin, rates):
    """`player` is None in the dashboard and in tests; a missing log must not
    cost the answer."""
    class BrokenPlayer:
        def write_log(self, _text):
            raise RuntimeError("no window")

    reply = plugin.run({"amount": 1, "from_currency": "USD", "to_currency": "IDR"},
                       player=BrokenPlayer())
    assert "IDR" in reply
