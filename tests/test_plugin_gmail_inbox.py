"""Tests for plugins/gmail_inbox.py and plugins/_gmail.py.

Covers MIME/HTML email parsing, IMAP command-injection sanitization, mocked
IMAP SSL check/read/count flows (verifying read-only mailbox selection and
BODY.PEEK so unread state is never mutated), recent-ID cache (`message_id="1"`),
OAuth read-only mode, Settings UI schema + test button, and manifest integrity.
Nothing here touches the live network.
"""
from __future__ import annotations

import base64
import hashlib
import imaplib
import importlib.util
import json
import sys
from email.message import EmailMessage
from pathlib import Path
from unittest.mock import MagicMock

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
def gmail():
    mod = _load("_gmail")
    mod.clear_recent_cache()
    yield mod
    mod.clear_recent_cache()


@pytest.fixture()
def plugin(gmail, monkeypatch):
    mod = _load("gmail_inbox")
    monkeypatch.setattr(mod, "_gmail", gmail)
    return mod


def _make_raw_email(
    *,
    sender: str = '"Budi Santoso" <budi@example.com>',
    to: str = "saya@gmail.com",
    subject: str = "Laporan Harian",
    date: str = "Wed, 11 Nov 2026 09:30:00 +0700",
    plain: str | None = "Halo, ini isi pesan utama.",
    html: str | None = None,
    attachment_name: str | None = None,
) -> bytes:
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = to
    msg["Subject"] = subject
    msg["Date"] = date
    if plain is not None:
        msg.set_content(plain)
        if html is not None:
            msg.add_alternative(html, subtype="html")
    elif html is not None:
        msg.set_content(html, subtype="html")
    if attachment_name:
        msg.add_attachment(
            b"%PDF-1.4 sample",
            maintype="application",
            subtype="pdf",
            filename=attachment_name,
        )
    return msg.as_bytes()


# ── MIME decoding & HTML parsing ────────────────────────────────────────────

def test_mime_header_decodes_utf8_and_handles_unknown_charset(gmail):
    encoded = "=?UTF-8?B?VGFnaWhhbiBCdWxhbiBOb3ZlbWJlcg==?="
    assert gmail.decode_mime_header(encoded) == "Tagihan Bulan November"
    bad_cs = "=?X-UNKNOWN-999?B?SGVsbG8=?="
    assert "Hello" in gmail.decode_mime_header(bad_cs)


def test_html_to_text_strips_scripts_and_preserves_structure(gmail):
    raw = (
        "<html><head><style>body{color:red}</style>"
        "<script>alert(1)</script></head>"
        "<body><p>Halo &amp; salam,</p>"
        "<ul><li>Item satu</li><li>Item dua</li></ul></body></html>"
    )
    text = gmail.html_to_text(raw)
    assert "alert(1)" not in text
    assert "color:red" not in text
    assert "Halo & salam," in text
    assert "- Item satu" in text
    assert "- Item dua" in text


def test_extract_email_parts_prefers_plain_and_lists_attachments(gmail):
    import email as std_email

    raw = _make_raw_email(
        plain="Teks polos penting",
        html="<p>Versi HTML</p>",
        attachment_name="invoice.pdf",
    )
    body, attachments = gmail.extract_email_parts(std_email.message_from_bytes(raw))
    assert "Teks polos penting" in body
    assert "Versi HTML" not in body
    assert attachments == ["invoice.pdf"]


def test_clean_imap_snippet_strips_mime_boundaries_and_decodes_qp(gmail):
    raw_slice = (
        b"--000000000000abc\r\n"
        b'Content-Type: text/plain; charset="UTF-8"\r\n'
        b"Content-Transfer-Encoding: quoted-printable\r\n\r\n"
        b"Halo=20Pak,=20tagihan=20bulan=20ini=20sudah=20terbit.\r\n"
    )
    out = gmail._clean_imap_snippet(raw_slice)
    assert "Content-Type" not in out
    assert "--0000" not in out
    assert "Halo Pak, tagihan bulan ini sudah terbit." in out


def test_extract_email_parts_falls_back_to_cleaned_html(gmail):
    import email as std_email

    raw = _make_raw_email(
        plain=None,
        html="<div><h2>Notifikasi</h2><p>Kode OTP: <b>991234</b></p></div>",
    )
    body, attachments = gmail.extract_email_parts(std_email.message_from_bytes(raw))
    assert "Notifikasi" in body
    assert "Kode OTP: 991234" in body
    assert attachments == []


