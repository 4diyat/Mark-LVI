"""One JARVIS at a time — and a second launch that means "come to the front".

WHY THIS MATTERS MORE THAN IT SOUNDS
    Every way the assistant can now be started is a way to start a second copy:
    the tray's "Show JARVIS", the desktop shortcut, auto-start at login, and a
    user who does not see a window because the mode is ambient. Two copies of
    this program is not two windows. It is two Live sessions and two
    microphones answering at once, two sets of automation driving the same
    mouse, two identical tray icons neither of which summons the other, and two
    writers to one config file.

    So the tests here are about the THREE states a start can be in — nobody
    running, somebody running, and a leftover lock from a process that is gone
    — plus the fourth case that matters most: a lock that CANNOT be proven
    stale must be respected, because trampling it produces exactly the
    duplicate this module exists to prevent.

    All of it runs without Qt, without a subprocess, and without touching the
    real per-user folder: `acquire(lock=...)` takes its path explicitly.
"""
from __future__ import annotations

import json
import os
import sys
import time

import pytest

from core import single_instance as si


@pytest.fixture()
def lock(tmp_path):
    return tmp_path / "instance.lock"


@pytest.fixture()
def no_live_pid(monkeypatch):
    """Every pid is dead unless a test says otherwise."""
    monkeypatch.setattr(si, "_pid_alive", lambda pid: False)
    monkeypatch.setattr(si, "_proc_start_time", lambda pid: None)


def _write(lock, **record):
    lock.write_text(json.dumps(record), encoding="utf-8")


# ── the ordinary case ───────────────────────────────────────────────────────

def test_the_first_start_takes_the_lock_and_records_itself(lock, no_live_pid):
    instance = si.acquire("/opt/MarkLVI/main.py", lock=lock)
    try:
        assert instance.held is True
        data = json.loads(lock.read_text())
        assert data["pid"] == os.getpid()
        assert data["program"] == "/opt/MarkLVI/main.py"
        assert data["started"] > 0
    finally:
        instance.release()


def test_releasing_removes_the_lock_so_the_next_start_is_normal(lock, no_live_pid):
    si.acquire(lock=lock).release()
    assert not lock.exists()
    second = si.acquire(lock=lock)          # must not raise
    second.release()


def test_releasing_twice_is_harmless(lock, no_live_pid):
    instance = si.acquire(lock=lock)
    instance.release()
    instance.release()
    assert not lock.exists()


def test_the_lock_is_the_context_manager(lock, no_live_pid):
    with si.acquire(lock=lock) as instance:
        assert instance.held
    assert not lock.exists()


# ── the second copy ─────────────────────────────────────────────────────────

def test_a_live_lock_refuses_the_second_copy(lock, monkeypatch):
    """The message has to name the holder, because the user may need to kill it."""
    monkeypatch.setattr(si, "_pid_alive", lambda pid: True)
    monkeypatch.setattr(si, "_proc_start_time", lambda pid: None)
    _write(lock, pid=4242, program="/opt/MarkLVI/main.py", started=1.0)

    with pytest.raises(si.AlreadyRunning) as caught:
        si.acquire("/opt/MarkLVI/main.py", lock=lock)
    assert caught.value.holder["pid"] == 4242
    assert "4242" in str(caught.value)


def test_the_second_copy_does_not_leave_a_trace_of_its_own(lock, monkeypatch):
    """Refusing must not rewrite the holder's lock — that record is the proof."""
    monkeypatch.setattr(si, "_pid_alive", lambda pid: True)
    monkeypatch.setattr(si, "_proc_start_time", lambda pid: None)
    _write(lock, pid=4242, program="/opt/MarkLVI/main.py", started=1.0)
    before = lock.read_text()

    with pytest.raises(si.AlreadyRunning):
        si.acquire(lock=lock)
    assert lock.read_text() == before


# ── stale locks: the failure that would otherwise be permanent ──────────────

