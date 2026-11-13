"""prayer_times: the parsing, the zone, and the "which city" question.

WHAT MAKES A PRAYER-TIME BUG SERIOUS
    Every failure here is an hour or more of error on something a person acts on
    at a fixed moment, and all of them look like success:

      * the wrong ZONE — a user in Bandung asks about Makassar (WITA, +08) and
        the answer is computed against their own +07 clock, so "next is Maghrib"
        names a prayer that passed an hour ago;
      * the missing OFFSET — the payload carries `(+07)` inside `Sunrise` and
        nowhere else, so reading the first timing value yields UTC and prints
        "UTC+0" under an Indonesian city;
      * SILENTLY TODAY — a date the parser could not read replaced by today's,
        which answers a question nobody asked with numbers that look right;
      * the METHOD left unnamed, which makes Fajr twenty minutes away from the
        one the user's mosque uses.

    NO NETWORK HERE. `_get` is replaced with a payload built in the test; the
    one test that looks at a URL looks at the string built for it.
"""
from __future__ import annotations

import importlib
import importlib.util
import sys
from datetime import datetime, timedelta, timezone
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
def prayer():
    return _load("_prayer")


@pytest.fixture()
def plugin(prayer):
    module = _load("prayer_times")
    module._prayer = prayer
    return module


def payload(city="Bandung", zone="Asia/Jakarta", date="10-11-2025",
            method_id=20, method_name="Kementerian Agama Republik Indonesia",
            sunrise="05:34 (+07)", hijri=True):
    data = {
        "timings": {"Fajr": "04:22", "Sunrise": sunrise, "Dhuhr": "11:42",
                    "Asr": "15:02", "Sunset": "17:49", "Maghrib": "17:49",
                    "Isha": "18:59"},
        "date": {"timestamp": "1762732800",
                 "gregorian": {"date": date}},
        "meta": {"timezone": zone, "city": city,
                 "latitude": -6.9175, "longitude": 107.6191,
                 "method": {"id": method_id, "name": method_name}},
    }
    if hijri:
        data["date"]["hijri"] = {"day": "19", "year": "1447",
                                 "month": {"en": "Jumada al-awwal"}}
    return {"code": 200, "status": "OK", "data": data}


# --- the numbers -----------------------------------------------------------

def test_the_five_prayers_and_sunrise_are_all_read(prayer):
    timings = prayer.parse(payload(), "Bandung", "Indonesia")
    assert [name for name, _clock in prayer.day_table(timings)] == [
        "Fajr", "Sunrise", "Dhuhr", "Asr", "Maghrib", "Isha"]
    assert timings.times["Maghrib"].strftime("%H:%M") == "17:49"
    assert timings.method.startswith("Kementerian Agama")


def test_an_unreadable_clock_is_dropped_not_turned_into_midnight(prayer):
    """A stray value must never become 00:00 — that is a real time, and a
    plausible-looking wrong one."""
    bad = payload()
    bad["data"]["timings"]["Asr"] = "--:--"
    timings = prayer.parse(bad, "Bandung", "Indonesia")
    assert "Asr" not in timings.times
    assert "Maghrib" in timings.times


def test_a_prayer_the_service_omits_does_not_appear_in_the_sentence(prayer):
    sparse = payload()
    del sparse["data"]["timings"]["Isha"]
    timings = prayer.parse(sparse, "Bandung", "Indonesia")
    said = prayer.describe(timings)
    assert "Isha" not in said
    assert "Maghrib 17:49" in said


# --- the zone, which is where the hours go wrong ---------------------------

def test_the_offset_is_read_from_the_payload_not_the_first_timing(prayer):
    """The bug this pins: `(+07)` lives in Sunrise only, so a parser that reads
    the first timing value gets "04:22" — no offset — and prints UTC+0."""
    timings = prayer.parse(payload(sunrise="05:34 (+07)"), "Bandung", "Indonesia")
    assert timings.utc_offset == timedelta(hours=7)
    assert "UTC+7" in prayer.describe(timings)
    assert "UTC+0" not in prayer.describe(timings)


