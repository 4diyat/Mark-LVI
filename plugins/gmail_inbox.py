"""gmail_inbox — check incoming Gmail messages and read them aloud or on screen.

WHAT THIS PLUGIN DOES
    * Check inbox / unread emails / filter by sender or keyword (`action="check"`
      or `"unread"`), showing a numbered list and remembering the message IDs so
      you can immediately say "read email #1".
    * Read the full body and attachment names of an incoming email (`action="read"`).
    * Count unread emails (`action="count"`).

HOW IT CONNECTS TO GMAIL
    Supports two read-only ways to connect (configured in ⚙ → Plugin Settings):
      1. Gmail App Password over IMAP SSL (`imap.gmail.com:993`) — uses Python's
         standard library (`imaplib` / `email`), needs zero extra packages, and
         opens the mailbox with `readonly=True` + `BODY.PEEK` so checking emails
         never silently marks unread messages as read.
      2. Gmail OAuth (`gmail.readonly` scope) via `config/gmail_credentials.json`
         if `google-api-python-client` and `google-auth-oauthlib` are installed.

WHAT IT REFUSES TO DO
    It is strictly read-only: it never sends, deletes, archives, or modifies
    messages, and it never leaks stored passwords or tokens in logs or replies.
"""
from __future__ import annotations

from plugins import _gmail

PLUGIN = {
    "name": "gmail_inbox",
    "description": (
        "Check incoming Gmail messages, count unread emails, and read the full "
        "content of a selected email. Use for 'cek email masuk', 'ada email baru "
        "di Gmail?', 'berapa email yang belum dibaca?', 'cek email dari Budi', "
        "'bacakan email nomor 1', or 'read my latest Gmail'. Read-only: cannot "
        "send or delete emails."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": (
                    "'check' (default — list recent/matching incoming emails), "
                    "'unread' (list only unread emails), 'read' (read full body "
                    "of a specific email), or 'count' (count unread emails)."
                ),
            },
            "unread_only": {
                "type": "BOOLEAN",
                "description": "True to show only unread emails.",
            },
            "sender": {
                "type": "STRING",
                "description": "Filter by sender name or email address.",
            },
            "query": {
                "type": "STRING",
                "description": "Filter by subject or body keyword.",
            },
            "message_id": {
                "type": "STRING",
                "description": (
                    "1-based number from the last email list (e.g. '1' or '#2') "
                    "or raw message UID/ID to read in full."
                ),
            },
            "limit": {
                "type": "INTEGER",
                "description": "Max number of emails to fetch when checking (1–15, default 5).",
            },
            "mailbox": {
                "type": "STRING",
                "description": "Mailbox/label to inspect (default 'INBOX').",
            },
        },
        "required": [],
    },
    "behavior": "NON_BLOCKING",
    "scheduling": "WHEN_IDLE",
    "tier": "core",
}


def test_connection(values: dict | None = None) -> tuple[bool, str]:
    """Verify Gmail credentials from Plugin Settings without raising."""
    try:
        cfg = _gmail.load_settings(values)
        client = _gmail.choose_backend(cfg)
        return True, client.test_connection()
    except _gmail.GmailError as exc:
        return False, str(exc)
    except Exception as exc:      # noqa: BLE001 — UI test button expects (ok, msg)
        return False, f"Connection test failed: {exc}"


PLUGIN_SETTINGS = {
    "namespace": "gmail_inbox",
    "title": "Gmail Inbox",
    "fields": [
        {
            "key": "auth_mode",
            "label": "Auth mode",
            "type": "choice",
            "options": ["auto", "imap_app_password", "oauth"],
            "default": "auto",
        },
        {
            "key": "email",
            "label": "Gmail address",
            "type": "text",
            "default": "",
            "placeholder": "nama@gmail.com",
        },
        {
            "key": "app_password",
            "label": "Gmail App Password (16 chars, IMAP)",
            "type": "password",
            "default": "",
            "placeholder": "xxxx xxxx xxxx xxxx",
        },
        {
            "key": "credentials_path",
            "label": "OAuth credentials.json path (optional)",
            "type": "text",
            "default": "config/gmail_credentials.json",
            "placeholder": "config/gmail_credentials.json",
        },
        {
            "key": "default_limit",
            "label": "Default email count per check",
            "type": "text",
            "default": str(_gmail.DEFAULT_LIMIT),
            "placeholder": str(_gmail.DEFAULT_LIMIT),
        },
    ],
    "action": {
        "label": "TEST GMAIL CONNECTION",
        "run": test_connection,
    },
}


