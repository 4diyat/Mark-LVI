"""
dashboard/server.py — JARVIS Local HTTP Dashboard

HTTPS on port 8000 with a self-signed certificate generated on first run, plus
a second layer inside it: commands are encrypted with AES-256-GCM under a key
derived from the pairing code with PBKDF2. Both layers are required — the
server refuses to start without TLS rather than quietly serving in clear.

Install deps:  pip install fastapi "uvicorn[standard]" cryptography
"""

import asyncio
import base64
import hashlib
import re
import secrets
import socket
import string
import threading
import time
from pathlib import Path

_DEPS_OK = False
try:
    from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
    from fastapi.responses import HTMLResponse, JSONResponse, FileResponse
    import uvicorn
    _DEPS_OK = True
except ImportError:
    pass

# python-multipart is required for file uploads — optional dependency
_UPLOAD_OK = False
try:
    from fastapi import UploadFile, File as FastAPIFile
    _UPLOAD_OK = True
except Exception:
    pass

# The dashboard runs in the app's process and its failures were previously
# invisible: the routes are wrapped in try/except for good reason (a phone
# disconnecting must not stop the server), and `pass` turned "the phone cannot
# reach us" into "no reason given". `_dlog` writes to logs/jarvis.log and to the
# console, so the answer survives the terminal being closed.
from core.logbook import get as _get_logger
_dlog = _get_logger("dashboard")

BASE_DIR    = Path(__file__).resolve().parent.parent
STATIC_DIR  = Path(__file__).parent / "static"
# The port people TYPE, and the port the app actually runs on.
#
# They are not the same, and that is the fix for the most confusing failure
# this dashboard had. A bare `192.168.1.108:8000` typed into a phone browser is
# tried over HTTP; against a TLS listener that means the connection is accepted,
# found to carry no handshake, and closed — which Chrome reports as "refused to
# connect". The server is running perfectly and the user is told it is off.
#
# So the port people reach for answers in the protocol they reach for it with,
# and sends them one hop to the secure one. The QR code carries the secure URL
# directly, so it never takes the hop.
PORT        = 8000      # HTTP, redirects to SECURE_PORT
SECURE_PORT = 8001      # HTTPS, the dashboard itself
MAX_UPLOAD_MB = 500


def _make_uploads_dir() -> Path:
    """Return (and create) the cross-platform uploads folder."""
    for candidate in [
        Path.home() / "Downloads" / "JARVIS Uploads",
        Path.home() / "Documents" / "JARVIS Uploads",
        BASE_DIR / "uploads",
    ]:
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            return candidate
        except Exception:
            pass
    return BASE_DIR / "uploads"


UPLOADS_DIR = _make_uploads_dir()

def _get_gemini_key() -> str | None:
    try:
        import json as _json
        with open(BASE_DIR / "config" / "api_keys.json", "r", encoding="utf-8") as f:
            return _json.load(f).get("gemini_api_key")
    except Exception:
        return None

_KEY_CHARS = [c for c in (string.ascii_uppercase + string.digits)
              if c not in ('O', 'I', 'L', '0', '1')]

# ── AES-256-CBC ───────────────────────────────────────────────────────────────
_AES_SALT = b'JARVIS-DASHBOARD-v1'


# Rounds for the pairing key -> AES key derivation.
#
# WHY THIS IS NOT ONE ROUND OF SHA-256, WHICH IS WHAT IT WAS
#     The pairing key is short because a person has to read it off a screen and
#     type it into a phone. Eight characters from a 31-letter alphabet is about
#     forty bits — fine against someone guessing at the login endpoint, which
#     is rate limited below, and NOT fine against someone who captured one
#     encrypted command and can guess offline as fast as their GPU allows.
#
#     At one round of SHA-256 that offline search is seconds. PBKDF2 at 200k
#     rounds makes each guess about five orders of magnitude more expensive
#     while costing this server ~80 ms once per session, at pairing time, where
#     nobody is waiting on a millisecond.
_KDF_ROUNDS = 200_000


def _derive_key(session_key: str) -> bytes:
    """Pairing key → 32-byte AES-256 key, deliberately slowly. See _KDF_ROUNDS."""
    return hashlib.pbkdf2_hmac(
        "sha256", session_key.encode("utf-8"), _AES_SALT, _KDF_ROUNDS, dklen=32
    )


def _decrypt(aes_key: bytes, enc_b64: str) -> str:
    """Decrypt base64(nonce[12] ‖ ciphertext‖tag) with AES-256-GCM.

    GCM RATHER THAN THE CBC THIS REPLACES
        CBC has no authentication. It hides a message and does nothing to stop
        one being CHANGED: an attacker on the same network can flip bits in the
        ciphertext and the server decrypts whatever falls out, with no way to
        tell. For a channel whose whole purpose is carrying commands to an
        assistant that opens applications and sends messages, "the text was
        secret" is the smaller half of what matters — "the text is the one that
        was sent" is the other half, and CBC never provided it.

        GCM authenticates as it decrypts. A single altered byte raises
        InvalidTag and the request is refused rather than obeyed.

    The old CBC path is not kept as a fallback on purpose. An attacker who can
    choose which format the server accepts can simply choose the weak one, and
    a downgrade left available is a downgrade that will be used.
    """
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    raw = base64.b64decode(enc_b64)
    if len(raw) < 13:
        raise ValueError("ciphertext too short to contain a nonce")
    nonce, payload = raw[:12], raw[12:]
    return AESGCM(aes_key).decrypt(nonce, payload, None).decode("utf-8")


_BLOCK_CACHE = None


def blocking_firewall_rules() -> list:
    """Inbound Windows BLOCK rules aimed at the interpreter running this app.

    Public, read-only and never elevated, so the interface can warn about the
    one failure that is invisible from inside the app: a block rule overrides
    every allow rule, so the server listens correctly and the phone still
    cannot reach it. Empty on every other platform and whenever nothing is
    blocked.

    -> [(rule name, program path), ...]
    """
    import sys
    if sys.platform != "win32":
        return []

    # Cached for the process. Reading every inbound rule costs about a second,
    # and this is called from the Qt thread when the Remote Control panel
    # opens — a second of frozen interface every time, for an answer that only
    # changes when somebody edits their firewall.
    global _BLOCK_CACHE
    if _BLOCK_CACHE is not None:
        return _BLOCK_CACHE
    import os
    import subprocess

    py_exe = sys.executable
    sibling = os.path.join(
        os.path.dirname(py_exe),
        "pythonw.exe" if py_exe.lower().endswith("python.exe") else "python.exe")
    wanted = {py_exe.lower()}
    if os.path.exists(sibling):
        wanted.add(sibling.lower())

    found: list = []
    try:
        r = subprocess.run(
            ["netsh", "advfirewall", "firewall", "show", "rule",
             "name=all", "dir=in", "verbose"],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=20,
        )
        name = program = None
        for line in r.stdout.splitlines():
            if line.startswith("Rule Name:"):
                name = line.split(":", 1)[1].strip()
                program = None
            elif line.startswith("Program:"):
                program = line.split(":", 1)[1].strip().lower()
            elif line.startswith("Action:"):
                if (name and program and program in wanted
                        and line.split(":", 1)[1].strip().lower() == "block"
                        and (name, program) not in found):
                    found.append((name, program))
    except Exception as exc:
        print(f"[Dashboard] could not read the firewall rules: {exc}")
    _BLOCK_CACHE = found
    return found


_ACCESS_ASKED = False


def report_network_access(*ports: int) -> bool:
    """Read-only, never elevated: can a phone reach the dashboard? Prints why
    not. Called at startup instead of fixing anything.

    WHY STARTUP NO LONGER FIXES IT
        It used to repair the firewall on every launch, and repairing it needs
        administrator rights — so the app greeted people with Windows' "allow
        this app to make changes to your device?" dialog before it had done
        anything. On a machine where a Windows firewall popup had once been
        cancelled, that block rule came back and so did the dialog, every
        single start. For an open-source app that is the worst first
        impression available: an unexplained request for admin. The repair now
        happens only when somebody opens REMOTE CONTROL — the one feature that
        needs it — where the dialog has an obvious reason.
    """
    import sys
    if sys.platform != "win32":
        return True
    try:
        blocked = blocking_firewall_rules()
    except Exception:
        return True
    if blocked:
        print("[Dashboard] Windows Firewall is blocking this Python from the "
              "network — the phone dashboard will not connect until that is "
              "fixed. Open REMOTE CONTROL to fix it (Windows will ask once).")
        return False
    return True