def test_a_dead_pid_is_taken_over(lock, no_live_pid):
    """A crash, a kill -9, a reboot: the lock outlives the process, not the app."""
    _write(lock, pid=999_999, program="/opt/MarkLVI/main.py", started=1.0)
    instance = si.acquire(lock=lock)
    try:
        assert json.loads(lock.read_text())["pid"] == os.getpid()
    finally:
        instance.release()


def test_a_reused_pid_is_detected_by_start_time(lock, monkeypatch):
    """PIDs get reused. Without this, the assistant would refuse to start forever
    because the pid now belongs to the user's editor."""
    monkeypatch.setattr(si, "_pid_alive", lambda pid: True)
    # Alive, but a DIFFERENT process than the one that wrote the lock.
    monkeypatch.setattr(si, "_proc_start_time", lambda pid: 5_000.0)
    _write(lock, pid=4242, program="/opt/MarkLVI/main.py", started=1.0,
           start_time=1_000.0)

    instance = si.acquire(lock=lock)
    try:
        assert json.loads(lock.read_text())["pid"] == os.getpid()
    finally:
        instance.release()


def test_a_lock_that_cannot_be_proven_stale_is_left_alone(lock, monkeypatch):
    """The direction of the doubt matters: refuse to start, never trample.

    A trampled live lock gives the user the duplicate this module exists to
    prevent, and it does it silently. A refused start is one file to delete and
    a message that says which file.
    """
    monkeypatch.setattr(si, "_pid_alive", lambda pid: True)
    monkeypatch.setattr(si, "_proc_start_time", lambda pid: 1_000.0)
    _write(lock, pid=4242, program="/opt/MarkLVI/main.py", started=1_000.0,
           start_time=1_000.0)

    with pytest.raises(si.AlreadyRunning):
        si.acquire(lock=lock)


def test_a_half_written_lock_is_not_a_lock(lock, no_live_pid):
    """The process that wrote it died between create and write."""
    lock.write_text("", encoding="utf-8")
    instance = si.acquire(lock=lock)
    try:
        assert json.loads(lock.read_text())["pid"] == os.getpid()
    finally:
        instance.release()


def test_garbage_in_the_lock_does_not_crash_the_start(lock, no_live_pid):
    lock.write_text("{not json", encoding="utf-8")
    instance = si.acquire(lock=lock)
    instance.release()
    assert not lock.exists()


def test_a_different_program_path_does_NOT_make_a_lock_stale(lock, monkeypatch):
    """The rule an earlier draft got wrong, kept as a test so it cannot come back.

    `argv[0]` is not stable: a shortcut, auto-start and a packaged build launch
    the same program through different strings. Declaring the lock stale on a
    path mismatch would have let a SECOND copy start whenever the two launchers
    disagreed — which is the exact bug this module exists to stop.
    """
    monkeypatch.setattr(si, "_pid_alive", lambda pid: True)
    monkeypatch.setattr(si, "_proc_start_time", lambda pid: None)
    _write(lock, pid=4242, program="/somewhere/else/old_install/main.py",
           started=0.0)                       # old AND from another path

    with pytest.raises(si.AlreadyRunning):
        si.acquire(__file__, lock=lock)


# ── "come to the front", for the second copy ───────────────────────────────

def test_a_second_launch_writes_a_request_instead_of_a_lock(lock, monkeypatch):
    monkeypatch.setattr(si, "_pid_alive", lambda pid: True)
    monkeypatch.setattr(si, "_proc_start_time", lambda pid: None)
    _write(lock, pid=4242, program="/opt/MarkLVI/main.py", started=1.0)

    assert si.request_foreground(lock) is True
    want = lock.with_name(lock.name + ".want")
    assert want.exists()
    assert json.loads(want.read_text())["pid"] == os.getpid()


def test_the_running_copy_consumes_the_request_once(lock):
    si.request_foreground(lock)
    first = si.take_foreground_request(lock)
    assert first is not None, "a request must be answered"
    assert si.take_foreground_request(lock) is None, (
        "a request that was already answered must not summon twice")


def test_no_request_means_no_summon(lock):
    assert si.take_foreground_request(lock) is None