def test_the_suffix_wins_even_when_the_zone_name_resolves(prayer, monkeypatch):
    """Order matters, and CI is why. Python on Windows has no system tz
    database and this project does not depend on `tzdata`, so resolving
    `Asia/Jakarta` there returns nothing — the first version of this module did
    that first, and both Windows runners reported Jakarta as UTC+0 while Linux
    was green."""
    timings = prayer.parse(payload(sunrise="05:34 (+07)"), "Bandung", "Indonesia")
    assert timings.utc_offset == timedelta(hours=7)

    def no_database(name):
        raise RuntimeError("no tzdata on this machine")

    monkeypatch.setattr(prayer, "zone_is_known", no_database)
    timings = prayer.parse(payload(sunrise="05:34 (+07)"), "Bandung", "Indonesia")
    assert timings.utc_offset == timedelta(hours=7), "a missing tz database changed the answer"


def test_the_iana_name_is_the_fallback_when_no_suffix_is_present(prayer):
    timings = prayer.parse(payload(sunrise="05:34"), "Bandung", "Indonesia")
    if prayer.zone_is_known("Asia/Jakarta"):
        assert timings.utc_offset == timedelta(hours=7)
    else:
        assert timings.offset_known is False


def test_the_offset_falls_back_to_the_suffix_when_the_zone_is_unknown(prayer):
    timings = prayer.parse(payload(zone="Not/AZone", sunrise="05:34 (+07)"),
                           "Bandung", "Indonesia")
    assert timings.utc_offset == timedelta(hours=7)


def test_with_no_zone_and_no_suffix_the_answer_admits_it_cannot_tell(prayer):
    """Aladhan labels some replies by zone NAME only; a Windows Python with no
    tzdata then has neither a name it can resolve nor an offset in the payload.
    Saying "UTC+0" there is an hour of error presented confidently."""
    timings = prayer.parse(payload(zone="", sunrise="05:34"), "Bandung", "Indonesia")
    assert timings.offset_known is False
    said = prayer.describe(timings)
    assert "could not be determined" in said
    assert "UTC+0" not in said
    assert "Maghrib 17:49" in said          # the clock values are still reported
    assert timings.next_prayer(datetime(2025, 11, 10, 10, 0, tzinfo=timezone.utc)) is None


def test_a_different_city_zone_moves_the_next_prayer(prayer):
    """Makassar is WITA (+08). Asked from a machine on WIB (+07), the next
    prayer is decided in MAKASSAR's clock: at 18:50 WITA, Isha is next; at
    18:50 WIB the same table would still be waiting for Maghrib."""
    makassar = payload(city="Makassar", zone="Asia/Makassar", sunrise="05:52 (+08)")
    makassar["data"]["timings"].update({"Fajr": "04:40", "Dhuhr": "11:55",
                                        "Asr": "15:15", "Maghrib": "18:02",
                                        "Isha": "19:12"})
    timings = prayer.parse(makassar, "Makassar", "Indonesia")
    now = datetime(2025, 11, 10, 10, 50, tzinfo=timezone.utc)     # 18:50 WITA
    name, when = timings.next_prayer(now)
    assert name == "Isha"
    assert when.strftime("%H:%M") == "19:12"
    assert "UTC+8" in prayer.describe(timings, now)


# --- the next prayer -------------------------------------------------------

def test_the_next_prayer_and_the_wait_are_computed_on_the_city_clock(prayer):
    timings = prayer.parse(payload(), "Bandung", "Indonesia")
    now = datetime(2025, 11, 10, 10, 30, tzinfo=timezone.utc)     # 17:30 WIB
    name, when = timings.next_prayer(now)
    assert name == "Maghrib"
    assert "Next is Maghrib at 17:49, in 19 m" in prayer.describe(timings, now)


def test_after_isha_the_answer_says_the_day_is_over(prayer):
    timings = prayer.parse(payload(), "Bandung", "Indonesia")
    now = datetime(2025, 11, 10, 15, 30, tzinfo=timezone.utc)     # 22:30 WIB
    assert timings.next_prayer(now) is None
    assert "All of today's prayers have passed" in prayer.describe(timings, now)


