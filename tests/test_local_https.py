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


def test_dashboard_uses_issued_pair_and_https_url(tmp_path, monkeypatch):
    pytest.importorskip("fastapi")
    import json
    from dashboard import server
    monkeypatch.setattr(server, "BASE_DIR", tmp_path)
    config = tmp_path / "config"
    config.mkdir()
    (config / "api_keys.json").write_text(json.dumps({"dashboard_https": True}), encoding="utf-8")
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
