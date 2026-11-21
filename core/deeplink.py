"""`jarvis://` — the one address that reaches a running assistant.

WHY THIS EXISTS
    The app now has four ways to be started and no way to be REACHED. Every
    integration an operating system offers beyond a launch icon is an address:
    a browser link, a shortcut in another program, a Stream Deck button, a
    notification handler, a shell alias. Without a scheme, all of them can only
    do the one thing the tray already does — bring the window forward — and
    anything that should carry a REQUEST (say this, open that) has no way to say
    what it wants.

THE RULE THIS MODULE FOLLOWS
    A URL is UNTRUSTED INPUT. It arrives from a browser, a chat message, a
    web page, an address bar — anything that can call `open`. The whole class of
    bug here is an attacker writing `jarvis://run?cmd=...` and having the
    assistant execute it. So:

      * there is NO verb that runs a command, opens a file by path, or touches
        the config. The vocabulary is what the TRAY can already do, plus one:
        `summon`, `hide`, `ask`.
      * `ask` is the only one that carries text, and the text is bounded,
        single-purpose, and handed to the SESSION as a user turn — the same
        place a typed message or a spoken sentence goes. It cannot pick a tool,
        name a file, or set a flag.
      * every parameter is validated and REJECTED rather than repaired: an
        unknown verb, a query on a verb that takes none, text longer than the
        cap, control characters, NUL bytes. Nothing is silently truncated into
        something that means a different thing.
      * a URL with userinfo (`jarvis://user:pass@…`), a port, or a fragment is
        refused. None of them mean anything here, and accepting them quietly is
        how a parser and a caller end up disagreeing about what was asked.

WHY IT IS PURE
    Nothing in this file opens a socket, writes a file or needs Qt. `parse()`
    turns a string into a `Request` or raises `Rejected` with a sentence fit to
    show a user; `dispatch()` calls the handler the caller supplies. That is
    what makes the security properties checkable on a machine with no browser
    and no display — which is every CI runner here.
"""
from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import parse_qs, urlsplit

SCHEME = "jarvis"

# The whole vocabulary. Deliberately tiny, and deliberately the same set of
# things a person could already do without this file existing.
VERBS = ("summon", "hide", "ask")

# `ask` carries speech, not structure. 500 characters is two or three sentences
# — long enough for "remind me to call the dentist at four", short enough that
# nothing can be smuggled in behind a legitimate-looking question.
MAX_TEXT = 500

# Refused explicitly rather than ignored. Each of these parses to something
# Python accepts and a human would not expect.
_FORBIDDEN_PARTS = ("username", "password", "port", "fragment")


class Rejected(ValueError):
    """A URL this scheme does not accept. The message is shown to the user."""


@dataclass(frozen=True)
class Request:
    """What a URL asked for, validated.

    `verb` is always one of `VERBS`; `text` is only ever set for `ask`. A
    Request cannot express anything else — there is no field to put a path, a
    command or a setting in, which is the point: the type is the policy.
    """

    verb: str
    text: str = ""

    def as_dict(self) -> dict:
        return {"verb": self.verb, "text": self.text}


def parse(url: str) -> Request:
    """Turn `jarvis://…` into a Request, or raise `Rejected`.

    The two shapes accepted:

        jarvis://summon            (also jarvis:summon — see `_split`)
        jarvis://ask?text=...      text is required, url-encoded
        jarvis://hide

    A trailing slash is allowed; anything else in the path is not.
    """
    if not isinstance(url, str):
        raise Rejected("not a link")
    raw = url.strip()
    if not raw:
        raise Rejected("empty link")

    # Case-insensitive scheme: `JARVIS://summon` arrives from a browser that
    # normalised it, and refusing the upper case would be a coin flip for the
    # user over a detail nobody controls.
    if raw.lower().startswith(f"{SCHEME}:"):
        if not raw.lower().startswith(f"{SCHEME}://"):
            # `jarvis:summon` — a browser will pass this through. Handled here
            # rather than by rewriting the string, so what was parsed is what
            # arrived.
            rest = raw[len(SCHEME) + 1:]
            raw = f"{SCHEME}://{rest}"

    try:
        parts = urlsplit(raw)
    except ValueError as e:
        raise Rejected(f"that link is malformed ({e})") from None

    if parts.scheme.lower() != SCHEME:
        raise Rejected(f"not a {SCHEME}: link")

    for field in _FORBIDDEN_PARTS:
        if getattr(parts, field, None):
            raise Rejected(f"a {SCHEME}: link cannot carry a {field}")

    verb = parts.netloc.strip().lower()
    if not verb:
        raise Rejected("the link does not say what to do")
    if verb not in VERBS:
        raise Rejected(
            f"unknown action '{verb}' — this assistant understands: "
            + ", ".join(VERBS))
    if parts.path not in ("", "/"):
        raise Rejected(f"'{verb}' does not take a path")

    query = parse_qs(parts.query, keep_blank_values=True)
    if verb != "ask":
        if query:
            raise Rejected(f"'{verb}' does not take any parameters")
        return Request(verb)

    if set(query) - {"text"}:
        unknown = sorted(set(query) - {"text"})[0]
        raise Rejected(f"'ask' does not take a '{unknown}' parameter")
    text = (query.get("text") or [""])[0]
    if len(query.get("text") or []) > 1:
        raise Rejected("'ask' takes one text parameter")
    text = _clean_text(text)
    return Request(verb, text)


