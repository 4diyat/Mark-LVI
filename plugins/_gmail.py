"""plugins/_gmail.py — Gmail IMAP + OAuth reader used by plugins/gmail_inbox.py.

Kept separate from gmail_inbox.py so parsing, formatting, and credential
resolution stay testable without touching the live network, and so
discover_plugins skips this helper cleanly (leading underscore).
"""
from __future__ import annotations

import base64
import email
import html
import imaplib
import os
import quopri
import re
import ssl
from dataclasses import dataclass, field
from email.header import decode_header
from email.utils import parseaddr, parsedate_to_datetime
from pathlib import Path
from typing import Any

IMAP_HOST = "imap.gmail.com"
IMAP_PORT = 993
TIMEOUT_S = 15
DEFAULT_LIMIT = 5
MAX_LIMIT = 15
MAX_BODY_CHARS = 3000
MAX_SNIPPET_CHARS = 180
READONLY_SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = BASE_DIR / "config"
DEFAULT_CREDENTIALS_PATH = CONFIG_DIR / "gmail_credentials.json"
DEFAULT_TOKEN_PATH = CONFIG_DIR / "gmail_token.json"

# Remembered UIDs from the most recent check/list so the user can say
# "read email #2" without knowing Gmail/IMAP message IDs.
_LAST_UIDS: list[str] = []


class GmailError(Exception):
    """Any predictable Gmail configuration, auth, or network problem."""


@dataclass
class EmailSummary:
    uid: str
    sender: str
    sender_email: str
    subject: str
    date: str
    snippet: str = ""
    unread: bool = False


@dataclass
class EmailDetail(EmailSummary):
    body: str = ""
    attachments: list[str] = field(default_factory=list)
    to: str = ""


def clear_recent_cache() -> None:
    _LAST_UIDS.clear()


def remember_recent_uids(uids: list[str]) -> None:
    _LAST_UIDS[:] = [str(u) for u in uids if str(u).strip()]


def resolve_message_id(raw_id: str) -> str:
    """Resolve '1' / '#2' against the last listed emails, else keep raw id."""
    text = str(raw_id or "").strip()
    if text.startswith("#"):
        text = text[1:].strip()
    if text.isdigit():
        idx = int(text)
        if 1 <= idx <= len(_LAST_UIDS):
            return _LAST_UIDS[idx - 1]
    return text


def decode_mime_header(value: Any) -> str:
    """Decode an RFC 2047 MIME header string safely."""
    raw = str(value or "")
    if not raw:
        return ""
    parts: list[str] = []
    for chunk, charset in decode_header(raw):
        if isinstance(chunk, bytes):
            enc = (charset or "utf-8").strip() or "utf-8"
            try:
                parts.append(chunk.decode(enc, errors="replace"))
            except LookupError:
                parts.append(chunk.decode("utf-8", errors="replace"))
        else:
            parts.append(str(chunk))
    return re.sub(r"\s+", " ", "".join(parts)).strip()


def format_sender(raw_from: str) -> tuple[str, str]:
    """Return `(display_label, email_address)` from a From header."""
    decoded = decode_mime_header(raw_from)
    name, addr = parseaddr(decoded)
    name = name.strip().strip('"')
    addr = addr.strip()
    if name and addr:
        return f"{name} <{addr}>", addr
    return addr or decoded or "Unknown sender", addr


def format_date(raw_date: str) -> str:
    """Normalize an email Date header into a short readable timestamp."""
    raw = decode_mime_header(raw_date)
    if not raw:
        return ""
    try:
        dt = parsedate_to_datetime(raw)
        if dt.tzinfo is not None:
            dt = dt.astimezone()
        return dt.strftime("%Y-%m-%d %H:%M")
    except Exception:
        return raw[:32]