def test_build_imap_search_args_strips_crlf_and_quotes(gmail):
    args = gmail.build_imap_search_args(
        unread_only=True,
        sender='boss@example.com"\r\nLOGOUT',
        query='tagihan "nov"\\2026',
    )
    joined = " ".join(args)
    assert "\r" not in joined and "\n" not in joined
    assert args[0] == "UNSEEN"
    assert "FROM" in args
    assert "SUBJECT" in args


# ── IMAP client (mocked IMAP4_SSL, readonly + BODY.PEEK) ────────────────────

def test_imap_client_checks_and_reads_without_marking_seen(gmail, monkeypatch):
    raw_101 = _make_raw_email(
        sender='"GitHub" <noreply@github.com>',
        subject="[Mark-LVI] Security notice",
        plain="Review dependency alert #12.",
    )
    raw_102 = _make_raw_email(
        sender='"Budi" <budi@example.com>',
        subject="Jadwal rapat besok",
        plain="Kita ketemu jam 10 pagi ya.",
        attachment_name="agenda.pdf",
    )

    fake_conn = MagicMock()
    fake_conn.login.return_value = ("OK", [b"Logged in"])
    fake_conn.select.return_value = ("OK", [b"2"])

    def fake_uid(cmd, *args):
        if cmd == "SEARCH":
            if "UNSEEN" in args:
                return ("OK", [b"102"])
            return ("OK", [b"101 102"])
        if cmd == "FETCH":
            uid = args[0]
            spec = args[1]
            if "BODY.PEEK[]" in spec:
                blob = raw_102 if uid == "102" else raw_101
                return ("OK", [(b"1 (FLAGS () BODY[] {100})", blob)])
            if uid == "102":
                hdr = b"From: Budi <budi@example.com>\r\nSubject: Jadwal rapat besok\r\nDate: Wed, 11 Nov 2026 09:30:00 +0700\r\n"
                return ("OK", [
                    (b"2 (FLAGS () BODY[HEADER.FIELDS (FROM SUBJECT DATE)] {80})", hdr),
                    (b"2 (BODY[TEXT]<0> {30})", b"Kita ketemu jam 10 pagi ya."),
                ])
            hdr = b"From: GitHub <noreply@github.com>\r\nSubject: [Mark-LVI] Security notice\r\nDate: Wed, 11 Nov 2026 08:00:00 +0700\r\n"
            return ("OK", [
                (b"1 (FLAGS (\\Seen) BODY[HEADER.FIELDS (FROM SUBJECT DATE)] {80})", hdr),
                (b"1 (BODY[TEXT]<0> {28})", b"Review dependency alert #12."),
            ])
        return ("NO", [])

    fake_conn.uid.side_effect = fake_uid
    monkeypatch.setattr(imaplib, "IMAP4_SSL", MagicMock(return_value=fake_conn))

    client = gmail.ImapGmailClient("saya@gmail.com", "abcd efgh ijkl mnop")
    summaries, total = client.list_messages(limit=5)
    assert total == 2
    assert [s.uid for s in summaries] == ["102", "101"]  # newest first
    assert summaries[0].unread is True
    assert summaries[1].unread is False

    # Must open mailbox readonly so reading does not mutate unread state
    fake_conn.select.assert_called_with("INBOX", readonly=True)

    detail = client.read_message("102")
    assert detail.subject == "Jadwal rapat besok"
    assert "jam 10 pagi" in detail.body
    assert detail.attachments == ["agenda.pdf"]
    assert client.unread_count() == 1
    assert fake_conn.logout.called


def test_imap_auth_failure_does_not_leak_password_and_explains_app_password(gmail, monkeypatch):
    fake_conn = MagicMock()
    fake_conn.login.side_effect = imaplib.IMAP4.error(b"[AUTHENTICATIONFAILED] Invalid credentials")
    monkeypatch.setattr(imaplib, "IMAP4_SSL", MagicMock(return_value=fake_conn))

    secret = "supersecretapppw"
    client = gmail.ImapGmailClient("saya@gmail.com", secret)
    with pytest.raises(gmail.GmailError) as exc_info:
        client.list_messages()
    msg = str(exc_info.value)
    assert "App Password" in msg
    assert secret not in msg