def _clean_text(text: str) -> str:
    """Validate the only free-form thing this scheme accepts.

    Control characters are refused, not stripped: a NUL or an escape sequence
    removed from the middle of a sentence changes its meaning, and the caller
    deserves to know their link was wrong rather than to have it edited.
    """
    if not text:
        raise Rejected("'ask' needs something to say")
    if len(text) > MAX_TEXT:
        raise Rejected(f"that text is too long ({len(text)} > {MAX_TEXT} characters)")
    if any(ch < " " or ch == "\x7f" for ch in text):
        raise Rejected("that text contains control characters")
    return text


def dispatch(request: Request, *, summon, hide, ask) -> bool:
    """Run a parsed Request through the caller's three handlers.

    `ask` returns True when the request was actually delivered — the session may
    not be up yet, and a link that said something into a microphone nobody is
    reading must not report success. `dispatch` passes that answer back for the
    same reason: a shell command or a browser popup that closes with no message
    leaves the user unable to tell "it worked" from "nothing happened".
    """
    if request.verb == "summon":
        summon()
        return True
    if request.verb == "hide":
        hide()
        return True
    if request.verb == "ask":
        return bool(ask(request.text))
    raise Rejected(f"unknown action '{request.verb}'")     # unreachable: parse()


# ── registering the scheme with the operating system ────────────────────────
#
# Every platform stores this somewhere different, and every one of them has a
# detail that fails silently if it is wrong. The text builders are separate
# functions so the exact bytes can be asserted without writing to a registry.

def windows_command(script: str, python: str | None = None) -> str:
    r"""The `shell\open\command` value, quoted.

    `"%pythonw%" "%script%" "%1"` — `%1` is the URL, in quotes, and the
    interpreter is `pythonw.exe` where it exists so a link does not flash a
    console. Unquoted, `C:\Program Files\...` splits at the first space and the
    registration points at a program that does not exist.
    """
    import sys
    from pathlib import Path

    exe = python or sys.executable
    if Path(exe).name.lower() == "python.exe":
        windowed = Path(exe).parent / "pythonw.exe"
        if windowed.exists():
            exe = str(windowed)
    return f'"{exe}" "{script}" "%1"'


def linux_desktop_text(script: str, python: str | None = None,
                       name: str = "J.A.R.V.I.S") -> str:
    r"""A `.desktop` file with `MimeType=x-scheme-handler/jarvis` and `%u`.

    `%u` — a single URL — is what the spec requires for a scheme handler;
    `%U` (a list) would be accepted by the parser and then passed as several
    arguments, and `%f` (a file) means the URL arrives as a path with the
    scheme stripped. Each of those is a handler that starts but cannot read
    what it was given.
    """
    from core.autostart import _exec_value

    from core.app_identity import icon_path, startup_wm_class

    # The handler's own icon, in the same folder the tray draws to. A `.desktop`
    # pointing at a path that does not exist gets a generic icon, and the user
    # has no way to tell it is the app's fault.
    icon = icon_path(Path(script).resolve().parent)
    exe = _exec_value(script, python, args=("%u",))
    # Only when the file is really there: a `.desktop` pointing at a missing
    # icon gets a generic one anyway, and an empty `Icon=` is worse than none.
    icon_line = f"Icon={icon}\n" if icon.is_file() else ""
    return (
        "[Desktop Entry]\n"
        "Type=Application\n"
        f"Name={name}\n"
        f"Exec={exe}\n"
        "Terminal=false\n"
        f"StartupWMClass={startup_wm_class()}\n"
        "NoDisplay=true\n"          # a handler is not something to launch from a menu
        f"MimeType=x-scheme-handler/{SCHEME};\n"
        "Categories=Utility;\n"
        + icon_line
    )


