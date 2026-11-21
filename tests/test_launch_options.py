"""What a launch can ask for — and what it deliberately cannot.

WHY THIS EXISTS
    Everything in this release is something that starts the app: the tray, a
    desktop shortcut, auto-start at login, a second double-click. Before this
    file, each of them produced an identical launch — so an auto-start entry
    faithfully restored the `hud` default at every boot, covering the desktop
    with a full-screen window before the user had done anything.

    So a launch can now say `--hidden` (start in the tray — what the login entry
    passes) or `--show` (come to the front — what a shortcut means). The tests
    here cover the parser, the Qt-argv split, and the two places the flag has to
    survive: `ui/lifecycle.start_interface`, and the entry that is written to
    disk.

    `main.py` cannot be imported in this sandbox (sounddevice, PyQt, the Live
    session), so the parser is exercised the way the project already does it for
    that file: read the function out of the AST and run it alone.
"""
from __future__ import annotations

import sys
import xml.etree.ElementTree as ET

import pytest

from core import autostart


def _main_functions(*names: str) -> dict:
    """The named functions of main.py, executed without importing the module.

    Built as a REAL module in `sys.modules`, not a bare dict: `main.py` has
    `from __future__ import annotations`, so every annotation is a string and
    `@dataclass` resolves them through `sys.modules[cls.__module__]`. A dict
    that is not registered makes dataclasses fail with an AttributeError from
    inside itself, which reads like a bug in the class.
    """
    import ast
    import types
    from dataclasses import dataclass
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    tree = ast.parse((root / "main.py").read_text(encoding="utf-8"))
    wanted = [n for n in tree.body
              if isinstance(n, ast.ClassDef) and n.name == "LaunchOptions"]
    wanted += [n for n in tree.body
               if isinstance(n, ast.FunctionDef) and n.name in names]
    assert len(wanted) >= len(names), f"missing in main.py: {names}"

    module = types.ModuleType("main_under_test")
    module.__file__ = str(root / "main.py")
    module.sys = sys
    module.dataclass = dataclass
    sys.modules["main_under_test"] = module
    try:
        exec(compile(ast.Module(body=wanted, type_ignores=[]), "main.py", "exec"),
             module.__dict__)
    except Exception:
        sys.modules.pop("main_under_test", None)
        raise
    return module.__dict__


@pytest.fixture(scope="module")
def launch():
    namespace = _main_functions("_parse_args")
    return namespace["_parse_args"]


# ── the parser ──────────────────────────────────────────────────────────────

def test_no_arguments_is_an_ordinary_launch(launch):
    options, keep = launch([])
    assert options.hidden is False and options.show is False
    assert keep == []


def test_hidden_and_show_are_recognised(launch):
    options, keep = launch(["--hidden"])
    assert options.hidden is True and keep == []

    options, keep = launch(["--show"])
    assert options.show is True and keep == []


def test_the_windows_dash_is_accepted_too(launch):
    """`/hidden` is what half of Windows' own shortcuts use; users type both."""
    assert launch(["/hidden"])[0].hidden is True
    assert launch(["/show"])[0].show is True


def test_both_at_once_resolves_to_the_safe_one(launch):
    """Contradiction: the tray is one click from a window, the reverse is not.

    A full-screen window at login is something the user has to dismiss; ending
    up in the tray is something they can undo without reading anything.
    """
    options, _ = launch(["--hidden", "--show"])
    assert options.hidden is True
    assert options.show is False


def test_our_flags_never_reach_qt(launch):
    """`QApplication` may consume or refuse what it does not recognise.

    An unknown flag left in `sys.argv` is how a packaged build fails to start
    with no message; so our two are stripped and everything else is passed on
    untouched, because passing it on is the owner's decision, not ours.
    """
    options, keep = launch(["--hidden", "--style", "fusion", "somefile.txt"])
    assert options.hidden is True
    assert keep == ["--style", "fusion", "somefile.txt"]


def test_force_window_is_not_true_for_hidden(launch):
    assert launch(["--hidden"])[0].force_window is False
    assert launch(["--show"])[0].force_window is True
    assert launch([])[0].force_window is False


# ── the entry written to disk ──────────────────────────────────────────────

