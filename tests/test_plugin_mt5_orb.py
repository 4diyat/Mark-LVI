"""mt5_orb: the strategy's arithmetic, the chart, and the honest refusal.

WHAT CANNOT BE TESTED HERE, AND WHY THAT SHAPED THE FILE
    `MetaTrader5` publishes Windows x86-64 wheels and nothing else, so the live
    path — attach to a terminal, read bars — cannot run on this machine (or on
    any CI runner this repository uses). That is not a reason to leave the plugin
    untested; it is a reason to test the part that holds the bugs:

      * the SESSION BUCKET. Bar times are the broker's, so the offset decides
        which bars are "London". Get it wrong and the range is two hours of the
        Asian session with a confident label on it.
      * the BREAKOUT RULE. A close beyond the range is a breakout; a wick
        through it is not. Every test below that mentions a wick exists because
        the cheap implementation (`if high > range.high`) passes all the others.
      * the REFUSAL. On Linux the plugin must say why, in a sentence, not
        disappear or raise.

    So the plugin is loaded from its file the way the loader loads it, MT5 is
    never imported, and the bars are synthetic with known high/low values.
"""
from __future__ import annotations

import importlib
import importlib.util
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import plugin_manifest as pm  # noqa: E402

BROKER_OFFSET = 2          # the broker every fixture in this file models: GMT+2


def _load(name: str):
    """Load a plugin module by path, as the loader does — not as a package
    import, because `plugins.mt5_orb` is not what the app executes.

    The `sys.modules` registration is not decoration: with `from __future__
    import annotations` a dataclass resolves its field types through
    `sys.modules[cls.__module__]`, so a module exec'd without being registered
    fails at the `@dataclass` line with a bare AttributeError. The real loader
    does exactly this (core/plugin_loader.py), which is how this was noticed.
    """
    path = ROOT / "plugins" / f"{name}.py"
    module_name = f"{name}_under_test"
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def orb():
    sys.path.insert(0, str(ROOT / "plugins"))
    return _load("_orb")


@pytest.fixture()
def mt5_helper():
    sys.path.insert(0, str(ROOT / "plugins"))
    return _load("_mt5")


@pytest.fixture()
def plugin():
    """The plugin imports `from plugins import _mt5, _orb`, so the package has
    to be importable — which it is in the app, because `plugins/__init__.py`
    exists. The real loader registers `plugins._orb` too; a plain import is close
    enough for a tool-surface test."""
    importlib.import_module("plugins._orb")
    importlib.import_module("plugins._mt5")
    return _load("mt5_orb")


def bar(orb, day: int, hour: int, minute: int, o, h, l, c, *, offset=BROKER_OFFSET):
    """One M30 bar. `hour`/`minute` are UTC; the stamp is offset into broker time
    because that is what the terminal hands over."""
    epoch = int(datetime(2026, 11, day, hour, minute, tzinfo=timezone.utc).timestamp())
    return orb_bar(epoch + offset * 3600, o, h, l, c)


def orb_bar(epoch, o, h, l, c):
    # Same shape as plugins._mt5.Bar, built here so the strategy tests do not
    # depend on the bridge module at all.
    from collections import namedtuple
    return namedtuple("Bar", "time open high low close tick_volume")(epoch, o, h, l, c, 100)


def london_session(orb, day=3, base=1.0800, *, pad=0.0):
    """Eight M30 bars covering 07:00-10:59 UTC — a full four-hour window.
    Each bar's body steps up by 2 pips; the high/low are the body ± 0.6."""
    rows = []
    for i in range(8):
        mid = base + i * 0.0002
        rows.append(bar(orb, day, 7 + i // 2, (i % 2) * 30,
                        mid, mid + 0.0006 + pad, mid - 0.0006, mid + 0.0002))
    return rows


def after_session(orb, day=3, start=11, count=6, o=1.0830, high=1.0830 + 0.0008,
                  low=None, close=None):
    rows = []
    for i in range(count):
        rows.append(bar(orb, day, start + i // 2, (i % 2) * 30, o,
                        high, (o - 0.0003) if low is None else low,
                        o if close is None else close))
    return rows


def utc(orb, analysis, text):
    """The summary is what the user hears; asserting on it keeps the tests about
    the answer rather than about internal fields."""
    return text in orb.summary(analysis)


# --- the session window -----------------------------------------------------

def test_the_range_is_measured_only_inside_the_session_window(orb):
    bars = london_session(orb) + after_session(orb)
    ranges = orb.opening_ranges(bars, "london", offset_hours=BROKER_OFFSET)
    assert len(ranges) == 1
    assert ranges[0].bars == 8
    assert ranges[0].high == pytest.approx(1.0800 + 7 * 0.0002 + 0.0006)
    assert ranges[0].low == pytest.approx(1.0800 - 0.0006)
    assert ranges[0].day == "2026-11-03"


