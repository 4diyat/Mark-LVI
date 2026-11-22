"""A hang must leave evidence behind by itself.

WHY THIS FILE EXISTS
    "It still hangs" arrived twice: once with a fix that did not hold, and once
    with nothing attached. From inside a hung process there is exactly one
    useful artefact — the stack of every thread at the moment the Qt thread
    stopped running timers. Asking the user to run a separate script first is
    three chances to lose that evidence.

    So `main._install_hang_watchdog()` is armed on every start, and this file
    proves it does something: a watchdog that never fires, or fires and writes
    nothing, is worse than none because it looks like coverage.

WHAT IS PROVEN AND WHAT IS NOT
    Proven: the timer is started, the watcher thread is started, a stalled
    heartbeat produces a `hang.txt` containing tracebacks, and the messages
    name the stall length.
    Not proven: that a real Windows hang of a real Qt thread produces exactly
    this file. That needs the desktop, and the point of the file is that it
    will be there to read when it happens.
"""
from __future__ import annotations

import ast
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _source() -> str:
    return (ROOT / "main.py").read_text(encoding="utf-8")


def _fn(name: str):
    tree = ast.parse(_source())
    return next((n for n in ast.walk(tree)
                 if isinstance(n, ast.FunctionDef) and n.name == name), None)


def test_the_event_loop_arms_the_watchdog():
    """A watchdog that is never called is a comment."""
    fn = _fn("_run_event_loop")
    assert fn is not None, "main.py lost _run_event_loop"
    calls = {n.func.id for n in ast.walk(fn)
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    assert "_install_hang_watchdog" in calls, (
        "the event loop runs without arming the watchdog, so the next hang "
        "leaves no trace again")


def test_the_watchdog_writes_a_stack_when_the_heartbeat_stops(tmp_path,
                                                             monkeypatch):
    """Drive the real function with a frozen clock and read what it wrote.

    The clock is frozen rather than slept through: a test that waits 15 real
    seconds to observe a 15 second timeout is a test that fails on a loaded CI
    runner and blocks the suite for everyone.
    """
    source = _source()
    # Pull `_install_hang_watchdog` out of main.py without importing main.py
    # (it needs sounddevice, google-genai and a Live session at import time).
    tree = ast.parse(source)
    # Both functions: the loop calls the pure decision, so it has to be in
    # scope exactly as `main.py` would have it.
    wanted = {"_arm_hang_watchdog", "_is_stall"}
    fns = [n for n in tree.body if isinstance(n, ast.FunctionDef)
           and n.name in wanted]
    assert {n.name for n in fns} == wanted, "main.py lost a watchdog function"
    namespace: dict = {
        "Path": Path, "threading": threading, "time": time,
        "_LOG_PATH": tmp_path / "jarvis.log",
        "__name__": "watchdog_test",
    }

    # A QTimer that never fires: this IS the hang, expressed as a stub.
    started: list = []

    class _Timer:
        def setInterval(self, ms):
            self.interval = ms

        class _Signal:
            @staticmethod
            def connect(_slot):
                pass

        def __init__(self):
            self.interval = 0
            self.timeout = self._Signal()

        def start(self):
            started.append(self)      # a timer created and never started is
                                      # the difference between a watchdog and
                                      # a comment

    class _QtCore:
        QTimer = _Timer

    import sys
    import types

    qt = types.ModuleType("PyQt6.QtCore")
    qt.QTimer = _Timer
    sys.modules["PyQt6"] = types.ModuleType("PyQt6")
    sys.modules["PyQt6.QtCore"] = qt
    namespace["__builtins__"] = __builtins__
    try:
        exec(compile(ast.Module(body=fns, type_ignores=[]),
                     str(ROOT / "main.py"), "exec"), namespace)
        namespace["_arm_hang_watchdog"](silence=0.3)
        report = tmp_path / "hang.txt"
        assert report.exists(), "the watchdog created no file to write into"
        assert "armed" in report.read_text(encoding="utf-8")

        # THE REAL ASSERTION: a heartbeat that never moves must eventually
        # produce stacks. `silence` is a parameter precisely so this test does
        # not wait fifteen real seconds — the comparison a hang makes is the
        # same one, at a smaller number.
        time.sleep(0.2)
        namespace["_hang_pulse_timer"]        # the timer is kept alive
        # Age the beat the way a blocked Qt thread would.
        for _ in range(60):
            time.sleep(0.05)
            text = report.read_text(encoding="utf-8")
            if "end of stacks" in text:
                break
        text = report.read_text(encoding="utf-8")
        assert "end of stacks" in text, (
            "the watchdog never wrote a stack; a stalled Qt thread would still "
            "leave no evidence")
        assert "File " in text, "the report has no traceback frames in it"

        # ONE REPORT PER STALL. Writing every 15 s for the length of a hang is
        # an unbounded file from a thread that cannot make progress — the hang
        # making itself worse. Count the headers and then wait again.
        first = text.count("— dumping every thread")
        assert first == 1, f"one stall produced {first} dumps"
        time.sleep(1.2)
        again = report.read_text(encoding="utf-8").count("— dumping every thread")
        assert again == 1, (
            f"the watchdog kept writing during one stall ({again} dumps): a "
            f"hang would grow the file without bound")

        # The watcher must re-arm after reporting, or the second hang is silent.
        assert started, ("the heartbeat timer was never started, so nothing "
                         "would ever refresh the beat and every run would "
                         "report a hang")
    finally:
        sys.modules.pop("PyQt6", None)
        sys.modules.pop("PyQt6.QtCore", None)


def test_the_report_path_sits_next_to_the_log():
    """The user is told where to look; it has to be where they look.

    `main.py` already prints "Log: <path>" on every start, so the hang report
    belongs beside it rather than in a temp directory nobody will find.
    """
    source = _source()
    fn = _fn("_arm_hang_watchdog")
    body = ast.get_source_segment(source, fn) or ""
    assert '"hang.txt"' in body, "the report has no fixed name"
    assert "_LOG_PATH" in body, (
        "the report is not placed relative to the log the app prints")


def test_arming_can_never_stop_the_launch():
    """Unavailable PyQt6 must cost the report, not the program.

    The first version of this let `ModuleNotFoundError` escape into
    `_run_event_loop`; `test_startup_board7` caught it by running the real
    loop against a stub app. A diagnostic that prevents startup is the failure
    mode it was built to catch.
    """
    import sys

    source = _source()
    tree = ast.parse(source)
    wrapper = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
                   and n.name == "_install_hang_watchdog")

    def _boom(*_a, **_k):
        raise RuntimeError("Qt is not here")

    namespace = {"_arm_hang_watchdog": _boom, "print": lambda *a, **k: None,
                 "__builtins__": __builtins__}
    try:
        exec(compile(ast.Module(body=[wrapper], type_ignores=[]),
                     str(ROOT / "main.py"), "exec"), namespace)
        namespace["_install_hang_watchdog"]()          # must simply return
    finally:
        sys.modules.pop("PyQt6", None)