# ── Plugin dispatch & recent-ID resolution ──────────────────────────────────

def test_missing_credentials_returns_clear_setup_guidance(plugin, isolated_config, monkeypatch):
    monkeypatch.delenv("JARVIS_GMAIL_EMAIL", raising=False)
    monkeypatch.delenv("JARVIS_GMAIL_APP_PASSWORD", raising=False)
    reply = plugin.run({"action": "check"})
    assert "Plugin Settings" in reply or "App Password" in reply


def test_check_then_read_by_index_resolves_cached_uid(plugin, gmail, monkeypatch):
    shown: list[tuple[str, str]] = []
    logged: list[str] = []

    class FakePlayer:
        def write_log(self, text):
            logged.append(text)

        def show_content(self, title, text):
            shown.append((title, text))

    fake_client = MagicMock()
    fake_client.list_messages.return_value = (
        [
            gmail.EmailSummary(
                uid="9001",
                sender="Andi <andi@example.com>",
                sender_email="andi@example.com",
                subject="Konfirmasi Invoice",
                date="2026-11-11 09:00",
                snippet="Mohon dicek invoice terlampir.",
                unread=True,
            ),
            gmail.EmailSummary(
                uid="9000",
                sender="Newsletter <news@example.com>",
                sender_email="news@example.com",
                subject="Weekly Digest",
                date="2026-11-10 18:00",
                snippet="Top articles",
                unread=False,
            ),
        ],
        2,
    )
    fake_client.read_message.return_value = gmail.EmailDetail(
        uid="9001",
        sender="Andi <andi@example.com>",
        sender_email="andi@example.com",
        subject="Konfirmasi Invoice",
        date="2026-11-11 09:00",
        unread=True,
        body="Halo, total tagihan bulan ini Rp 1.500.000.",
        attachments=["invoice.pdf"],
    )
    fake_client.unread_count.return_value = 3

    monkeypatch.setattr(gmail, "load_settings", lambda overrides=None: {
        "auth_mode": "imap_app_password",
        "email": "me@gmail.com",
        "app_password": "abcdefghijklmnop",
        "credentials_path": Path("/tmp/none.json"),
        "token_path": Path("/tmp/tok.json"),
        "default_limit": 5,
    })
    monkeypatch.setattr(gmail, "choose_backend", lambda _cfg: fake_client)

    player = FakePlayer()
    check_reply = plugin.run({"action": "check"}, player=player)
    assert "Ditemukan 2 email" in check_reply
    assert "Konfirmasi Invoice" in check_reply
    assert shown and "GMAIL — INBOX" in shown[-1][0]

    read_reply = plugin.run({"action": "read", "message_id": "1"}, player=player)
    fake_client.read_message.assert_called_once_with("9001", mailbox="INBOX")
    assert "Rp 1.500.000" in read_reply
    assert "invoice.pdf" in read_reply
    assert shown[-1][0].startswith("GMAIL — Konfirmasi Invoice")

    count_reply = plugin.run({"action": "count"}, player=player)
    assert "3 email" in count_reply


def test_unread_action_and_read_by_sender_fallback(plugin, gmail, monkeypatch):
    fake_client = MagicMock()
    fake_client.list_messages.return_value = (
        [
            gmail.EmailSummary(
                uid="777",
                sender="HRD <hrd@company.id>",
                sender_email="hrd@company.id",
                subject="Undangan Interview",
                date="2026-11-11 10:00",
                unread=True,
            )
        ],
        1,
    )
    fake_client.read_message.return_value = gmail.EmailDetail(
        uid="777",
        sender="HRD <hrd@company.id>",
        sender_email="hrd@company.id",
        subject="Undangan Interview",
        date="2026-11-11 10:00",
        unread=True,
        body="Jadwal interview Kamis pukul 14.00 WIB.",
    )
    monkeypatch.setattr(gmail, "load_settings", lambda overrides=None: {
        "auth_mode": "imap_app_password",
        "email": "me@gmail.com",
        "app_password": "abcdefghijklmnop",
        "credentials_path": Path("/tmp/none.json"),
        "token_path": Path("/tmp/tok.json"),
        "default_limit": 5,
    })
    monkeypatch.setattr(gmail, "choose_backend", lambda _cfg: fake_client)

    plugin.run({"action": "unread"})
    assert fake_client.list_messages.call_args.kwargs["unread_only"] is True

    reply = plugin.run({"action": "read", "sender": "hrd@company.id"})
    assert "Kamis pukul 14.00 WIB" in reply