def test_a_bar_from_after_the_window_never_stretches_the_range(orb):
    """The trap: the post-window bar has a higher high than anything in the
    window. If `opening_ranges` ignored the window the range would include it
    and there would be no breakout to find, because price would already be
    'inside' its own range."""
    bars = london_session(orb) + after_session(orb, high=1.0900)
    r = orb.opening_ranges(bars, "london", offset_hours=BROKER_OFFSET)[0]
    assert r.high < 1.0900


def test_the_broker_offset_decides_which_bars_are_the_session(orb):
    """Same bars, offset shifted by twelve hours: the London window now lands on
    nothing, because those bars are stamped 19:00-22:59 in the broker's clock."""
    bars = london_session(orb)
    assert orb.opening_ranges(bars, "london", offset_hours=BROKER_OFFSET)
    assert orb.opening_ranges(bars, "london", offset_hours=14) == []


def test_new_york_is_also_a_session_and_ny_is_its_alias(orb):
    assert orb.session_window("ny") == orb.session_window("newyork")
    assert orb.session_window("US") == orb.session_window("newyork")
    assert orb.session_window("London") == (7, 11)


def test_an_unknown_session_lists_the_known_ones(orb):
    with pytest.raises(ValueError) as err:
        orb.session_window("sidney")
    assert "sidney" in str(err.value)
    assert "london" in str(err.value) and "tokyo" in str(err.value)


# --- the breakout rule ------------------------------------------------------

def test_a_wick_through_the_high_is_not_a_breakout(orb):
    # Range high is 1.08200; this bar's high (1.08650) is 45 pips above it and
    # its close (1.08100) is back inside. Nothing has been decided.
    bars = london_session(orb) + after_session(orb, high=1.0865, close=1.0810)
    a = orb.analyse(bars, "EURUSD", "london", offset_hours=BROKER_OFFSET)
    assert a.state == "inside"
    assert a.breakout is None
    assert utc(orb, a, "wick through the level is not one")


def test_a_close_beyond_the_high_is_a_breakout_up(orb):
    range_high = 1.0800 + 7 * 0.0002 + 0.0006
    bars = london_session(orb) + after_session(orb, high=1.0870, close=range_high + 0.004)
    a = orb.analyse(bars, "EURUSD", "london", offset_hours=BROKER_OFFSET)
    assert a.state == "broke-up"
    assert a.breakout.direction == "up"
    assert a.breakout.close == pytest.approx(range_high + 0.004)
    assert a.breakout.distance == pytest.approx(0.004)
    assert a.breakout.bars_after_range == 1


def test_the_first_close_beyond_the_range_is_the_breakout_not_the_furthest(orb):
    """The interesting moment is when the range failed, not how far price ran
    afterwards. Reporting the latest bar would move the level every minute."""
    rows = after_session(orb, count=4, high=1.0870, close=1.0840)
    rows.append(bar(orb, 3, 13, 0, 1.0840, 1.0920, 1.0838, 1.0900))
    bars = london_session(orb) + rows
    a = orb.analyse(bars, "EURUSD", "london", offset_hours=BROKER_OFFSET)
    assert a.breakout.close == pytest.approx(1.0840)
    assert a.breakout.bars_after_range == 1


def test_a_close_below_the_low_is_a_breakout_down(orb):
    range_low = 1.0800 - 0.0006
    bars = london_session(orb) + after_session(orb, high=1.0830, close=range_low - 0.003)
    a = orb.analyse(bars, "EURUSD", "london", offset_hours=BROKER_OFFSET)
    assert a.state == "broke-down"
    assert a.breakout.direction == "down"
    assert utc(orb, a, "below the low")


def test_the_level_that_has_to_hold_is_named(orb):
    bars = london_session(orb) + after_session(orb, high=1.0870, close=1.0850)
    a = orb.analyse(bars, "EURUSD", "london", offset_hours=BROKER_OFFSET)
    assert utc(orb, a, "is the level that now has to hold")
    assert utc(orb, a, "Invalidated by a close back inside")


def test_a_range_with_no_bars_after_it_says_so(orb):
    bars = london_session(orb)
    a = orb.analyse(bars, "EURUSD", "london", offset_hours=BROKER_OFFSET)
    assert a.range is not None
    assert a.breakout is None
    assert utc(orb, a, "the session in progress")


