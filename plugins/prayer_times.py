"""prayer_times — the five prayers for a city, with the method that produced them.

WHAT IT ANSWERS
    "Jam berapa maghrib di Bandung?", "kapan subuh besok di Makassar?",
    "prayer times in Jakarta today". The times come from Aladhan, which needs no
    key and covers any city by name; `plugins/_prayer.py` holds the parser and
    the reasons every number in the answer is more conditional than it looks.

WHY IT IS A PLUGIN AND NOT A REMEMBERED FACT
    Prayer times are solar: they move a minute or two every day and they are
    defined by a calculation convention, not by a table. A model answering from
    memory is wrong twice — stale and, quite often, using somebody else's
    method. This fetches, dates, and names the convention.

THE DEFAULTS, AND WHY THEY ARE THOSE
    method 20 is Kemenag's (Kementerian Agama RI), the official Indonesian
    calculation; school 0 is Shafi, which is what the answer assumes unless the
    user says Hanafi. Both are parameters, both are echoed in the answer, and
    both can be changed once in the plugin settings instead of in every sentence
    ("my city is Bandung" is a fact about the user, not about today).

WHAT IT REFUSES TO DO
    * It does not guess a city from nothing. No city at all and no saved default
      is a question back — an answer for the wrong city is worse than a question.
    * It does not claim a Hijri date as official. The service's date can differ
      by a day from the government's decree, and the sentence says so.
    * It does not add the local mosque's ihtiyati (the 2-minute safety margin).
      That is a local convention this app has no way to know.
"""
from __future__ import annotations

from datetime import datetime, timezone

from plugins import _prayer

PLUGIN = {
    "name": "prayer_times",
    "description": (
        "Look up today's (or a given date's) Islamic prayer times — Subuh/Fajr, "
        "Dzuhur/Dhuhr, Ashar/Asr, Maghrib, Isya/Isha — for a city, with the next "
        "prayer and how long until it. Use for 'jam berapa maghrib di Bandung', "
        "'kapan subuh besok', 'prayer times in Jakarta'. Defaults to Bandung and "
        "Indonesia with the Kemenag (method 20) calculation; say so if the user "
        "names another city or country. Never answer a prayer time from memory."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "city": {
                "type": "STRING",
                "description": ("City name, e.g. Bandung, Jakarta, Makassar, "
                                "Surabaya. Omit to use the saved default."),
            },
            "country": {
                "type": "STRING",
                "description": "Country name. Default Indonesia.",
            },
            "date": {
                "type": "STRING",
                "description": ("Optional YYYY-MM-DD (today if omitted). For "
                                "'besok' or 'tanggal 20', work out the date "
                                "yourself and pass it here."),
            },
            "school": {
                "type": "INTEGER",
                "description": ("Asr rule: 0 (default, Shafi) or 1 (Hanafi). The "
                                "two genuinely differ by up to an hour."),
            },
        },
        "required": [],
    },
    # A single HTTP GET; the assistant keeps talking while it lands.
    "behavior": "NON_BLOCKING",
    "scheduling": "WHEN_IDLE",
    "tier": "core",
}

# Defaults live in the settings panel once and in the tool call only when the
# user overrides them: "my city is Bandung" is a fact about the person, not
# about today's question, and repeating it in every call is how it gets
# forgotten on the one day it mattered.
PLUGIN_SETTINGS = {
    "namespace": "prayer_times",
    "title": "Prayer times",
    "fields": [
        {"key": "city", "label": "City", "type": "text", "default": "Bandung",
         "placeholder": "Bandung"},
        {"key": "country", "label": "Country", "type": "text", "default": "Indonesia"},
        {"key": "method", "label": "Calculation method (Aladhan id)",
         "type": "text", "default": str(_prayer.DEFAULT_METHOD),
         "placeholder": "20 = Kemenag"},
        {"key": "school", "label": "Asr school (0 = Shafi, 1 = Hanafi)",
         "type": "text", "default": "0"},
    ],
}


def _setting(key: str, fallback: str) -> str:
    """A saved setting, or the fallback. Never raises: a plugin whose settings
    file is unreadable must still be able to answer about today."""
    try:
        from memory.config_manager import get_plugin_setting
        value = get_plugin_setting("prayer_times", key, fallback)
    except Exception:
        return fallback
    text = str(value if value is not None else fallback).strip()
    return text or fallback


def _int(text: str, fallback: int) -> int:
    try:
        return int(float(text))
    except (TypeError, ValueError):
        return fallback


def _iso_day(raw: str) -> str:
    """YYYY-MM-DD → DD-MM-YYYY, which is what the service wants. A date this
    code cannot read is refused rather than silently replaced with today: "kapan
    subuh 20 November" answered with today's date is a wrong answer that looks
    like a right one."""
    text = str(raw or "").strip()
    if not text:
        return ""
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%Y/%m/%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(text, fmt).strftime("%d-%m-%Y")
        except ValueError:
            continue
    raise ValueError(f"I could not read {raw!r} as a date — use YYYY-MM-DD.")


def _tomorrow_note(timings, asked: str) -> str:
    """When the date asked for is not today, say which day it is: "besok" has no
    meaning in a transcript read the day after."""
    if not asked or timings.day is None:
        return ""
    if timings.day == datetime.now(timezone.utc).date():
        return ""
    return f" ({timings.day.strftime('%A')})"


def run(parameters: dict, player=None, session_memory=None) -> str:
    parameters = parameters or {}
    city = str(parameters.get("city") or "").strip() or _setting("city", "Bandung")
    country = (str(parameters.get("country") or "").strip()
               or _setting("country", "Indonesia"))
    method = _int(str(parameters.get("method") or _setting("method", str(_prayer.DEFAULT_METHOD))),
                  _prayer.DEFAULT_METHOD)
    school_raw = parameters.get("school")
    school = _int(str(school_raw if school_raw is not None else _setting("school", "0")), 0)

    try:
        when = _iso_day(str(parameters.get("date") or ""))
        timings = _prayer.fetch(city, country, method, school, when)
    except ValueError as e:
        message = str(e)
        return f"Sir, {message[0].lower() + message[1:] if message else message}"
    except _prayer.PrayerError as e:
        return (f"Sir, I could not get the prayer times for {city} ({e}). "
                "I would rather say that than quote a time from memory.")

    answer = _prayer.describe(timings) + _tomorrow_note(timings, when)
    if player:
        try:
            player.write_log("JARVIS: " + " · ".join(
                f"{name} {clock}" for name, clock in _prayer.day_table(timings)))
        except Exception:
            pass          # a failed log line must not fail the times
    return answer