def fix_network_access(*ports: int) -> None:
    """Make the dashboard reachable from the phone — at most once per run,
    and only because the user asked for the phone dashboard."""
    global _ACCESS_ASKED
    if _ACCESS_ASKED:
        return
    _ACCESS_ASKED = True
    _ensure_network_access(*ports)


def _ensure_network_access(*ports: int) -> None:
    """Cross-platform, best-effort: open port in the OS firewall for LAN access.

    Runs in a background thread. Only ever reached through fix_network_access,
    i.e. from the user opening REMOTE CONTROL — never at startup.

    Windows : writes a .bat file, runs it elevated via Windows ShellExecuteW
              (native UAC dialog, guaranteed to appear). One-time setup.
    macOS   : osascript admin dialog if the Application Firewall is on.
    Linux   : pkexec GUI → sudo -n → prints manual command as fallback.
    """
    import sys, subprocess, os, tempfile, threading

    # ── Windows ──────────────────────────────────────────────────────────────
    if sys.platform == "win32":
        import ctypes, time

        # Every port in one pass. Called once per port, this asked for
        # elevation once per port — two UAC dialogs for one dashboard, and two
        # racing .bat files whose output interleaved into contradictory
        # messages on the console.
        port_rules = {pt: f"JARVIS Dashboard Port {pt}" for pt in ports}
        prog_rule  = "JARVIS Dashboard Python"

        # BOTH interpreters, because the app runs under either one.
        #
        # THIS IS THE BUG THAT MADE THE PHONE UNREACHABLE FROM THE SHORTCUT.
        #     Started from an editor the app runs under `python.exe`. The
        #     desktop shortcut targets `pythonw.exe`, so that there is no
        #     console window — a different executable, and Windows Firewall
        #     rules are per-executable. Allowing one said nothing about the
        #     other, and the symptom was a dashboard that worked when launched
        #     one way and "refused to connect" when launched the other, on the
        #     same machine and the same network.
        py_exe = sys.executable
        _sibling = os.path.join(os.path.dirname(py_exe),
                                "pythonw.exe" if py_exe.lower().endswith("python.exe")
                                else "python.exe")
        py_exes = [py_exe] + ([_sibling] if os.path.exists(_sibling) else [])

        def _netsh_rule_exists(name: str) -> bool:
            try:
                r = subprocess.run(
                    ["netsh", "advfirewall", "firewall", "show", "rule", f"name={name}"],
                    capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=5,
                )
                return r.returncode == 0 and "No rules match" not in r.stdout
            except Exception:
                return False

        def _network_is_public() -> bool:
            try:
                r = subprocess.run(
                    ["powershell", "-NoProfile", "-NonInteractive", "-Command",
                     "(Get-NetConnectionProfile | "
                     "Where-Object {$_.NetworkCategory -eq 'Public'} | "
                     "Measure-Object).Count"],
                    capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=6,
                )
                return r.stdout.strip() not in ("", "0")
            except Exception:
                return False

        # One implementation, at module scope — see blocking_firewall_rules().
        # There were briefly two, and they disagreed about their return type,
        # which surfaced as 'too many values to unpack' in the error path.
        blocked      = blocking_firewall_rules()
        missing_ports = [pt for pt, nm in port_rules.items()
                         if not _netsh_rule_exists(nm)]
        need_prog    = not _netsh_rule_exists(prog_rule)
        if _network_is_public():
            print("[Dashboard] This network is set to Public in Windows, which "
                  "blocks phones on it. If it is your own network, set it to "
                  "Private in Settings > Network & internet. JARVIS will not "
                  "change that for you — on public Wi-Fi it would expose this "
                  "computer.")
        need_private = False

        if blocked:
            print(f"[Dashboard] Windows is BLOCKING inbound connections to "
                  f"{', '.join(sorted(set(os.path.basename(e) for e in py_exes)))} "
                  f"({len(blocked)} block rule(s)). Your phone cannot reach the "
                  f"dashboard until those are removed — asking for permission "
                  f"to do that now.")

        if not missing_ports and not need_prog and not need_private and not blocked:
            return  # already fully configured

        # Build a .bat file — netsh + powershell, runs fast when elevated
        bat_lines = ["@echo off"]
        if need_private:
            bat_lines.append(
                'powershell -NoProfile -NonInteractive -Command "'
                'Get-NetConnectionProfile | '
                "Where-Object {$_.NetworkCategory -eq 'Public'} | "
                'Set-NetConnectionProfile -NetworkCategory Private"'
            )
        for pt in missing_ports:
            bat_lines.append(
                f'netsh advfirewall firewall add rule '
                f'name="{port_rules[pt]}" protocol=TCP dir=in '
                f'localport={pt} action=allow'
            )
        # Remove the blocks FIRST. Adding an allow rule beside a block rule
        # changes nothing at all — Windows resolves the conflict in the block's
        # favour — so this is the line that actually fixes the connection.
        for rule_name in blocked:
            bat_lines.append(
                f'netsh advfirewall firewall delete rule '
                f'name="{rule_name}" dir=in'
            )

        if need_prog or blocked:
            # One allow rule per interpreter. `add rule` with an existing name
            # appends rather than replacing, so deleting first keeps this from
            # accumulating a new copy on every launch.
            bat_lines.append(
                f'netsh advfirewall firewall delete rule name="{prog_rule}" dir=in'
            )
            for exe in py_exes:
                bat_lines.append(
                    f'netsh advfirewall firewall add rule '
                    f'name="{prog_rule}" dir=in action=allow '
                    f'program="{exe}" enable=yes'
                )

        # Say what will be attempted, so a UAC prompt nobody expected has a
        # reason attached to it in the terminal.
        if blocked:
            print("[Dashboard] The Windows prompt about to appear is JARVIS "
                  "removing those block rules. Declining it leaves the phone "
                  "dashboard unreachable, and nothing else is affected.")

        bat_body = "\r\n".join(bat_lines) + "\r\n"
        fd, bat_path = tempfile.mkstemp(suffix=".bat", prefix="jarvis_fw_")
        try:
            os.write(fd, bat_body.encode("mbcs"))   # Windows cmd.exe expects ANSI
            os.close(fd)
        except Exception:
            try:
                os.close(fd)
            except Exception:
                pass
            return

        # ── Try running directly (succeeds when already admin) ────────────────
        try:
            # cmd /c, not shell=True: a .bat is batch, not a shell command
            # line. `shell=True` over a list is also the one form whose meaning
            # differs between platforms, and it is the shape antivirus and
            # SmartScreen heuristics flag.
            r = subprocess.run(
                ["cmd", "/c", bat_path], capture_output=True, timeout=8
            )
            if r.returncode == 0:
                print(f"[Dashboard] Firewall configured for {', '.join(str(pt) for pt in ports)}.")
                try:
                    os.unlink(bat_path)
                except OSError as e:
                    _dlog.debug("firewall script left behind (%s): %s", bat_path, e)
                return
        except Exception as e:
            # Not admin yet — the UAC path below is the normal route, so this
            # is expected rather than an error. Recorded because the case that
            # IS a bug looks identical from the outside: a rule that never gets
            # added.
            _dlog.debug("firewall: direct run failed, trying UAC: %s", e)

        # ── ShellExecuteW: native UAC elevation (most reliable on Windows) ────
        # ShellExecuteW with verb "runas" always shows the UAC dialog regardless
        # of UAC level settings. Non-blocking — uvicorn is already running.
        print("[Dashboard] One-time network setup required.")
        print("[Dashboard] >>> A Windows security dialog will appear — click 'Yes' <<<")
        try:
            ret = ctypes.windll.shell32.ShellExecuteW(
                None,       # hwnd  (no parent window)
                "runas",    # verb  (request elevation)
                bat_path,   # file  (our .bat)
                None,       # params
                None,       # working dir
                0,          # SW_HIDE (run without a visible cmd window)
            )
            if int(ret) > 32:
                # ShellExecuteW returns immediately; bat finishes in ~1 second.
                # Sleep briefly so the rules are in place before the first retry.
                time.sleep(2)
                # CHECK, DO NOT ASSUME. ShellExecuteW succeeding means the
                # dialog was accepted, not that netsh did what was asked — and
                # the whole point of this release is not to report an outcome
                # nobody looked at.
                still = blocking_firewall_rules()
                if still:
                    print("[Dashboard] ⚠️  Windows is STILL blocking inbound "
                          "connections to this interpreter.")
                    print("[Dashboard] ⚠️  Remove these by hand in Windows "
                          "Defender Firewall > Inbound Rules: "
                          + ", ".join(sorted({n for n, _ in still})))
                else:
                    print(f"[Dashboard] Network setup complete — "
                          f"{', '.join(str(pt) for pt in ports)} open.")
                    print("[Dashboard] Refresh your phone browser to connect.")
            else:
                print("[Dashboard] Setup was not allowed.")
                if blocked:
                    print("[Dashboard] Your phone CANNOT reach the dashboard "
                          "until this is done: Windows has block rules for "
                          + ", ".join(sorted({n for n, _ in blocked}))
                          + " which override every allow rule.")
                    print("[Dashboard] Either restart JARVIS and accept the "
                          "prompt, or delete those rules in Windows Defender "
                          "Firewall > Inbound Rules.")
                else:
                    print("[Dashboard] Phone connections may fail until JARVIS "
                          "is run as Administrator.")
        except Exception as e:
            print(f"[Dashboard] Firewall setup error: {e}")
        finally:
            # Cleanup after the bat has had time to run
            def _cleanup(path: str) -> None:
                time.sleep(5)
                try:
                    os.unlink(path)
                except Exception:
                    pass
            threading.Thread(target=_cleanup, args=(bat_path,), daemon=True).start()
        return

    # ── macOS ─────────────────────────────────────────────────────────────────
    if sys.platform == "darwin":
        fw_ctl = "/usr/libexec/ApplicationFirewall/socketfilterfw"
        try:
            r = subprocess.run(
                [fw_ctl, "--getglobalstate"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=5,
            )
            if "disabled" in r.stdout.lower():
                return  # firewall off — nothing to do

            py = sys.executable
            listed = subprocess.run(
                [fw_ctl, "--listapps"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=5,
            )
            if py in listed.stdout:
                return  # already allowed

            print("[Dashboard] One-time network setup — enter your password in the macOS dialog.")
            subprocess.run(
                ["osascript", "-e",
                 f'do shell script "{fw_ctl} --add {py} && {fw_ctl} --unblockapp {py}"'
                 f' with administrator privileges'],
                timeout=60,
            )
        except FileNotFoundError:
            pass  # macOS firewall is off by default — nothing to do
        except Exception as e:
            # Not silent any more. This is the branch shape that hid the Linux
            # `port` NameError for a release: a broad except, a comment saying
            # the failure does not matter, and a swallow. macOS with the
            # firewall ON is exactly where this one DOES matter.
            _dlog.warning("macOS firewall setup failed: %s", e)
        return

    # ── Linux ─────────────────────────────────────────────────────────────────
    def _privileged(cmd: list[str]) -> bool:
        for prefix in (["pkexec"], ["sudo", "-n"]):
            try:
                r = subprocess.run(prefix + cmd, capture_output=True, timeout=30)
                if r.returncode == 0:
                    return True
            except Exception:
                pass
        return False

    # WHY THIS LOOPS OVER `ports` AND NOT OVER A VARIABLE CALLED `port`
    #     This block used to read `f"{port}/tcp"`, `str(port)` and so on. There
    #     was no `port` — the parameter is `*ports`, plural — so every one of
    #     those lines raised NameError. Each branch below is wrapped in
    #     try/except, but the catches list FileNotFoundError, so the NameError
    #     escaped each one in turn and landed in the caller's bare `except
    #     Exception`: the whole Linux path did nothing at all. No port was
    #     opened and — worse for an app whose rule is to never claim an outcome
    #     nobody observed — no manual `sudo ufw allow …` line was printed
    #     either. The dashboard never worked from a phone on Linux and said
    #     nothing about it. Windows was unaffected: it already looped.
    #
    #     pyflakes reports this as F821 undefined-name, which is why CI now runs
    #     a lint step: 9 lines of this file were dead code that looked alive.
    #
    # And the failures SPEAK now. "Your phone cannot reach the dashboard" with
    # no reason attached is the failure this whole file keeps trying to avoid,
    # so each tool reports which ports it opened and which it could not.
    wanted = [int(pt) for pt in ports]

    try:  # ufw
        r = subprocess.run(["ufw", "status"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=5)
        if "active" in r.stdout.lower():
            failed = []
            for port in wanted:
                if _privileged(["ufw", "allow", f"{port}/tcp"]):
                    print(f"[Dashboard] ufw: port {port} allowed.")
                else:
                    failed.append(port)
            for port in failed:
                print(f"[Dashboard] Run manually:  sudo ufw allow {port}/tcp")
            return
    except FileNotFoundError:
        pass
    except Exception as e:
        print(f"[Dashboard] ufw check failed: {e}")

    try:  # firewalld
        r = subprocess.run(
            ["firewall-cmd", "--state"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=5,
        )
        if "running" in r.stdout.lower():
            ok = all(_privileged(["firewall-cmd", "--add-port", f"{port}/tcp", "--permanent"])
                     for port in wanted)
            if ok:
                _privileged(["firewall-cmd", "--reload"])
                for port in wanted:
                    print(f"[Dashboard] firewalld: port {port} allowed.")
            else:
                for port in wanted:
                    print(f"[Dashboard] Run manually:  sudo firewall-cmd --add-port={port}/tcp --permanent"
                          " && sudo firewall-cmd --reload")
            return
    except FileNotFoundError:
        pass
    except Exception as e:
        print(f"[Dashboard] firewalld check failed: {e}")

    try:  # iptables (not persistent but works until reboot)
        r = subprocess.run(["iptables", "-L", "INPUT", "-n"], capture_output=True, timeout=5)
        if r.returncode == 0:
            failed = []
            for port in wanted:
                if _privileged(["iptables", "-A", "INPUT", "-p", "tcp", "--dport", str(port), "-j", "ACCEPT"]):
                    print(f"[Dashboard] iptables: port {port} opened.")
                else:
                    failed.append(port)
            for port in failed:
                print(f"[Dashboard] Run manually:  sudo iptables -A INPUT -p tcp "
                      f"--dport {port} -j ACCEPT")
    except FileNotFoundError:
        pass  # no iptables means firewall is probably off — nothing to do
    except Exception as e:
        print(f"[Dashboard] iptables check failed: {e}")




# ── helpers ───────────────────────────────────────────────────────────────────

def _local_ip() -> str:
    """Return the best LAN-facing IPv4 address, no internet required."""
    # Method 1: route trick (fast, works when internet is available)
    for probe in ("8.8.8.8", "1.1.1.1", "192.168.1.1"):
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(0.5)
            s.connect((probe, 80))
            ip = s.getsockname()[0]
            s.close()
            if not ip.startswith("127."):
                return ip
        except OSError as e:
            # Two more methods follow; this one fails on a machine with no
            # route out (which is a normal way to run a LAN dashboard).
            _dlog.debug("local IP, UDP probe failed: %s", e)

    # Method 2: hostname resolution (works offline on most systems)
    try:
        ip = socket.gethostbyname(socket.gethostname())
        if not ip.startswith("127."):
            return ip
    except OSError as e:
        _dlog.debug("local IP, hostname lookup failed: %s", e)

    # Method 3: enumerate all interfaces (fully offline, no external deps)
    try:
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if not ip.startswith("127.") and not ip.startswith("169.254."):
                return ip
    except OSError as e:
        _dlog.debug("local IP, interface enumeration failed: %s", e)

    # The QR code then shows localhost, which no phone can reach — the one
    # symptom of this that a person sees, so the reason belongs in the log.
    _dlog.debug("no LAN address found; the dashboard link will say 127.0.0.1")
    return "127.0.0.1"


def _ensure_certs() -> bool:
    """
    Make sure config/certs holds a TLS key pair, generating a self-signed one the
    first time the dashboard runs.

    The pair is deliberately NOT shipped in the repository. A private key that
    every user downloads is the same as having no private key at all: anyone can
    present a certificate that matches it. Generating locally gives each install
    its own key, costs about a second, and happens exactly once.

    Returns True when a usable pair exists afterwards; False leaves the caller on
    plain HTTP, which still works — the QR code simply encodes http:// instead.
    """
    certs = BASE_DIR / "config" / "certs"
    key_p = certs / "jarvis.key"
    crt_p = certs / "jarvis.crt"
    if key_p.exists() and crt_p.exists():
        return True

    try:
        import datetime
        import ipaddress
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.x509.oid import NameOID
    except ImportError:
        print("[Dashboard] cryptography not installed — serving over plain HTTP.")
        print("[Dashboard] For HTTPS run:  pip install cryptography")
        return False

    try:
        certs.mkdir(parents=True, exist_ok=True)
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

        who = x509.Name([
            x509.NameAttribute(NameOID.COMMON_NAME, "JARVIS Dashboard"),
            x509.NameAttribute(NameOID.ORGANIZATION_NAME, "JARVIS"),
        ])

        # The SAN has to cover every address the phone might use: the LAN IP the
        # QR code encodes, plus localhost when testing on the machine itself.
        alt = [x509.DNSName("localhost"),
               x509.IPAddress(ipaddress.IPv4Address("127.0.0.1"))]
        try:
            lan = _local_ip()
            if not lan.startswith("127."):
                alt.append(x509.IPAddress(ipaddress.IPv4Address(lan)))
        except Exception as e:
            # A certificate without the LAN address is still a working
            # certificate for localhost, but it is why a phone with TLS on will
            # reject it — worth a line in the log.
            _dlog.info("no LAN address for the certificate: %s", e)

        # Timezone-aware UTC: datetime.utcnow() is deprecated from Python 3.12 on,
        # and the builder normalises aware values to UTC itself.
        now = datetime.datetime.now(datetime.timezone.utc)
        cert = (
            x509.CertificateBuilder()
            .subject_name(who)
            .issuer_name(who)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(days=1))
            .not_valid_after(now + datetime.timedelta(days=3650))
            .add_extension(x509.SubjectAlternativeName(alt), critical=False)
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .sign(key, hashes.SHA256())
        )

        key_p.write_bytes(key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        ))
        crt_p.write_bytes(cert.public_bytes(serialization.Encoding.PEM))

        try:
            import os as _os
            _os.chmod(key_p, 0o600)   # best effort — largely a no-op on Windows
        except Exception as e:
            _dlog.warning("could not restrict the TLS key's permissions: %s", e)

        print(f"[Dashboard] Generated a self-signed certificate for this machine: {certs}")
        return True
    except Exception as e:
        print(f"[Dashboard] Certificate generation failed ({e}) — serving over plain HTTP.")
        return False


def _read(name: str) -> str:
    return (STATIC_DIR / name).read_text(encoding="utf-8")


def _dir_size_mb(path: Path) -> float:
    """Total size of the uploads folder, in MB. Never raises.

    A phone upload is capped at MAX_UPLOAD_MB per file, which bounds one request
    and says nothing about the folder: fifty files fill a disk on the machine
    the assistant is meant to be running on, and the failure it causes is not
    "upload failed" but "everything else stopped working, including the app".
    """
    total = 0
    try:
        for entry in path.iterdir():
            try:
                if entry.is_file():
                    total += entry.stat().st_size
            except OSError:
                continue
    except OSError:
        return 0.0
    return total / (1024 * 1024)


def _sweep_uploads(path: Path, max_age_days: int | None = None) -> int:
    """Delete uploads older than `max_age_days`. Returns how many went.

    Called once at startup, in the server's own thread. A file somebody sent
    from their phone two weeks ago and never opened again is not a record of
    anything — it is clutter that quietly fills the quota above.
    """
    if max_age_days is None:
        max_age_days = _UPLOAD_MAX_AGE_DAYS
    cutoff = time.time() - max_age_days * 86400
    removed = 0
    try:
        for entry in path.iterdir():
            try:
                if entry.is_file() and entry.stat().st_mtime < cutoff:
                    entry.unlink()
                    removed += 1
            except OSError:
                continue
    except OSError:
        return 0
    if removed:
        print(f"[Dashboard] Removed {removed} upload(s) older than {max_age_days} days.")
    return removed


# ── DashboardServer ───────────────────────────────────────────────────────────

# How long an auth token stays valid, and how many failed logins an address
# gets before it has to wait.
#
# The old code had neither. A token, once issued, worked until the process
# ended — no expiry, no logout — and /login accepted unlimited guesses at the
# pairing key as fast as a script could send them. Eight characters is a large
# space, but "large" is not the same as "let them try forever": the point of a
# limit is that an attacker's cost grows while a person who mistypes their key
# twice never notices it exists.
_TOKEN_TTL_SECONDS = 12 * 3600
# A token nobody has used for this long is dropped even if the 12 hours are not
# up. A phone left in a drawer should not still be able to send commands.
_TOKEN_IDLE_SECONDS = 2 * 3600
_LOGIN_MAX_TRIES   = 6
_LOGIN_WINDOW      = 300.0      # seconds the counter looks back over
_LOGIN_LOCKOUT     = 300.0      # seconds an address waits after using them up

# ── What a token is allowed to do ────────────────────────────────────────────
# Not every paired device should be able to type into the assistant. A QR code
# is a cheap thing to show somebody, and "look at what JARVIS is doing" is a
# different permission from "tell JARVIS what to do". A paired token carries
# "command" because that is what the dashboard is FOR; a device token can be
# given "read" only, and the difference is enforced here rather than trusted to
# the page.
_SCOPE_COMMAND = "command"      # send commands, upload files, wake it
_SCOPE_READ    = "read"         # watch the feed and the status only

# ── Security headers ─────────────────────────────────────────────────────────
# WHAT THESE ARE FOR, GIVEN THE DASHBOARD ALREADY HAS AUTH
#     They are not about the person holding the phone. They are about what the
#     PAGE can be made to do in a browser that is also logged in somewhere else:
#
#     * `default-src 'self'` with no `unsafe-inline` for scripts. Both pages
#       ship one inline <script> block, so the policy uses a per-response nonce
#       (see _security_headers) — an injected <script> from a message body, a
#       file name or a chat reply has no nonce and does not run.
#     * `frame-ancestors 'none'` / X-Frame-Options: the dashboard cannot be
#       framed, so a page on another origin cannot overlay invisible controls
#       over it and collect taps.
#     * `Referrer-Policy: no-referrer` — the download URL carries the auth token
#       in its query string (a browser <a download> cannot send a header), and a
#       Referer header would hand that token to whoever the page linked to.
#     * `X-Content-Type-Options: nosniff` — a file uploaded from the phone is
#       served back under its own name; without this a browser may sniff an
#       uploaded .html or .js and run it on this origin.
#     * A Permissions-Policy that switches off everything the page does not use.
_DEVICE_TOKEN_IDLE_SECONDS = 30 * 86400   # a remembered phone, unused for a month
_MAX_LOGIN_BODY = 4096          # /login carries a key and nothing else
_MAX_COMMAND_BODY = 64 * 1024   # a command is one sentence; 64 KB is generous
_MAX_KEY_BYTES = 1024           # an encrypted command is small
_UPLOAD_QUOTA_MB = 2000         # total, across the uploads folder
_UPLOAD_MAX_AGE_DAYS = 14       # older files are swept at startup


class _Throttle:
    """Failed-attempt counter, per client address.

    Deliberately tiny and in memory: it protects a pairing key that is itself
    only alive for ten minutes, so nothing here needs to survive a restart.
    Successful logins clear the count, which keeps a household on one address
    from locking itself out because somebody fumbled the code once.
    """

    def __init__(self):
        self._fails: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def blocked_for(self, who: str) -> float:
        """Seconds this address must wait, or 0."""
        now = time.time()
        with self._lock:
            tries = [t for t in self._fails.get(who, []) if now - t < _LOGIN_WINDOW]
            self._fails[who] = tries
            if len(tries) < _LOGIN_MAX_TRIES:
                return 0.0
            return max(0.0, _LOGIN_LOCKOUT - (now - tries[-1]))

    def record_failure(self, who: str) -> None:
        with self._lock:
            self._fails.setdefault(who, []).append(time.time())

    def clear(self, who: str) -> None:
        with self._lock:
            self._fails.pop(who, None)


class DashboardServer:

    def __init__(self):
        self._ip                          = _local_ip()
        # token -> issued-at. A set had no way to expire anything; this does,
        # and `_auth` sweeps as it reads so nothing has to run a timer.
        # auth_token → [issued_at, last_seen, scope]. A bare issued-at could
        # only answer "is this 12 hours old"; a phone left in a drawer stayed
        # valid until the clock ran out, whoever was holding it.
        self._tokens: dict[str, list]     = {}
        self._token_keys: dict[str, str]  = {}   # auth_token → session_key
        self._aes_cache:  dict[str, bytes]= {}   # session_key → AES bytes
        self._clients: set[WebSocket]     = set()
        self._history: list[dict]         = []
        self._command_queue               = asyncio.Queue()
        self._wake_callback               = None
        self._connect_callback            = None
        self._pending_keys: dict[str, float] = {}
        self._throttle                    = _Throttle()
        # device_token → {"session_key": str, "scope": str, "last_seen": float}
        self._device_sessions: dict[str, dict] = {}
        # Serialises the token dictionaries. FastAPI may run two requests on
        # different threads (a sync route pool) and the WebSocket handler lives
        # on the loop, so a `dict.pop` on one while another iterates is not a
        # theoretical race — it is a RuntimeError waiting for a slow phone.
        self._token_lock = threading.Lock()
        self._audit: list[dict] = []          # last N dashboard actions
        self._audit_lock = threading.Lock()
        self._phone_audio_queue: asyncio.Queue    = asyncio.Queue(maxsize=200)
        self._uploads_dir                 = UPLOADS_DIR
        # Set by serve() when the port could not be taken, so the UI can say
        # why the QR code leads nowhere instead of showing it regardless.
        self._bind_error: str = ""
        self._login_html                  = _read("login.html")
        self._app_html                    = _read("app.html")
        self._sweep_tokens()
        # Refuse to serve a page whose inline script the CSP would block. The
        # two must agree, and a page with no nonce placeholder is the one way
        # they silently stop agreeing — the result is a blank dashboard.
        for _name, _html in (("login.html", self._login_html),
                             ("app.html", self._app_html)):
            if "<script" in _html and "__NONCE__" not in _html:
                print(f"[Dashboard] ⚠️  {_name} has an inline <script> with no "
                      f"nonce placeholder; CSP will block it.")
        self.app                          = self._build_app()

    # ── one-time key management ───────────────────────────────────────────

    def new_key(self, expiry_secs: int = 600) -> str:
        now = time.time()
        self._pending_keys = {k: v for k, v in self._pending_keys.items() if v > now}
        key = ''.join(secrets.choice(_KEY_CHARS) for _ in range(8))
        self._pending_keys[key] = now + expiry_secs
        return key

    @staticmethod
    def _ssl_enabled() -> bool:
        """Is HTTPS switched on? Off unless the user asked for it.

        WHY THE DEFAULT IS PLAIN HTTP, AFTER A RELEASE THAT MADE TLS MANDATORY
            The certificate has to be self-signed — there is no certificate
            authority on earth that will vouch for 192.168.1.108 — and a phone
            treats a self-signed certificate as an attack. Chrome shows a
            full-page interstitial; a QR scanner that opens links in its own
            in-app browser often shows nothing at all and offers no way to
            proceed, because those views deliberately have no "Advanced" button.

            So the practical result of requiring TLS was a dashboard nobody
            could reach, which is not a more secure product than one they can.
            The pairing key, the rate limit, the token expiry and the
            revoke-all-devices fix are all unaffected and all still apply.

            What IS lost over plain HTTP is the AES-GCM layer, because
            `crypto.subtle` does not exist outside a secure context. The page
            says so on its own badge rather than pretending, and commands then
            travel the local network in clear — which is what this dashboard
            did for every release before this one.

            Turn it on with "dashboard_https": true in config/api_keys.json if
            the network is one where that matters; the certificate is generated
            automatically and you will have to accept it once per device.
        """
        try:
            import json as _json
            with open(BASE_DIR / "config" / "api_keys.json", "r",
                      encoding="utf-8") as f:
                if not _json.load(f).get("dashboard_https"):
                    return False
        except Exception:
            return False
        certs = BASE_DIR / "config" / "certs"
        return (certs / "jarvis.key").exists() and (certs / "jarvis.crt").exists()

    def get_url(self) -> str:
        """The full URL the QR code carries — always with its scheme, so a
        scanner never has to guess."""
        if self._ssl_enabled():
            return f"https://{self._ip}:{SECURE_PORT}"
        return f"http://{self._ip}:{PORT}"

    def get_manual_url(self) -> str:
        """What to type into a phone browser by hand.

        Points at the redirect port when TLS is on, because a bare `ip:port`
        typed into a browser is tried over HTTP — and HTTP against the TLS port
        looks exactly like the server being switched off. The redirector speaks
        HTTP, so it answers, and sends the browser on to the secure page.
        """
        return f"{self._ip}:{PORT}"

    def _sweep_tokens(self) -> None:
        """Drop expired sessions and forgotten devices. Called at startup.

        Lives in one function because the rule is easy to state and easy to
        scatter: a token stops working when it ages out, and a device pairing
        stops working when the phone has not come back for a month. The second
        half did not exist — a paired phone token worked forever.
        """
        now = time.time()
        with self._token_lock:
            dead = [t for t, rec in self._tokens.items()
                    if now - rec[0] > _TOKEN_TTL_SECONDS
                    or now - rec[1] > _TOKEN_IDLE_SECONDS]
            for t in dead:
                self._tokens.pop(t, None)
                self._token_keys.pop(t, None)
            stale = [d for d, e in self._device_sessions.items()
                     if now - e.get("last_seen", now) > _DEVICE_TOKEN_IDLE_SECONDS]
            for d in stale:
                self._device_sessions.pop(d, None)
        if dead or stale:
            print(f"[Dashboard] Cleared {len(dead)} expired session(s), "
                  f"{len(stale)} forgotten device(s).")

    def _aes_key(self, session_key: str) -> bytes:
        """Derive (once) and cache the AES key for a pairing key.

        80 ms of PBKDF2 per session is the point; keeping every one of them
        forever is not. Each dashboard open from the UI mints a new pairing key,
        so this dict grew for the life of the process. Capped here rather than
        swept on a timer: 32 entries is far more than the handful a phone can
        hold open, and evicting the oldest costs one re-derivation nobody feels.
        """
        if session_key not in self._aes_cache:
            if len(self._aes_cache) >= 32:
                self._aes_cache.pop(next(iter(self._aes_cache)), None)
            self._aes_cache[session_key] = _derive_key(session_key)
        return self._aes_cache[session_key]

    def _decrypt(self, token: str, enc_b64: str) -> str | None:
        sk = self._token_keys.get(token)
        if not sk:
            return None
        try:
            return _decrypt(self._aes_key(sk), enc_b64)
        except Exception:
            return None

    # ── callbacks ────────────────────────────────────────────────────────

    def set_wake_callback(self, fn) -> None:
        self._wake_callback = fn

    def set_connect_callback(self, fn) -> None:
        self._connect_callback = fn

    # ── broadcast ────────────────────────────────────────────────────────

    async def broadcast(self, msg: dict) -> None:
        self._history.append(msg)
        if len(self._history) > 300:
            self._history = self._history[-300:]
        dead: set[WebSocket] = set()
        for ws in list(self._clients):
            try:
                await ws.send_json(msg)
            except Exception as e:
                # Expected when a phone sleeps or walks out of Wi-Fi range; the
                # point of logging it is that a client that fails EVERY send is
                # a different problem from one that closed.
                _dlog.debug("dropped a client: %s", e)
                dead.add(ws)
        self._clients -= dead

    # ── FastAPI app ───────────────────────────────────────────────────────

    def _build_app(self) -> "FastAPI":
        app = FastAPI(docs_url=None, redoc_url=None)

        def _valid(tok: str, need: str = _SCOPE_READ) -> bool:
            """Is this token live, and may it do `need`?

            Two clocks, not one. The absolute TTL stops a token lasting forever;
            the idle window stops one nobody is using from still working
            because it happens to be inside the 12 hours. Every check refreshes
            last_seen, so a page that is open keeps working and a page that was
            abandoned stops.

            Expired tokens are dropped as they are found, which keeps the sweep
            free and needs no background timer.
            """
            if not tok:
                return False
            now = time.time()
            with self._token_lock:
                rec = self._tokens.get(tok)
                if rec is None:
                    return False
                issued, last_seen, scope = rec
                if (now - issued > _TOKEN_TTL_SECONDS
                        or now - last_seen > _TOKEN_IDLE_SECONDS):
                    self._tokens.pop(tok, None)
                    self._token_keys.pop(tok, None)
                    return False
                if need == _SCOPE_COMMAND and scope != _SCOPE_COMMAND:
                    return False
                rec[1] = now
            return True

        def _auth(req: Request, need: str = _SCOPE_COMMAND) -> bool:
            return _valid(req.headers.get("authorization", "")
                          .removeprefix("Bearer ").strip(), need)

        def _issue_token(session_key: str, scope: str = _SCOPE_COMMAND) -> str:
            tok = secrets.token_urlsafe(32)
            now = time.time()
            with self._token_lock:
                self._tokens[tok] = [now, now, scope]
                self._token_keys[tok] = session_key
            return tok

        def _audit_event(kind: str, who: str, detail: str = "") -> None:
            """Record one dashboard action, in memory, capped.

            The dashboard is a remote control for a program that can delete
            files and drive the keyboard. When somebody asks "did my phone send
            that?", the answer used to be a shrug and whatever was still in the
            console scrollback. This keeps the last 200 actions on the machine
            that received them.
            """
            entry = {"at": time.time(), "kind": kind, "who": who, "detail": detail[:200]}
            with self._audit_lock:
                self._audit.append(entry)
                if len(self._audit) > 200:
                    del self._audit[:len(self._audit) - 200]
            print(f"[Dashboard] {kind} from {who}{(': ' + detail[:60]) if detail else ''}")

        def _who(req: Request) -> str:
            """The client address a throttle counts against."""
            return (getattr(getattr(req, "client", None), "host", "") or "unknown")

        # ── Security headers, applied to every response ──────────────────────
        # Implemented as middleware rather than per-route so a route added later
        # cannot forget them, and so the WebSocket handshake carries them too.
        @app.middleware("http")
        async def _security_headers(request: Request, call_next):
            response = await call_next(request)
            # setdefault, NOT assignment. _page() below has already set a CSP
            # carrying the exact nonce that its <script> tag uses; overwriting
            # it here would hand the browser a policy naming a different nonce
            # and block the page's own script — a hardening layer that breaks
            # the page is the same failure as no layer at all.
            response.headers.setdefault(
                "Content-Security-Policy",
                "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
                "img-src 'self' data: blob:; media-src 'self' blob:; "
                "connect-src 'self' ws: wss:; worker-src 'self' blob:; "
                "frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
            response.headers.setdefault("X-Content-Type-Options", "nosniff")
            response.headers.setdefault("X-Frame-Options", "DENY")
            response.headers.setdefault("Referrer-Policy", "no-referrer")
            response.headers.setdefault(
                "Permissions-Policy",
                "camera=(), geolocation=(), payment=(), usb=(), "
                "microphone=(self)")       # the phone mic is a deliberate feature
            response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
            # The download route puts the auth token in the URL; no cache keeps it.
            response.headers.setdefault("Cache-Control", "no-store")
            return response

        def _page(html: str) -> HTMLResponse:
            """HTML with the per-response nonce substituted into <script>."""
            nonce = secrets.token_urlsafe(16)
            html = html.replace("{{NONCE}}", nonce).replace("__NONCE__", nonce)
            resp = HTMLResponse(html)
            resp.headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                f"script-src 'self' 'nonce-{nonce}'; "
                "style-src 'self' 'unsafe-inline'; "
                "img-src 'self' data: blob:; "
                "media-src 'self' blob:; "
                "connect-src 'self' ws: wss:; "
                "worker-src 'self' blob:; "
                "frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
            )
            resp.headers["X-Content-Type-Options"] = "nosniff"
            resp.headers["X-Frame-Options"] = "DENY"
            resp.headers["Referrer-Policy"] = "no-referrer"
            resp.headers["Cache-Control"] = "no-store"
            return resp

        @app.get("/login", response_class=HTMLResponse)
        async def login_page():
            return _page(self._login_html)

        @app.get("/", response_class=HTMLResponse)
        async def index():
            # Auth is handled client-side via sessionStorage bearer token.
            # Server-side header auth can't work here because browser navigations
            # don't send custom headers (location.href doesn't carry Authorization).
            html = (self._app_html
                    .replace("__IP__", self._ip)
                    .replace("__PORT__", str(PORT)))
            return _page(html)

        @app.post("/login")
        async def login(req: Request):
            who  = _who(req)
            wait = self._throttle.blocked_for(who)
            if wait > 0:
                # 429 rather than 401 on purpose: it tells an honest user why
                # their correct key was refused, and it tells a script that
                # guessing is not working.
                return JSONResponse(
                    {"ok": False,
                     "error": f"Too many attempts. Try again in "
                              f"{int(wait) + 1} seconds."},
                    status_code=429,
                )
            if int(req.headers.get("content-length") or 0) > _MAX_LOGIN_BODY:
                return JSONResponse({"ok": False, "error": "Bad request"}, status_code=400)
            try:
                body = await req.json()
            except Exception:
                return JSONResponse({"ok": False, "error": "Bad request"}, status_code=400)
            if not isinstance(body, dict):
                return JSONResponse({"ok": False, "error": "Bad request"}, status_code=400)
            entered = str(body.get("pin", ""))[:64].strip().upper()
            now     = time.time()
            if entered in self._pending_keys and self._pending_keys[entered] > now:
                self._throttle.clear(who)
                del self._pending_keys[entered]          # one-time use
                tok = _issue_token(entered, _SCOPE_COMMAND)
                self._aes_key(entered)                   # pre-derive & cache
                if self._connect_callback:
                    self._connect_callback()
                asyncio.create_task(self.broadcast(
                    {"type": "sys", "text": "Remote connection established."}
                ))
                # Bearer token in response body — no cookies needed (works on any browser/HTTP)
                return JSONResponse({"ok": True, "token": tok})
            self._throttle.record_failure(who)
            return JSONResponse({"ok": False, "error": "Invalid or expired key"},
                                status_code=401)

        @app.get("/auto-login")
        async def auto_login(key: str = ""):
            """QR code target — validates one-time key, creates session, redirects phone."""
            now = time.time()
            if not key or key not in self._pending_keys or self._pending_keys[key] <= now:
                return HTMLResponse("""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width">
<style>
  body{background:#07090f;color:#dde3ed;font-family:sans-serif;
       display:flex;align-items:center;justify-content:center;height:100vh;margin:0;text-align:center}
  h2{color:#f87171;margin-bottom:12px}p{color:#5e6a7e;font-size:14px}
</style></head>
<body><div><h2>Link Expired</h2>
<p>Press <strong style="color:#dde3ed">Remote Control</strong> in JARVIS to get a new QR code.</p>
</div></body></html>""")

            del self._pending_keys[key]
            tok     = _issue_token(key, _SCOPE_COMMAND)
            dev_tok = secrets.token_urlsafe(32)
            self._aes_key(key)
            self._device_sessions[dev_tok] = {
                "session_key": key,
                "scope": _SCOPE_COMMAND,
                "last_seen": time.time(),
            }

            if self._connect_callback:
                self._connect_callback()
            asyncio.create_task(self.broadcast(
                {"type": "sys", "text": "Remote connection established via QR code."}
            ))

            return HTMLResponse(f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width">
<style>
  body{{background:#07090f;color:#dde3ed;font-family:sans-serif;
       display:flex;align-items:center;justify-content:center;height:100vh;margin:0;text-align:center}}
  p{{color:#5e6a7e;font-size:14px}}
</style></head>
<body>
<script>
  sessionStorage.setItem('jarvis_token','{tok}');
  sessionStorage.setItem('jarvis_key','{key}');
  localStorage.setItem('jarvis_device_token','{dev_tok}');
  setTimeout(function(){{location.replace('/')}},400);
</script>
<p>Connecting to JARVIS…</p>
</body></html>""")

        @app.post("/api/device-login")
        async def device_login_ep(req: Request):
            """Return a fresh auth token for a previously paired device token."""
            try:
                body = await req.json()
            except Exception:
                return JSONResponse({"ok": False}, status_code=400)
            dev_tok = (body.get("device_token") or "").strip()
            if not dev_tok or dev_tok not in self._device_sessions:
                return JSONResponse({"ok": False}, status_code=401)
            entry = self._device_sessions[dev_tok]
            session_key = entry["session_key"]
            entry["last_seen"] = time.time()
            tok = _issue_token(session_key, entry.get("scope", _SCOPE_COMMAND))
            self._aes_key(session_key)
            if self._connect_callback:
                self._connect_callback()
            asyncio.create_task(self.broadcast(
                {"type": "sys", "text": "Known device reconnected automatically."}
            ))
            return JSONResponse({"ok": True, "token": tok, "key": session_key})

        @app.post("/api/revoke-devices")
        async def revoke_devices(req: Request):
            """Invalidate all persistent device tokens (admin action)."""
            if not _auth(req):
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            # ALSO drop the live tokens, which this did not do.
            #
            # It cleared the remembered devices and left every session those
            # devices had already opened working until the app restarted — so
            # "revoke all devices" revoked nothing anybody was currently using,
            # which is the one case somebody presses it for.
            #
            # The caller's own token is kept, or pressing the button would log
            # out the person who pressed it.
            mine = req.headers.get("authorization", "").removeprefix("Bearer ").strip()
            with self._token_lock:
                count = len(self._device_sessions)
                live  = len(self._tokens) - (1 if mine in self._tokens else 0)
                self._device_sessions.clear()
                keep      = self._tokens.get(mine)
                keep_key  = self._token_keys.get(mine)
                self._tokens.clear()
                self._token_keys.clear()
                if keep is not None:
                    self._tokens[mine] = keep
                    self._token_keys[mine] = keep_key
            _audit_event("revoked-devices", _who(req), f"{count} devices, {live} sessions")
            return JSONResponse({"ok": True, "revoked": count, "sessions_ended": live})

        @app.post("/api/command")
        async def command(req: Request):
            # A command is one sentence. Without a cap, "send a 200 MB body to
            # /api/command" is a way to make the assistant's own machine spend
            # its memory before any auth check runs inside req.json().
            if int(req.headers.get("content-length") or 0) > _MAX_COMMAND_BODY:
                return JSONResponse({"error": "Command too large"}, status_code=413)
            if not _auth(req, _SCOPE_COMMAND):
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            try:
                body = await req.json()
            except Exception:
                return JSONResponse({"error": "Bad request"}, status_code=400)
            if not isinstance(body, dict):
                return JSONResponse({"error": "Bad request"}, status_code=400)
            token = req.headers.get("authorization", "").removeprefix("Bearer ").strip()
            enc   = str(body.get("enc") or "")[: _MAX_KEY_BYTES * 4]
            if enc:
                text = self._decrypt(token, enc)
                if text is None:
                    return JSONResponse({"error": "Decryption failed"}, status_code=400)
            else:
                text = str(body.get("text") or "").strip()
            text = text[:2000]
            if text:
                _audit_event("command", _who(req), text)
                await self._command_queue.put(text)
                if self._wake_callback:
                    self._wake_callback()
            return JSONResponse({"ok": True})

        @app.post("/api/wake")
        async def wake_ep(req: Request):
            if not _auth(req, _SCOPE_COMMAND):
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            _audit_event("wake", _who(req))
            if self._wake_callback:
                self._wake_callback()
            return JSONResponse({"ok": True})

        # ── Phone mic real-time audio → Gemini Live ──────────────────────────

        @app.websocket("/ws/phone-audio")
        async def phone_audio_ws(websocket: WebSocket, token: str = ""):
            tok = token.strip()
            if not _valid(tok, _SCOPE_COMMAND):
                await websocket.close(code=4001)
                return
            await websocket.accept()
            asyncio.create_task(self.broadcast(
                {"type": "sys", "text": "Phone microphone live."}
            ))
            try:
                while True:
                    data = await websocket.receive_bytes()
                    try:
                        self._phone_audio_queue.put_nowait(
                            {"data": data, "mime_type": "audio/pcm"}
                        )
                    except asyncio.QueueFull:
                        pass  # drop frame rather than block
            except WebSocketDisconnect:
                pass
            finally:
                asyncio.create_task(self.broadcast(
                    {"type": "sys", "text": "Phone microphone stopped."}
                ))

        # ── File sharing ──────────────────────────────────────────────────────

        def _safe_filename(raw: str) -> str:
            name = Path(raw).name                          # strip path components
            name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', name).strip(". ")
            return name or "upload"

        if _UPLOAD_OK:
            @app.post("/api/upload")
            async def upload_file(req: Request, file: UploadFile = FastAPIFile(...)):
                if not _auth(req):
                    return JSONResponse({"error": "Unauthorized"}, status_code=401)

                safe = _safe_filename(file.filename or "upload")
                dest = self._uploads_dir / safe
                stem, suffix = Path(safe).stem, Path(safe).suffix
                counter = 1
                while dest.exists():
                    dest = self._uploads_dir / f"{stem}_{counter}{suffix}"
                    counter += 1

                size = 0
                max_bytes = MAX_UPLOAD_MB * 1024 * 1024
                # One 500 MB file is a decision; fifty of them is a full disk on
                # the machine the assistant is supposed to be running.
                used_mb = _dir_size_mb(self._uploads_dir)
                if used_mb + (int(req.headers.get("content-length") or 0) >> 20) > _UPLOAD_QUOTA_MB:
                    return JSONResponse(
                        {"error": f"Uploads folder is full ({used_mb:.0f} MB of "
                                  f"{_UPLOAD_QUOTA_MB} MB). Delete some files and retry."},
                        status_code=507,
                    )
                try:
                    with open(dest, "wb") as fout:
                        while True:
                            chunk = await file.read(65536)
                            if not chunk:
                                break
                            size += len(chunk)
                            if size > max_bytes:
                                fout.close()
                                dest.unlink(missing_ok=True)
                                return JSONResponse(
                                    {"error": f"File too large (max {MAX_UPLOAD_MB} MB)"},
                                    status_code=413,
                                )
                            fout.write(chunk)
                except Exception as exc:
                    try:
                        dest.unlink(missing_ok=True)
                    except Exception:
                        pass
                    return JSONResponse({"error": str(exc)}, status_code=500)

                _audit_event("upload", _who(req), f"{dest.name} ({size // 1024} KB)")
                asyncio.create_task(self.broadcast({
                    "type": "file_received",
                    "name": dest.name,
                    "size": size,
                    "saved_to": str(self._uploads_dir),
                }))
                return JSONResponse({"ok": True, "name": dest.name, "size": size})
        else:
            @app.post("/api/upload")
            async def upload_unavailable(req: Request):
                return JSONResponse(
                    {"error": "File uploads require: pip install python-multipart"},
                    status_code=503,
                )

        @app.get("/api/files")
        async def list_files(req: Request):
            if not _auth(req):
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            files = []
            try:
                for f in sorted(
                    (p for p in self._uploads_dir.iterdir() if p.is_file()),
                    key=lambda p: p.stat().st_mtime,
                    reverse=True,
                ):
                    files.append({"name": f.name, "size": f.stat().st_size})
            except OSError as e:
                # Listing a folder that was deleted, or a file that vanished
                # between iterdir() and stat(). The list is a convenience; an
                # empty one with a reason in the log beats a 500.
                _dlog.debug("listing uploads: %s", e)
            return JSONResponse({"files": files})

        @app.get("/api/devices")
        async def list_devices(req: Request):
            """What is paired with this machine, so 'revoke all' is not a blind
            button. Counts and ages only — no tokens leave this route."""
            if not _auth(req, _SCOPE_READ):
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            now = time.time()
            with self._token_lock:
                live = [
                    {"age_s": int(now - rec[0]), "idle_s": int(now - rec[1]),
                     "scope": rec[2]}
                    for rec in self._tokens.values()
                ]
                paired = [{"idle_days": int((now - d.get("last_seen", now)) / 86400),
                           "scope": d.get("scope", _SCOPE_COMMAND)}
                          for d in self._device_sessions.values()]
            return JSONResponse({"ok": True, "live_sessions": live, "paired_devices": paired})

        @app.get("/api/audit")
        async def audit_log(req: Request):
            """The last 200 dashboard actions, for "did my phone do that?"."""
            if not _auth(req, _SCOPE_READ):
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            with self._audit_lock:
                return JSONResponse({"ok": True, "entries": list(self._audit[-200:])})

        @app.get("/uploads/{filename}")
        async def download_file(filename: str, token: str = ""):
            # Auth via query param — browser <a download> can't send custom headers
            tok = token.strip()
            if not _valid(tok, _SCOPE_READ):
                return JSONResponse({"error": "Unauthorized"}, status_code=401)
            safe = re.sub(r'[/\\]', '', filename)
            path = self._uploads_dir / safe
            if not path.exists() or not path.is_file():
                return JSONResponse({"error": "Not found"}, status_code=404)
            return FileResponse(str(path), filename=safe)

        @app.websocket("/ws")
        async def ws_ep(websocket: WebSocket, token: str = ""):
            tok = token.strip()
            # Reading the feed needs read scope; sending a command over this
            # socket is checked again below, because one connection can be
            # opened with a read-only token and then try to type into JARVIS.
            if not _valid(tok, _SCOPE_READ):
                await websocket.close(code=4001)
                return
            await websocket.accept()
            self._clients.add(websocket)
            for entry in self._history[-50:]:
                try:
                    await websocket.send_json(entry)
                except Exception:
                    break
            try:
                while True:
                    data = await websocket.receive_json()
                    if data.get("type") == "command":
                        if not _valid(tok, _SCOPE_COMMAND):
                            await websocket.send_json(
                                {"type": "sys", "text": "This device may watch, not command."})
                            continue
                        enc = str(data.get("enc", "") or "")[: _MAX_KEY_BYTES * 4]
                        t   = self._decrypt(tok, enc) if enc else str(data.get("text") or "").strip()
                        t   = t[:2000]
                        if t:
                            await self._command_queue.put(t)
                            if self._wake_callback:
                                self._wake_callback()
            except WebSocketDisconnect:
                pass
            finally:
                self._clients.discard(websocket)

        return app

    # ── serve ─────────────────────────────────────────────────────────────

    async def _serve_redirector(self) -> None:
        """A plain-HTTP listener whose only job is to send people to HTTPS.

        THE PROBLEM THIS SOLVES, WHICH LOOKED LIKE THE SERVER BEING DOWN
            Type `192.168.1.108:8000` into a phone browser and it tries HTTP.
            The TLS server accepts the connection, finds no handshake and
            closes it — which Chrome reports as "This site can't be reached,
            192.168.1.108 refused to connect". The server is running perfectly
            and the user is told it is off.

            The port that used to sit here was a SECOND HTTPS server, added on
            the belief that browsers upgrade a bare `ip:port` to https. Some
            do. Android Chrome does not, so the second port had exactly the
            same failure as the first.

        So this speaks HTTP, and answers everything with a redirect to the same
        path on the HTTPS port. Typing the address by hand now works, which is
        what people do when a QR code is inconvenient.
        """
        from fastapi.responses import RedirectResponse

        bounce = FastAPI(docs_url=None, redoc_url=None)

        @bounce.get("/{path:path}")
        async def _to_https(path: str, request: Request):
            query = f"?{request.url.query}" if request.url.query else ""
            return RedirectResponse(
                f"https://{self._ip}:{SECURE_PORT}/{path}{query}",
                status_code=307)

        cfg = uvicorn.Config(bounce, host="0.0.0.0", port=PORT,
                             log_level="warning")
        print(f"[Dashboard] Type by hand:  {self._ip}:{PORT}  "
              f"(sends you to the secure page)")
        await uvicorn.Server(cfg).serve()

    async def serve(self) -> None:
        if not _DEPS_OK:
            print("[Dashboard] fastapi/uvicorn not installed — dashboard disabled.")
            print("[Dashboard] Run:  pip install fastapi 'uvicorn[standard]' cryptography")
            return

        # Startup only CHECKS — see report_network_access for why it never
        # asks for administrator rights here. In a thread: reading the
        # firewall rules takes about a second.
        asyncio.get_running_loop().run_in_executor(
            None, report_network_access, PORT, SECURE_PORT)

        # Only make a certificate if HTTPS was actually asked for. Generating
        # one nobody uses just leaves a private key on disk.
        try:
            import json as _json
            with open(BASE_DIR / "config" / "api_keys.json", "r",
                      encoding="utf-8") as f:
                if _json.load(f).get("dashboard_https"):
                    _ensure_certs()
        except Exception as e:
            # A missing or corrupt config means HTTPS was not asked for. When
            # it WAS asked for and this failed, the server below starts on
            # plain HTTP — worth knowing before blaming the phone.
            _dlog.debug("could not read dashboard_https: %s", e)

        use_ssl  = self._ssl_enabled()
        ssl_key  = BASE_DIR / "config" / "certs" / "jarvis.key"
        ssl_cert = BASE_DIR / "config" / "certs" / "jarvis.crt"

        # TLS IS WANTED, BUT NOT AT THE COST OF NOT STARTING.
        #
        # An earlier version returned here when certificates could not be made,
        # on the argument that serving a remote-control channel in clear is a
        # different product. The argument is right and the behaviour was wrong:
        # a dashboard that does not start is not more secure, it is absent, and
        # the user is left with "refused to connect" and nothing to act on.
        #
        # So: HTTPS whenever it can be had — which is almost always, since the
        # certificate is generated locally on first run — and plain HTTP with a
        # loud, repeated warning when it cannot. The page keeps working either
        # way; without a secure context it simply cannot encrypt, and it says
        # so on screen rather than pretending.
        if use_ssl:
            asyncio.create_task(self._serve_redirector())
        else:
            print("[Dashboard] Plain HTTP on your local network. Commands are "
                  "not encrypted; the pairing key still gates access.")
            print('[Dashboard] For HTTPS set "dashboard_https": true in '
                  'config/api_keys.json (your phone will ask you to trust the '
                  'certificate once).')

        cfg = uvicorn.Config(
            self.app, host="0.0.0.0",
            port=SECURE_PORT if use_ssl else PORT, log_level="warning",
            **({"ssl_keyfile": str(ssl_key), "ssl_certfile": str(ssl_cert)}
               if use_ssl else {}),
        )

        # CAN THIS PORT ACTUALLY BE TAKEN?
        #
        # uvicorn raises when the port is busy, and under pythonw.exe there is
        # no console for that to be seen in — so a second JARVIS, or anything
        # else already on 8000, produced a dashboard that was silently dead
        # while the HUD went on showing a QR code pointing at it. The phone
        # then reports ERR_CONNECTION_REFUSED, which is true and impossible to
        # act on.
        #
        # Asking first costs a millisecond and turns that into a sentence.
        import socket as _socket
        # No SO_REUSEADDR. On Windows that option lets a second socket bind a
        # port another socket already holds — which is exactly the condition
        # being tested for, so setting it made the probe always succeed.
        _probe = _socket.socket()
        try:
            _probe.bind(("0.0.0.0", SECURE_PORT if use_ssl else PORT))
        except OSError as exc:
            _probe.close()
            self._bind_error = (
                f"port {SECURE_PORT if use_ssl else PORT} is already in use — "
                f"another copy of JARVIS is probably running. Close it and "
                f"restart, or the phone dashboard will stay unreachable "
                f"({exc.__class__.__name__})")
            print(f"[Dashboard] {self._bind_error}")
            return
        _probe.close()

        # Expired uploads go before anybody can reach the quota above. Off the
        # loop: it walks a folder that may hold thousands of files.
        try:
            await asyncio.to_thread(_sweep_uploads, self._uploads_dir)
        except Exception as e:
            print(f"[Dashboard] Upload sweep skipped: {e}")

        print(f"[Dashboard] {self.get_url()}")
        print("[Dashboard] Press 'Remote Control' in JARVIS UI to get the QR code.")
        await uvicorn.Server(cfg).serve()