def test_broken_player_callbacks_never_crash_run(plugin, gmail, monkeypatch):
    class BrokenPlayer:
        def write_log(self, _):
            raise RuntimeError("ui dead")

        def show_content(self, *_):
            raise RuntimeError("panel dead")

    fake_client = MagicMock()
    fake_client.unread_count.return_value = 0
    monkeypatch.setattr(gmail, "load_settings", lambda overrides=None: {
        "auth_mode": "imap_app_password",
        "email": "me@gmail.com",
        "app_password": "abcdefghijklmnop",
        "credentials_path": Path("/tmp/none.json"),
        "token_path": Path("/tmp/tok.json"),
        "default_limit": 5,
    })
    monkeypatch.setattr(gmail, "choose_backend", lambda _cfg: fake_client)
    assert "0 email" in plugin.run({"action": "count"}, player=BrokenPlayer())


def test_settings_schema_and_test_connection_button(plugin, gmail, monkeypatch):
    schema = plugin.PLUGIN_SETTINGS
    assert schema["namespace"] == "gmail_inbox"
    by_key = {f["key"]: f for f in schema["fields"]}
    assert by_key["app_password"]["type"] == "password"
    assert by_key["auth_mode"]["type"] == "choice"
    assert callable(schema["action"]["run"])

    fake_client = MagicMock()
    fake_client.test_connection.return_value = "Connected (me@gmail.com): 2 unread / 10 total in INBOX"
    monkeypatch.setattr(gmail, "choose_backend", lambda _cfg: fake_client)

    ok, msg = plugin.test_connection({"email": "me@gmail.com", "app_password": "aaaa bbbb cccc dddd"})
    assert ok is True
    assert "2 unread" in msg


# ── OAuth client path (mocked service) ──────────────────────────────────────

def test_oauth_client_reads_raw_rfc822_message(gmail, tmp_path, monkeypatch):
    raw_bytes = _make_raw_email(
        sender='"Tokopedia" <no-reply@tokopedia.com>',
        subject="Pesanan Dikirim",
        plain="Resi: JNE123456",
    )
    raw_b64 = base64.urlsafe_b64encode(raw_bytes).decode("ascii")

    fake_service = MagicMock()
    fake_service.users.return_value.messages.return_value.get.return_value.execute.return_value = {
        "id": "18f0abc",
        "labelIds": ["INBOX", "UNREAD"],
        "raw": raw_b64,
    }

    client = gmail.OAuthGmailClient(tmp_path / "cred.json", tmp_path / "tok.json")
    monkeypatch.setattr(client, "_service", lambda: fake_service)

    detail = client.read_message("18f0abc")
    assert detail.uid == "18f0abc"
    assert detail.unread is True
    assert detail.subject == "Pesanan Dikirim"
    assert "JNE123456" in detail.body


# ── Manifest & discovery integration ────────────────────────────────────────

def test_manifest_matches_sha256_and_helper_permissions():
    py = ROOT / "plugins" / "gmail_inbox.py"
    stored = json.loads((ROOT / "plugins" / "gmail_inbox.json").read_text(encoding="utf-8"))["sha256"]
    assert stored == hashlib.sha256(py.read_bytes()).hexdigest()

    manifest = pm.verify(py, "gmail_inbox")
    assert manifest is not None
    assert manifest.ok, manifest.problems
    assert manifest.permissions == ("network", "files")

    helper_implied = pm.implied_permissions(ROOT / "plugins" / "_gmail.py")
    assert {"network", "files"} <= helper_implied


def test_gmail_plugin_ships_disabled_until_user_consents(isolated_config):
    from core.plugin_loader import discover_plugins

    rows = {
        r["name"]: r
        for r in discover_plugins(ROOT / "plugins", set(), logger=lambda _m: None).list_for_ui()
    }
    assert rows["gmail_inbox"]["valid"] is True
    assert rows["gmail_inbox"]["enabled"] is False
    assert rows["gmail_inbox"]["permissions"] == ["network", "files"]
