"""Real local CA and TLS verification, without altering the user's trust store."""
import ipaddress
import os
import socket
import ssl
import threading

import pytest

pytest.importorskip("cryptography")
from cryptography import x509  # noqa: E402
from cryptography.hazmat.primitives import hashes, serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import padding  # noqa: E402
from cryptography.x509.oid import ExtendedKeyUsageOID  # noqa: E402
from tools import setup_local_https as tls  # noqa: E402


def test_ca_leaf_signatures_identity_reuse_and_renewal(tmp_path):
    certs = tmp_path / "certs"
    result = tls.setup(certs, "192.168.1.17")
    ca_bytes = (certs / "local_ca.crt").read_bytes()
    ca = x509.load_pem_x509_certificate(ca_bytes)
    leaf = x509.load_pem_x509_certificate((certs / "jarvis.crt").read_bytes())
    key = serialization.load_pem_private_key((certs / "jarvis.key").read_bytes(), None)
    assert ca.extensions.get_extension_for_class(x509.BasicConstraints).value.ca
    assert not leaf.extensions.get_extension_for_class(x509.BasicConstraints).value.ca
    assert ExtendedKeyUsageOID.SERVER_AUTH in leaf.extensions.get_extension_for_class(x509.ExtendedKeyUsage).value
    names = leaf.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    assert ipaddress.ip_address("192.168.1.17") in names.get_values_for_type(x509.IPAddress)
    assert leaf.public_key().public_numbers() == key.public_key().public_numbers()
    ca.public_key().verify(leaf.signature, leaf.tbs_certificate_bytes, padding.PKCS1v15(), leaf.signature_hash_algorithm)
    assert result["fingerprint"] == ca.fingerprint(hashes.SHA256()).hex(":").upper()
    if os.name != "nt":
        assert (certs / "local_ca.key").stat().st_mode & 0o077 == 0
        assert (certs / "jarvis.key").stat().st_mode & 0o077 == 0
    with pytest.raises(FileExistsError):
        tls.setup(certs, "192.168.1.18")
    tls.setup(certs, "192.168.1.18", replace_server=True)
    renewed = x509.load_pem_x509_certificate((certs / "jarvis.crt").read_bytes())
    assert (certs / "local_ca.crt").read_bytes() == ca_bytes
    assert ipaddress.ip_address("192.168.1.18") in renewed.extensions.get_extension_for_class(
        x509.SubjectAlternativeName).value.get_values_for_type(x509.IPAddress)


def test_incomplete_ca_and_invalid_address_do_not_destroy_existing_certificates(tmp_path):
    certs = tmp_path / "certs"
    tls.setup(certs, "192.168.1.10")
    prior = (certs / "jarvis.crt").read_bytes()
    (certs / "local_ca.key").unlink()
    with pytest.raises(ValueError, match="incomplete"):
        tls.setup(certs, "192.168.1.10", replace_server=True)
    assert (certs / "jarvis.crt").read_bytes() == prior
    with pytest.raises(ValueError):
        tls.setup(certs, "0.0.0.0", replace_server=True)
    assert (certs / "jarvis.crt").read_bytes() == prior


def test_https_tls_handshake_checks_ca_and_ip(tmp_path):
    certs = tmp_path / "certs"
    tls.setup(certs, "127.0.0.1")
    server_context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    server_context.load_cert_chain(str(certs / "jarvis.crt"), str(certs / "jarvis.key"))
    client_context = ssl.create_default_context(cafile=str(certs / "local_ca.crt"))
    def connect(hostname, context=client_context):
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = listener.getsockname()[1]
        def serve():
            try:
                conn, _ = listener.accept()
                with conn:
                    with server_context.wrap_socket(conn, server_side=True):
                        pass
            except (ssl.SSLError, OSError):
                pass
            finally:
                listener.close()
        thread = threading.Thread(target=serve, daemon=True)
        thread.start()
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=3) as sock:
                with context.wrap_socket(sock, server_hostname=hostname):
                    pass
        finally:
            thread.join(timeout=3)
    connect("127.0.0.1")
    with pytest.raises(ssl.SSLCertVerificationError):
        connect("127.0.0.1", ssl.create_default_context())
    with pytest.raises(ssl.SSLCertVerificationError):
        connect("192.168.1.17")


