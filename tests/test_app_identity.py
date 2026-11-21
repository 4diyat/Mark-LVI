"""What the OS calls this program, and the three places that must agree.

The failure this suite exists for is invisible from inside the app: every
window works, every icon is drawn, and the taskbar still says `python3`. It
was true on all three platforms until `core/app_identity.py` existed, so the
tests are about AGREEMENT — the same identifier reaching Windows, Qt, and the
`.desktop` files — rather than about any one setter.
"""
from __future__ import annotations

import ast
import platform
import sys
from pathlib import Path

import pytest

from core import app_identity as ident

ROOT = Path(__file__).resolve().parent.parent


# ── the identifier itself ───────────────────────────────────────────────────

def test_the_identifier_is_a_reverse_dns_name():
    """Windows parses an AppUserModelID as Company.Product.Sub.Product.Version
    and the bundle identifier has the same shape. One spelling serves both, so
    it has to already look like both."""
    parts = ident.APP_ID.split(".")
    assert len(parts) >= 3
    assert all(p and p.isascii() for p in parts)
    assert ident.APP_ID == ident.APP_ID.lower()
    assert " " not in ident.APP_ID


def test_the_display_name_is_not_the_identifier():
    """A taskbar button labelled `com.jarvis.assistant` is a button nobody
    recognises, and a WM_CLASS of `J.A.R.V.I.S` is one the window manager
    mangles. They are separate facts on purpose."""
    assert ident.APP_NAME != ident.APP_ID
    assert "." in ident.APP_NAME or ident.APP_NAME.isupper()


def test_the_wm_class_is_the_identifier_not_the_pretty_name():
    """Qt sets WM_CLASS from the application name; the `.desktop` entry has to
    say the same thing or the two never match. Since `apply_qt` hands Qt the
    identifier through `setDesktopFileName`, this must be the identifier."""
    assert ident.startup_wm_class() == ident.APP_ID


def test_the_app_user_model_id_has_no_second_spelling():
    assert ident.app_user_model_id() == ident.APP_ID


# ── the Qt half ─────────────────────────────────────────────────────────────

class _FakeApp:
    def __init__(self, refuse=()):
        self.set_calls = {}
        self._refuse = set(refuse)

    def __getattr__(self, name):
        if not name.startswith("set"):
            raise AttributeError(name)

        def _set(value):
            if name in self._refuse:
                raise RuntimeError(f"{name} refused")
            self.set_calls[name] = value
        return _set


def test_applying_the_identity_names_the_application_and_the_desktop_file():
    app = _FakeApp()
    assert ident.apply_qt(app) is True
    assert app.set_calls["setApplicationName"] == ident.APP_NAME
    assert app.set_calls["setApplicationDisplayName"] == ident.APP_NAME
    # The one Qt uses as WM_CLASS / bundle hint: same string as the .desktop.
    assert app.set_calls["setDesktopFileName"] == ident.startup_wm_class()
    assert app.set_calls["setOrganizationDomain"] == ident.APP_ID


def test_a_qt_that_refuses_is_reported_and_never_raised():
    """An app that will not start because it could not rename itself is worse
    than one that is called python3."""
    assert ident.apply_qt(_FakeApp(refuse={"setApplicationName"})) is False


# ── the OS half ─────────────────────────────────────────────────────────────

def test_windows_gets_the_identifier_through_the_shell_api(monkeypatch):
    seen = []

    class _Shell32:
        @staticmethod
        def SetCurrentProcessExplicitAppUserModelID(value):
            seen.append(value.value)
            return 0

    class _Windll:
        shell32 = _Shell32()

    fake_ctypes = type("fake_ctypes", (), {
        "windll": _Windll(),
        "c_wchar_p": staticmethod(lambda v: type("W", (), {"value": v})()),
    })
    monkeypatch.setitem(sys.modules, "ctypes", fake_ctypes)

    assert ident.apply_os("Windows") is True
    assert seen == [ident.APP_ID]


def test_a_shell_that_refuses_does_not_stop_the_launch(monkeypatch):
    class _Sdk:
        @staticmethod
        def SetCurrentProcessExplicitAppUserModelID(value):
            raise OSError("no shell")

    monkeypatch.setitem(sys.modules, "ctypes", type("c", (), {
        "windll": type("w", (), {"shell32": _Sdk()})(),
        "c_wchar_p": staticmethod(lambda v: type("W", (), {"value": v})()),
    })())

    assert ident.apply_os("Windows") is False


def test_the_other_platforms_have_nothing_process_wide_to_set(monkeypatch):
    """Linux and macOS carry the identity in the launcher entry and the bundle.
    Pretending to set something here would be a lie the user could not see."""
    monkeypatch.setitem(sys.modules, "ctypes", None)     # would raise if touched
    assert ident.apply_os("Linux") is True
    assert ident.apply_os("Darwin") is True