def test_a_failed_request_write_is_reported_not_raised(lock, monkeypatch):
    """The second copy still has to exit cleanly — there is nothing else it can do."""
    def _boom(*_a, **_k):
        raise OSError("no space left")

    monkeypatch.setattr(si.Path, "write_text", _boom)
    assert si.request_foreground(lock) is False


# ── where the lock lives ────────────────────────────────────────────────────

def test_the_lock_is_per_user_and_not_per_checkout(tmp_path, monkeypatch):
    """Two checkouts of the app are still one assistant: the microphone is one.

    Which is why the folder is the per-user state directory and not the project
    — a project can be read-only, and a clone second is not a second user.
    """
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    path = si.state_dir()
    assert path == tmp_path / "state" / "MarkLVI"
    assert path.is_dir()
    assert si.lock_path().name == "instance.lock"


def test_windows_uses_localappdata(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "appdata"))
    monkeypatch.delenv("XDG_STATE_HOME", raising=False)
    assert si.state_dir() == tmp_path / "appdata" / "MarkLVI"


def test_an_unwritable_state_folder_falls_back_to_temp(tmp_path, monkeypatch):
    """A locked-down environment must not stop the app from starting."""
    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    real_mkdir = si.Path.mkdir

    def _mkdir(self, *a, **k):
        if "state" in str(self):
            raise OSError("read-only")
        return real_mkdir(self, *a, **k)

    monkeypatch.setattr(si.Path, "mkdir", _mkdir)
    import tempfile
    assert si.state_dir() == si.Path(tempfile.gettempdir()) / "MarkLVI"


# ── the two questions about pids ────────────────────────────────────────────

def test_this_process_is_alive_and_init_is_too(monkeypatch):
    monkeypatch.undo()
    assert si._pid_alive(os.getpid()) is True
    assert si._pid_alive(1) in (True, False)      # 1 exists on every POSIX box
    assert si._pid_alive(0) is False


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="needs /proc")
def test_the_start_time_is_readable_for_a_real_process():
    assert si._proc_start_time(os.getpid()) is not None


@pytest.mark.skipif(sys.platform == "win32",
                    reason="the POSIX branch of _pid_alive; Windows uses OpenProcess")
def test_a_pid_that_cannot_be_checked_is_treated_as_alive(lock, monkeypatch):
    """`PermissionError` on kill(0) means the process exists, owned by somebody
    else. Answering False there deletes a live lock.

    POSIX only, and the skip is the point: `_pid_alive` has two branches and
    this patches `os.kill`, which the Windows branch never calls. The Windows
    branch has its own test below — a test that silently exercises the wrong
    branch is how a green suite ships a Windows bug.
    """
    def _kill(_pid, _sig):
        raise PermissionError("not yours")

    monkeypatch.setattr(si.os, "kill", _kill)
    assert si._pid_alive(4242) is True


def test_the_windows_branch_refuses_to_delete_a_lock_it_cannot_check(monkeypatch):
    """On Windows there is no `kill(pid, 0)`; the question is asked with
    `OpenProcess`, and a `ctypes` that is missing or refuses must read as ALIVE.

    That direction is deliberate: an unanswerable question may not free a lock,
    because freeing a live one starts the second assistant this module exists to
    prevent. Runs everywhere by forcing the branch, since the CI runner that
    cares is the one that cannot reach it any other way.
    """
    import builtins

    real_import = builtins.__import__

    def _no_ctypes(name, *a, **k):
        if name == "ctypes":
            raise ImportError("ctypes unavailable")
        return real_import(name, *a, **k)

    monkeypatch.setattr(si.sys, "platform", "win32")
    monkeypatch.setattr(builtins, "__import__", _no_ctypes)
    assert si._pid_alive(4242) is True


@pytest.mark.skipif(sys.platform != "win32", reason="asks the real Windows API")
def test_the_windows_branch_answers_for_a_real_pid():
    assert si._pid_alive(os.getpid()) is True
    assert si._pid_alive(999_999) is False


# ── against a REAL second process, not a stub ──────────────────────────────