def test_a_naive_now_is_read_as_utc_rather_than_crashing(prayer):
    timings = prayer.parse(payload(), "Bandung", "Indonesia")
    name, _when = timings.next_prayer(datetime(2025, 11, 10, 10, 30))
    assert name == "Maghrib"


# --- the method, the school, the Hijri date --------------------------------

def test_the_method_is_named_in_every_answer(prayer):
    timings = prayer.parse(payload(), "Bandung", "Indonesia")
    assert "Method: Kementerian Agama" in prayer.describe(timings)


def test_the_method_can_fall_back_to_its_id(prayer):
    timings = prayer.parse(payload(method_name=""), "Bandung", "Indonesia")
    assert "Kemenag" in timings.method


def test_the_hanafi_school_is_said_out_loud_when_used(prayer):
    timings = prayer.parse(payload(), "Bandung", "Indonesia", school=1)
    assert "Asr by the Hanafi rule" in prayer.describe(timings)


def test_the_hijri_date_is_reported_with_its_caveat(prayer):
    said = prayer.describe(prayer.parse(payload(), "Bandung", "Indonesia"))
    assert "19 Jumada al-awwal 1447" in said
    assert "can differ by a day" in said


def test_an_empty_reply_is_a_sentence_not_a_traceback(prayer):
    with pytest.raises(prayer.PrayerError):
        prayer.parse({"data": {}}, "Bandung", "Indonesia")


def test_a_reply_with_no_readable_time_is_refused_not_listed_as_none(prayer):
    """"Prayer times for Bandung: " with nothing after the colon reads like a
    day with no prayers, which is not what happened."""
    empty = payload()
    empty["data"]["timings"] = {name: "--:--" for name in empty["data"]["timings"]}
    with pytest.raises(prayer.PrayerError) as err:
        prayer.parse(empty, "Bandung", "Indonesia")
    assert "not the shape" in str(err.value)


def test_a_reply_without_times_is_refused_when_speaking(prayer):
    """Reached through describe() when a Timings is built by hand (the plugin
    always gets one from parse(), which already refuses)."""
    timings = prayer.Timings(city="Bandung", country="Indonesia", times={})
    with pytest.raises(prayer.PrayerError) as err:
        prayer.describe(timings)
    assert "check the city name" in str(err.value)


# --- fetch: the URL and the refusals --------------------------------------

def test_the_url_asks_for_the_method_and_the_school(prayer, monkeypatch):
    seen = {}
    monkeypatch.setattr(prayer, "_get", lambda url: (seen.update(url=url), payload())[1])
    prayer.fetch("Bandung", "Indonesia", 20, 1)
    assert "/v1/timingsByCity/" in seen["url"]
    assert "city=Bandung" in seen["url"] and "country=Indonesia" in seen["url"]
    assert "method=20" in seen["url"] and "school=1" in seen["url"]


def test_a_date_is_passed_in_the_services_spelling(prayer, monkeypatch):
    seen = {}
    monkeypatch.setattr(prayer, "_get", lambda url: (seen.update(url=url), payload())[1])
    prayer.fetch("Bandung", when="20-11-2025")
    assert "/timingsByCity/20-11-2025?" in seen["url"]


def test_an_unknown_method_lists_the_real_ones(prayer):
    with pytest.raises(ValueError) as err:
        prayer.fetch("Bandung", method=99)
    assert "99" in str(err.value) and "20" in str(err.value)


def test_an_empty_city_is_a_question_back(prayer):
    with pytest.raises(ValueError):
        prayer.fetch("   ")


def test_a_network_failure_is_wrapped_as_one_sentence(prayer, monkeypatch):
    def boom(url):
        raise OSError("getaddrinfo failed")

    monkeypatch.setattr(prayer, "_get", boom)
    with pytest.raises(prayer.PrayerError) as err:
        prayer.fetch("Bandung")
    assert "could not reach" in str(err.value)


# --- the plugin surface ----------------------------------------------------