def _ui_log(player, text: str) -> None:
    if not player:
        return
    try:
        player.write_log(f"JARVIS: {text}")
    except Exception:
        pass


def _ui_panel(player, title: str, text: str) -> None:
    if not player or not hasattr(player, "show_content"):
        return
    try:
        player.show_content(title, text)
    except Exception:
        pass


def _parse_bool(val, default: bool = False) -> bool:
    if isinstance(val, bool):
        return val
    if val is None:
        return default
    text = str(val).strip().lower()
    if text in ("true", "1", "yes", "ya"):
        return True
    if text in ("false", "0", "no", "tidak"):
        return False
    return default


def _parse_limit(raw, fallback: int) -> int:
    if raw is None or str(raw).strip() == "":
        return fallback
    try:
        val = int(float(raw))
    except (TypeError, ValueError):
        return fallback
    return max(1, min(_gmail.MAX_LIMIT, val))


def run(parameters: dict, player=None, session_memory=None) -> str:
    parameters = dict(parameters or {})
    action = str(parameters.get("action") or "check").strip().lower()
    sender = str(parameters.get("sender") or "").strip()
    query = str(parameters.get("query") or "").strip()
    mailbox = str(parameters.get("mailbox") or "INBOX").strip() or "INBOX"
    raw_id = str(parameters.get("message_id") or "").strip()

    try:
        cfg = _gmail.load_settings()
        client = _gmail.choose_backend(cfg)

        if action in ("count", "unread_count"):
            count = client.unread_count(mailbox=mailbox)
            reply = f"Ada {count} email yang belum dibaca di Gmail ({mailbox})."
            _ui_log(player, reply)
            return reply

        if action in ("read", "open", "show", "detail"):
            uid = _gmail.resolve_message_id(raw_id) if raw_id else ""
            if not uid:
                unread = _parse_bool(parameters.get("unread_only"), default=False)
                matches, _ = client.list_messages(
                    unread_only=unread,
                    sender=sender,
                    query=query,
                    limit=1,
                    mailbox=mailbox,
                )
                if not matches:
                    return "Tidak ada email yang cocok untuk dibaca di Gmail."
                uid = matches[0].uid
            detail = client.read_message(uid, mailbox=mailbox)
            spoken, panel = _gmail.format_email_detail(detail)
            _ui_panel(player, f"GMAIL — {detail.subject[:36]}", panel)
            _ui_log(player, f"Email dari {detail.sender}: {detail.subject}")
            return spoken

        if action in ("check", "list", "inbox", "unread", "search"):
            unread = _parse_bool(
                parameters.get("unread_only"),
                default=(action == "unread"),
            )
            limit = _parse_limit(parameters.get("limit"), cfg["default_limit"])
            summaries, total = client.list_messages(
                unread_only=unread,
                sender=sender,
                query=query,
                limit=limit,
                mailbox=mailbox,
            )
            spoken, panel = _gmail.format_check_result(
                summaries, total, unread_only=unread
            )
            _ui_panel(player, f"GMAIL — {mailbox}", panel)
            _ui_log(player, spoken)
            return spoken

        return (
            f"Sir, aksi '{action}' tidak dikenal untuk gmail_inbox. "
            "Gunakan check, unread, read, atau count."
        )
    except _gmail.GmailError as exc:
        msg = f"Sir, Gmail belum siap atau gagal diakses: {exc}"
        _ui_log(player, msg)
        return msg
    except Exception as exc:      # noqa: BLE001 — never crash the tool loop
        msg = f"Sir, gagal memeriksa Gmail: {exc}"
        _ui_log(player, msg)
        return msg