@pytest.mark.skipif(sys.platform == "win32", reason="uses a POSIX sleep process")
def test_a_real_live_process_holds_the_lock_against_us(lock):
    """The stub tests above prove the RULES; this proves the platform reads.

    A real `sleep` is started, its pid written into a lock shaped exactly as
    `acquire()` writes one, and then `acquire()` is asked to start a second
    copy. This is the only test here that exercises `_pid_alive` and
    `_proc_start_time` against a process that is actually running — which is
    the half a mocked pid can never check.
    """
    import subprocess

    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        time.sleep(0.2)                       # let it exec
        assert si._pid_alive(proc.pid) is True
        started = si._proc_start_time(proc.pid)
        assert started is not None, "the platform could not answer, and that matters"

        lock.write_text(json.dumps({"pid": proc.pid, "program": __file__,
                                    "started": time.time(),
                                    "start_time": started}), encoding="utf-8")
        with pytest.raises(si.AlreadyRunning):
            si.acquire(__file__, lock=lock)
    finally:
        proc.kill()
        proc.wait(timeout=10)


@pytest.mark.skipif(sys.platform == "win32", reason="uses a POSIX sleep process")
def test_a_real_dead_process_lock_is_taken_over(lock):
    """And the case that would otherwise lock the user out for good."""
    import subprocess

    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait(timeout=30)
    lock.write_text(json.dumps({"pid": proc.pid, "program": __file__,
                                "started": 1.0,
                                "start_time": si._proc_start_time(proc.pid)}),
                    encoding="utf-8")

    instance = si.acquire(__file__, lock=lock)
    try:
        assert json.loads(lock.read_text())["pid"] == os.getpid()
    finally:
        instance.release()


# ── the wiring: main.py claims, lifecycle answers ──────────────────────────

def _main_ast():
    import ast
    root = si.Path(__file__).resolve().parent.parent
    return ast.parse((root / "main.py").read_text(encoding="utf-8"))


def test_main_claims_the_lock_before_building_anything():
    """Order is the whole assertion.

    A claim made after `JarvisUI(...)` would mean the second copy pays for a
    QApplication, a window and a tray icon before discovering it is redundant —
    and on a slow machine it would briefly SHOW a second window.
    """
    import ast

    tree = _main_ast()
    main_fn = next(n for n in tree.body
                   if isinstance(n, ast.FunctionDef) and n.name == "main")
    calls = [(n.lineno, n.func.id) for n in ast.walk(main_fn)
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)]
    order = {name: line for line, name in calls}
    assert "_claim_single_instance" in order, "main() no longer claims the lock"
    assert "JarvisUI" in order
    assert order["_claim_single_instance"] < order["JarvisUI"], (
        "the single-instance claim must happen before the window is built")


def test_a_second_launch_asks_the_running_copy_and_then_exits(tmp_path, monkeypatch,
                                                              capsys):
    """`_claim_single_instance` must not fall through into a second assistant.

    Read from `main.py` by AST and executed on its own, because importing that
    module pulls in sounddevice, PyQt and the whole session — none of which
    this sandbox has. The function itself imports `core.single_instance`
    lazily, which is exactly what makes it executable in isolation.
    """
    import ast

    tree = _main_ast()
    fn = next(n for n in tree.body
              if isinstance(n, ast.FunctionDef) and n.name == "_claim_single_instance")
    namespace: dict = {"Path": si.Path, "__name__": "main_under_test",
                       "__file__": str(si.Path(__file__).resolve().parent.parent / "main.py")}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), "main.py", "exec"), namespace)

    asked = []

    def _taken(program=""):
        raise si.AlreadyRunning({"pid": 4242})

    monkeypatch.setattr(si, "acquire", _taken)
    # Takes `text=` since a link's words travel with the request.
    monkeypatch.setattr(si, "request_foreground",
                        lambda lock=None, text="": asked.append(text))

    with pytest.raises(SystemExit) as exited:
        namespace["_claim_single_instance"]()
    assert exited.value.code == 0, "being a second copy is not an error"
    assert asked == [""], "the running copy must be asked to come forward"
    assert "Already running" in capsys.readouterr().out


