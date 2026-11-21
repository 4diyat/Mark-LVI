"""Auto-start — the assistant starts with the machine, on all three systems.

WHY THIS EXISTS (AND WHY IT IS NOT IN ui/window.py ANY MORE)
    The window already had a "start with the system" toggle, three OS branches
    of it, and it could not have worked on any of the three. The reason is one
    line in every branch:

        script = str(Path(__file__).resolve().parent / "main.py")

    `__file__` here was `ui/window.py` before the split, and `ui/window.py`
    after it — so the path was `ui/main.py`, which has never existed. Windows
    registered a launch command pointing at a missing file, macOS wrote a
    LaunchAgent with a missing `ProgramArguments` entry, and Linux wrote a
    `.desktop` whose `Exec=` line could not start. All three failed the same
    way a good many things do: silently, at the NEXT login, on somebody else's
    machine.

    So the path is not computed here at all. The caller passes `script` — the
    file it actually ran — and this module has no opinion about where the
    project lives.

WHAT IS ACTUALLY WRITTEN, PER PLATFORM
    WINDOWS  HKCU\\...\\CurrentVersion\\Run, value `JARVIS_AI`. Per-user, no
    elevation, and visible in Task Manager → Startup. The value must be
    QUOTED: `C:\\Program Files\\…\\pythonw.exe` and `C:\\Users\\Fatih Makes\\…`
    both contain spaces often enough that an unquoted command line is a coin
    flip.

    macOS    ~/Library/LaunchAgents/com.jarvis.assistant.plist, launching the
    interpreter directly with `RunAtLoad`. No `KeepAlive`: a crash loop of an
    assistant that is supposed to sit in the tray is worse than not starting.

    LINUX    ~/.config/autostart/jarvis.desktop. The `Exec=` value is written
    in the Desktop Entry escaping rules (see `_exec_value`), which is the part
    everyone gets wrong — it is not shell quoting, and a plain space in a path
    makes the entry unparseable rather than merely wrong.

    A .desktop file also usually wants an absolute icon path and a
    `TryExec`, so a launcher that has gone missing shows up as broken instead
    of doing nothing. Both are written when an icon file exists.

WHAT THIS DELIBERATELY DOES NOT DO
    It never raises for a platform it cannot handle, and `enabled()` tells the
    truth by READING BACK what is on disk instead of trusting a flag. A toggle
    that reports "on" while nothing was written is the bug this module replaces.
"""
from __future__ import annotations

import platform
import sys
import xml.sax.saxutils
from pathlib import Path

APP_KEY = "JARVIS_AI"                     # the Windows Run value name
MAC_LABEL = "com.jarvis.assistant"        # LaunchAgent label, and its filename
DESKTOP_NAME = "jarvis.desktop"           # under ~/.config/autostart


def _run_key_windows():
    r"""The `Run` key, opened lazily so importing this module needs no winreg.

    Lazy on purpose and NOT optional: `winreg` exists only on Windows, and this
    module is imported by `ui/tray.py`, which every platform loads. A top-level
    `import winreg` would make the whole interface fail to start on the two
    systems the tray matters most on. (It is also why the stub Win32 runs in
    the tests can exercise the writer without one.)

    HKCU, not HKLM: writing to HKLM needs elevation, and an assistant that
    asks for administrator rights to start with the user is an assistant most
    people uninstall. The same key is what Task Manager's Startup tab reads.
    """
    import winreg
    return winreg, (r"Software\Microsoft\Windows\CurrentVersion\Run")


def _python_command() -> str:
    """The interpreter to launch with — `pythonw.exe` on Windows where it exists.

    `python.exe` opens a console window on every login. `pythonw.exe` is the
    one that does not, and it ships beside the interpreter in every standard
    CPython install on Windows.
    """
    exe = Path(sys.executable)
    if platform.system() == "Windows":
        windowed = exe.parent / "pythonw.exe"
        if windowed.exists():
            return str(windowed)
    return str(exe)


def _plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{MAC_LABEL}.plist"


def _desktop_path() -> Path:
    return Path.home() / ".config" / "autostart" / DESKTOP_NAME


def target_path(os_name: str | None = None) -> Path:
    """Where the entry lives on this OS. Named so a test can assert it."""
    os_name = os_name or platform.system()
    if os_name == "Windows":
        return Path("HKCU") / "Run" / APP_KEY
    if os_name == "Darwin":
        return _plist_path()
    return _desktop_path()


# ── the write side ──────────────────────────────────────────────────────────

def _enable_windows(script: Path) -> None:
    winreg, key_path = _run_key_windows()
    command = f'"{_python_command()}" "{script}"'
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0,
                        winreg.KEY_ALL_ACCESS) as key:
        winreg.SetValueEx(key, APP_KEY, 0, winreg.REG_SZ, command)


def _disable_windows() -> None:
    winreg, key_path = _run_key_windows()
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0,
                            winreg.KEY_ALL_ACCESS) as key:
            winreg.DeleteValue(key, APP_KEY)
    except FileNotFoundError:
        pass          # already gone: disabling twice is not an error


