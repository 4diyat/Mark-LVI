"""Opt-in local CA and TLS certificate for the dashboard; never trusts it for you.

Run on the JARVIS computer while JARVIS is stopped. The CA private key stays
on this computer. Only the public CA certificate may be copied to a phone.
"""
from __future__ import annotations

import argparse
import datetime as dt
import ipaddress
import os
import sys
import tempfile
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import ExtendedKeyUsageOID, NameOID

ROOT = Path(__file__).resolve().parents[1]
UTC = dt.timezone.utc


def _private_bytes(key) -> bytes:
    return key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                             serialization.NoEncryption())


def _stage(path: Path, data: bytes, *, private: bool) -> Path:
    """Create a same-directory temp file; private mode is best effort on Windows."""
    fd, name = tempfile.mkstemp(prefix=".tls-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            if private and os.name != "nt":
                os.fchmod(stream.fileno(), 0o600)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        Path(name).unlink(missing_ok=True)
        raise
    return Path(name)


def _install_pair(first: Path, first_data: bytes, second: Path, second_data: bytes,
                  *, replace: bool) -> None:
    """Stage both files before changing either. Restore old contents on errors.

    The two renames cannot be made atomic as a pair; callers must stop JARVIS
    before running this tool. Temp files live in the ignored cert directory.
    """
    if not replace and (first.exists() or second.exists()):
        raise FileExistsError(f"Refusing to overwrite {first.name} or {second.name}.")
    old_first = first.read_bytes() if first.exists() else None
    staged = []
    first_replaced = False
    try:
        staged.append(_stage(first, first_data, private=True))
        staged.append(_stage(second, second_data, private=False))
        os.replace(staged[0], first)
        first_replaced = True
        os.replace(staged[1], second)
    except Exception:
        # Only the first rename can have succeeded if an exception is raised.
        if first_replaced:
            if old_first is None:
                first.unlink(missing_ok=True)
            else:
                temp = _stage(first, old_first, private=True)
                try:
                    os.replace(temp, first)
                finally:
                    temp.unlink(missing_ok=True)
        raise
    finally:
        for path in staged:
            path.unlink(missing_ok=True)


def setup(certs: Path, address: str, *, replace_server: bool = False) -> dict:
    """Generate/reuse CA and issue a leaf for exactly this IP and localhost."""
    ip = ipaddress.ip_address(address)
    if not isinstance(ip, ipaddress.IPv4Address) or ip.is_unspecified or ip.is_multicast:
        raise ValueError("Use the actual IPv4 unicast LAN IP of the JARVIS computer.")
    ca_key_path, ca_cert_path = certs / "local_ca.key", certs / "local_ca.crt"
    key_path, cert_path = certs / "jarvis.key", certs / "jarvis.crt"
    if not replace_server and (key_path.exists() or cert_path.exists()):
        raise FileExistsError("Server certificate already exists. Stop JARVIS and use "
                              "--replace-server-cert to explicitly replace it.")
    if ca_key_path.exists() != ca_cert_path.exists():
        raise ValueError("Local CA key and certificate are incomplete; restore the missing file. "
                         "The existing CA will not be replaced automatically.")
    certs.mkdir(parents=True, exist_ok=True)
    now = dt.datetime.now(UTC)
    if ca_key_path.exists():
        ca_key = serialization.load_pem_private_key(ca_key_path.read_bytes(), password=None)
        ca = x509.load_pem_x509_certificate(ca_cert_path.read_bytes())
        pub_format = (serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
        if ca.public_key().public_bytes(*pub_format) != ca_key.public_key().public_bytes(*pub_format):
            raise ValueError("The existing local CA key and certificate do not match.")
        try:
            if not ca.extensions.get_extension_for_class(x509.BasicConstraints).value.ca:
                raise ValueError("The existing certificate is not a CA.")
        except x509.ExtensionNotFound as exc:
            raise ValueError("The existing certificate has no CA constraint.") from exc
        if ca.not_valid_before_utc > now or ca.not_valid_after_utc <= now + dt.timedelta(days=2):
            raise ValueError("The existing local CA is not valid or is near expiry; replace it manually.")
    else:
        ca_key = rsa.generate_private_key(public_exponent=65537, key_size=3072)
        subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "JARVIS Local Root CA")])
        ca = (x509.CertificateBuilder().subject_name(subject).issuer_name(subject)
              .public_key(ca_key.public_key()).serial_number(x509.random_serial_number())
              .not_valid_before(now - dt.timedelta(minutes=5))
              .not_valid_after(now + dt.timedelta(days=365 * 5))
              .add_extension(x509.BasicConstraints(ca=True, path_length=0), critical=True)
              .add_extension(x509.KeyUsage(digital_signature=True, content_commitment=False,
                  key_encipherment=False, data_encipherment=False, key_agreement=False,
                  key_cert_sign=True, crl_sign=True, encipher_only=False, decipher_only=False), critical=True)
              .add_extension(x509.SubjectKeyIdentifier.from_public_key(ca_key.public_key()), critical=False)
              .sign(ca_key, hashes.SHA256()))
        _install_pair(ca_key_path, _private_bytes(ca_key), ca_cert_path,
                      ca.public_bytes(serialization.Encoding.PEM), replace=False)
    leaf_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "JARVIS Local Dashboard")])
    valid_until = min(now + dt.timedelta(days=180), ca.not_valid_after_utc - dt.timedelta(days=1))
    leaf = (x509.CertificateBuilder().subject_name(subject).issuer_name(ca.subject)
            .public_key(leaf_key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - dt.timedelta(minutes=5)).not_valid_after(valid_until)
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(x509.SubjectAlternativeName([x509.IPAddress(ip), x509.DNSName("localhost"),
                x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]), critical=False)
            .add_extension(x509.ExtendedKeyUsage([ExtendedKeyUsageOID.SERVER_AUTH]), critical=False)
            .add_extension(x509.KeyUsage(digital_signature=True, content_commitment=False,
                key_encipherment=True, data_encipherment=False, key_agreement=False,
                key_cert_sign=False, crl_sign=False, encipher_only=False, decipher_only=False), critical=True)
            .add_extension(x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()), critical=False)
            .sign(ca_key, hashes.SHA256()))
    _install_pair(key_path, _private_bytes(leaf_key), cert_path,
                  leaf.public_bytes(serialization.Encoding.PEM), replace=replace_server)
    return {"ip": str(ip), "ca_path": ca_cert_path, "leaf_expires": valid_until,
            "fingerprint": ca.fingerprint(hashes.SHA256()).hex(":").upper()}