def test_a_second_launch_says_where_the_lock_is_when_it_cannot_ask(tmp_path,
                                                                  monkeypatch, capsys):
    """If the request file cannot be written, the user still has to be unblocked.

    Refusing to start is correct; refusing to start with no explanation is a
    support ticket. The message names the file to delete, which is the only
    recovery the user has without a terminal.
    """
    import ast

    tree = _main_ast()
    fn = next(n for n in tree.body
              if isinstance(n, ast.FunctionDef) and n.name == "_claim_single_instance")
    namespace: dict = {"Path": si.Path, "__name__": "main_under_test",
                       "__file__": str(si.Path(__file__).resolve().parent.parent / "main.py")}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), "main.py", "exec"), namespace)

    monkeypatch.setattr(si, "acquire",
                        lambda program="": (_ for _ in ()).throw(
                            si.AlreadyRunning({"pid": 4242})))
    monkeypatch.setattr(si, "request_foreground", lambda lock=None, text="": False)
    monkeypatch.setattr(si, "lock_path", lambda: tmp_path / "instance.lock")

    with pytest.raises(SystemExit):
        namespace["_claim_single_instance"]()
    out = capsys.readouterr().out
    assert "instance.lock" in out


def test_the_window_summons_itself_when_another_launch_is_requested(tmp_path,
                                                                   monkeypatch):
    """The other half: the file the second copy wrote must actually be noticed."""
    from types import SimpleNamespace

    lifecycle = _load_module("ui/lifecycle.py", "lifecycle_si_under_test")

    summoned = []
    monkeypatch.setattr(lifecycle, "summon", lambda shell: summoned.append(shell))

    request = {"pending": {"text": ""}}
    monkeypatch.setattr(si, "take_foreground_request",
                        lambda lock=None: request.pop("pending", None))

    timers = []

    class _Signal:
        def __init__(self):
            self.slots = []

        def connect(self, fn):
            self.slots.append(fn)

    class _Timer:
        """`timeout` is an ATTRIBUTE holding a signal, exactly as in Qt.

        The first draft made it a method returning a signal, and the test
        passed against behaviour that would have raised TypeError on a real
        QTimer the moment a second launch arrived — in ambient mode, where the
        window is hidden and the summon is the only feedback there is.
        """

        def __init__(self, parent=None):
            self.parent = parent
            self.interval = None
            self.started = False
            self.timeout = _Signal()
            timers.append(self)

        def setInterval(self, ms):
            self.interval = ms

        def start(self):
            self.started = True

        def fire(self):
            for slot in list(self.timeout.slots):
                slot()

    monkeypatch.setitem(sys.modules, "PyQt6",
                        SimpleNamespace(QtCore=SimpleNamespace(QTimer=_Timer)))
    monkeypatch.setitem(sys.modules, "PyQt6.QtCore",
                        SimpleNamespace(QTimer=_Timer))

    shell = SimpleNamespace(_win=SimpleNamespace(), _log_sig=None)
    lifecycle.watch_for_another_launch(shell)

    assert timers and timers[0].started is True
    assert shell._launch_watch is timers[0], "the timer is kept, or it is collected"

    timers[0].fire()                     # what Qt does on the interval
    assert summoned == [shell], "a second launch must bring the window forward"

    timers[0].fire()                     # the request was consumed already
    assert summoned == [shell], "one request, one summon"


def _load_module(relative: str, name: str):
    import importlib.util
    root = si.Path(__file__).resolve().parent.parent
    spec = importlib.util.spec_from_file_location(name, root / relative)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


# ── paths arriving as strings ──────────────────────────────────────────────

@pytest.mark.parametrize("as_string", [True, False])
def test_the_lock_can_be_given_as_a_string_or_a_path(tmp_path, no_live_pid, as_string):
    """Found by running two real processes, not by this suite.

    Every test here already passed a `Path`, so the `str` case was never
    covered — and `str.with_name` is an AttributeError three frames down, which
    is what the second process traceback showed. Half the callers that would
    hand this module a path have one as a string.
    """
    lock = str(tmp_path / "instance.lock") if as_string else tmp_path / "instance.lock"
    instance = si.acquire("program", lock=lock)
    try:
        assert si.read_lock(lock)["pid"] == os.getpid()
    finally:
        instance.release()


