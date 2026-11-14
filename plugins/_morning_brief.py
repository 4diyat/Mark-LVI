"""Bounded, opt-in data sources for the startup brief. No Qt or order APIs."""
from __future__ import annotations

import os
import tempfile
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
CALENDAR_TOKEN = BASE_DIR / "config" / "token_calendar.json"
CALENDAR_SCOPE = ["https://www.googleapis.com/auth/calendar.events.readonly"]


def _credential_path(values: dict) -> Path:
    path = Path(str(values.get("calendar_credentials_path") or "config/calendar_credentials.json")).expanduser()
    return path if path.is_absolute() else BASE_DIR / path


def _save_token(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    name = None
    try:
        fd, name = tempfile.mkstemp(prefix=".calendar-token-", dir=str(path.parent))
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(name, path)
        name = None
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
    finally:
        if name:
            os.unlink(name)


def authorize_calendar(values: dict | None = None) -> tuple[bool, str]:
    """Explicit user-click only: opens OAuth consent in the browser."""
    path = _credential_path(values or {})
    if not path.is_file():
        return False, "Calendar OAuth desktop credentials not found. Configure the credentials path first."
    try:
        from google_auth_oauthlib.flow import InstalledAppFlow
        flow = InstalledAppFlow.from_client_secrets_file(str(path), CALENDAR_SCOPE)
        creds = flow.run_local_server(port=0, timeout_seconds=120)
        _save_token(CALENDAR_TOKEN, creds.to_json())
        return True, "Calendar authorized read-only. Morning Brief can now read today's events."
    except Exception as exc:
        # OAuth errors can contain secrets; do not return exception details.
        return False, f"Calendar authorization failed ({type(exc).__name__}). Check credentials and try again."


def weather(values: dict) -> str:
    city = str(values.get("city") or "").strip()
    country = str(values.get("country_code") or "").strip().upper()
    if not city:
        return "Not configured: enter a weather city in Morning Brief settings."
    if len(city) > 100 or (country and (len(country) != 2 or not country.isalpha())):
        return "Invalid city or country code in Morning Brief settings."
    import requests
    result = requests.get("https://geocoding-api.open-meteo.com/v1/search",
                          params={"name": city, "count": 10, "language": "en", "format": "json"},
                          timeout=(3, 4))
    result.raise_for_status()
    places = result.json().get("results") or []
    if country:
        places = [p for p in places if str(p.get("country_code") or "").upper() == country]
    if not places:
        return "Weather location not found; check the city and country code."
    place = places[0]
    forecast = requests.get("https://api.open-meteo.com/v1/forecast", params={
        "latitude": place["latitude"], "longitude": place["longitude"],
        "current": "temperature_2m,weather_code,wind_speed_10m",
        "daily": "temperature_2m_max,temperature_2m_min,precipitation_probability_max",
        "forecast_days": 1, "timezone": "auto"}, timeout=(3, 4))
    forecast.raise_for_status()
    obj = forecast.json()
    cur, daily = obj.get("current") or {}, obj.get("daily") or {}
    temp = cur.get("temperature_2m")
    high = (daily.get("temperature_2m_max") or [None])[0]
    low = (daily.get("temperature_2m_min") or [None])[0]
    rain = (daily.get("precipitation_probability_max") or [None])[0]
    if any(v is None for v in (temp, high, low)):
        return "Weather service returned incomplete data."
    label = ", ".join(str(place.get(k) or "") for k in ("name", "admin1", "country") if place.get(k))
    rain_text = f", max rain probability {rain}%" if rain is not None else ""
    return (f"{label}: {temp}°C now; today's low {low}°C, high {high}°C{rain_text}. "
            f"Time zone: {obj.get('timezone', 'unknown')}; observation {cur.get('time', 'unknown')}. Source: Open-Meteo.")


def _calendar_service():
    if not CALENDAR_TOKEN.is_file():
        return None
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    import google_auth_httplib2
    import httplib2
    from googleapiclient.discovery import build

    creds = Credentials.from_authorized_user_file(str(CALENDAR_TOKEN), CALENDAR_SCOPE)
    if not creds.valid:
        if not (creds.expired and creds.refresh_token):
            return None
        transport = Request()
        def bounded_request(*args, **kwargs):
            kwargs.setdefault("timeout", 6)
            return transport(*args, **kwargs)
        creds.refresh(bounded_request)
        _save_token(CALENDAR_TOKEN, creds.to_json())
    http = google_auth_httplib2.AuthorizedHttp(creds, http=httplib2.Http(timeout=6))
    return build("calendar", "v3", http=http, cache_discovery=False)


def calendar(values: dict, *, service_factory=None, now=None) -> str:
    """Today's upcoming primary-calendar events; never starts interactive OAuth."""
    service = (service_factory or _calendar_service)()
    if service is None:
        return "Not authorized: use AUTHORIZE GOOGLE CALENDAR in Morning Brief settings."
    # Use the machine's local zone for both midnight boundaries; calculating
    # each independently respects a DST change between them.
    now = now or datetime.now().astimezone()
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("Calendar time must be timezone-aware.")
    tomorrow = now.date() + timedelta(days=1)
    end = datetime.combine(tomorrow, datetime.min.time()).astimezone()
    result = service.events().list(calendarId="primary", timeMin=now.isoformat(),
                                   timeMax=end.isoformat(), singleEvents=True,
                                   orderBy="startTime", maxResults=6,
                                   fields="items(start,summary),nextPageToken").execute()
    rows = []
    for event in result.get("items", [])[:5]:
        start = event.get("start") or {}
        raw = start.get("dateTime") or start.get("date") or ""
        if start.get("dateTime"):
            try:
                raw = datetime.fromisoformat(raw.replace("Z", "+00:00")).astimezone().strftime("%H:%M %Z")
            except ValueError:
                raw = "time unavailable"
        else:
            raw = "all day"
        title = " ".join(str(event.get("summary") or "(untitled)").split())[:120]
        rows.append(f"{raw}: {title}")
    if not rows:
        return "No upcoming events for the rest of today (primary calendar, local time)."
    return "Today's upcoming events (primary calendar, local time): " + "; ".join(rows)


def gmail(_values: dict) -> str:
    from plugins import _gmail
    cfg = _gmail.load_settings()
    try:
        client = _gmail.choose_backend(cfg)
        if isinstance(client, _gmail.OAuthGmailClient):
            # Startup must never cause a browser authorization popup.
            client.allow_interactive = False
        count = client.unread_count("INBOX")
    except _gmail.GmailError:
        return "Gmail unavailable; check Gmail Inbox settings or authorize it first."
    return f"Gmail inbox: {int(count)} unread messages. No message bodies were read."


def market(_values: dict) -> str:
    from memory.config_manager import get_plugin_config
    from plugins import _trading_terminal
    snap = _trading_terminal.snapshot(get_plugin_config("trading_terminal"))
    lines = [f"{snap['settings']['symbol']} bid {snap['bid']:.5f}, ask {snap['ask']:.5f}; "
             f"tick {snap['tick_time']:%Y-%m-%d %H:%M:%S UTC}; "
             + ("recent" if snap["fresh"] else "STALE, no current signal")]
    for name, item in snap["sessions"].items():
        levels = (f"high {item['high']:.5f}, low {item['low']:.5f}"
                  if item["high"] is not None else "range unavailable")
        state = item["state"]
        if item.get("data_stale"):
            state += " (stale)"
        lines.append(f"{name}: {state}; {levels}; range {item['start']:%Y-%m-%d %H:%M}–"
                     f"{item['range_end']:%H:%M} UTC ({item['timezone']})")
    return "; ".join(lines) + ". Observations only, not trade advice; no orders are placed."


def _enabled(values: dict, key: str) -> bool:
    val = values.get(key, True)
    return val if isinstance(val, bool) else str(val).strip().lower() not in ("0", "false", "off", "no", "")


def collect(values: dict, enabled_plugins: set[str], timeout: float = 8.0) -> dict[str, str]:
    """Fetch independently, with a shared deadline; slow services cannot stall startup.

    Each worker is daemonized so a slow SDK does not hold process shutdown open.
    A timed-out worker may finish in the background but cannot add to the result
    returned for this briefing. Personal data is not logged here.
    """
    if "morning_brief" not in enabled_plugins:
        return {}
    sources = (("Weather", "include_weather", weather, None),
               ("Calendar", "include_calendar", calendar, None),
               ("Gmail", "include_gmail", gmail, "gmail_inbox"),
               ("MT5 ORB", "include_market", market, "trading_terminal"))
    results: dict[str, str] = {}
    threads = []
    lock = threading.Lock()
    def launch(label, fn):
        def worker():
            try:
                text = fn(values)
            except Exception as exc:
                text = f"Unavailable ({type(exc).__name__}); check service setup and connection."
            with lock:
                results[label] = text
        thread = threading.Thread(target=worker, daemon=True, name="brief-source")
        thread.start()
        threads.append(thread)
    for label, flag, fn, required in sources:
        if not _enabled(values, flag):
            continue
        if required and required not in enabled_plugins:
            with lock:
                results[label] = f"Unavailable: enable the {required} plugin first."
        else:
            launch(label, fn)
    deadline = time.monotonic() + max(0.0, timeout)
    for thread in threads:
        thread.join(max(0.0, deadline - time.monotonic()))
    with lock:
        copy = dict(results)
    return {label: copy.get(label, "Timed out; try again later.")
            for label, flag, _, _ in sources if _enabled(values, flag)}