def test_no_bars_at_all_is_an_answer_not_a_crash(orb):
    a = orb.analyse([], "EURUSD", "london")
    assert a.state == "no-range"
    assert "No bars were available" in a.notes[0]
    assert "EURUSD on M30" in orb.summary(a)


def test_bars_that_miss_the_window_say_what_to_check(orb):
    """The likeliest real failure: the offset is wrong, so no bar falls in the
    window. The message has to name the offset, or the user has no way to know
    it is a parameter at all."""
    bars = [bar(orb, 3, 18, 30, 1.08, 1.081, 1.079, 1.0805)]
    a = orb.analyse(bars, "EURUSD", "london", offset_hours=BROKER_OFFSET)
    assert a.range is None
    assert "UTC+2" in a.notes[0]


def test_a_partial_window_is_flagged_rather_than_used_silently(orb):
    bars = london_session(orb)[:3] + after_session(orb, high=1.0900, close=1.0860)
    a = orb.analyse(bars, "EURUSD", "london", offset_hours=BROKER_OFFSET)
    assert a.range.bars == 3
    assert any("incomplete" in n for n in a.notes)


def test_the_summary_states_the_assumptions_it_used(orb):
    bars = london_session(orb) + after_session(orb, high=1.0870, close=1.0850)
    a = orb.analyse(bars, "EURUSD", "london", offset_hours=BROKER_OFFSET)
    said = orb.summary(a)
    assert "broker time is UTC+2" in said
    assert "london" in said.lower()
    assert "No probability is implied" in said


def test_nothing_in_the_strategy_claims_a_prediction(orb):
    """A guard with teeth: the word list is the promise the module docstring
    makes, and a later edit that starts forecasting fails here."""
    source = (ROOT / "plugins" / "_orb.py").read_text(encoding="utf-8").lower()
    for word in ("guaranteed", "sure win", "will go up", "will go down",
                 "expected profit", "win rate", "accuracy is"):
        assert word not in source


# --- levels, for the chart and the table ------------------------------------

def test_levels_match_the_analysis(orb):
    bars = london_session(orb) + after_session(orb, high=1.0870, close=1.0850)
    a = orb.analyse(bars, "EURUSD", "london", offset_hours=BROKER_OFFSET)
    lv = orb.levels(a)
    assert lv["high"] == a.range.high
    assert lv["mid"] == pytest.approx((a.range.high + a.range.low) / 2)
    assert lv["state"] == "broke-up"
    assert lv["breakout_at"].startswith("2026-11-03")


def test_levels_of_a_missing_range_are_empty(orb):
    assert orb.levels(orb.analyse([], "EURUSD")) == {}


# --- the chart --------------------------------------------------------------

def test_the_text_chart_draws_the_range_levels(orb):
    bars = london_session(orb) + after_session(orb, high=1.0870, close=1.0850)
    a = orb.analyse(bars, "EURUSD", "london", offset_hours=BROKER_OFFSET)
    art = orb.render_text(bars, a, width=48, height=12)
    assert "EURUSD M30" in art
    assert "H=range high" in art
    for letter in "HLM":
        assert letter in art
    assert "#" in art          # candle bodies


def test_the_text_chart_of_no_bars_says_so(orb):
    a = orb.analyse([], "EURUSD")
    assert orb.render_text([], a) == "(no bars to draw)"


def test_the_png_is_a_real_png_when_pillow_is_installed(orb, tmp_path):
    pytest.importorskip("PIL")
    bars = london_session(orb) + after_session(orb, high=1.0870, close=1.0850)
    a = orb.analyse(bars, "EURUSD", "london", offset_hours=BROKER_OFFSET)
    out = tmp_path / "chart.png"
    orb.render_png(bars, a, out)
    assert out.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n"
    assert out.stat().st_size > 5_000


def test_without_pillow_the_plugin_answers_in_text(plugin, monkeypatch, tmp_path):
    """The import inside render_png is the seam: making it fail is exactly what a
    user without Pillow experiences, and the plugin must not lose the analysis
    over a missing optional package."""
    def no_pillow(*_a, **_k):
        raise ImportError("No module named 'PIL'")

    monkeypatch.setattr(plugin._orb, "render_png", no_pillow)
    monkeypatch.setattr(plugin, "_read", lambda p: (
        [bar(plugin._orb, 3, 7, 0, 1.08, 1.081, 1.079, 1.0805)],
        plugin._orb.analyse([bar(plugin._orb, 3, 7, 0, 1.08, 1.081, 1.079, 1.0805)],
                            "EURUSD", "london"),
        "EURUSD"))
    said = plugin.run({"symbol": "EURUSD", "draw": True})
    assert "Pillow is not installed" in said
    assert "EURUSD on M30" in said


