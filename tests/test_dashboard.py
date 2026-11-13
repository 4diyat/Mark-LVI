"""The phone dashboard: what it refuses, and what it tells the browser.

Every test here corresponds to a way the dashboard was exploitable or
unhelpful. The routes are exercised through FastAPI's TestClient against a real
app object — not a mock — so a decorator that stops being applied, or a header
that stops being set, fails here.

Needs fastapi (in requirements.txt). On a machine without it the whole module
skips rather than failing: the app is still runnable there, the dashboard is
just off. CI runs these in the job that installs the real requirements.
"""
from __future__ import annotations

import time
import uuid
from unittest import mock

import pytest

pytest.importorskip("fastapi", reason="dashboard dependencies not installed")
pytest.importorskip("httpx", reason="TestClient needs httpx")

from fastapi.testclient import TestClient  # noqa: E402

import dashboard.server as ds  # noqa: E402


@pytest.fixture()
def server(tmp_path, monkeypatch):
    """A dashboard with its own uploads folder and a fresh one-time key."""
    monkeypatch.setattr(ds, "UPLOADS_DIR", tmp_path)
    srv = ds.DashboardServer()
    srv._uploads_dir = tmp_path
    # Use the server's own generator rather than re-rolling the length here:
    # a duplicated magic number is exactly how the login page and the server
    # drifted apart (8 vs 6) and manual entry became impossible.
    key = srv.new_key()
    client = TestClient(srv.app)
    token = client.post("/login", json={"pin": key}).json()["token"]
    return srv, client, token, key


