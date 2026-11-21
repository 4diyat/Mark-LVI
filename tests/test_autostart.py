"""Auto-start: what gets written, and to what path.

WHY THIS FILE EXISTS
    The window has had a "start with the system" toggle for as long as it has
    had a settings drawer, and on all three platforms it registered a command
    pointing at `ui/main.py` — a file that has never existed in this
    repository. Nothing failed at the time. It failed at the NEXT login, on
    somebody else's machine, by doing nothing at all, which is the failure mode
    this project keeps having to design against.

    So the tests here are in two groups, and the split is deliberate:

      * the FORMAT of each of the three entries — pure text, no OS, no
        registry. These are the ones that catch the quoting bug that makes a
        `.desktop` file unparseable and a Windows Run value that dies on the
        first space in a username.
      * the READ-BACK that makes the toggle honest. `enabled()` and
        `status()` are what the menu tick and the button label are drawn from,
        and the rule they enforce is "report what is on disk, never what we
        just intended to write".

    None of it needs a Windows machine, a Mac, or a login. That is the point:
    the three commands were wrong on every platform for years precisely because
    nobody could test any of them without rebooting.
"""
from __future__ import annotations

import sys
import xml.etree.ElementTree as ET

import pytest

from core import autostart

SCRIPT = "/home/me/Mark LVI/main.py"


def _load(relative: str, name: str):
    """Load a `ui/` module by PATH, past `ui/__init__.py`, which needs Qt.

    `ui/` is a package whose `__init__` imports the whole window, and the
    window imports QtMultimedia. Every test in this file has to run on a
    machine with no display — including the CI runners — so the two modules
    that do not need Qt are loaded from their files instead of by name.
    """
    import importlib.util
    from pathlib import Path as _Path
    path = _Path(__file__).resolve().parent.parent / relative
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _import_lifecycle():
    return _load("ui/lifecycle.py", "lifecycle_under_test")


def _desktop_script(path) -> str:
    """Read a .desktop entry's Exec= the way the real reader does, or "".

    Used by the wiring tests, which are about the toggle's DECISIONS (three
    states: off / on / registered-but-broken) rather than about the Linux
    parser, which has its own tests above.
    """
    if not path.exists():
        return ""
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("Exec="):
            parts = autostart._split_desktop_command(line[len("Exec="):])
            return parts[1] if len(parts) >= 2 else ""
    return ""