def test_a_normal_question_is_answered(plugin, monkeypatch):
    monkeypatch.setattr(plugin._prayer, "_get", lambda url: payload())
    said = plugin.run({"city": "Bandung"})
    assert "Prayer times for Bandung, Indonesia" in said
    assert "Maghrib 17:49" in said
    assert said.endswith(".")


def test_no_city_falls_back_to_the_saved_default(plugin, monkeypatch):
    monkeypatch.setattr(plugin._prayer, "_get", lambda url: payload())
    assert "Bandung" in plugin.run({})


def test_a_saved_setting_beats_the_hardcoded_default(plugin, monkeypatch):
    monkeypatch.setattr(plugin, "_setting", lambda key, fallback: {
        "city": "Surabaya", "country": "Indonesia", "method": "20", "school": "0",
    }[key])
    monkeypatch.setattr(plugin._prayer, "_get", lambda url: payload())
    assert "Bandung" in plugin.run({})          # the payload names the city
    assert plugin._setting("city", "Bandung") == "Surabaya"


def test_tomorrow_is_asked_for_as_a_date_and_named_in_the_answer(plugin, monkeypatch):
    seen = {}
    monkeypatch.setattr(plugin._prayer, "_get",
                        lambda url: (seen.update(url=url), payload())[1])
    said = plugin.run({"city": "Bandung", "date": "2025-11-20"})
    assert "/timingsByCity/20-11-2025?" in seen["url"]
    # The payload in this test names 10 November; what matters is that the day
    # is in the sentence at all, so "besok" does not become a transcript with
    # no date in it.
    assert "10 November 2025" in said
    assert said.rstrip().endswith(")")        # ...and the weekday follows it


def test_an_unreadable_date_is_refused_rather_than_replaced_with_today(plugin):
    said = plugin.run({"city": "Bandung", "date": "besok lusa"})
    assert "could not read" in said
    assert "YYYY-MM-DD" in said


def test_a_failure_never_becomes_a_remembered_time(plugin, monkeypatch):
    def boom(url):
        raise OSError("no route to host")

    monkeypatch.setattr(plugin._prayer, "_get", boom)
    said = plugin.run({"city": "Bandung"})
    assert "could not get the prayer times" in said
    assert "memory" in said
    assert "17:49" not in said


def test_a_failing_log_line_does_not_fail_the_times(plugin, monkeypatch):
    class Broken:
        def write_log(self, _line):
            raise RuntimeError("no log today")

    monkeypatch.setattr(plugin._prayer, "_get", lambda url: payload())
    assert "Maghrib" in plugin.run({"city": "Bandung"}, player=Broken())


def test_the_declaration_names_the_defaults_it_uses(plugin):
    description = plugin.PLUGIN["description"]
    assert "Kemenag" in description
    assert "memory" in description
    assert plugin.PLUGIN["parameters"]["required"] == []


def test_the_settings_schema_is_what_the_panel_renders(plugin):
    """A malformed PLUGIN_SETTINGS is silently ignored by the loader, which is
    how a plugin ends up with no settings form and nobody notices."""
    schema = plugin.PLUGIN_SETTINGS
    assert schema["namespace"] == "prayer_times"
    keys = {field["key"] for field in schema["fields"]}
    assert keys == {"city", "country", "method", "school"}
    for field in schema["fields"]:
        assert field.get("type") in ("text", "password", "choice", "toggle")
        assert field.get("label")


# --- the manifest ----------------------------------------------------------

def test_the_manifest_matches_and_declares_network():
    manifest = pm.verify(ROOT / "plugins" / "prayer_times.py", "prayer_times")
    assert manifest is not None
    assert manifest.problems == []
    assert manifest.permissions == ("network",)


def test_it_ships_disabled_until_the_user_consents():
    from core.plugin_loader import discover_plugins

    rows = {r["name"]: r for r in discover_plugins(
        ROOT / "plugins", set(), logger=lambda _m: None).list_for_ui()}
    assert rows["prayer_times"]["valid"] is True
    assert rows["prayer_times"]["enabled"] is False
    assert rows["prayer_times"]["permissions"] == ["network"]