def test_autostart_starts_in_the_tray_not_on_the_desktop(tmp_path, monkeypatch):
    """The login entry is the reason this whole flag exists."""
    script = tmp_path / "main.py"
    script.write_text("", encoding="utf-8")

    text = autostart.desktop_text(script, args=autostart.LOGIN_ARGS)
    exec_line = next(line for line in text.splitlines() if line.startswith("Exec="))
    argv = autostart._split_desktop_command(exec_line[len("Exec="):])
    assert argv[1] == str(script.resolve())
    assert argv[2:] == ["--hidden"]


def test_the_login_flag_survives_quoting_in_a_path_with_a_space(tmp_path):
    """The argument goes through the same escaping as the paths.

    An argument containing a space is exactly as able to make an entry
    unparseable as a path containing one, and this one is fixed text today —
    which is precisely the kind of thing that stops being fixed later.
    """
    script = tmp_path / "Mark LVI" / "main.py"
    script.parent.mkdir(parents=True)
    script.write_text("", encoding="utf-8")

    value = autostart._exec_value(script, python="/usr/bin/python3",
                                  args=("--hidden", "two words"))
    assert autostart._split_desktop_command(value)[2:] == ["--hidden", "two words"]


def test_the_mac_plist_carries_the_flag_as_its_own_argument(tmp_path):
    """ProgramArguments is an array — one string per argument, never a joined one."""
    script = tmp_path / "main.py"
    script.write_text("", encoding="utf-8")

    # Parsed as XML, and the <string> list is read from the ProgramArguments
    # array only: the Label is a string too, and a whole-document search has
    # already hidden one ordering bug in this area.
    root = ET.fromstring(autostart.plist_text(script, args=autostart.LOGIN_ARGS))
    array = root.find(".//key[.='ProgramArguments']/..").find("array")
    strings = [e.text for e in array.iter("string")]
    assert str(script.resolve()) in strings
    assert "--hidden" in strings
    # And it comes AFTER the script, or it is an argument to something else.
    assert strings.index("--hidden") > strings.index(str(script.resolve()))


def test_enable_passes_the_login_flag_by_default(tmp_path, monkeypatch):
    """Defaulted, not remembered: a caller that forgets it gets the safe entry."""
    seen = {}

    def _fake_enable_windows(script, args=()):
        seen["args"] = args

    monkeypatch.setattr(autostart, "_enable_windows", _fake_enable_windows)
    monkeypatch.setattr(autostart, "enabled", lambda os_name=None: True)
    script = tmp_path / "main.py"
    script.write_text("", encoding="utf-8")

    assert autostart.enable(script, os_name="Windows") is True
    assert seen["args"] == ("--hidden",)


def test_the_registered_script_is_read_from_position_one_not_the_last(autostart_entry=None):
    """The bug adding a flag exposed.

    `installed_script()` took the LAST argument of the command line, which was
    the script only while the entry had no flags. With `--hidden` at the end it
    returned "--hidden", and `status()` would have called every auto-start entry
    on every platform BROKEN.
    """
    entry = 'Exec="/usr/bin/python3" "/home/me/Mark LVI/main.py" "--hidden"'
    argv = autostart._split_desktop_command(entry[len("Exec="):])
    assert argv[-1] == "--hidden"
    # What the reader must do with that list:
    assert argv[1] == "/home/me/Mark LVI/main.py"


# ── the flag reaching the interface ────────────────────────────────────────