@pytest.fixture()
def home(tmp_path, monkeypatch):
    """A throwaway HOME, so these tests never touch the real autostart folder."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(autostart.Path, "home", classmethod(lambda cls: tmp_path))
    return tmp_path


@pytest.fixture()
def script(tmp_path):
    path = tmp_path / "Mark LVI" / "main.py"
    path.parent.mkdir(parents=True)
    path.write_text("# the entry point\n", encoding="utf-8")
    return path


# ── the bug this module replaces ────────────────────────────────────────────

def test_the_registered_script_is_the_one_we_were_given(tmp_path, script, home):
    """The path comes from the caller, because this module cannot know it.

    The old code derived it from `__file__` — which was `ui/window.py`, so the
    entry pointed at `ui/main.py`. Passing it in is the fix, and the assertion
    is that the file the entry names is the file that was passed.
    """
    assert autostart.enable(script, os_name="Linux") is True
    written = autostart.installed_script("Linux")
    assert written == str(script.resolve())
    assert "ui/main.py" not in (home / ".config" / "autostart" / "jarvis.desktop").read_text()


def test_a_script_that_is_not_there_is_refused_loudly(tmp_path):
    """Better a visible error now than a silent no-op at the next login."""
    with pytest.raises(FileNotFoundError):
        autostart.enable(tmp_path / "nope" / "main.py", os_name="Linux")


def test_a_registered_entry_whose_target_vanished_is_reported_broken(tmp_path, script, home):
    """"Auto-start is on" is only worth saying when it would actually start."""
    autostart.enable(script, os_name="Linux")
    assert autostart.status("Linux")["broken"] is False

    script.unlink()
    status = autostart.status("Linux")
    assert status["enabled"] is True, "the entry is still registered"
    assert status["broken"] is True, "and it points at nothing, which is the bug"


# ── the Linux entry ─────────────────────────────────────────────────────────

def test_the_desktop_entry_survives_a_space_in_the_project_path(tmp_path, script, home):
    """`Exec=/usr/bin/python3 /home/me/Mark LVI/main.py` is not two arguments.

    It is either an unparseable entry or a launcher that starts the interpreter
    with `LVI/main.py` as argv[1]. Both paths are quoted, so both survive.
    """
    autostart.enable(script, os_name="Linux")
    text = (home / ".config" / "autostart" / "jarvis.desktop").read_text()
    exec_line = next(line for line in text.splitlines() if line.startswith("Exec="))
    argv = autostart._split_desktop_command(exec_line[len("Exec="):])
    # The script is argv[1]: argv[0] is the interpreter and the LOGIN_ARGS flag
    # comes after it.
    assert "--hidden" in argv, "the login entry must not open a window at boot"
    assert argv[1] == str(script.resolve())
    assert argv[0] == sys.executable or argv[0].endswith("pythonw.exe")


def test_the_desktop_entry_escapes_the_characters_the_spec_names(tmp_path, home):
    r"""`"`, `` ` ``, `$` and `\` inside a quoted value, doubled for the key file.

    A project under `~/Work & Play/$draft` is not exotic, and a `$` that is
    not escaped is a launcher that expands a variable that does not exist.
    """
    value = autostart._exec_value("$HOME/My Project/main.py", python="/usr/bin/python3")
    assert value == '"/usr/bin/python3" "\\$HOME/My Project/main.py"'
    # One escaping layer only (see _exec_value): a parser undoes the backslash
    # and does not expand the variable, which is what GLib does.
    argv = autostart._split_desktop_command(value)
    assert argv == ["/usr/bin/python3", "$HOME/My Project/main.py"]


def test_the_desktop_entry_names_the_app_and_never_opens_a_terminal(tmp_path, script, home):
    autostart.enable(script, os_name="Linux", name="J.A.R.V.I.S")
    text = (home / ".config" / "autostart" / "jarvis.desktop").read_text()
    assert "Name=J.A.R.V.I.S" in text
    assert "Terminal=false" in text
    assert "Type=Application" in text
    assert "X-GNOME-Autostart-enabled=true" in text


def test_the_desktop_entry_gets_an_icon_only_when_the_file_exists(tmp_path, script, home):
    """"Icon=/nonexistent" is a broken launcher icon, not a missing one."""
    autostart.enable(script, os_name="Linux")
    text = (home / ".config" / "autostart" / "jarvis.desktop").read_text()
    assert "Icon=" not in text

    icon = tmp_path / "jarvis.ico"
    icon.write_bytes(b"\x00\x00\x01\x00")
    autostart.enable(script, os_name="Linux", icon=icon)
    text = (home / ".config" / "autostart" / "jarvis.desktop").read_text()
    assert f"Icon={icon}" in text


# ── the macOS entry ─────────────────────────────────────────────────────────

@pytest.fixture()
def mac(tmp_path, monkeypatch):
    """A macOS-shaped target for ONE test: the plist, in this test's folder.

    `target_path` is the single function the writer and the reader both name,
    so pointing it here tests the real read-back instead of a file nobody
    reads. The first version of these tests asserted the plist's TEXT and never
    asked `installed_script` anything — which is how a reader that returned
    "Interactive" (a later `<string>` in the same file) passed on Linux and
    failed on macOS CI.
    """
    path = tmp_path / "com.jarvis.assistant.plist"
    monkeypatch.setattr(autostart, "target_path", lambda os_name=None: path)
    return path


def test_the_launch_agent_is_a_plist_that_parses(tmp_path, script, home, mac):
    """Parsed with a real XML parser: the old one was assembled by f-string and
    never checked by anything that would have noticed a stray `&`."""
    autostart.enable(script, os_name="Darwin")
    root = ET.parse(mac).getroot()
    assert root.tag == "plist"

    strings = [e.text for e in root.iter("string")]
    assert "com.jarvis.assistant" in strings
    assert str(script.resolve()) in strings
    assert root.find(".//key[.='RunAtLoad']") is not None


def test_the_launch_agent_reads_back_as_the_script_it_will_start(tmp_path, script, home, mac):
    """The bug macOS CI found: the reader took the LAST <string> in the file.

    `ProcessType` is a string too, and it comes after `ProgramArguments`, so
    "which file would this start" answered "Interactive" — status said
    registered-but-not-broken, and the toggle reported success for an entry
    that could never be verified.
    """
    autostart.enable(script, os_name="Darwin")
    assert autostart.installed_script("Darwin") == str(script.resolve())
    status = autostart.status("Darwin")
    assert status["broken"] is False
    assert status["script"] == str(script.resolve())


def test_the_launch_agent_has_no_keepalive(tmp_path, script, home, mac):
    """A crashing assistant relaunched forever is worse than one that stays down.

    The user starts it themselves; nothing in the tray suggests it is immortal.
    """
    autostart.enable(script, os_name="Darwin")
    assert "KeepAlive" not in mac.read_text()


def test_a_project_path_with_an_ampersand_still_produces_valid_xml(tmp_path, home, mac):
    script = tmp_path / "Work & Play" / "main.py"
    script.parent.mkdir(parents=True)
    script.write_text("", encoding="utf-8")
    autostart.enable(script, os_name="Darwin")
    root = ET.parse(mac).getroot()             # raises if the escaping is wrong
    assert str(script.resolve()) in [e.text for e in root.iter("string")]


# ── the Windows entry ───────────────────────────────────────────────────────

def test_the_windows_value_quotes_both_paths(tmp_path, script):
    r"""`C:\Users\Fatih Makes\...` is the normal case, not the edge case.

    An unquoted Run value is parsed at the first space: the interpreter gets an
    argument it cannot open, Windows shows nothing, and the app does not start.
    """
    written = {}
    autostart._enable_windows.__globals__["_run_key_windows"]  # exists
    value = f'"{sys.executable}" "{script.resolve()}"'
    argv = autostart._split_windows_command(value)
    assert argv == [sys.executable, str(script.resolve())]

    # And the value the writer produces has the same shape.
    import inspect
    source = inspect.getsource(autostart._enable_windows)
    assert 'command = f\'"{_python_command()}" "{script}"\'' in source
    del written


def test_an_unquoted_legacy_windows_value_is_still_read_back(tmp_path):
    """Somebody may already have a value from the old code. Report it, do not crash."""
    argv = autostart._split_windows_command(r"C:\Python\pythonw.exe C:\tools\main.py")
    assert argv == [r"C:\Python\pythonw.exe", r"C:\tools\main.py"]


# ── the toggle itself ───────────────────────────────────────────────────────

def test_enable_then_disable_leaves_nothing_behind(tmp_path, script, home):
    assert autostart.enable(script, os_name="Linux") is True
    assert autostart.enabled("Linux") is True

    # `disable` returns "it is off now" — symmetric with `enable`.
    assert autostart.disable("Linux") is True
    assert autostart.enabled("Linux") is False
    assert not (home / ".config" / "autostart" / "jarvis.desktop").exists()


def test_disabling_twice_is_not_an_error(tmp_path, home):
    """The button is a toggle; a double click must not raise into the log."""
    assert autostart.disable("Linux") is True
    assert autostart.disable("Linux") is True, "an absent entry is already off"


def test_linux_and_mac_report_their_own_files(tmp_path, home):
    """`target_path` is what the tests and the UI both name, so it is asserted.

    A single wrong constant here (a missing `LaunchAgents`, a typo in
    `.config`) is invisible-until-login on a platform nobody here runs.
    """
    assert autostart.target_path("Linux") == home / ".config" / "autostart" / "jarvis.desktop"
    assert autostart.target_path("Darwin") == (
        home / "Library" / "LaunchAgents" / "com.jarvis.assistant.plist")


def test_status_survives_a_path_it_cannot_stat(tmp_path, home, monkeypatch):
    """It is called while a menu is being built. A probe may not cost the menu.

    An entry pointing into a mount that is not there, or a path this user
    cannot stat, must read as "registered, unknown" — not as broken (a claim)
    and not as an exception into the tray.
    """
    hostile = str(tmp_path / "denied" / "main.py")
    entry = home / ".config" / "autostart" / "jarvis.desktop"
    entry.parent.mkdir(parents=True)
    entry.write_text("[Desktop Entry]\n", encoding="utf-8")
    monkeypatch.setattr(autostart, "installed_script", lambda os_name=None: hostile)
    real_is_file = autostart.Path.is_file

    def _is_file(self):
        if str(self) == hostile:
            raise PermissionError("denied")
        return real_is_file(self)

    # `exists`, not `is_file`: the latter is a METHOD whose default is used by
    # the rest of this module, so patching it outlives the test in `tmp_path`
    # fixtures that ran before it. Nothing here may leave the module different.
    monkeypatch.setattr(autostart.Path, "is_file", _is_file)
    status = autostart.status("Linux")
    assert status["script"] == hostile
    assert status["enabled"] is True
    assert status["broken"] is False, "we cannot claim broken for a path we cannot read"


# ── the wiring: the path, the tray item, the button ─────────────────────────

def test_the_program_path_is_never_guessed(tmp_path, monkeypatch):
    """`lifecycle.program_path` refuses rather than inventing one.

    This is the assertion that would have caught the original bug at the seam:
    the old code ALWAYS produced a path (a wrong one). A function that raises
    when it has not been told cannot produce `ui/main.py`.
    """
    from types import SimpleNamespace
    lifecycle = _import_lifecycle()

    with pytest.raises(RuntimeError):
        lifecycle.program_path(SimpleNamespace(_program_path=""))

    told = tmp_path / "main.py"
    told.write_text("", encoding="utf-8")
    assert lifecycle.program_path(SimpleNamespace(_program_path=str(told))) == str(told)


def test_main_records_the_file_it_was_run_as():
    """Read as source: it is the one line that fixes all three platforms.

    `main.py` is the entry point and the only module that knows its own path.
    A test cannot import and run it (it builds the whole app), so the assertion
    is on the source — and it is checking the two things that matter: the
    attribute the lifecycle reads, and `__file__` rather than a constant.
    """
    import ast
    source = (autostart.Path(__file__).resolve().parent.parent / "main.py").read_text(
        encoding="utf-8")
    tree = ast.parse(source)
    found = []
    for node in ast.walk(tree):
        if (isinstance(node, ast.Assign)
                and isinstance(node.targets[0], ast.Attribute)
                and node.targets[0].attr == "_program_path"):
            found.append(ast.unparse(node.value))
    assert found, "main.py no longer records the program path for auto-start"
    assert any("__file__" in expr for expr in found), (
        "the recorded path must come from __file__, not a literal: " + repr(found))


def test_the_tray_menu_offers_auto_start_as_a_checkbox():
    """A switch the user cannot see the state of is a switch they will not use."""
    tray = _load("ui/tray.py", "tray_under_test")

    keys = [key for key, _label in tray.MENU_ITEMS]
    assert "autostart" in keys
    assert "autostart" in tray.CHECKABLE_ITEMS
    assert keys.index("autostart") < keys.index("quit"), (
        "the one item that must never be hit by accident stays last")


def test_toggling_reports_the_state_it_left_behind(tmp_path, monkeypatch):
    """`toggle_autostart` returns the READ-BACK, so a tick cannot lie.

    Three cases, and the third is the one this whole change is about: a
    registered entry pointing at a file that is gone must read as OFF, because
    "on" is a promise that something will start.
    """
    from types import SimpleNamespace
    lifecycle = _import_lifecycle()

    script = tmp_path / "main.py"
    script.write_text("", encoding="utf-8")
    notes = []
    shell = SimpleNamespace(_program_path=str(script),
                            _win=SimpleNamespace(write_log=notes.append))

    # The real `status()`/`enabled()`/`installed_script()` path, but pointed at
    # this test's folder instead of the machine's own autostart directory — and
    # at Linux, because the entry written below is a .desktop file. On macOS CI
    # the un-pinned version read a plist that was not there and failed; the
    # production code picks the platform the same way, so this is not a bypass.
    monkeypatch.setattr(autostart.platform, "system", lambda: "Linux")
    monkeypatch.setattr(autostart, "target_path",
                        lambda os_name=None: tmp_path / "jarvis.desktop")
    monkeypatch.setattr(autostart, "enabled",
                        lambda os_name=None: (tmp_path / "jarvis.desktop").exists())
    monkeypatch.setattr(autostart, "installed_script",
                        lambda os_name=None: _desktop_script(tmp_path / "jarvis.desktop"))
    (tmp_path / "jarvis.desktop").write_text(
        autostart.desktop_text(script), encoding="utf-8")

    assert lifecycle.toggle_autostart(shell) is False, "on -> toggle turns it off"
    assert any("disabled" in n for n in notes)
    assert not (tmp_path / "jarvis.desktop").exists()

    notes.clear()
    assert lifecycle.toggle_autostart(shell) is True, "off -> toggle turns it on"
    assert any("enabled" in n for n in notes)

    script.unlink()
    notes.clear()
    assert lifecycle.toggle_autostart(shell) is False, (
        "a registered entry whose target is gone is not 'on'")
    assert any("no longer there" in n for n in notes), notes
    assert not (tmp_path / "jarvis.desktop").exists(), (
        "a stale entry is removed, not left to promise a launch that cannot happen")

    # With the file back, the next toggle is an ordinary "turn it on".
    script.write_text("", encoding="utf-8")
    notes.clear()
    assert lifecycle.toggle_autostart(shell) is True
    assert autostart.installed_script() == str(script)


def test_a_failing_toggle_writes_a_log_line_instead_of_raising(tmp_path, monkeypatch):
    """It runs from a menu. An exception there is a menu item that did nothing."""
    from types import SimpleNamespace
    lifecycle = _import_lifecycle()

    # Isolated from whatever this machine has registered, so the test exercises
    # "turning it ON fails" rather than "turning it off succeeds".
    monkeypatch.setattr(autostart.platform, "system", lambda: "Linux")
    monkeypatch.setattr(autostart, "target_path",
                        lambda os_name=None: tmp_path / "jarvis.desktop")
    notes = []
    shell = SimpleNamespace(_program_path="", _win=SimpleNamespace(write_log=notes.append))
    result = lifecycle.toggle_autostart(shell)
    assert result is False
    assert any("Auto-start failed" in n for n in notes), notes
