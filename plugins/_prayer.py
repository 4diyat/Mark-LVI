"""Prayer times from Aladhan — the numbers, and the four things they depend on.

WHY THIS NEEDS A PLUGIN AT ALL
    "Jam berapa maghrib di Bandung?" has an exact answer that changes every day
    and cannot be recalled: prayer times are solar, they shift by a minute or
    two daily, and the model has no clock. Guessing is not merely stale here, it
    is wrong in a way that matters.

WHY ALADHAN, AND WHY `method=20`
    Aladhan (api.aladhan.com) is free, needs no key, and covers every city by
    name. The calculation METHOD is the whole ballgame: Fajr and Isha are
    defined by the sun's angle below the horizon, and different authorities use
    different angles — so the same city on the same day has a Fajr that differs
    by up to twenty minutes depending on who computed it. Indonesia's official
    method is Kemenag's (Kementerian Agama), which Aladhan implements as
    method=20; that is the default here, and the answer always names the method
    that produced the number, because a timestamp without its convention is a
    rumour with a colon in it.

THE FOUR THINGS A TIME DEPENDS ON, ALL OF THEM REPORTED
    1. THE METHOD — Kemenag, MWL, ISNA, Umm al-Qura… (see `METHODS`).
    2. THE JURISTIC SCHOOL for Asr — Shafi (school=0) or Hanafi (school=1).
       Asr genuinely differs, sometimes by an hour, because the shadow-length
       rule is the one schools disagree about.
    3. THE CITY, and therefore its TIME ZONE. The reply carries the zone in
       `meta.timezone` (e.g. `Asia/Jakarta`), and the times are local to THAT
       city. Someone in Bandung asking about Makassar gets WITA times, which is
       an hour ahead of their own clock — so the zone is said out loud rather
       than assumed to be the user's.
    4. THE DATE — including the Hijri one, which is what people actually ask
       about in Ramadan. The API's Hijri date can differ by a day from the
       government's decree, so it is reported as the API's, not as an
       announcement.

WHAT THIS DOES NOT DO
    It does not decide when to pray, and it does not adjust for a local mosque's
    ihtiyati (safety margin, usually 2 minutes) — Aladhan takes a `tune` for
    that, and the plugin does not pretend to know the local convention.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date as _date, datetime, timedelta, timezone
from urllib import request as _urlrequest

TIMEOUT_S = 8
ENDPOINT = "https://api.aladhan.com/v1/timingsByCity/{when}?city={city}&country={country}&method={method}&school={school}"

# The calculation methods, by Aladhan's id. Short on purpose: the ones a user is
# likely to be under, plus every method used in South-East Asia.
METHODS = {
    20: "Kemenag (Kementerian Agama, Indonesia)",
    17: "JAKIM (Malaysia)",
    11: "Majlis Ugama Islam Singapura",
    3: "Muslim World League",
    2: "Islamic Society of North America (ISNA)",
    4: "Umm al-Qura (Makkah)",
    1: "University of Islamic Sciences, Karachi",
    5: "Egyptian General Authority of Survey",
    8: "Gulf Region",
    9: "Kuwait",
    10: "Qatar",
    13: "Diyanet (Turkey)",
    15: "Moonsighting Committee",
    16: "Dubai",
}
DEFAULT_METHOD = 20          # Kemenag — this app's users are in Indonesia

# The five prayers, in order. Sunrise is not a prayer but is in the reply and is
# what people use to know when Fajr's window ends, so it travels with them.
PRAYERS = ("Fajr", "Sunrise", "Dhuhr", "Asr", "Maghrib", "Isha")
OBLIGATORY = ("Fajr", "Dhuhr", "Asr", "Maghrib", "Isha")


class PrayerError(RuntimeError):
    """A sentence for a person: unknown city, no network, unusable reply."""


@dataclass
class Timings:
    city: str
    country: str
    zone: str = ""                       # IANA name from meta.timezone
    utc_offset: timedelta = timedelta(0)
    method: str = ""
    school: int = 0
    times: dict[str, datetime] = field(default_factory=dict)   # aware, in the city's zone
    day: _date | None = None
    hijri: str = ""
    latitude: float = 0.0
    longitude: float = 0.0
    offset_known: bool = True

    def next_prayer(self, now: datetime | None = None) -> tuple[str, datetime] | None:
        """The next obligatory prayer at or after `now`, on this day's table.

        `now` is compared in the CITY's zone, not the machine's: someone in
        Jakarta asking about Makassar is an hour behind the table they are being
        read, and comparing a naive local time to it would answer with a prayer
        that already passed.
        """
        if not self.times or not self.offset_known:
            # Without the offset, "next" would be computed against UTC and could
            # name a prayer that passed hours ago. No answer is better.
            return None
        reference = (now or datetime.now(timezone.utc))
        if reference.tzinfo is None:
            reference = reference.replace(tzinfo=timezone.utc)
        local = reference.astimezone(timezone(self.utc_offset))
        for name in OBLIGATORY:
            when = self.times.get(name)
            if when is not None and when >= local:
                return name, when
        return None


def _zone_offset(zone_name: str, *values: str) -> timedelta | None:
    """How far the city's clock is from UTC, from the payload alone.

    THE ORDER HERE IS NOT THE OBVIOUS ONE, AND THE OBVIOUS ONE WAS WRONG
        The first version resolved `meta.timezone` through `zoneinfo`, which is
        the better answer — an hour is not a zone, because a zone follows DST
        and an offset does not. It also made the tests pass on a Linux machine
        and FAIL ON BOTH WINDOWS RUNNERS in CI: Python on Windows has no system
        tz database, and `tzdata` is not a dependency of this project. Every
        zone name resolved to nothing there, the offset fell through to the
        `(+07)` suffix that Aladhan only puts in `Sunrise`, and Jakarta came
        out as UTC+0.

        So: the `(+07)` suffix first, because it is IN THE REPLY and needs no
        database; the IANA name second, for the cases where the suffix is
        absent; and None — "cannot tell" — when neither is there. Tests pin both
        paths, and one of them pins that a missing tz database cannot change the
        answer.
    """
    for value in values:
        text = str(value or "")
        if "(" not in text or ")" not in text:
            continue
        inside = text[text.index("(") + 1:text.rindex(")")].strip()
        if len(inside) < 3 or inside[0] not in "+-" or not inside[1:].isdigit():
            continue     # "(WIB)" — a zone NAME, not an offset
        sign = 1 if inside[0] == "+" else -1
        return timedelta(hours=sign * int(inside[1:]))
    name = str(zone_name or "").strip()
    if name:
        try:
            from zoneinfo import ZoneInfo
            reference = datetime(2026, 1, 1, tzinfo=timezone.utc)
            return reference.astimezone(ZoneInfo(name)).utcoffset() or timedelta(0)
        except Exception:
            # No tzdata on this machine (the normal case on Windows), or a zone
            # name this build does not know. Returning None lets the caller say
            # it cannot tell instead of pretending UTC.
            pass
    return None


def _clock(value: str) -> tuple[int, int] | None:
    """`04:32 (+07)` → (4, 32). Anything else → None, and the caller drops it:
    a prayer time this module could not read must not become 00:00."""
    head = str(value or "").strip().split(" ")[0]
    if ":" not in head:
        return None
    hour, _, minute = head.partition(":")
    if not (hour.isdigit() and minute.isdigit()):
        return None
    return int(hour) % 24, int(minute) % 60


def parse(payload: dict, city: str, country: str, school: int = 0) -> Timings:
    """The Aladhan reply → Timings, or PrayerError with its own reason."""
    data = (payload or {}).get("data")
    if not isinstance(data, dict):
        raise PrayerError("the prayer-times service returned no data for that city")
    timings = data.get("timings") or {}
    meta = data.get("meta") or {}
    date_info = data.get("date") or {}

    # Every timing value, because the offset is not in the one you look at
    # first: `Fajr` is "04:22" and `Sunrise` is "05:34 (+07)".
    raw_values = [str(v) for v in timings.values() if isinstance(v, str)]
    offset = _zone_offset(str(meta.get("timezone") or ""), *raw_values)
    # timezone() rejects None, and a reply with neither an IANA name nor a
    # "(+07)" suffix is a real case — a bare Windows Python with no tzdata
    # asking about a city the service only labels by name.
    known_offset = offset is not None
    zone = timezone(offset if known_offset else timedelta(0))

    grouped = date_info.get("gregorian") or {}
    day = None
    try:
        day = datetime.strptime(str(grouped.get("date") or ""), "%d-%m-%Y").date()
    except ValueError:
        # The reply usually carries `timestamp`, which is a date we can trust
        # more than a string we failed to parse.
        try:
            day = datetime.fromtimestamp(int(date_info.get("timestamp")),
                                         tz=zone).date()
        except (TypeError, ValueError, OSError):
            day = None

    parsed: dict[str, datetime] = {}
    if day is not None:
        for name in PRAYERS:
            clock = _clock(timings.get(name, ""))
            if clock is None:
                continue
            parsed[name] = datetime(day.year, day.month, day.day,
                                    clock[0], clock[1], tzinfo=zone)

    if not parsed:
        # Every timing was unreadable. Better a refusal here than a sentence
        # listing nothing, which reads like "there are no prayers today".
        raise PrayerError(
            f"{city} came back without a single readable prayer time — the reply "
            "was not the shape this plugin understands.")

    hijri_info = date_info.get("hijri") or {}
    month = (hijri_info.get("month") or {}).get("en") or ""
    hijri = " ".join(part for part in (str(hijri_info.get("day") or ""), month,
                                       str(hijri_info.get("year") or "")) if part)

    method_id = (meta.get("method") or {}).get("id")
    method = (meta.get("method") or {}).get("name") or ""
    if not method:
        try:
            method = METHODS.get(int(method_id), "")
        except (TypeError, ValueError):
            method = ""
    return Timings(
        city=str(meta.get("city") or city),
        country=country,
        zone=str(meta.get("timezone") or ""),
        utc_offset=offset if offset is not None else timedelta(0),
        offset_known=known_offset,
        method=str(method),
        school=school,
        times=parsed,
        day=day,
        hijri=hijri,
        latitude=float(meta.get("latitude") or 0.0),
        longitude=float(meta.get("longitude") or 0.0),
    )


def _get(url: str) -> dict:
    """One HTTP GET, kept tiny so the tests can replace exactly this."""
    req = _urlrequest.Request(url, headers={
        "User-Agent": "MARK-LVI/1.0 (prayer_times plugin)",
        "Accept": "application/json"})
    with _urlrequest.urlopen(req, timeout=TIMEOUT_S) as response:   # noqa: S310
        return json.loads(response.read().decode("utf-8", "replace"))


def fetch(city: str, country: str = "Indonesia", method: int = DEFAULT_METHOD,
          school: int = 0, when: str = "") -> Timings:
    """Today's times for a city, or PrayerError with a sentence.

    `when` is DD-MM-YYYY (the API's spelling). Empty means today.
    """
    city = " ".join(str(city or "").split())
    if not city:
        raise ValueError("which city? I need a name like Bandung or Makassar.")
    country = " ".join(str(country or "Indonesia").split())
    method = int(method)
    if method not in METHODS:
        raise ValueError(
            f"I do not know calculation method {method}; I have "
            + ", ".join(f"{mid} ({METHODS[mid].split(' (')[0]})" for mid in sorted(METHODS))
            + ".")
    if school not in (0, 1):
        raise ValueError("school is 0 for Shafi (the default here) or 1 for Hanafi.")
    url = ENDPOINT.format(when=when, city=city.replace(" ", "+"),
                          country=country.replace(" ", "+"),
                          method=method, school=school)
    try:
        payload = _get(url)
    except Exception as e:      # noqa: BLE001 — the network has many ways to fail
        raise PrayerError(f"could not reach the prayer-times service ({e})") from e
    return parse(payload, city, country, school)


def zone_is_known(name: str) -> bool:
    """Can this machine resolve the zone name? False on a bare Windows Python
    with no `tzdata` installed.

    Not used to decide the offset — the payload's own `(+07)` wins, because it
    does not need a database that Windows may not have. This exists so a caller
    (and a test) can ask the question directly, and so the reason the fallback
    order is what it is stays visible in the code."""
    try:
        from zoneinfo import ZoneInfo
        ZoneInfo(name)
        return True
    except Exception:
        return False


def _clock_text(when: datetime) -> str:
    return when.strftime("%H:%M")


def describe(timings: Timings, now: datetime | None = None) -> str:
    """The sentence: the five times, the next one, and the three caveats."""
    if not timings.times:
        raise PrayerError(
            f"no prayer times came back for {timings.city} — check the city name "
            "and the country; the service matches both.")
    day = timings.day.strftime("%d %B %Y") if timings.day else "today"
    offset_hours = timings.utc_offset.total_seconds() / 3600
    zone = f" in {timings.zone}" if timings.zone else ""
    if timings.offset_known:
        where = f"local time{zone}, UTC{offset_hours:+g}"
    else:
        # No resolvable zone name and no "(+07)" suffix in the payload. Printing
        # "+0" under an Indonesian city is an hour of error with a confident
        # label on it, which is the failure this plugin exists to avoid.
        where = f"local time{zone} (the city's UTC offset could not be determined)"
    said = (f"Prayer times for {timings.city}, {timings.country}, {day}: "
            + ", ".join(f"{name} {_clock_text(timings.times[name])}"
                        for name in OBLIGATORY if name in timings.times)
            + f" ({where}).")

    upcoming = timings.next_prayer(now)
    if upcoming is not None:
        name, when = upcoming
        left = when - (now or datetime.now(timezone.utc)).astimezone(
            timezone(timings.utc_offset))
        minutes = int(left.total_seconds() // 60)
        hours, minutes = divmod(max(minutes, 0), 60)
        wait = f"{hours} h {minutes} m" if hours else f"{minutes} m"
        said += f" Next is {name} at {_clock_text(when)}, in {wait}."
    else:
        said += " All of today's prayers have passed."

    said += f" Method: {timings.method or 'as supplied by the service'}"
    if timings.school == 1:
        said += ", Asr by the Hanafi rule"
    said += "."
    if timings.hijri:
        said += (f" The service dates it {timings.hijri} AH — its Hijri date can "
                 "differ by a day from the official decree.")
    return said


def day_table(timings: Timings) -> list[tuple[str, str]]:
    """(name, HH:MM) including Sunrise, for a table or a log line."""
    return [(name, _clock_text(timings.times[name]))
            for name in PRAYERS if name in timings.times]