def mac_info_plist(app_name: str = "JARVIS") -> str:
    """The `CFBundleURLTypes` fragment an `.app` needs to receive the scheme.

    Returned as text to be merged into the bundle's `Info.plist`; the caller
    owns that file. `CFBundleURLName` must be unique across the system, which is
    why it is a reverse-DNS identifier rather than the scheme itself.
    """
    from core.app_identity import APP_ID

    return (
        "<key>CFBundleURLTypes</key>\n"
        "<array><dict>\n"
        f"  <key>CFBundleURLName</key><string>{APP_ID}</string>\n"
        "  <key>CFBundleURLSchemes</key>\n"
        f"  <array><string>{SCHEME}</string></array>\n"
        f"  <key>CFBundleTypeRole</key><string>Viewer</string>\n"
        f"  <key>CFBundleURLIconFile</key><string>{app_name}</string>\n"
        "</dict></array>\n"
    )


# ── actually registering it ────────────────────────────────────────────────
#
# The text builders above describe the entries; these write them. Split for the
# same reason `core/autostart.py` is split: the format can be asserted on any
# machine, and the write is one small function per platform that a test can
# point at a temporary directory.

import os
import platform
import subprocess
import sys
from pathlib import Path

# Windows: HKCU\Software\Classes\jarvis. Per-user, no elevation — the same rule
# as auto-start, and for the same reason: an assistant that asks for
# administrator rights to be reachable is one most people will not install.
_WIN_CLASSES = r"Software\Classes"


def _win_registry(*args):
    import winreg
    return winreg, args


def _enable_windows_scheme(script: str) -> None:
    winreg, _ = _win_registry()
    root = winreg.HKEY_CURRENT_USER
    base = f"{_WIN_CLASSES}\\{SCHEME}"

    def _set(path: str, name: str, value: str) -> None:
        with winreg.CreateKeyEx(root, path, 0, winreg.KEY_WRITE) as key:
            winreg.SetValueEx(key, name, 0, winreg.REG_SZ, value)

    # `URL Protocol` (a value with an EMPTY name) is what makes Windows treat
    # the key as a protocol handler rather than a file extension. Without it
    # the registration is accepted, appears correct in regedit, and the scheme
    # does nothing at all — which is the failure this project keeps fixing.
    _set(base, "", f"URL:{SCHEME} protocol")
    _set(base, "URL Protocol", "")
    _set(f"{base}\\DefaultIcon", "", f'"{script}",0')
    _set(f"{base}\\shell\\open\\command", "", windows_command(script))


def _disable_windows_scheme() -> None:
    import winreg
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER,
                         f"{_WIN_CLASSES}\\{SCHEME}\\shell\\open\\command")
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER,
                         f"{_WIN_CLASSES}\\{SCHEME}\\shell\\open")
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER,
                         f"{_WIN_CLASSES}\\{SCHEME}\\shell")
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER,
                         f"{_WIN_CLASSES}\\{SCHEME}\\DefaultIcon")
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, f"{_WIN_CLASSES}\\{SCHEME}")
    except FileNotFoundError:
        pass              # already gone: disabling twice is not an error


def applications_path(script: str | Path | None = None) -> "object":
    """Where a Linux handler lives: `$XDG_DATA_HOME/applications`.

    Not `.local/share/autostart` and not `/usr/share/applications`: the first
    is for things that start with the session, and the second needs root. The
    per-user applications folder is the one `update-desktop-database` reads for
    the person who installed this.
    """
    env = os.environ.get("XDG_DATA_HOME")
    base = Path(env) if env else Path.home() / ".local" / "share"
    return base / "applications" / f"{SCHEME}-handler.desktop"


def _enable_linux_scheme(script: str | Path) -> None:
    path = applications_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(linux_desktop_text(str(Path(script).resolve())), encoding="utf-8")
    try:
        path.chmod(0o755)
    except OSError:
        pass
    # Two commands, both of which only rebuild a cache — a missing one is not a
    # failure, because the handler file itself is already correct and the
    # desktop reads it on next login.
    for command in (["update-desktop-database", str(path.parent)],
                    ["xdg-mime", "default", f"{SCHEME}-handler.desktop",
                     f"x-scheme-handler/{SCHEME}"]):
        try:
            subprocess.run(command, capture_output=True, timeout=10, check=False)
        except (OSError, subprocess.SubprocessError):
            continue


