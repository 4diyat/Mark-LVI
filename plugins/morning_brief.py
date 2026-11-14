"""Settings and explicit Calendar authorization for the expanded morning brief."""
from plugins import _morning_brief

PLUGIN = {
    "name": "morning_brief",
    "description": ("Configure the startup briefing: local weather, today's Calendar, "
                    "unread Gmail count and read-only MT5 session information. "
                    "Calendar access requires explicit authorization; Gmail and MT5 "
                    "also require their own plugins enabled. Calendar event titles and "
                    "weather city may be sent to external services and the assistant model. "
                    "Never places orders."),
    "parameters": {"type": "OBJECT", "properties": {}, "required": []},
    "behavior": "NON_BLOCKING", "scheduling": "WHEN_IDLE", "tier": "extra",
}

PLUGIN_SETTINGS = {
    "namespace": "morning_brief", "title": "Morning Brief — sources",
    "fields": [
        {"key": "city", "label": "Weather city (required)", "type": "text", "default": "", "placeholder": "Bandung"},
        {"key": "country_code", "label": "Weather country code, e.g. ID (optional)", "type": "text", "default": ""},
        {"key": "include_weather", "label": "Include weather", "type": "toggle", "default": True},
        {"key": "include_calendar", "label": "Include Calendar titles (sent to assistant)", "type": "toggle", "default": True},
        {"key": "include_gmail", "label": "Include Gmail unread count", "type": "toggle", "default": True},
        {"key": "include_market", "label": "Include read-only MT5 ORB", "type": "toggle", "default": True},
        {"key": "calendar_credentials_path", "label": "Google Calendar OAuth desktop credentials path", "type": "text", "default": "config/calendar_credentials.json"},
    ],
    "action": {"label": "AUTHORIZE GOOGLE CALENDAR", "run": _morning_brief.authorize_calendar},
}


def run(parameters: dict, player=None, session_memory=None) -> str:
    return ("Configure Morning Brief in Plugin Settings. It runs at startup; "
            "Calendar authorization, Gmail and MT5 require their own setup.")