def plist_text(script: Path, python: str | None = None) -> str:
    """The LaunchAgent. `ProgramArguments`, not `Program` — argv[0] is `-`.

    `script` is XML-escaped: a path with `&` in it (a folder called "Work &
    Play" is not exotic) otherwise produces a plist that `launchctl` rejects
    while the file still looks fine to a reader.
    """
    esc = xml.sax.saxutils.escape
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" '
        '"http://www.apple.com/DTDs/PropertyList-1.0.dtd">\n'
        '<plist version="1.0">\n'
        '<dict>\n'
        f'  <key>Label</key><string>{esc(MAC_LABEL)}</string>\n'
        '  <key>ProgramArguments</key>\n'
        '  <array>\n'
        f'    <string>{esc(python or sys.executable)}</string>\n'
        f'    <string>{esc(str(script))}</string>\n'
        '  </array>\n'
        '  <key>RunAtLoad</key><true/>\n'
        '  <key>ProcessType</key><string>Interactive</string>\n'
        '</dict>\n'
        '</plist>\n'
    )


def _exec_value(script: Path, python: str | None = None) -> str:
    r"""The Desktop Entry `Exec=` value — NOT shell quoting, and not JSON.

    The spec says each argument may be wrapped in double quotes, and that
    inside those quotes `"`, `` ` ``, `$` and ``\`` are escaped with a
    backslash. That is exactly ONE layer of escaping, and it is the layer
    implementations actually undo: GLib — which is what GNOME, KDE and every
    other launcher here uses — reads `Exec` with `g_shell_parse_argv`, which
    removes the backslash and does NOT expand variables.

    WHAT THIS DELIBERATELY DOES NOT DO
        The spec also describes a second escape pass for string values (the
        key-file layer, where `\$` would double again). Launchers do not
        expect it — g_shell_parse_argv would return a literal backslash — so
        applying it here would break every path with a `$` in it on the
        machines that exist. The residual risk is a launcher that DOES expand
        `$VAR` itself; the quoting below protects the common case and this
        paragraph is here so nobody "fixes" it back.

    The consequence people miss, and the reason this is a function at all:
    `Exec=/usr/bin/python3 /home/me/My Project/main.py` is not two arguments.
    It is an unparseable entry, or the interpreter started with `LVI/main.py`
    as argv[1].
    """
    python = python or _python_command()

    def quote(value: str) -> str:
        out = []
        for ch in value:
            if ch in '"`$\\':
                out.append("\\" + ch)
            else:
                out.append(ch)
        return '"' + "".join(out) + '"'

    return f"{quote(python)} {quote(str(script))}"


def desktop_text(script: Path, name: str = "J.A.R.V.I.S",
                 icon: Path | None = None, python: str | None = None) -> str:
    lines = [
        "[Desktop Entry]",
        "Type=Application",
        f"Name={name}",
        f"Exec={_exec_value(script, python)}",
        "Terminal=false",
        "X-GNOME-Autostart-enabled=true",
        # A launcher whose target vanished should show up as broken rather than
        # silently doing nothing at login.
        f"TryExec={python or _python_command()}",
    ]
    if icon and Path(icon).exists():
        lines.append(f"Icon={icon}")
    return "\n".join(lines) + "\n"