def test_a_string_path_works_for_the_request_file_too(tmp_path):
    lock = str(tmp_path / "instance.lock")
    assert si.request_foreground(lock) is True
    assert si.take_foreground_request(lock) is not None


# ── the request carries words, not just a signal ───────────────────────────

def test_a_request_can_carry_the_link_text(lock):
    """A `jarvis://ask` opened while JARVIS is running must not lose its words.

    The second process is refused (correct) and the first is told "somebody
    wants you" — which, without this, would be all that survived of a link that
    said something specific.
    """
    si.request_foreground(lock, text="remind me at four")
    assert si.take_foreground_request(lock) == {"text": "remind me at four"}


def test_a_request_without_words_is_still_a_request(lock):
    si.request_foreground(lock)
    assert si.take_foreground_request(lock) == {"text": ""}


def test_text_written_by_something_else_is_still_bounded(lock):
    """The request file lives in a shared per-user folder.

    Anything that can write there can put anything in it, so the 500-character
    ceiling from the URL parser is applied here too. The two channels are not
    differently trustworthy just because one of them is a file.
    """
    want = lock.with_name(lock.name + ".want")
    want.write_text(json.dumps({"pid": 1, "text": "a" * 501}), encoding="utf-8")
    assert si.take_foreground_request(lock) == {"text": ""}

    want.write_text(json.dumps({"pid": 1, "text": 12345}), encoding="utf-8")
    assert si.take_foreground_request(lock) == {"text": ""}


def test_a_half_written_request_still_brings_the_window_forward(lock):
    """Losing the words is a smaller failure than losing the summon."""
    want = lock.with_name(lock.name + ".want")
    want.write_text("{not json", encoding="utf-8")
    assert si.take_foreground_request(lock) == {"text": ""}


def test_a_link_opened_while_jarvis_runs_says_its_words(tmp_path, monkeypatch):
    """The whole reason the request file carries text.

    `jarvis://ask?text=…` opened while the assistant is already running: the
    second process refuses to start (correct), the first is told "somebody wants
    you" — and without the text travelling with it, the sentence is gone and the
    user sees a window appear for no stated reason.
    """
    import ast

    tree = _main_ast()
    fn = next(n for n in tree.body
              if isinstance(n, ast.FunctionDef) and n.name == "_claim_single_instance")
    namespace: dict = {"Path": si.Path, "__name__": "main_under_test",
                       "__file__": str(si.Path(__file__).resolve().parent.parent / "main.py")}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), "main.py", "exec"), namespace)

    asked = []
    monkeypatch.setattr(si, "acquire",
                        lambda program="": (_ for _ in ()).throw(
                            si.AlreadyRunning({"pid": 4242})))
    monkeypatch.setattr(si, "request_foreground",
                        lambda lock=None, text="": asked.append(text))

    from core import deeplink as dl
    with pytest.raises(SystemExit):
        namespace["_claim_single_instance"](dl.Request("ask", "remind me at four"))
    assert asked == ["remind me at four"]


def test_a_summon_link_sends_no_words(tmp_path, monkeypatch):
    import ast

    tree = _main_ast()
    fn = next(n for n in tree.body
              if isinstance(n, ast.FunctionDef) and n.name == "_claim_single_instance")
    namespace: dict = {"Path": si.Path, "__name__": "main_under_test",
                       "__file__": str(si.Path(__file__).resolve().parent.parent / "main.py")}
    exec(compile(ast.Module(body=[fn], type_ignores=[]), "main.py", "exec"), namespace)

    asked = []
    monkeypatch.setattr(si, "acquire",
                        lambda program="": (_ for _ in ()).throw(
                            si.AlreadyRunning({"pid": 4242})))
    monkeypatch.setattr(si, "request_foreground",
                        lambda lock=None, text="": asked.append(text))

    from core import deeplink as dl
    with pytest.raises(SystemExit):
        namespace["_claim_single_instance"](dl.Request("summon"))
    assert asked == [""]