# --- the tool surface -------------------------------------------------------

def test_the_declaration_is_a_single_valid_object_tool(plugin):
    meta = plugin.PLUGIN
    assert meta["parameters"]["type"] == "OBJECT"
    assert meta["parameters"]["required"] == ["symbol"]
    assert "draw" in meta["parameters"]["properties"]
    # The tool name must match the file stem, or the loader's collision check
    # and the manifest disagree about what to call it.
    assert meta["name"] == "mt5_orb"


def test_on_a_machine_without_mt5_it_explains_instead_of_raising(plugin):
    said = plugin.run({"symbol": "EURUSD"})
    assert said.startswith("Sir, I cannot read MetaTrader 5 here.")
    assert "Windows" in said or "not installed" in said


def test_an_unknown_session_is_refused_before_mt5_is_touched(plugin, monkeypatch):
    called = []
    monkeypatch.setattr(plugin._mt5, "connect", lambda *a, **k: called.append(1))
    said = plugin.run({"symbol": "EURUSD", "session": "sidney"})
    assert "sidney" in said and "london" in said
    assert called == []


def test_a_missing_symbol_asks_one_question(plugin):
    assert plugin.run({}) == "Sir, no symbol was given — which pair should I open?"


def test_an_unknown_timeframe_lists_the_ones_that_exist(plugin):
    said = plugin.run({"symbol": "EURUSD", "timeframe": "M7"})
    assert "M7" in said and "M30" in said


def test_the_offset_falls_back_to_the_documented_default(plugin):
    symbol, session, timeframe, offset = plugin._settings({"symbol": "eurusd"})
    assert (symbol, session, timeframe) == ("EURUSD", "london", "M30")
    assert offset == plugin._orb.DEFAULT_BROKER_UTC_OFFSET_H == 2
    assert plugin._settings({"symbol": "X", "broker_utc_offset": "3"})[3] == 3
    assert plugin._settings({"symbol": "X", "broker_utc_offset": "noon"})[3] == 2


def test_the_chart_path_is_a_png_named_after_the_symbol(plugin):
    path = plugin._chart_path("EURUSD")
    assert path.suffix == ".png"
    assert "EURUSD" in path.name and path.name.startswith("mt5_")


def test_a_symbol_with_slashes_cannot_escape_the_folder(plugin):
    assert "/" not in plugin._chart_path("../../etc/passwd").name


def test_draw_false_takes_the_analysis_only_path(plugin, monkeypatch):
    seen = {}

    def fake_read(parameters):
        seen["called"] = True
        bars = london_session(plugin._orb) + after_session(plugin._orb)
        return bars, plugin._orb.analyse(bars, "EURUSD", "london",
                                         offset_hours=BROKER_OFFSET), "EURUSD"

    monkeypatch.setattr(plugin, "_read", fake_read)
    monkeypatch.setattr(plugin, "_chart_path", lambda s: pytest.fail("drew a chart"))
    said = plugin.run({"symbol": "EURUSD", "draw": False})
    assert seen["called"]
    assert "EURUSD on M30" in said and "Chart saved" not in said


def test_a_player_that_fails_to_log_does_not_fail_the_answer(plugin, monkeypatch):
    class Broken:
        def write_log(self, _line):
            raise RuntimeError("no log today")

    bars = london_session(plugin._orb) + after_session(plugin._orb)
    monkeypatch.setattr(plugin, "_read", lambda p: (
        bars, plugin._orb.analyse(bars, "EURUSD", "london",
                                  offset_hours=BROKER_OFFSET), "EURUSD"))
    said = plugin.run({"symbol": "EURUSD", "draw": False}, player=Broken())
    assert "EURUSD on M30" in said


# --- the bridge helper ------------------------------------------------------

def test_the_bridge_reports_why_mt5_is_missing_in_plain_words(mt5_helper):
    with pytest.raises(mt5_helper.MT5Unavailable) as err:
        mt5_helper._module()
    said = str(err.value)
    assert "MetaTrader 5 is not available here" in said
    assert "Windows" in said or "not installed" in said


def test_no_connection_means_no_commands(mt5_helper, monkeypatch):
    """connect() must not report success after a failed initialize — the Session
    object it returns is the only thing the plugin trusts."""
    class FakeMT5:
        def __init__(self):
            self.shut = 0

        def initialize(self, **_k):
            return False

        def last_error(self):
            return (-10005, "IPC timeout")

        def shutdown(self):
            self.shut += 1

    fake = FakeMT5()
    monkeypatch.setattr(mt5_helper, "_module", lambda: fake)
    with pytest.raises(mt5_helper.MT5Unavailable) as err:
        mt5_helper.connect()
    assert "running and logged in" in str(err.value)
    assert fake.shut == 0          # nothing to shut down; it never opened