def test_dashboard_uses_issued_pair_and_https_url(tmp_path, monkeypatch, isolated_config):
    pytest.importorskip("fastapi")
    from dashboard import server
    monkeypatch.setattr(server, "BASE_DIR", tmp_path)
    config = tmp_path / "config"
    config.mkdir()
    isolated_config.set_config_values(dashboard_https=True)
    tls.setup(config / "certs", "192.168.1.17")
    assert server.DashboardServer._ssl_enabled()
    srv = server.DashboardServer()
    srv._ip = "192.168.1.17"
    assert srv.get_url() == "https://192.168.1.17:8001"
    assert server._ensure_certs() is True
    assert x509.load_pem_x509_certificate((config / "certs" / "jarvis.crt").read_bytes()).issuer == \
        x509.load_pem_x509_certificate((config / "certs" / "local_ca.crt").read_bytes()).subject


def test_server_certificate_replacement_rolls_back_on_second_rename_failure(tmp_path, monkeypatch):
    tls.setup(tmp_path, "192.168.1.10")
    previous_key = (tmp_path / "jarvis.key").read_bytes()
    previous_cert = (tmp_path / "jarvis.crt").read_bytes()
    replace = os.replace
    def fail_once(src, dst):
        if str(dst).endswith("jarvis.crt"):
            raise OSError("simulated failure")
        return replace(src, dst)
    monkeypatch.setattr(tls.os, "replace", fail_once)
    with pytest.raises(OSError, match="simulated"):
        tls.setup(tmp_path, "192.168.1.11", replace_server=True)
    assert (tmp_path / "jarvis.key").read_bytes() == previous_key
    assert (tmp_path / "jarvis.crt").read_bytes() == previous_cert
    assert not list(tmp_path.glob(".tls-*"))


def test_tls_fails_closed_and_url_does_not_change(tmp_path, monkeypatch, isolated_config):
    import asyncio
    from dashboard import server
    isolated_config.set_config_values(dashboard_https=True)
    monkeypatch.setattr(server, "BASE_DIR", tmp_path)
    monkeypatch.setattr(server, "report_network_access", lambda *args: None)
    monkeypatch.setattr(server, "_local_ip", lambda: "192.168.1.17")
    monkeypatch.setattr(server, "_ensure_certs", lambda ip: False)
    monkeypatch.setattr(server.uvicorn, "Server", lambda cfg: pytest.fail("listener must not start"))
    srv = server.DashboardServer()
    isolated_config.set_config_values(dashboard_https=False)
    asyncio.run(srv.serve())
    assert srv.get_url() == srv.get_manual_url() == "https://192.168.1.17:8001"
    assert "HTTPS unavailable" in srv._bind_error


def test_generated_certificate_validation_and_partial_pair(tmp_path, monkeypatch):
    from dashboard import server
    monkeypatch.setattr(server, "BASE_DIR", tmp_path)
    assert server._ensure_certs("192.168.1.17")
    key = tmp_path / "config/certs/jarvis.key"
    cert = tmp_path / "config/certs/jarvis.crt"
    server._validate_certs(key, cert, "192.168.1.17")
    with pytest.raises(ValueError, match="LAN IP"):
        server._validate_certs(key, cert, "192.168.1.18")
    key.unlink()
    assert not server._ensure_certs("192.168.1.17")


def test_http_redirect_does_not_forward_pairing_query(monkeypatch, isolated_config):
    import asyncio
    from fastapi.testclient import TestClient
    from dashboard import server
    isolated_config.set_config_values(dashboard_https=True)
    monkeypatch.setattr(server, "_local_ip", lambda: "192.168.1.17")
    srv = server.DashboardServer()
    apps = []
    class FakeServer:
        def __init__(self, cfg):
            assert cfg.access_log is False
            apps.append(cfg.app)
        async def serve(self):
            pass
    monkeypatch.setattr(server.uvicorn, "Server", FakeServer)
    asyncio.run(srv._serve_redirector())
    with TestClient(apps[0]) as client:
        response = client.get("/login", follow_redirects=False)
        assert response.headers["location"] == "https://192.168.1.17:8001/login"
        response = client.get("/auto-login?key=SECRET", follow_redirects=False)
        assert response.status_code == 400
        assert "location" not in response.headers
        assert "SECRET" not in response.text