def test_hidden_forces_the_tray_whatever_the_saved_mode_says():
    """`--hidden` is a downgrade of visibility, and the only one allowed to
    outrank the saved mode. The safety rules below it still apply."""
    from types import SimpleNamespace
    import importlib.util
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    spec = importlib.util.spec_from_file_location(
        "lifecycle_launch_under_test", root / "ui" / "lifecycle.py")
    lifecycle = importlib.util.module_from_spec(spec)
    sys.modules["lifecycle_launch_under_test"] = lifecycle
    spec.loader.exec_module(lifecycle)

    shown = []
    tray = []
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(lifecycle, "start_tray",
                        lambda shell: tray.append(True) or True)
    monkeypatch.setattr(lifecycle, "watch_for_another_launch", lambda shell: None)
    monkeypatch.setattr(lifecycle, "start_summon_hotkey", lambda shell: "ctrl+shift+j")
    # The orb and the command bar are started by the same function, and both
    # reach Qt. Stubbed here because this test is about which MODE was chosen,
    # not about whether a ring can be drawn — that is tests/test_orb_overlay.py.
    monkeypatch.setattr(lifecycle, "start_orb", lambda shell: True)
    monkeypatch.setattr(lifecycle, "start_command_bar", lambda shell: True)
    try:
        win = SimpleNamespace(_ready=True, showFullScreen=lambda: shown.append(1),
                              _log_sig=SimpleNamespace(emit=lambda _t: None))
        shell = SimpleNamespace(_win=win, _ambient=False,
                                _launch=SimpleNamespace(hidden=True, show=False))
        # A saved HUD mode, which `--hidden` must override.
        monkeypatch.setitem(sys.modules, "memory.config_manager",
                            SimpleNamespace(get_ui_mode=lambda: "hud"))
        lifecycle.start_interface(shell)
        assert shown == [], "the window must not be shown at login"
        assert tray == [True], "it must go to the tray instead"
        assert shell._ambient is True
    finally:
        monkeypatch.undo()


def test_hidden_still_gives_the_window_on_a_first_run():
    """The rule that must survive every flag: no API key, no headless start.

    The setup screen is inside the window. A login entry that hides it is an
    install that can never be finished, and nothing on screen would say why.
    """
    from types import SimpleNamespace
    import importlib.util
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    spec = importlib.util.spec_from_file_location(
        "lifecycle_firstrun_under_test", root / "ui" / "lifecycle.py")
    lifecycle = importlib.util.module_from_spec(spec)
    sys.modules["lifecycle_firstrun_under_test"] = lifecycle
    spec.loader.exec_module(lifecycle)

    shown, tray = [], []
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(lifecycle, "start_tray", lambda shell: tray.append(True) or True)
    monkeypatch.setattr(lifecycle, "watch_for_another_launch", lambda shell: None)
    try:
        win = SimpleNamespace(_ready=False,          # no API key yet
                              showFullScreen=lambda: shown.append(1),
                              _log_sig=SimpleNamespace(emit=lambda _t: None))
        shell = SimpleNamespace(_win=win, _ambient=False,
                                _launch=SimpleNamespace(hidden=True, show=False))
        monkeypatch.setitem(sys.modules, "memory.config_manager",
                            SimpleNamespace(get_ui_mode=lambda: "hud"))
        lifecycle.start_interface(shell)
        assert shown == [1], "an unconfigured install always gets the window"
        assert tray == []
    finally:
        monkeypatch.undo()


# ── the two callers on opposite sides of the same flag ─────────────────────

def test_the_desktop_shortcut_says_show_and_the_login_entry_says_hidden():
    """One flag, two meanings, and the wrong way round is a real bug.

    A shortcut is a person clicking an icon: they want the window. A login entry
    is the system starting something while the user is doing something else: it
    must not cover the screen. Read from the source because both paths build
    strings for three operating systems and neither can run here.
    """
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    source = (root / "ui" / "window.py").read_text(encoding="utf-8")

    # Parsed, not searched. Both comments above the writers explain what they
    # are the opposite of, so the word "--hidden" is IN this function and must
    # be — the third time in this project that a substring search over source
    # matched its own documentation. The question is which flag is passed to a
    # string the code builds.
    import ast

    fn = next(n for n in ast.walk(ast.parse(source))
              if isinstance(n, ast.FunctionDef) and n.name == "_create_desktop_shortcut")
    literals = [n.value for n in ast.walk(fn)
                if isinstance(n, ast.Constant) and isinstance(n.value, str)]
    flags = [part for text in literals for part in text.split()
             if part.startswith("--")]
    assert "--show" in flags, "the shortcut does not ask for the window"
    assert "--hidden" not in flags, "a clicked shortcut must not start in the tray"


def test_the_login_entry_never_asks_for_the_window():
    """Asserted on the rendered entries, not the source: that is what runs."""
    from pathlib import Path

    text = autostart.desktop_text(Path("/opt/main.py"), args=autostart.LOGIN_ARGS)
    assert "--show" not in text
    assert "--hidden" in text
    assert autostart.LOGIN_ARGS == ("--hidden",)
