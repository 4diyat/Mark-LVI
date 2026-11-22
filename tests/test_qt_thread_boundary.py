"""No widget may be touched from the thread that does not own it.

WHY THIS FILE EXISTS
    `main.py` calls `shell.set_state` from the asyncio runner thread — seventeen
    call sites, including the microphone recovery loop every two seconds — and
    `set_audio_level` from the audio threads twenty times a second. Until this
    change those calls went straight into `QSystemTrayIcon.setToolTip`,
    `QWidget.update()` and the orb's `_repaint()`.

    Qt has one event dispatcher per thread and it is not re-entrant. Touching a
    widget from a foreign thread is undefined behaviour; on Windows it presents
    as a window that is painted and will not answer, because the dispatcher's
    queue is being drained by a thread the platform is not delivering events
    to. That is the reported hang, and it is not fixed by painting less.

WHAT IS PROVEN HERE
    The rule, and that the shell uses it:
      * on the Qt thread → inline, because queuing and waiting deadlocks with
        one participant and queuing without waiting reorders the states;
      * from another thread → posted as a queued call, never run in place;
      * with no Qt at all → inline, because "no Qt" is normal here;
      * the level push coalesces, so a 20 Hz signal cannot grow the queue.

    Not proven: that a real Windows Qt thread was the thing hanging. Qt cannot
    run in this sandbox. What is proven is that the call no longer crosses the
    boundary, which is the condition that produced it.
"""
from __future__ import annotations

import sys
import threading
import types
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from ui import qt_thread  # noqa: E402


# ── the rule, on its own ─────────────────────────────────────────────────────

def test_the_qt_thread_runs_its_own_work_inline():
    """Not an optimisation: queuing here would deadlock or reorder.

    QT IS PRESENT FOR THIS TEST ON PURPOSE. Without it the function falls into
    its no-Qt path and passes for the wrong reason — a mutation that removed
    the inline rule survived the first version of this file because of exactly
    that.
    """
    posted, ran = [], []

    class _Timer:
        @staticmethod
        def singleShot(_ms, work):
            posted.append(work)

    sys.modules["PyQt6"] = types.ModuleType("PyQt6")
    core = types.ModuleType("PyQt6.QtCore")
    core.QTimer = _Timer
    sys.modules["PyQt6.QtCore"] = core
    try:
        qt_thread.run_on_qt_thread(threading.get_ident(),
                                   lambda: ran.append("in"))
        assert ran == ["in"], (
            "work from the Qt thread was queued instead of run: a caller that "
            "waits for its own queue is a deadlock, and one that does not "
            "reorders NO MIC → LISTENING so the wrong word stays on screen")
        assert posted == [], "the Qt thread posted to itself"
    finally:
        sys.modules.pop("PyQt6", None)
        sys.modules.pop("PyQt6.QtCore", None)


def test_a_foreign_thread_never_runs_widget_work_in_place():
    """THE WHOLE POINT. This is the call that used to freeze the dispatcher."""
    posted, ran = [], []

    class _Timer:
        @staticmethod
        def singleShot(_ms, work):
            posted.append(work)          # queued, NOT called

    sys.modules["PyQt6"] = types.ModuleType("PyQt6")
    core = types.ModuleType("PyQt6.QtCore")
    core.QTimer = _Timer
    sys.modules["PyQt6.QtCore"] = core
    try:
        qt_thread.run_on_qt_thread(0, lambda: ran.append("painted"))
        assert ran == [], (
            "widget work ran on the calling thread; on Windows that is the "
            "undefined behaviour behind a painted window that answers nothing")
        assert len(posted) == 1, "the work was dropped instead of queued"
        posted[0]()                       # the Qt loop would run it
        assert ran == ["painted"]
    finally:
        sys.modules.pop("PyQt6", None)
        sys.modules.pop("PyQt6.QtCore", None)


def test_without_qt_the_call_still_happens():
    """A headless test and a broken install both get here. Dropping the state
    would leave the surfaces permanently showing the first word."""
    sys.modules.pop("PyQt6", None)
    ran = []
    for name in ("PyQt6.QtCore",):
        sys.modules.pop(name, None)
    qt_thread.run_on_qt_thread(0, lambda: ran.append("kept"))
    assert ran == ["kept"]


def test_a_posted_call_that_raises_does_not_escape():
    """Qt tearing down during shutdown must not turn a status change into an
    exception on an audio callback."""
    class _Timer:
        @staticmethod
        def singleShot(_ms, _work):
            raise RuntimeError("QApplication is gone")

    sys.modules["PyQt6"] = types.ModuleType("PyQt6")
    core = types.ModuleType("PyQt6.QtCore")
    core.QTimer = _Timer
    sys.modules["PyQt6.QtCore"] = core
    ran = []
    try:
        qt_thread.run_on_qt_thread(0, lambda: ran.append("fallback"))
        assert ran == ["fallback"], "the call was lost instead of run inline"
    finally:
        sys.modules.pop("PyQt6", None)
        sys.modules.pop("PyQt6.QtCore", None)