def test_an_unknown_symbol_names_the_broker_suffix_problem(mt5_helper):
    class FakeMT5:
        def symbol_select(self, _symbol, _enable):
            return False

    session = mt5_helper.Session(mt5=FakeMT5())
    with pytest.raises(mt5_helper.MT5Unavailable) as err:
        session.select("EURUSD")
    assert "suffix" in str(err.value)


def test_closed_only_skips_the_forming_bar(mt5_helper):
    """Position 0 is the bar that has not finished. Asking from position 1 is the
    whole reason a two-minute spike cannot become a breakout."""
    calls = {}

    class FakeMT5:
        TIMEFRAME_M30 = 30

        def copy_rates_from_pos(self, symbol, tf, start, count):
            calls["start"], calls["count"], calls["tf"] = start, count, tf
            return []

        def last_error(self):
            return (0, "ok")

    session = mt5_helper.Session(mt5=FakeMT5())
    with pytest.raises(mt5_helper.MT5Unavailable):
        session.bars("EURUSD", "M30", 10)
    assert calls == {"start": 1, "count": 10, "tf": 30}

    with pytest.raises(mt5_helper.MT5Unavailable):
        session.bars("EURUSD", "M30", 10, closed_only=False)
    assert calls["start"] == 0


def test_no_bars_is_reported_with_the_terminal_limits(mt5_helper):
    class FakeMT5:
        TIMEFRAME_M30 = 30

        def copy_rates_from_pos(self, *_a):
            return None

        def last_error(self):
            return (-2, "no history")

    with pytest.raises(mt5_helper.MT5Unavailable) as err:
        mt5_helper.Session(mt5=FakeMT5()).bars("EURUSD")
    assert "Max. bars in chart" in str(err.value)


def test_pip_size_follows_the_symbol_digits(mt5_helper):
    class Info:
        def __init__(self, point, digits):
            self.point, self.digits = point, digits

    assert mt5_helper.pip_size(Info(0.00001, 5)) == pytest.approx(0.0001)
    assert mt5_helper.pip_size(Info(0.001, 3)) == pytest.approx(0.01)
    assert mt5_helper.pip_size(Info(0.01, 2)) == pytest.approx(0.01)   # gold
    assert mt5_helper.pip_size(Info(0.0, 5)) == 0.0


def test_the_helper_can_never_place_an_order():
    """A market order is irreversible, and this app's confirmation gate is built
    for reversible actions. If someone later adds `order_send`, this test is the
    one that has to be deleted deliberately.

    Checked through the AST rather than the text, because the module docstring
    says the word `order_send` — explaining that it is absent should not be the
    thing that fails the test."""
    import ast

    tree = ast.parse((ROOT / "plugins" / "_mt5.py").read_text(encoding="utf-8"))
    used = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            used.add(node.attr)
        elif isinstance(node, ast.Name):
            used.add(node.id)
    forbidden = {"order_send", "order_check", "positions_close", "positions_modify"}
    assert not (used & forbidden), f"trading call in _mt5.py: {used & forbidden}"


# --- the manifest and the loader -------------------------------------------

def test_the_manifest_hash_matches_the_file_on_disk():
    manifest = pm.verify(ROOT / "plugins" / "mt5_orb.py", "mt5_orb")
    assert manifest is not None, "mt5_orb.py must ship a manifest beside it"
    assert manifest.problems == []
    assert manifest.ok


def test_the_manifest_says_what_the_source_actually_does():
    """The permission list is checked against an import scan, so declaring
    `network` here would be a warning and declaring nothing would be a refusal.
    This plugin writes a PNG, which is `files`."""
    manifest = pm.verify(ROOT / "plugins" / "mt5_orb.py", "mt5_orb")
    assert manifest.permissions == ("files",)
    assert pm.implied_permissions(ROOT / "plugins" / "mt5_orb.py") == {"files"}


def test_a_declared_permission_plugin_ships_disabled():
    """Consent, not a default: a plugin that asked for something starts off."""
    rows = {
        r["name"]: r
        for r in __import__("core.plugin_loader", fromlist=["x"]).discover_plugins(
            ROOT / "plugins", set(), logger=lambda _m: None).list_for_ui()
    }
    assert rows["mt5_orb"]["valid"] is True
    assert rows["mt5_orb"]["enabled"] is False
    assert rows["mt5_orb"]["permissions"] == ["files"]