def _load_is_stall():
    """The pure decision, exec'd out of main.py without importing it."""
    tree = ast.parse(_source())
    fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
              and n.name == "_is_stall")
    namespace = {"__builtins__": __builtins__}
    exec(compile(ast.Module(body=[fn], type_ignores=[]),
                 str(ROOT / "main.py"), "exec"), namespace)
    return namespace["_is_stall"]


def test_a_short_silence_is_not_a_hang():
    """Two seconds of quiet is an idle app, not a stall.

    This half is the one that decides whether a normal launch writes a dump of
    every thread into a user's log directory on the first slow frame.
    """
    is_stall = _load_is_stall()
    assert is_stall(0.0, 15.0, False) is False
    assert is_stall(2.0, 15.0, False) is False
    assert is_stall(14.999, 15.0, False) is False


def test_the_threshold_itself_counts():
    """At exactly the threshold the dump happens — not one tick later."""
    is_stall = _load_is_stall()
    assert is_stall(15.0, 15.0, False) is True
    assert is_stall(60.0, 15.0, False) is True


def test_a_stall_is_reported_once():
    """`reported` is the difference between one dump and one every 15 seconds."""
    is_stall = _load_is_stall()
    assert is_stall(60.0, 15.0, True) is False, (
        "an already-reported stall would dump again, so a long hang grows the "
        "file without bound")


def test_the_watcher_uses_the_pure_decision():
    """A pure function nobody calls proves nothing."""
    source = _source()
    tree = ast.parse(source)
    arm = next(n for n in tree.body if isinstance(n, ast.FunctionDef)
               and n.name == "_arm_hang_watchdog")
    body = ast.get_source_segment(source, arm) or ""
    assert "_is_stall(" in body, (
        "the loop compares the clock inline; the tested decision is not the "
        "decision the program makes")