def html_to_text(raw_html: str) -> str:
    """Turn an HTML email body into readable plain text."""
    text = str(raw_html or "")
    if not text:
        return ""
    text = re.sub(r"(?is)<(script|style|head).*?>.*?</\1>", " ", text)
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</(p|div|li|tr|h[1-6]|blockquote)>", "\n", text)
    text = re.sub(r"(?i)<li[^>]*>", "- ", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    lines = [re.sub(r"[ \t]+", " ", ln).strip() for ln in text.splitlines()]
    out: list[str] = []
    blank = False
    for ln in lines:
        if not ln:
            if out and not blank:
                out.append("")
            blank = True
        else:
            out.append(ln)
            blank = False
    return "\n".join(out).strip()


def _decode_bytes(payload: bytes, charset: str | None) -> str:
    if not payload:
        return ""
    for enc in [charset, "utf-8", "latin-1"]:
        if not enc:
            continue
        try:
            return payload.decode(enc, errors="replace")
        except LookupError:
            continue
    return payload.decode("utf-8", errors="replace")


def extract_email_parts(msg: email.message.Message) -> tuple[str, list[str]]:
    """Extract `(plain_text_body, attachment_names)` from a MIME Message."""
    plain_parts: list[str] = []
    html_parts: list[str] = []
    attachments: list[str] = []

    if msg.is_multipart():
        for part in msg.walk():
            if part.is_multipart():
                continue
            disp = str(part.get("Content-Disposition") or "").lower()
            fname = decode_mime_header(part.get_filename() or "")
            if fname:
                attachments.append(fname)
            if "attachment" in disp:
                continue
            ctype = (part.get_content_type() or "").lower()
            payload = part.get_payload(decode=True)
            if payload is None:
                continue
            decoded = _decode_bytes(payload, part.get_content_charset())
            if ctype == "text/plain" and decoded.strip():
                plain_parts.append(decoded.strip())
            elif ctype == "text/html" and decoded.strip():
                html_parts.append(decoded.strip())
    else:
        payload = msg.get_payload(decode=True)
        raw_text = (
            _decode_bytes(payload, msg.get_content_charset())
            if payload is not None
            else str(msg.get_payload() or "")
        )
        if (msg.get_content_type() or "").lower() == "text/html":
            html_parts.append(raw_text)
        elif raw_text.strip():
            plain_parts.append(raw_text.strip())

    body = "\n\n".join(plain_parts).strip() if plain_parts else ""
    if not body and html_parts:
        body = html_to_text("\n\n".join(html_parts))
    body = re.sub(r"\n{3,}", "\n\n", body).strip()
    if len(body) > MAX_BODY_CHARS:
        body = body[:MAX_BODY_CHARS].rstrip() + "\n...[truncated]"
    return body, attachments


def _snippet_from_body(body: str) -> str:
    clean = re.sub(r"\s+", " ", (body or "")).strip()
    if len(clean) <= MAX_SNIPPET_CHARS:
        return clean
    return clean[: MAX_SNIPPET_CHARS - 1].rstrip() + "…"


def _clean_imap_snippet(snippet_bytes: bytes) -> str:
    """Turn a partial IMAP BODY.PEEK[TEXT] slice into clean preview text."""
    if not snippet_bytes:
        return ""
    raw = _decode_bytes(snippet_bytes, "utf-8")
    low = raw.lower()
    is_qp = "quoted-printable" in low
    is_b64 = "content-transfer-encoding: base64" in low

    # Strip leading MIME boundary & Content-* lines emitted by multipart emails.
    body_lines: list[str] = []
    in_mime_hdr = False
    for line in raw.splitlines():
        s = line.strip()
        if s.startswith("--") and len(s) >= 6 and " " not in s:
            in_mime_hdr = True
            continue
        if in_mime_hdr:
            if not s:
                in_mime_hdr = False
                continue
            if re.match(r"^(content-[a-z-]+:|charset=)", s, re.I):
                continue
            # Continuation of folded Content-* header
            if line[:1] in (" ", "\t"):
                continue
            in_mime_hdr = False
        if re.match(r"^content-(type|transfer-encoding|disposition):", s, re.I):
            in_mime_hdr = True
            continue
        body_lines.append(line)

    text = "\n".join(body_lines).strip()
    if not text:
        return ""
    if is_qp:
        try:
            text = quopri.decodestring(text.encode("latin-1", errors="replace")).decode(
                "utf-8", errors="replace"
            )
        except Exception:
            pass
    elif is_b64:
        b64_clean = re.sub(r"\s+", "", text)
        pad = (-len(b64_clean)) % 4
        try:
            decoded = base64.b64decode(b64_clean + ("=" * pad), validate=False)
            decoded_txt = decoded.decode("utf-8", errors="replace")
            if decoded_txt.strip():
                text = decoded_txt
        except Exception:
            pass

    if "<" in text and ">" in text:
        text = html_to_text(text)
    return _snippet_from_body(text)


def _sanitize_imap_term(value: str) -> str:
    """Strip CR/LF and quote characters so IMAP SEARCH cannot be injected."""
    cleaned = re.sub(r"[\r\n\x00]+", " ", str(value or "")).strip()
    return cleaned.replace("\\", " ").replace('"', " ").strip()


def build_imap_search_args(
    *,
    unread_only: bool = False,
    sender: str = "",
    query: str = "",
) -> list[str]:
    """Build safe IMAP UID SEARCH criteria tokens."""
    args: list[str] = []
    if unread_only:
        args.append("UNSEEN")
    s_clean = _sanitize_imap_term(sender)
    if s_clean:
        args.extend(["FROM", f'"{s_clean}"'])
    q_clean = _sanitize_imap_term(query)
    if q_clean:
        args.extend(["OR", "SUBJECT", f'"{q_clean}"', "TEXT", f'"{q_clean}"'])
    if not args:
        args.append("ALL")
    return args


def build_gmail_query(
    *,
    unread_only: bool = False,
    sender: str = "",
    query: str = "",
) -> str:
    """Build a Gmail search query string for the REST API."""
    parts: list[str] = []
    if unread_only:
        parts.append("is:unread")
    s_clean = re.sub(r"[\r\n]+", " ", str(sender or "")).strip()
    if s_clean:
        parts.append(f"from:{s_clean}")
    q_clean = re.sub(r"[\r\n]+", " ", str(query or "")).strip()
    if q_clean:
        parts.append(q_clean)
    return " ".join(parts).strip()


def _resolve_path(raw: str, default: Path) -> Path:
    text = str(raw or "").strip()
    if not text:
        return default
    p = Path(text).expanduser()
    return p if p.is_absolute() else (BASE_DIR / p)


def _normalize_password(raw: str) -> str:
    # Google displays 16-char App Passwords in four groups separated by spaces.
    return "".join(str(raw or "").split())


def load_settings(overrides: dict | None = None) -> dict[str, Any]:
    """Read Gmail plugin settings from config_manager + keychain + env."""
    cfg: dict[str, Any] = {}
    try:
        from memory.config_manager import get_plugin_config
        stored = get_plugin_config("gmail_inbox")
        if isinstance(stored, dict):
            cfg.update(stored)
    except Exception:
        pass

    if isinstance(overrides, dict):
        for k, v in overrides.items():
            if v is not None and str(v).strip() != "":
                cfg[k] = v

    email_addr = (
        str(cfg.get("email") or "").strip()
        or str(os.environ.get("JARVIS_GMAIL_EMAIL") or "").strip()
    )
    app_pw = _normalize_password(str(cfg.get("app_password") or ""))
    if not app_pw:
        try:
            from core.keychain import get_secret
            app_pw = _normalize_password(get_secret("gmail_app_password") or "")
        except Exception:
            pass
    if not app_pw:
        app_pw = _normalize_password(
            os.environ.get("JARVIS_GMAIL_APP_PASSWORD") or ""
        )

    mode = str(cfg.get("auth_mode") or "auto").strip().lower()
    if mode not in ("auto", "imap_app_password", "oauth"):
        mode = "auto"

    cred_path = _resolve_path(
        str(cfg.get("credentials_path") or ""), DEFAULT_CREDENTIALS_PATH
    )
    token_path = _resolve_path(
        str(cfg.get("token_path") or ""), DEFAULT_TOKEN_PATH
    )
    try:
        limit = int(float(cfg.get("default_limit") or DEFAULT_LIMIT))
    except (TypeError, ValueError):
        limit = DEFAULT_LIMIT
    limit = max(1, min(MAX_LIMIT, limit))

    return {
        "auth_mode": mode,
        "email": email_addr,
        "app_password": app_pw,
        "credentials_path": cred_path,
        "token_path": token_path,
        "default_limit": limit,
    }


def _oauth_available() -> bool:
    try:
        import googleapiclient.discovery  # noqa: F401
        import google.oauth2.credentials  # noqa: F401
        return True
    except Exception:
        return False


def choose_backend(cfg: dict[str, Any]):
    """Select IMAP or OAuth backend from config, or raise GmailError."""
    mode = cfg["auth_mode"]
    has_imap = bool(cfg["email"] and cfg["app_password"])
    cred_p: Path = cfg["credentials_path"]
    tok_p: Path = cfg["token_path"]
    has_oauth_files = tok_p.is_file() or cred_p.is_file()

    if mode == "imap_app_password":
        if not has_imap:
            raise GmailError(
                "Gmail App Password belum diisi. Buka ⚙ → Plugin Settings → Gmail Inbox, "
                "isi alamat Gmail dan 16-karakter App Password Google Anda."
            )
        return ImapGmailClient(cfg["email"], cfg["app_password"])

    if mode == "oauth":
        if not _oauth_available():
            raise GmailError(
                "Mode OAuth butuh paket google-api-python-client dan google-auth-oauthlib. "
                "Install keduanya atau ubah auth_mode ke 'imap_app_password'."
            )
        if not has_oauth_files:
            raise GmailError(
                f"File kredensial OAuth tidak ditemukan di {cred_p}."
            )
        return OAuthGmailClient(cred_p, tok_p)

    # auto: prefer IMAP App Password when configured (zero extra deps), else OAuth
    if has_imap:
        return ImapGmailClient(cfg["email"], cfg["app_password"])
    if has_oauth_files and _oauth_available():
        return OAuthGmailClient(cred_p, tok_p)
    if has_oauth_files and not _oauth_available():
        raise GmailError(
            "File OAuth Gmail ada, tetapi paket google-api-python-client / "
            "google-auth-oauthlib belum terpasang. Install paket tersebut atau "
            "gunakan Gmail App Password di ⚙ → Plugin Settings → Gmail Inbox."
        )
    raise GmailError(
        "Gmail belum dikonfigurasi. Buka ⚙ → Plugin Settings → Gmail Inbox "
        "untuk mengisi alamat Gmail dan Google App Password (16 karakter), atau "
        f"letakkan file OAuth di {cred_p}."
    )


class ImapGmailClient:
    """Read-only Gmail client over IMAP SSL (stdlib imaplib, no extra packages)."""

    def __init__(self, email_addr: str, app_password: str,
                 host: str = IMAP_HOST, port: int = IMAP_PORT):
        self.email_addr = email_addr.strip()
        self.app_password = app_password
        self.host = host
        self.port = port

    def _connect(self, mailbox: str = "INBOX") -> imaplib.IMAP4_SSL:
        ctx = ssl.create_default_context()
        try:
            conn = imaplib.IMAP4_SSL(
                self.host, self.port, ssl_context=ctx, timeout=TIMEOUT_S
            )
        except Exception as exc:
            raise GmailError(f"gagal terhubung ke server Gmail IMAP: {exc}") from exc
        try:
            conn.login(self.email_addr, self.app_password)
        except imaplib.IMAP4.error as exc:
            try:
                conn.logout()
            except Exception:
                pass
            raise GmailError(
                "login Gmail IMAP ditolak — pastikan alamat email benar dan gunakan "
                "Google App Password 16 karakter (bukan password login biasa)."
            ) from exc
        mbox = re.sub(r"[\r\n]+", "", mailbox or "INBOX").strip() or "INBOX"
        status, _ = conn.select(mbox, readonly=True)
        if status != "OK":
            try:
                conn.logout()
            except Exception:
                pass
            raise GmailError(f"folder/label Gmail {mbox!r} tidak dapat dibuka.")
        return conn

    def _uid_search(self, conn: imaplib.IMAP4_SSL, criteria: list[str]) -> list[str]:
        joined = " ".join(criteria)
        is_ascii = all(ord(ch) < 128 for ch in joined)
        try:
            if is_ascii:
                status, data = conn.uid("SEARCH", None, *criteria)
            else:
                status, data = conn.uid(
                    "SEARCH", "CHARSET", "UTF-8",
                    *[c.encode("utf-8") for c in criteria],
                )
        except imaplib.IMAP4.error:
            # Fallback if IMAP server rejects UTF-8 charset literal formatting
            ascii_criteria = [
                c.encode("ascii", "ignore").decode("ascii") for c in criteria
            ]
            status, data = conn.uid("SEARCH", None, *ascii_criteria)
        if status != "OK" or not data or not data[0]:
            return []
        raw = data[0].decode("utf-8", errors="replace") if isinstance(data[0], bytes) else str(data[0])
        return [u for u in raw.split() if u]

    def test_connection(self) -> str:
        conn = self._connect("INBOX")
        try:
            unread = len(self._uid_search(conn, ["UNSEEN"]))
            total = len(self._uid_search(conn, ["ALL"]))
            return f"Connected ({self.email_addr}): {unread} unread / {total} total in INBOX"
        finally:
            try:
                conn.logout()
            except Exception:
                pass

    def unread_count(self, mailbox: str = "INBOX") -> int:
        conn = self._connect(mailbox)
        try:
            return len(self._uid_search(conn, ["UNSEEN"]))
        finally:
            try:
                conn.logout()
            except Exception:
                pass

    def list_messages(
        self,
        *,
        unread_only: bool = False,
        sender: str = "",
        query: str = "",
        limit: int = DEFAULT_LIMIT,
        mailbox: str = "INBOX",
    ) -> tuple[list[EmailSummary], int]:
        limit = max(1, min(MAX_LIMIT, int(limit)))
        conn = self._connect(mailbox)
        try:
            criteria = build_imap_search_args(
                unread_only=unread_only, sender=sender, query=query
            )
            uids = self._uid_search(conn, criteria)
            total_matches = len(uids)
            if not uids:
                return [], 0
            selected = list(reversed(uids[-limit:]))
            summaries: list[EmailSummary] = []
            for uid in selected:
                status, msg_data = conn.uid(
                    "FETCH", uid,
                    "(FLAGS BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE)] BODY.PEEK[TEXT]<0.512>)",
                )
                if status != "OK" or not msg_data:
                    continue
                flags_blob = b""
                header_bytes = b""
                snippet_bytes = b""
                for item in msg_data:
                    if not isinstance(item, tuple) or len(item) < 2:
                        continue
                    meta = item[0] if isinstance(item[0], bytes) else b""
                    if b"FLAGS" in meta:
                        flags_blob += meta
                    if b"HEADER" in meta:
                        header_bytes += item[1]
                    elif b"TEXT" in meta:
                        snippet_bytes += item[1]
                msg = email.message_from_bytes(header_bytes)
                sender_label, sender_addr = format_sender(msg.get("From", ""))
                subject = decode_mime_header(msg.get("Subject", "")) or "(No subject)"
                date_str = format_date(msg.get("Date", ""))
                unread = b"\\Seen" not in flags_blob
                snippet = _clean_imap_snippet(snippet_bytes)
                summaries.append(EmailSummary(
                    uid=uid,
                    sender=sender_label,
                    sender_email=sender_addr,
                    subject=subject,
                    date=date_str,
                    snippet=snippet,
                    unread=unread,
                ))
            return summaries, total_matches
        finally:
            try:
                conn.logout()
            except Exception:
                pass

    def read_message(self, uid: str, mailbox: str = "INBOX") -> EmailDetail:
        target_uid = re.sub(r"[^0-9A-Za-z_-]", "", str(uid or "").strip())
        if not target_uid:
            raise GmailError("ID email tidak valid.")
        conn = self._connect(mailbox)
        try:
            status, msg_data = conn.uid("FETCH", target_uid, "(FLAGS BODY.PEEK[])")
            if status != "OK" or not msg_data:
                raise GmailError(f"email dengan ID {target_uid} tidak ditemukan.")
            flags_blob = b""
            raw_bytes = b""
            for item in msg_data:
                if isinstance(item, tuple) and len(item) >= 2:
                    if isinstance(item[0], bytes) and b"FLAGS" in item[0]:
                        flags_blob += item[0]
                    if isinstance(item[1], bytes) and len(item[1]) > len(raw_bytes):
                        raw_bytes = item[1]
            if not raw_bytes:
                raise GmailError(f"isi email ID {target_uid} kosong atau tidak ditemukan.")
            msg = email.message_from_bytes(raw_bytes)
            sender_label, sender_addr = format_sender(msg.get("From", ""))
            subject = decode_mime_header(msg.get("Subject", "")) or "(No subject)"
            date_str = format_date(msg.get("Date", ""))
            to_str = decode_mime_header(msg.get("To", ""))
            body, attachments = extract_email_parts(msg)
            return EmailDetail(
                uid=target_uid,
                sender=sender_label,
                sender_email=sender_addr,
                subject=subject,
                date=date_str,
                snippet=_snippet_from_body(body),
                unread=b"\\Seen" not in flags_blob,
                body=body or "(Empty body)",
                attachments=attachments,
                to=to_str,
            )
        finally:
            try:
                conn.logout()
            except Exception:
                pass


class OAuthGmailClient:
    """Read-only Gmail REST API client via google-api-python-client."""

    def __init__(self, credentials_path: Path, token_path: Path):
        self.credentials_path = Path(credentials_path)
        self.token_path = Path(token_path)

    def _service(self):
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build

        creds = None
        if self.token_path.is_file():
            creds = Credentials.from_authorized_user_file(
                str(self.token_path), READONLY_SCOPES
            )
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                if not self.credentials_path.is_file():
                    raise GmailError(
                        f"File OAuth tidak ditemukan di {self.credentials_path}."
                    )
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(self.credentials_path), READONLY_SCOPES
                )
                creds = flow.run_local_server(port=0)
            self.token_path.parent.mkdir(parents=True, exist_ok=True)
            self.token_path.write_text(creds.to_json(), encoding="utf-8")
            try:
                os.chmod(self.token_path, 0o600)
            except OSError:
                pass
        return build("gmail", "v1", credentials=creds, cache_discovery=False)

    def test_connection(self) -> str:
        svc = self._service()
        profile = svc.users().getProfile(userId="me").execute()
        inbox = svc.users().labels().get(userId="me", id="INBOX").execute()
        addr = profile.get("emailAddress") or "me"
        unread = inbox.get("messagesUnread", 0)
        return f"Connected ({addr} via OAuth): {unread} unread in INBOX"

    def unread_count(self, mailbox: str = "INBOX") -> int:
        svc = self._service()
        if mailbox.upper() == "INBOX":
            inbox = svc.users().labels().get(userId="me", id="INBOX").execute()
            return int(inbox.get("messagesUnread", 0))
        res = svc.users().messages().list(
            userId="me", q="is:unread", maxResults=100
        ).execute()
        return int(res.get("resultSizeEstimate") or len(res.get("messages") or []))

    def list_messages(
        self,
        *,
        unread_only: bool = False,
        sender: str = "",
        query: str = "",
        limit: int = DEFAULT_LIMIT,
        mailbox: str = "INBOX",
    ) -> tuple[list[EmailSummary], int]:
        limit = max(1, min(MAX_LIMIT, int(limit)))
        svc = self._service()
        q = build_gmail_query(unread_only=unread_only, sender=sender, query=query)
        label_ids = ["INBOX"] if mailbox.upper() == "INBOX" else None
        kwargs: dict[str, Any] = {"userId": "me", "maxResults": limit}
        if q:
            kwargs["q"] = q
        if label_ids:
            kwargs["labelIds"] = label_ids
        res = svc.users().messages().list(**kwargs).execute()
        msgs = res.get("messages") or []
        total = int(res.get("resultSizeEstimate") or len(msgs))
        summaries: list[EmailSummary] = []
        for item in msgs[:limit]:
            mid = item.get("id")
            if not mid:
                continue
            detail = svc.users().messages().get(
                userId="me", id=mid, format="metadata",
                metadataHeaders=["From", "Subject", "Date"],
            ).execute()
            headers = {
                h["name"].lower(): h.get("value", "")
                for h in (detail.get("payload") or {}).get("headers") or []
            }
            sender_label, sender_addr = format_sender(headers.get("from", ""))
            subject = decode_mime_header(headers.get("subject", "")) or "(No subject)"
            date_str = format_date(headers.get("date", ""))
            labels = set(detail.get("labelIds") or [])
            summaries.append(EmailSummary(
                uid=str(mid),
                sender=sender_label,
                sender_email=sender_addr,
                subject=subject,
                date=date_str,
                snippet=html.unescape(detail.get("snippet") or ""),
                unread="UNREAD" in labels,
            ))
        return summaries, total

    def read_message(self, uid: str, mailbox: str = "INBOX") -> EmailDetail:
        svc = self._service()
        raw_res = svc.users().messages().get(
            userId="me", id=str(uid), format="raw"
        ).execute()
        raw_b64 = raw_res.get("raw") or ""
        if raw_b64:
            raw_bytes = base64.urlsafe_b64decode(raw_b64.encode("ascii"))
            msg = email.message_from_bytes(raw_bytes)
            sender_label, sender_addr = format_sender(msg.get("From", ""))
            subject = decode_mime_header(msg.get("Subject", "")) or "(No subject)"
            date_str = format_date(msg.get("Date", ""))
            to_str = decode_mime_header(msg.get("To", ""))
            body, attachments = extract_email_parts(msg)
        else:
            sender_label, sender_addr, subject, date_str, to_str = "Unknown", "", "(No subject)", "", ""
            body, attachments = html.unescape(raw_res.get("snippet") or ""), []
        labels = set(raw_res.get("labelIds") or [])
        return EmailDetail(
            uid=str(uid),
            sender=sender_label,
            sender_email=sender_addr,
            subject=subject,
            date=date_str,
            snippet=_snippet_from_body(body),
            unread="UNREAD" in labels,
            body=body or "(Empty body)",
            attachments=attachments,
            to=to_str,
        )


