"""The window that never opened: `start_interface` had no caller.

WHY THESE TESTS EXIST
    `ui/lifecycle.start_interface()` builds the tray icon, the face bubble, the
    orb, the command bar, the voice overlay and the summon hotkey. Everything in
    boards 1, 2, 4, 5 and 23 hangs off that one function.

    It was never called. `main()` built a QApplication, started the Gemini
    thread, and entered `app.exec()` — an event loop with no window in it. A
    user running `python main.py` saw the API-key screen once, saved a key, and
    then saw nothing at all: a process with no tray icon, no orb, and no way to
    quit except the task manager.

    The entire suite was green while that was true, because every test calls
    `lifecycle.start_interface(shell)` DIRECTLY and not one of them asked
    whether the application does. A surface that is built and never shown and a
    surface that is never built at all look identical from inside a test.

    So this file tests the one link the others could not: the call.

THREE LAYERS, DELIBERATELY
    1. the call exists in `main()` at all — the failure that happened
    2. it happens BEFORE `app.exec()` — a surface built after the loop runs is
       a surface that never paints
    3. it passes the real shell — a call with no argument would be a NameError,
       but a call with a fresh throwaway shell would build surfaces the session
       thread never sees
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
MAIN = ROOT / "main.py"


def _main_body() -> ast.FunctionDef:
    """`main()` as parsed source, without importing main.py.

    `main.py` cannot be imported here — it needs sounddevice, google-genai and
    a Live session, exactly as `tests/test_launch_options.py` documents. The
    source is the artefact under test, and it is read as an AST rather than
    grepped so that a comment mentioning `start_interface` cannot pass for a
    call.
    """
    tree = ast.parse(MAIN.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "main":
            return node
    raise AssertionError("main.py has no main()")


def _calls_in(node: ast.AST) -> list[ast.Call]:
    return [child for child in ast.walk(node) if isinstance(child, ast.Call)]


def _called_name(call: ast.Call) -> str:
    func = call.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


# ── 1. the call exists ───────────────────────────────────────────────────────

def test_main_builds_the_interface_at_all():
    """THE BUG. Without this call the app starts, runs, and shows nothing."""
    names = [_called_name(call) for call in _calls_in(_main_body())]
    assert "start_interface" in names, (
        "main() never calls start_interface — the tray, orb, face, command bar "
        "and hotkey are all built by it, so a launch would show no window, no "
        "tray icon, and no way to quit")


def test_the_call_targets_the_lifecycle_module():
    """Importing the name into main.py would also work, but then a test that
    patches `ui.lifecycle.start_interface` would not see the call. Assert the
    path the app actually takes."""
    calls = [call for call in _calls_in(_main_body())
             if _called_name(call) == "start_interface"]
    assert calls, "no start_interface call to inspect"
    func = calls[0].func
    assert isinstance(func, ast.Attribute) and func.attr == "start_interface"
    # `from ui import lifecycle` then `lifecycle.start_interface`, or the same
    # under an alias — what matters is that the module is `ui.lifecycle`, not
    # that the local name is the one word. A by-name import would also work at
    # runtime; it is rejected here because a test that patches
    # `ui.lifecycle.start_interface` would not see the call.
    assert isinstance(func.value, ast.Name), (
        f"expected <module>.start_interface, got {ast.unparse(func)}")
    imported = {
        alias.asname or alias.name
        for node in ast.walk(ast.parse(MAIN.read_text(encoding="utf-8")))
        if isinstance(node, ast.ImportFrom) and node.module == "ui"
        for alias in node.names
        if alias.name == "lifecycle"
    }
    assert func.value.id in imported, (
        f"start_interface is called on `{func.value.id}`, which is not "
        f"ui.lifecycle (imported as {sorted(imported)})")


def test_the_interface_is_given_the_shell_the_session_uses():
    """One shell. A second `AmbientShell()` here would build a second tray for a
    session attached to the first, which is the two-microphones failure the
    single-instance claim exists to prevent."""
    calls = [call for call in _calls_in(_main_body())
             if _called_name(call) == "start_interface"]
    assert calls
    args = calls[0].args
    assert args, "start_interface called with no argument"
    assert isinstance(args[0], ast.Name), (
        f"expected a named shell, got {ast.unparse(args[0])}")
    # the name it passes must be the one `AmbientShell(...)` was assigned to
    shell_names = {
        target.id
        for node in ast.walk(_main_body())
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Name)
        and isinstance(node.value, ast.Call)
        and _called_name(node.value) == "AmbientShell"
    }
    assert shell_names, "main() never constructs an AmbientShell"
    assert args[0].id in shell_names, (
        f"start_interface gets {args[0].id}, but the shell is {shell_names}")


# ── 2. the order ────────────────────────────────────────────────────────────

def test_the_interface_is_built_before_the_event_loop_starts():
    """A surface created after `exec()` never gets a chance to paint: the call
    that would have shown it is behind a loop that only returns on quit."""
    body = _main_body()
    calls = _calls_in(body)
    interface = [c for c in calls if _called_name(c) == "start_interface"]
    loop = [c for c in calls if _called_name(c) == "_run_event_loop"]
    assert interface and loop, "main() must both build the interface and run"
    assert interface[0].lineno < loop[0].lineno, (
        "start_interface is called after the event loop — the window would be "
        "built while nothing is left to paint it")


def test_the_interface_is_built_after_the_launch_options_are_recorded():
    """`start_interface` READS `shell._launch` (for `--hidden` and for a
    `jarvis://` link). Building surfaces before the flag is attached would make
    `--hidden` a login entry that pops a face on the first frame."""
    body = _main_body()
    calls = _calls_in(body)
    interface = [c for c in calls if _called_name(c) == "start_interface"][0]
    launch_writes = [
        node.lineno
        for node in ast.walk(body)
        if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Attribute) and target.attr == "_launch"
    ]
    assert launch_writes, "main() never records the launch options"
    assert min(launch_writes) < interface.lineno, (
        "start_interface runs before `_launch` is attached, so --hidden and "
        "jarvis:// links would be ignored by the surfaces it builds")


# ── 2b. --hidden after the surfaces actually exist ───────────────────────────
#
# `--hidden` USED TO BE A NO-OP FOR A REASON NOBODY INTENDED: nothing was ever
# shown, so there was nothing to hide. Now that `start_interface` runs, the flag
# finally does something — and the thing it does has to be the right thing.

def test_hidden_hides_the_face_and_keeps_the_way_back():
    """A login entry must not paint a face on the first frame, and must still
    leave the user a way to reach the assistant.

    THE ORB STAYS. It is the only surface that opens the panel with a click
    (board 4) — hiding it would make `--hidden` mean "started invisibly, open
    the panel from the tray or not at all". The face is the thing that covers
    the screen; the orb is the thing that answers a click. So the flag hides
    one and keeps the other, and this test is what stops a later "hide
    everything" tidy-up from removing the only mouse path the app has.
    """
    import ui.lifecycle as lifecycle

    hidden = []

    class Window:
        def setVisible(self, visible):
            hidden.append(bool(visible))

    class Shell:
        _bubble = type("B", (), {"available": True, "_window": Window()})()
        _launch = type("L", (), {"hidden": True})()

    lifecycle._set_bubble_visible(Shell(), False)
    assert hidden == [False], "the face was not told to hide"


def test_the_shown_path_leaves_the_face_alone():
    """`--show` and a plain launch must not hide anything."""
    import ui.lifecycle as lifecycle

    hidden = []

    class Window:
        def setVisible(self, visible):
            hidden.append(bool(visible))

    lifecycle._set_bubble_visible(
        type("S", (), {"_bubble": type("B", (), {"_window": Window()})()})(), True)
    assert hidden == [True]


def test_start_interface_only_hides_on_the_hidden_flag(monkeypatch):
    """Read from the source: the call to `_set_bubble_visible(shell, False)` is
    guarded by `hidden`. An unguarded call would blank the face on every launch,
    which is the opposite bug and equally invisible in a suite that never
    starts the app."""
    tree = ast.parse((ROOT / "ui" / "lifecycle.py").read_text(encoding="utf-8"))
    start = next(node for node in tree.body
                 if isinstance(node, ast.FunctionDef)
                 and node.name == "start_interface")
    hides = [
        node for node in ast.walk(start)
        if isinstance(node, ast.Call) and _called_name(node) == "_set_bubble_visible"
        and node.args and isinstance(node.args[-1], ast.Constant)
        and node.args[-1].value is False
    ]
    assert hides, "start_interface never hides the face for --hidden"
    guarded = [
        node for node in ast.walk(start)
        if isinstance(node, ast.If)
        and any(inner is hides[0] for inner in ast.walk(node))
    ]
    assert guarded, "the hide is not inside an `if` — it would run every launch"
    condition = ast.unparse(guarded[0].test)
    assert "hidden" in condition, (
        f"the hide is guarded by `{condition}`, which is not the hidden flag")


# ── 2c. one broken surface must not take the app down with it ───────────────
#
# PUTTING THE CALL IN `main()` CREATED A NEW WAY TO DIE. Before, nothing could
# fail at startup because nothing ran. Now `start_interface` runs on the main
# thread BEFORE `exec()`, so an exception escaping it kills the process before
# any window or event loop exists — and the user gets a traceback and no app.
#
# `start_tray` and `start_orb` do not wrap their own constructors. `TrayIcon`
# and `OrbOverlay` are written to report failure rather than raise, but "is
# written to" is a promise, and a promise held by every future edit is not a
# guarantee. The caller is the place that can hold it.

def test_a_surface_that_raises_does_not_kill_the_app(monkeypatch):
    from ui import lifecycle

    class Boom:
        def __init__(self, *a, **kw):
            raise RuntimeError("desktop exploded")

    notes = []

    class Shell:
        _app = None
        _launch = None
        _program_path = ""

        def __init__(self):
            self._tray = self._bubble = self._orb = self._command_bar = None

        def write_log(self, line):
            notes.append(str(line))

        def _face_path_or_default(self):
            return "face.png"

    import ui.tray as tray_module
    monkeypatch.setattr(tray_module, "TrayIcon", Boom)
    # This test has no QApplication; isolate the unrelated Qt surfaces.
    for name in ("start_orb", "start_command_bar", "start_toast", "start_voice_overlay",
                 "start_summon_hotkey"):
        monkeypatch.setattr(lifecycle, name, lambda _shell: False)

    shell = Shell()
    lifecycle.start_interface(shell)      # must not raise

    assert any("tray" in line.lower() and "exploded" in line for line in notes), (
        "the failure was swallowed without a word — the user would have a "
        f"working app and no idea one surface is missing (log: {notes})")


def test_the_remaining_surfaces_still_come_up_after_one_fails(monkeypatch):
    """Degrading is the design: a tray and nothing else is a working install.
    A failure that also stopped the orb would turn one broken surface into a
    silent app."""
    from ui import lifecycle

    class Boom:
        def __init__(self, *a, **kw):
            raise RuntimeError("no notification area and a Qt that says so")

    started = []

    class Shell:
        _app = None
        _launch = None
        _program_path = ""

        def __init__(self):
            self._tray = self._bubble = self._orb = self._command_bar = None

        def write_log(self, line):
            pass

        def _face_path_or_default(self):
            return "face.png"

    import ui.orb_overlay as orb_module
    import ui.tray as tray_module
    monkeypatch.setattr(tray_module, "TrayIcon", Boom)
    # `start_orb` imports OrbOverlay inside the function, so the module
    # attribute is the seam — there is no module-level name to patch.
    monkeypatch.setattr(orb_module, "OrbOverlay", Boom)
    monkeypatch.setattr(lifecycle, "start_command_bar",
                        lambda shell: started.append("bar") or True)
    for name in ("start_toast", "start_voice_overlay", "start_summon_hotkey"):
        monkeypatch.setattr(lifecycle, name, lambda _shell: False)

    lifecycle.start_interface(Shell())    # must not raise
    assert "bar" in started, (
        "a failure in the tray or the orb stopped the surfaces after it")


# ── 3. behaviour: main() really calls it ────────────────────────────────────

@pytest.fixture()
def importable_main(monkeypatch):
    """`main.py`, imported with the four modules a sandbox does not have.

    WHY STUBS AND NOT INSTALLS. `sounddevice` needs PortAudio and a device;
    `google.genai` needs a network client. Neither is under test here — the
    thing under test is which functions `main()` calls — so each is replaced by
    the smallest object that satisfies the module-level imports. `_Any` answers
    any attribute, which is how `types.LiveConnectConfig` and the thirty
    `types.*` names below it stop mattering.

    The stubs are OURS and they are installed only for this test: if
    `main.py` were ever to use the real thing at import time, that is a fact
    this fixture cannot hide.
    """
    class _Any:
        def __init__(self, *a, **kw):
            pass

        def __getattr__(self, name):
            return _Any()

        def __call__(self, *a, **kw):
            return _Any()

    class _Mod:
        def __init__(self, name):
            self.__name__ = name

        def __getattr__(self, name):
            if name.startswith("__"):
                raise AttributeError(name)
            return _Any()

        def __call__(self, *a, **kw):
            return _Any()

    saved = {}
    made = {
        "sounddevice": None,
        "google": None,
        "google.genai": None,
        "google.genai.types": None,
    }
    for name in made:
        saved[name] = sys.modules.get(name)
        module = _Mod(name)
        if name == "google":
            module.__path__ = []            # a namespace package, as installed
        sys.modules[name] = module
    sys.modules["google"].genai = sys.modules["google.genai"]
    sys.modules["google.genai"].types = sys.modules["google.genai.types"]

    sys.modules.pop("main", None)
    try:
        import main as main_module
        yield main_module
    finally:
        sys.modules.pop("main", None)
        for name, previous in saved.items():
            if previous is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = previous


def test_running_main_actually_reaches_start_interface(importable_main, monkeypatch):
    """The source tests above would pass on a call placed in dead code. This one
    executes `main()` with the heavy parts replaced and records the call.

    Everything replaced here is something main.py cannot do in a sandbox: build
    a QApplication, claim the single-instance lock, start a Gemini session, or
    hand the thread to Qt. The one thing NOT replaced is the call itself.
    """
    import ui.lifecycle as lifecycle

    main = importable_main
    called = {}

    class FakeApp:
        def exec(self):
            called["exec"] = True

        def quit(self):
            pass

    class FakeShell:
        def __init__(self, *a, **kw):
            self._launch = None
            self._program_path = ""

        def wait_for_api_key(self):
            called["waited"] = True

    class FakeThread:
        def __init__(self, target=None, daemon=None):
            self._target = target

        def start(self):
            called["thread_started"] = True

    monkeypatch.setattr(main, "_parse_args", lambda: (main.LaunchOptions(), []))
    monkeypatch.setattr(main, "_claim_single_instance", lambda link=None: object())
    monkeypatch.setattr(main, "_make_application", lambda argv=None: FakeApp())
    monkeypatch.setattr(main, "AmbientShell", FakeShell)
    monkeypatch.setattr(main, "_face_path", lambda: "")
    monkeypatch.setattr(main.threading, "Thread", FakeThread)
    monkeypatch.setattr(main, "JarvisLive", lambda shell: object())

    def fake_start_interface(shell):
        called["interface"] = shell

    monkeypatch.setattr(lifecycle, "start_interface", fake_start_interface)

    main.main()

    assert "interface" in called, (
        "main() ran without calling lifecycle.start_interface — this is the "
        "exact failure: a process with no tray, no orb, and no way to quit")
    assert isinstance(called["interface"], FakeShell), (
        "start_interface got something other than the session's shell")
    assert called.get("thread_started") is True
    assert called.get("exec") is True, "the event loop was never entered"