def test_dashboard_disables_access_log_for_query_credentials(monkeypatch, isolated_config):
    import asyncio
    from dashboard import server
    # Plaintext is now an explicit opt-out, not the default: the pairing key
    # travels in a query string, so access_log=True would write it to a file.
    isolated_config.set_config_values(dashboard_https=False,
                                      dashboard_allow_insecure_http=True)
    monkeypatch.setattr(server, "PORT", 0)
    monkeypatch.setattr(server, "report_network_access", lambda *args: None)
    monkeypatch.setattr(server, "_sweep_uploads", lambda *args: None)
    seen = []
    class FakeServer:
        def __init__(self, cfg):
            seen.append(cfg.access_log)
        async def serve(self):
            pass
    monkeypatch.setattr(server.uvicorn, "Server", FakeServer)
    asyncio.run(server.DashboardServer().serve())
    assert seen == [False]



# ── plaintext keeps its warning, and now records it ─────────────────────────
#
# The old code printed "HTTP does not protect pairing and commands" to stdout
# and nothing else. Under `pythonw main.py` — the desktop shortcut — stdout is a
# null device, so on a shared Wi-Fi network the pairing key and every remote
# command travelled in clear text and no record of the choice survived.
#
# HTTPS stays opt-in on purpose (readme.md: mandatory TLS produced a full-page
# interstitial on Android and a blank page in in-app browsers). The fix is that
# the decision is now written to logs/jarvis.log and reported to the panel.

def test_plain_http_starts_but_is_recorded_as_insecure(monkeypatch, isolated_config,
                                                       caplog):
    import asyncio
    import logging
    from dashboard import server
    isolated_config.set_config_values(dashboard_https=False)
    monkeypatch.setattr(server, "PORT", 0)
    monkeypatch.setattr(server, "report_network_access", lambda *args: None)
    monkeypatch.setattr(server, "_sweep_uploads", lambda *args: None)

    class FakeServer:
        def __init__(self, cfg):
            pass
        async def serve(self):
            pass

    monkeypatch.setattr(server.uvicorn, "Server", FakeServer)
    srv = server.DashboardServer()
    with caplog.at_level(logging.WARNING, logger="dashboard"):
        asyncio.run(srv.serve())

    assert getattr(srv, "_insecure_http", False) is True
    assert any("plain HTTP" in r.getMessage() for r in caplog.records), caplog.text


def test_https_mode_is_not_flagged_insecure(monkeypatch, isolated_config):
    import asyncio
    from dashboard import server
    isolated_config.set_config_values(dashboard_https=True)
    monkeypatch.setattr(server, "report_network_access", lambda *args: None)
    monkeypatch.setattr(server, "_ensure_certs", lambda ip: True)
    monkeypatch.setattr(server, "_validate_certs", lambda *a: None)
    monkeypatch.setattr(server, "SECURE_PORT", 0)

    class FakeServer:
        def __init__(self, cfg):
            assert cfg.ssl_keyfile and cfg.ssl_certfile
        async def serve(self):
            pass

    monkeypatch.setattr(server.uvicorn, "Server", FakeServer)
    srv = server.DashboardServer()
    asyncio.run(srv.serve())

    assert getattr(srv, "_insecure_http", False) is False


def test_broken_https_still_fails_closed(tmp_path, monkeypatch, isolated_config):
    """A certificate that cannot be built must never fall back to plaintext."""
    import asyncio
    from dashboard import server
    isolated_config.set_config_values(dashboard_https=True)
    monkeypatch.setattr(server, "BASE_DIR", tmp_path)
    monkeypatch.setattr(server, "report_network_access", lambda *args: None)
    monkeypatch.setattr(server, "_ensure_certs", lambda ip: False)
    monkeypatch.setattr(server.uvicorn, "Server",
                        lambda cfg: pytest.fail("must not fall back to HTTP"))
    srv = server.DashboardServer()
    asyncio.run(srv.serve())

    assert "HTTPS unavailable" in srv._bind_error
    assert getattr(srv, "_insecure_http", False) is False