def _enable_mac_scheme(script: str | Path) -> None:
    """The bundle has to exist before it can claim a scheme.

    A `.app` is the only thing macOS will register a URL type from, so this
    writes a minimal one whose launcher runs the real interpreter and script.
    `LSUIElement` is deliberately absent: the app may show a window.
    """
    from core.app_identity import APP_ID, APP_NAME, icon_path

    script = Path(script).resolve()
    app = Path.home() / "Applications" / f"{APP_NAME}.app"
    contents = app / "Contents"
    macos = contents / "MacOS"
    macos.mkdir(parents=True, exist_ok=True)

    launcher = macos / "JARVIS"
    launcher.write_text(
        "#!/usr/bin/env bash\n"
        f'exec "{sys.executable}" "{script}" "$@"\n'
    )
    launcher.chmod(0o755)
    (contents / "Info.plist").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
        '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
        '<plist version="1.0"><dict>\n'
        '  <key>CFBundleExecutable</key><string>JARVIS</string>\n'
        f'  <key>CFBundleIdentifier</key><string>{APP_ID}</string>\n'
        f'  <key>CFBundleName</key><string>{APP_NAME}</string>\n'
        '  <key>CFBundlePackageType</key><string>APPL</string>\n'
        + mac_info_plist()
        + '</dict></plist>\n',
        encoding="utf-8",
    )
    # The bundle's own icon, copied rather than referenced: macOS reads
    # `CFBundleIconFile` from inside the bundle and nowhere else.
    ico = icon_path(script.parent)
    if ico.is_file():
        (contents / "Resources").mkdir(parents=True, exist_ok=True)
        try:
            import shutil
            shutil.copyfile(ico, contents / "Resources" / f"{APP_NAME}.ico")
        except OSError:
            pass

    # macOS caches the association; re-registering the bundle is what makes a
    # freshly written Info.plist take effect without a logout.
    try:
        subprocess.run(["/System/Library/Frameworks/CoreServices.framework/"
                        "Frameworks/LaunchServices.framework/Support/lsregister",
                        "-f", str(app)], capture_output=True, timeout=20, check=False)
    except (OSError, subprocess.SubprocessError):
        pass


def register(script: str | Path, os_name: str | None = None) -> bool:
    """Make `jarvis://` reach `script`. True when it is registered afterwards."""
    os_name = os_name or platform.system()
    script = str(script)
    try:
        if os_name == "Windows":
            _enable_windows_scheme(script)
        elif os_name == "Darwin":
            _enable_mac_scheme(script)
        else:
            _enable_linux_scheme(script)
    except Exception as e:                          # noqa: BLE001
        from core.logbook import get as _log
        _log(__name__).debug("could not register %s: %s", SCHEME, e)
        return False
    return registered(os_name)


def unregister(os_name: str | None = None) -> bool:
    """Remove the association. `registered()` afterwards is the answer."""
    os_name = os_name or platform.system()
    try:
        if os_name == "Windows":
            _disable_windows_scheme()
        elif os_name == "Darwin":
            from core.app_identity import APP_NAME
            app = Path.home() / "Applications" / f"{APP_NAME}.app"
            if app.exists():
                import shutil
                shutil.rmtree(app, ignore_errors=True)
        else:
            applications_path().unlink(missing_ok=True)
    except Exception as e:                          # noqa: BLE001
        from core.logbook import get as _log
        _log(__name__).debug("could not unregister %s: %s", SCHEME, e)
    return not registered(os_name)


def registered(os_name: str | None = None) -> bool:
    """Whether the scheme is registered — READ BACK, never remembered.

    The same rule as the auto-start toggle, and for the same reason: a settings
    panel that says "registered" because it just called a writer is a panel
    that lies when the write was refused. On Linux "registered" also means the
    handler file is executable, because a `.desktop` that is not is one the
    desktop ignores.
    """
    os_name = os_name or platform.system()
    try:
        if os_name == "Windows":
            import winreg
            key = f"{_WIN_CLASSES}\\{SCHEME}"
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key, 0, winreg.KEY_READ) as k:
                try:
                    winreg.QueryValueEx(k, "URL Protocol")
                except FileNotFoundError:
                    return False
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                f"{key}\\shell\\open\\command", 0,
                                winreg.KEY_READ) as k:
                value, _ = winreg.QueryValueEx(k, "")
            return bool(value) and "%1" in str(value)
        if os_name == "Darwin":
            from core.app_identity import APP_NAME
            plist = (Path.home() / "Applications" / f"{APP_NAME}.app"
                     / "Contents" / "Info.plist")
            if not plist.is_file():
                return False
            return f"<string>{SCHEME}</string>" in plist.read_text(encoding="utf-8",
                                                                  errors="replace")
        path = applications_path()
        if not path.is_file():
            return False
        text = path.read_text(encoding="utf-8", errors="replace")
        return (f"x-scheme-handler/{SCHEME}" in text
                and os.access(path, os.X_OK))
    except Exception:                 # noqa: BLE001 — a probe may never crash a caller
        return False