def format_check_result(
    summaries: list[EmailSummary],
    total: int,
    *,
    unread_only: bool = False,
) -> tuple[str, str]:
    """Return `(spoken_summary, panel_text)` for a list of emails."""
    if not summaries:
        empty = (
            "Tidak ada email yang belum dibaca di Gmail."
            if unread_only
            else "Tidak ada email yang cocok di Gmail."
        )
        return empty, empty

    remember_recent_uids([m.uid for m in summaries])
    lines: list[str] = []
    spoken_items: list[str] = []
    for idx, item in enumerate(summaries, start=1):
        tag = "[UNREAD]" if item.unread else "[READ]"
        when = f" ({item.date})" if item.date else ""
        lines.append(
            f"{idx}. {tag} {item.subject}\n"
            f"   Dari: {item.sender}{when} [ID: {item.uid}]"
        )
        if item.snippet:
            lines.append(f"   Cuplikan: {item.snippet}")
        if idx <= 3:
            who = item.sender.split("<")[0].strip() or item.sender
            spoken_items.append(f"nomor {idx} dari {who}: {item.subject}")

    head = (
        f"Ditemukan {len(summaries)} email"
        + (f" (total cocok: {total})" if total > len(summaries) else "")
        + ": "
        + "; ".join(spoken_items)
        + ". Sebutkan nomor atau pengirim jika ingin saya bacakan isi lengkapnya."
    )
    return head, "\n".join(lines)


def format_email_detail(detail: EmailDetail) -> tuple[str, str]:
    """Return `(spoken_reply, panel_text)` for a single full email."""
    meta = [
        f"Subjek : {detail.subject}",
        f"Dari   : {detail.sender}",
    ]
    if detail.to:
        meta.append(f"Kepada : {detail.to}")
    if detail.date:
        meta.append(f"Tanggal: {detail.date}")
    meta.append(f"Status : {'Belum dibaca' if detail.unread else 'Sudah dibaca'}")
    if detail.attachments:
        meta.append("Lampiran: " + ", ".join(detail.attachments))
    panel = "\n".join(meta) + "\n" + ("─" * 44) + "\n" + detail.body

    spoken_body = detail.body[:1400]
    attach_note = (
        f" Ada {len(detail.attachments)} lampiran: {', '.join(detail.attachments[:3])}."
        if detail.attachments else ""
    )
    spoken = (
        f"Email dari {detail.sender}, subjek '{detail.subject}'"
        + (f", tanggal {detail.date}" if detail.date else "")
        + f".{attach_note} Isinya:\n{spoken_body}"
    )
    return spoken, panel