def enable(script: str | Path, os_name: str | None = None,
           icon: str | Path | None = None, name: str = "J.A.R.V.I.S") -> bool:
    """Register auto-start for `script`. True when it is now on.

    `script` is REQUIRED and is the file that was actually run. Passing it in
    is the entire fix: this module cannot know where the project lives, and
    guessing is what produced `ui/main.py`.
    """
    os_name = os_name or platform.system()
    script = Path(script).resolve()
    if not script.is_file():
        raise FileNotFoundError(f"cannot auto-start a script that is not there: {script}")

    if os_name == "Windows":
        _enable_windows(script)
    elif os_name == "Darwin":
        # Through `target_path`, the same function `enabled()` reads with. The
        # writer and the reader naming the file differently is how "it saved
        # but the toggle still says off" happens.
        path = target_path(os_name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(plist_text(script), encoding="utf-8")
    else:
        path = target_path(os_name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(desktop_text(script, name=name,
                                     icon=Path(icon) if icon else None),
                        encoding="utf-8")
    return enabled(os_name)


def disable(os_name: str | None = None) -> bool:
    """Remove the entry. True when auto-start is now OFF — a success, not an
    "already off".

    Symmetric with `enable()`, which returns True when it is now on. Both
    report the state they left behind, read back from disk, because that is
    what the menu tick and the settings button both display.
    """
    os_name = os_name or platform.system()
    if os_name == "Windows":
        _disable_windows()
    else:
        target_path(os_name).unlink(missing_ok=True)
    return not enabled(os_name)


def enabled(os_name: str | None = None) -> bool:
    """Whether it is registered — READ BACK, never remembered.

    The old toggle assumed that because it had just called `SetValueEx` the
    value was therefore readable at the next login. It was readable; it just
    pointed at `ui/main.py`. `installed_script()` is what answers the question
    that actually matters, and `status()` reports both.
    """
    os_name = os_name or platform.system()
    try:
        if os_name == "Windows":
            winreg, key_path = _run_key_windows()
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0,
                                    winreg.KEY_READ) as key:
                    winreg.QueryValueEx(key, APP_KEY)
                    return True
            except FileNotFoundError:
                return False
        return target_path(os_name).is_file()
    except Exception:                 # noqa: BLE001 — a probe may never crash the toggle
        return False


def installed_script(os_name: str | None = None) -> str:
    """The script the CURRENT entry would start. "" when there is none.

    Reported to the user rather than guessed at: after the `ui/main.py` bug,
    "auto-start is on" is only worth saying when this returns a path that
    exists, which is exactly what `status()` checks.
    """
    os_name = os_name or platform.system()
    try:
        if os_name == "Windows":
            winreg, key_path = _run_key_windows()
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path, 0,
                                winreg.KEY_READ) as key:
                raw, _ = winreg.QueryValueEx(key, APP_KEY)
            parts = _split_windows_command(str(raw))
            return parts[-1] if parts else ""
        text = target_path(os_name).read_text(encoding="utf-8", errors="replace")
    except Exception:                 # noqa: BLE001
        return ""

    if os_name == "Darwin":
        # The LAST <string> inside ProgramArguments — not the last <string> in
        # the file. There are other keys after it (`ProcessType` is a string
        # too), so a whole-file search returns "Interactive" and reads as
        # "registered, points at nothing" on every Mac. That is exactly what CI
        # on macOS reported before this line was written.
        import re
        block = re.search(r"<key>ProgramArguments</key>\s*<array>(.*?)</array>",
                          text, re.S)
        if block is None:
            return ""
        args = [a.strip() for a in
                re.findall(r"<string>(.*?)</string>", block.group(1), re.S)]
        return args[-1] if len(args) >= 2 else ""
    for line in text.splitlines():
        if line.startswith("Exec="):
            parts = _split_desktop_command(line[len("Exec="):])
            return parts[-1] if parts else ""
    return ""


def status(os_name: str | None = None) -> dict:
    """`{"enabled": bool, "script": str, "broken": bool}` — one dict for the UI.

    `broken` is the case worth telling somebody about: an entry is registered,
    but the file it would start is not there. That is precisely what this
    machine's users had, on all three platforms, and nothing said so.
    """
    script = installed_script(os_name)
    try:
        present = bool(script) and Path(script).is_file()
    except OSError:
        # A path we cannot even stat (permissions, a broken mount). "Not
        # broken" is the honest answer: we do not know that it is.
        present = True
    return {
        "enabled": enabled(os_name),
        "script": script,
        "broken": bool(script) and not present,
    }


# ── parsing back out of the three formats ───────────────────────────────────
# Written by hand rather than with shlex: shlex is POSIX shell rules, and
# neither of these formats uses them. `shlex.split` on a Desktop Entry Exec=
# value SILENTLY drops trailing backslashes, which is a parser that agrees with
# the bug.

def _split_desktop_command(value: str) -> list[str]:
    r"""Split an `Exec=` value into argv per the Desktop Entry spec.

    Double-quoted strings only, with `"` `` ` `` `$` `\` escaped as `\x`; a
    doubled backslash `\\` means one literal backslash. Unquoted words are
    split on spaces.
    """
    args: list[str] = []
    current: list[str] = []
    in_quotes = False
    had_token = False
    i = 0
    while i < len(value):
        ch = value[i]
        if ch == "\\" and i + 1 < len(value):
            nxt = value[i + 1]
            if nxt == "\\" and not in_quotes:
                current.append("\\")
                had_token = True
                i += 2
                continue
            if in_quotes and nxt in '"`$\\':
                current.append(nxt)
                had_token = True
                i += 2
                continue
        if ch == '"':
            in_quotes = not in_quotes
            had_token = True
            i += 1
            continue
        if ch == " " and not in_quotes:
            if had_token:
                args.append("".join(current))
                current, had_token = [], False
            i += 1
            continue
        current.append(ch)
        had_token = True
        i += 1
    if had_token:
        args.append("".join(current))
    return args


def _split_windows_command(command: str) -> list[str]:
    """Split a quoted Windows command line into argv.

    `CreateProcess` does its own thing with quotes and `shlex` is not it; this
    handles the two shapes we write — `"exe" "script"` — and the unquoted
    legacy value somebody may still have registered.
    """
    args: list[str] = []
    current: list[str] = []
    in_quotes = False
    for ch in command:
        if ch == '"':
            in_quotes = not in_quotes
            continue
        if ch == " " and not in_quotes:
            if current:
                args.append("".join(current))
                current = []
            continue
        current.append(ch)
    if current:
        args.append("".join(current))
    return args