def main() -> int:
    parser = argparse.ArgumentParser(description="Create an opt-in local CA and HTTPS dashboard certificate.")
    parser.add_argument("--ip", required=True, help="LAN IP of this computer, as used in the dashboard URL")
    parser.add_argument("--replace-server-cert", action="store_true",
                        help="explicitly replace existing jarvis.crt and jarvis.key")
    args = parser.parse_args()
    try:
        info = setup(ROOT / "config" / "certs", args.ip, replace_server=args.replace_server_cert)
    except (OSError, ValueError, TypeError) as exc:
        print(f"HTTPS setup failed: {exc}", file=sys.stderr)
        return 1
    host = f"[{info['ip']}]" if ":" in info["ip"] else info["ip"]
    print(f"HTTPS certificate issued for https://{host}:8001; expires {info['leaf_expires'].date()} UTC.")
    print(f"Public CA certificate (copy ONLY this file to your phone): {info['ca_path']}")
    print(f"CA SHA-256 fingerprint: {info['fingerprint']}")
    print("Keep local_ca.key and jarvis.key private; protect the certs folder with OS permissions.")
    print("Trusting this CA grants it broad certificate-issuing authority on that device.")
    print("Enable dashboard_https in config/api_keys.json, restart JARVIS, then trust the public CA on your phone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