def test_the_icon_is_one_path_for_everybody(tmp_path):
    path = ident.icon_path(tmp_path)
    assert path == tmp_path / "config" / "jarvis.ico"
    # The same file the tray and the desktop shortcut already use.
    assert path.name == "jarvis.ico"


# ── the three call sites agree ──────────────────────────────────────────────

def test_the_window_is_named_before_it_is_built():
    """Order is the whole point: Qt reads the application name when a window
    is created, so setting it afterwards renames nothing already on screen."""
    src = (ROOT / "ui" / "window.py").read_text(encoding="utf-8")
    qi = src.index("_identity.apply_qt")
    win = src.index("self._win = MainWindow(")
    assert qi < win, "the identity must be applied before the first window"
    os_call = src.index("app_identity.apply_os()")
    assert os_call < src.index("QApplication.instance() or QApplication("), \
        "the OS identity must be set before the QApplication exists"


def test_main_sets_the_os_identity_before_parsing_arguments():
    """A second launch must announce its identity too: the taskbar groups the
    process that is running, and the `--show` path goes through the same
    entry point."""
    tree = ast.parse((ROOT / "main.py").read_text(encoding="utf-8"))
    main_fn = next(n for n in tree.body
                   if isinstance(n, ast.FunctionDef) and n.name == "main")
    calls = [n for n in ast.walk(main_fn) if isinstance(n, ast.Call)]
    names = []
    for call in calls:
        attr = call.func
        if isinstance(attr, ast.Attribute):
            names.append(attr.attr)
    assert "apply_os" in names, "main() must give the process its OS identity"
    # And before the QApplication is paid for, which is what `JarvisUI(...)`
    # does: the identity is a fact about the process, not about the window.
    os_line = min(n.lineno for n in calls
                  if isinstance(n.func, ast.Attribute) and n.func.attr == "apply_os")
    ui_line = min(n.lineno for n in calls
                  if isinstance(n.func, ast.Name) and n.func.id == "JarvisUI")
    assert os_line < ui_line


def test_both_desktop_writers_say_which_window_they_own():
    """An entry without `StartupWMClass` is an entry the desktop cannot match
    to the window it just launched, so it draws a second, generic icon."""
    from core import autostart, deeplink

    for text in (autostart.desktop_text(Path("/x/main.py")),
                 deeplink.linux_desktop_text("/x/main.py")):
        assert f"StartupWMClass={ident.startup_wm_class()}" in text


def test_the_mac_bundle_uses_the_same_identifier_and_name(tmp_path, monkeypatch):
    from core import deeplink

    home = tmp_path / "home"
    monkeypatch.setattr(deeplink.Path, "home", classmethod(lambda cls: home))
    monkeypatch.setattr(deeplink.subprocess, "run", lambda *a, **k: None)
    script = tmp_path / "main.py"
    script.write_text("", encoding="utf-8")

    assert deeplink.register(script, os_name="Darwin") is True
    plist = (home / "Applications" / f"{ident.APP_NAME}.app"
             / "Contents" / "Info.plist").read_text(encoding="utf-8")
    assert f"<string>{ident.APP_ID}</string>" in plist
    assert f"CFBundleURLName</key><string>{ident.APP_ID}</string>" in plist


def test_the_scheme_handler_is_registered_under_the_same_class(tmp_path, monkeypatch):
    from core import deeplink

    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "share"))
    monkeypatch.setattr(deeplink.subprocess, "run", lambda *a, **k: None)
    script = tmp_path / "main.py"
    script.write_text("", encoding="utf-8")
    deeplink.register(script, os_name="Linux")

    text = deeplink.applications_path().read_text(encoding="utf-8")
    assert f"StartupWMClass={ident.APP_ID}" in text

    # And the handler's icon is the app's icon — the same file the tray draws —
    # included only when it is really on disk. An `Icon=` line pointing at
    # nothing gives a generic icon and no way to tell why.
    assert "Icon=" not in text
    ident.icon_path(script.parent).parent.mkdir(parents=True)
    ident.icon_path(script.parent).write_bytes(b"\x00")
    deeplink.register(script, os_name="Linux")
    assert f"Icon={ident.icon_path(script.parent)}" in \
        deeplink.applications_path().read_text(encoding="utf-8")


def test_the_identity_module_writes_nothing_itself():
    """Identity is told to two other modules, not written by a third writer.
    Two modules writing one file is how a settings panel starts lying."""
    src = (ROOT / "core" / "app_identity.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    forbidden = {"open", "write_text", "write_bytes", "mkdir", "makedirs"}
    used = {n.attr for n in ast.walk(tree) if isinstance(n, ast.Attribute)}
    used |= {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
    assert not (forbidden & used)


@pytest.mark.skipif(platform.system() != "Windows",
                    reason="the AppUserModelID API only exists on Windows")
def test_on_real_windows_the_call_returns_success():
    """Unverified in CI by construction: this sandbox is Linux. On a Windows
    runner the shell32 call is real, and it must not report failure."""
    assert ident.apply_os() is True