def _h(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ── headers ──────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("path", ["/login", "/"])
def test_pages_carry_security_headers(server, path):
    _, client, _, _ = server
    r = client.get(path)
    assert r.status_code == 200
    assert r.headers["x-frame-options"] == "DENY"
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["referrer-policy"] == "no-referrer"
    assert "frame-ancestors 'none'" in r.headers["content-security-policy"]


@pytest.mark.parametrize("path", ["/login", "/"])
def test_inline_script_nonce_matches_the_policy(server, path):
    """A nonce in the header that does not match the tag blocks the page.

    This is the failure mode of adding a CSP to a page with an inline script:
    every layer "present", the dashboard blank. The two must be the same value.
    """
    _, client, _, _ = server
    r = client.get(path)
    csp = r.headers["content-security-policy"]
    nonce = csp.split("'nonce-")[1].split("'")[0]
    assert f'nonce="{nonce}"' in r.text
    assert "__NONCE__" not in r.text, "the nonce placeholder was never substituted"
    assert nonce not in ("", "__NONCE__")


def test_two_pages_get_different_nonces(server):
    _, client, _, _ = server
    def nonce_of(path):
        csp = client.get(path).headers["content-security-policy"]
        return csp.split("'nonce-")[1].split("'")[0]
    assert nonce_of("/") != nonce_of("/")


def test_json_endpoints_get_headers_too(server):
    """The middleware covers routes added later; a per-route decorator would not."""
    _, client, token, _ = server
    r = client.get("/api/devices", headers=_h(token))
    assert r.headers["x-frame-options"] == "DENY"


# ── authentication and scope ─────────────────────────────────────────────────

def test_commands_need_a_token(server):
    _, client, _, _ = server
    assert client.post("/api/command", json={"text": "hi"}).status_code == 401
    assert client.post("/api/wake").status_code == 401
    assert client.get("/api/devices").status_code == 401
    assert client.get("/api/audit").status_code == 401


def test_wrong_key_is_refused(server):
    _, client, _, _ = server
    r = client.post("/login", json={"pin": "ZZZZZZZZ"})
    assert r.status_code == 401


def test_login_attempts_are_throttled(server):
    """Six guesses then a wait. There was no limit at all before."""
    _, client, _, _ = server
    codes = [client.post("/login", json={"pin": f"AAAAAA{i}"}).status_code
             for i in range(ds._LOGIN_MAX_TRIES + 2)]
    assert 429 in codes, codes


def test_scope_read_cannot_send_a_command(server):
    """A paired device may be allowed to watch without being allowed to type."""
    srv, client, _, _ = server
    read_tok = f"read-{uuid.uuid4().hex}"
    now = time.time()
    with srv._token_lock:
        srv._tokens[read_tok] = [now, now, ds._SCOPE_READ]

    assert client.get("/api/devices", headers=_h(read_tok)).status_code == 200
    assert client.post("/api/command", json={"text": "shutdown"},
                       headers=_h(read_tok)).status_code == 401
    assert client.post("/api/wake", headers=_h(read_tok)).status_code == 401


def test_expired_and_idle_tokens_stop_working(server):
    """Twelve hours absolute, two hours unused — both clocks, not one."""
    srv, client, _, _ = server
    now = time.time()
    cases = {
        "expired": [now - ds._TOKEN_TTL_SECONDS - 1, now, ds._SCOPE_COMMAND],
        "idle":    [now - 60, now - ds._TOKEN_IDLE_SECONDS - 1, ds._SCOPE_COMMAND],
    }
    with srv._token_lock:
        for tok, rec in cases.items():
            srv._tokens[tok] = rec
    for tok in cases:
        assert client.post("/api/command", json={"text": "hi"},
                           headers=_h(tok)).status_code == 401, tok


def test_a_used_token_keeps_working(server):
    """The idle clock must be refreshed by use, or a page open for two hours dies."""
    srv, client, token, _ = server
    with srv._token_lock:
        srv._tokens[token][1] = time.time() - ds._TOKEN_IDLE_SECONDS + 60
    assert client.post("/api/command", json={"text": "hi"}, headers=_h(token)).status_code == 200
    with srv._token_lock:
        assert time.time() - srv._tokens[token][1] < 5


# ── bodies ───────────────────────────────────────────────────────────────────

def test_oversized_command_is_refused(server):
    """A command is a sentence. 64 KB is not one, and parsing it costs the app."""
    _, client, token, _ = server
    r = client.post("/api/command", json={"text": "x" * (ds._MAX_COMMAND_BODY + 10)},
                    headers=_h(token))
    assert r.status_code == 413


def test_malformed_login_body_is_a_400_not_a_500(server):
    _, client, _, _ = server
    r = client.post("/login", content=b"not json",
                    headers={"Content-Type": "application/json"})
    assert r.status_code == 400


def test_command_text_is_capped(server):
    srv, client, token, _ = server
    client.post("/api/command", json={"text": "a" * 10_000}, headers=_h(token))
    # queued, and shorter than what was sent
    queued = srv._command_queue.get_nowait()
    assert len(queued) <= 2000


# ── files ────────────────────────────────────────────────────────────────────

def test_upload_name_cannot_escape_the_folder(server, tmp_path):
    _, client, token, _ = server
    r = client.post("/api/upload", files={"file": ("../../evil.sh", b"echo hi")},
                    headers=_h(token))
    assert r.status_code == 200
    assert r.json()["name"] == "evil.sh"
    assert not (tmp_path.parent / "evil.sh").exists()
    assert (tmp_path / "evil.sh").exists()


def test_upload_refused_when_the_folder_is_full(server, tmp_path, monkeypatch):
    """A per-file cap bounds one request; it says nothing about the folder."""
    monkeypatch.setattr(ds, "_UPLOAD_QUOTA_MB", 1)
    (tmp_path / "already.bin").write_bytes(b"0" * (2 * 1024 * 1024))
    _, client, token, _ = server
    r = client.post("/api/upload", files={"file": ("x.txt", b"hello")}, headers=_h(token))
    assert r.status_code == 507
    assert "full" in r.json()["error"].lower()


def test_download_needs_a_token(server, tmp_path):
    (tmp_path / "a.txt").write_text("secret", encoding="utf-8")
    _, client, token, _ = server
    assert client.get("/uploads/a.txt").status_code == 401
    assert client.get(f"/uploads/a.txt?token={token}").status_code == 200


def test_old_uploads_are_swept(tmp_path):
    old = tmp_path / "old.txt"
    new = tmp_path / "new.txt"
    old.write_text("x", encoding="utf-8")
    new.write_text("y", encoding="utf-8")
    import os
    past = time.time() - 40 * 86400
    os.utime(old, (past, past))
    assert ds._sweep_uploads(tmp_path) == 1
    assert not old.exists()
    assert new.exists()


# ── audit ────────────────────────────────────────────────────────────────────

def test_actions_are_recorded(server):
    """"Did my phone send that?" needs an answer that outlives the scrollback."""
    srv, client, token, _ = server
    client.post("/api/command", json={"text": "open spotify"}, headers=_h(token))
    client.post("/api/wake", headers=_h(token))
    kinds = [e["kind"] for e in client.get("/api/audit", headers=_h(token)).json()["entries"]]
    assert kinds[:2] == ["command", "wake"]
    assert any("open spotify" in e["detail"] for e in srv._audit)


def test_audit_is_capped(server):
    srv, client, token, _ = server
    for i in range(260):
        client.post("/api/command", json={"text": f"n{i}"}, headers=_h(token))
    with srv._audit_lock:
        assert len(srv._audit) <= 200


def test_revoke_ends_live_sessions_but_keeps_the_caller(server):
    srv, client, token, _ = server
    with srv._token_lock:
        srv._tokens["other"] = [time.time(), time.time(), ds._SCOPE_COMMAND]
    r = client.post("/api/revoke-devices", headers=_h(token)).json()
    assert r["sessions_ended"] >= 1
    assert client.get("/api/devices", headers=_h(token)).status_code == 200
    assert client.post("/api/command", json={"text": "hi"},
                       headers=_h("other")).status_code == 401


def test_local_address_logs_when_it_can_only_offer_localhost(caplog):
    """The QR code saying 127.0.0.1 is the only symptom of a problem here.

    `_local_ip()` tries three methods and used to swallow all three failures
    with `except: pass`; the caller then shows a link no phone can open, with
    nothing anywhere saying why. The log line is the difference between "the
    dashboard is broken" and "this machine is not on a network".
    """
    import logging

    from dashboard import server

    with caplog.at_level(logging.DEBUG, logger="dashboard"):
        with mock.patch.object(server.socket, "socket", side_effect=OSError("no route")), \
             mock.patch.object(server.socket, "gethostbyname", side_effect=OSError("no dns")), \
             mock.patch.object(server.socket, "getaddrinfo", side_effect=OSError("no ifaces")):
            assert server._local_ip() == "127.0.0.1"

    text = caplog.text
    assert "no LAN address" in text
    assert "no route" in text or "no dns" in text or "no ifaces" in text


# ── the login page must accept the whole key ────────────────────────────────

def test_login_page_accepts_the_whole_key(server):
    """The page and the server must agree on how long a key is.

    They did not: the server minted 8-character keys while login.html capped
    the field at 6 and auto-submitted at 6. Typing therefore submitted a
    truncated key, the server refused it, and the page cleared the field —
    "the code keeps failing and resets". No test caught it because none read
    the page's numbers against the server's.
    """
    import re

    srv, client, _, _ = server
    html = client.get("/login").text

    maxlength = int(re.search(r'maxlength="(\d+)"', html).group(1))
    auto_submit = int(re.search(r"length === (\d+)", html).group(1))
    minimum = int(re.search(r"length < (\d+)", html).group(1))

    assert maxlength == ds._KEY_LENGTH
    assert auto_submit == ds._KEY_LENGTH
    assert minimum == ds._KEY_LENGTH
    assert len(srv.new_key()) == ds._KEY_LENGTH


def test_a_full_length_key_logs_in(server):
    """The key the desktop shows, typed in full, is accepted."""
    srv, client, _, _ = server
    key = srv.new_key()
    r = client.post("/login", json={"pin": key})
    assert r.status_code == 200
    assert r.json()["ok"] is True