def test_an_object_with_no_owner_treats_every_thread_as_the_qt_thread():
    """`__new__`-built shells in tests, and processes with no Qt, have no owner.
    Raising there would be a crash inside a status update."""
    assert qt_thread.is_qt_thread(None) is True


# ── the shell actually uses it ───────────────────────────────────────────────

def _shell():
    from ui.shell import AmbientShell

    shell = AmbientShell.__new__(AmbientShell)
    touched = []

    class Surface:
        def set_state(self, word):
            touched.append(("state", word, threading.current_thread().name))

        def set_audio_level(self, level):
            touched.append(("level", level, threading.current_thread().name))

    shell._tray = shell._bubble = shell._orb = Surface()
    shell._state = ""
    shell._notifier = None
    shell._last_answer = ""
    shell._toaster = None
    shell._pending_level = 0.0
    shell._level_flush_queued = False
    return shell, touched


def test_set_state_from_the_runner_thread_paints_nothing_until_qt_runs_it():
    """Drive the real `AmbientShell.set_state` off its own thread."""
    shell, touched = _shell()
    shell._ui_thread_id = threading.get_ident()      # "Qt" is this thread
    posted = []

    class _Timer:
        @staticmethod
        def singleShot(_ms, work):
            posted.append(work)

    sys.modules["PyQt6"] = types.ModuleType("PyQt6")
    core = types.ModuleType("PyQt6.QtCore")
    core.QTimer = _Timer
    sys.modules["PyQt6.QtCore"] = core
    try:
        shell._announce = lambda _w: None            # no notification policy here
        worker = threading.Thread(target=shell.set_state, args=("LISTENING",))
        worker.start()
        worker.join()
        assert touched == [], (
            "the runner thread painted the tray, the face and the orb itself")
        assert len(posted) == 1, "the state was dropped instead of queued"
        posted[0]()                                  # the Qt loop runs it
        assert [t[1] for t in touched] == ["listening"] * 3
    finally:
        sys.modules.pop("PyQt6", None)
        sys.modules.pop("PyQt6.QtCore", None)


def test_the_audio_level_coalesces_instead_of_queueing_twenty_times_a_second():
    """20 Hz of queued lambdas behind a busy dispatcher is a backlog that grows
    without bound and repaints stale levels when it drains."""
    shell, touched = _shell()
    shell._ui_thread_id = threading.get_ident()
    posted = []

    class _Timer:
        @staticmethod
        def singleShot(_ms, work):
            posted.append(work)

    sys.modules["PyQt6"] = types.ModuleType("PyQt6")
    core = types.ModuleType("PyQt6.QtCore")
    core.QTimer = _Timer
    sys.modules["PyQt6.QtCore"] = core
    try:
        worker = threading.Thread(
            target=lambda: [shell.set_audio_level(i / 100) for i in range(20)])
        worker.start()
        worker.join()
        assert len(posted) == 1, f"twenty levels queued {len(posted)} flushes"
        posted[0]()
        levels = [t[1] for t in touched if t[0] == "level"]
        assert levels and levels[0] == pytest.approx(0.19), (
            "the flush painted an old level instead of the newest one")
    finally:
        sys.modules.pop("PyQt6", None)
        sys.modules.pop("PyQt6.QtCore", None)


def test_write_log_from_the_audio_thread_paints_nothing_until_qt_runs_it():
    """`write_log` is called from the audio thread, the runner thread and the
    process reader — 48 call sites — and it feeds the full-screen exchange and
    the toast stack. Both are widgets."""
    shell, _touched = _shell()
    shell._ui_thread_id = threading.get_ident()
    reached = []

    class _Toaster:
        def push(self, text):
            reached.append(("toast", text, threading.current_thread().name))

    shell._toaster = _Toaster()
    posted = []

    class _Timer:
        @staticmethod
        def singleShot(_ms, work):
            posted.append(work)

    sys.modules["PyQt6"] = types.ModuleType("PyQt6")
    core = types.ModuleType("PyQt6.QtCore")
    core.QTimer = _Timer
    sys.modules["PyQt6.QtCore"] = core
    try:
        worker = threading.Thread(target=shell.write_log, args=("Halo.",))
        worker.start()
        worker.join()
        assert reached == [], (
            "the toast was built from the calling thread instead of the one "
            "that owns it")
        assert len(posted) == 1, "the line never reached the surface half"
        posted[0]()
        assert [r[1] for r in reached] == ["Halo."]
    finally:
        sys.modules.pop("PyQt6", None)
        sys.modules.pop("PyQt6.QtCore", None)
