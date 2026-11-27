"""The one door where a background thread hands work to Qt.

WHY THIS IS A MODULE AND NOT TWO METHODS ON THE SHELL
    `main.py` calls `shell.set_state` and `shell.write_log` from the asyncio
    runner thread — seventeen and forty-eight call sites — and the audio
    threads call `set_audio_level` twenty times a second. Every one of those
    ends at a `QWidget`, a `QSystemTrayIcon` or `canvas.update()`.

    Qt owns one event dispatcher per thread and it is not re-entrant. Touching
    a widget from a thread that does not pump that dispatcher is undefined
    behaviour; on Windows it presents as a window that is painted and will not
    answer, because the dispatcher's queue is being drained by a thread that is
    not the one the platform is delivering events to. That is the reported
    hang, and the fix is not a smaller paint — it is that the call never
    crosses the boundary.

WHAT THE RULE ACTUALLY IS
    * already on the Qt thread → run inline. Queuing and waiting would be a
      deadlock with one participant, and queuing without waiting would reorder
      a fast NO MIC → LISTENING pair so the wrong word stayed on screen;
    * anywhere else → a queued signal to a QObject created on the Qt thread.
      A timer created on a Python worker has no Qt event loop to deliver it;
    * no Qt at all → run inline. A headless test and a broken install both get
      here, and "no Qt" is a normal state in this codebase. The surface's own
      guard decides what to do with the call.

WHY IT MUST NOT GROW A WAIT
    Nothing in this file blocks. A background thread that waits for the Qt
    thread while the Qt thread waits for that background thread is the hang
    this module exists to prevent, and it is one `join()` away at all times.
"""
from __future__ import annotations

import threading


# Created on the Qt thread, after QApplication. Unlike QTimer.singleShot called
# from a Python worker (which has no Qt event loop), this signal has a receiver
# with main-thread affinity and is delivered by that receiver's event loop.
_dispatcher = None


def init_dispatcher() -> None:
    global _dispatcher
    if _dispatcher is not None:
        return
    try:
        from PyQt6.QtCore import QCoreApplication, QObject, Qt, pyqtSignal, pyqtSlot
        if QCoreApplication.instance() is None:
            return

        class Dispatcher(QObject):
            queued = pyqtSignal(object)

            def __init__(self):
                super().__init__()
                self.queued.connect(self.execute, Qt.ConnectionType.QueuedConnection)

            @pyqtSlot(object)
            def execute(self, work):
                try:
                    work()
                except Exception as exc:  # noqa: BLE001
                    print(f"[JARVIS] Qt dispatch failed: {type(exc).__name__}: {exc}")

        _dispatcher = Dispatcher()
    except Exception as exc:  # noqa: BLE001
        print(f"[JARVIS] Qt dispatcher unavailable: {type(exc).__name__}: {exc}")


def is_qt_thread(owner: int | None) -> bool:
    """Whether the caller is the thread that owns the widgets.

    `owner` is stamped when the owning object is built. `None` — an object
    assembled by `__new__` in a test, or a process with no Qt — means "every
    thread", and the wrapper collapses to a direct call.
    """
    if owner is None:
        return True
    return threading.get_ident() == owner


def run_on_qt_thread(owner: int | None, work) -> None:
    """Run `work` on the Qt thread. Never blocks, never raises, never waits.

    With an initialized dispatcher, the work is always queued to its Qt
    receiver. A missing Qt installation retains the headless fallback.
    """
    if is_qt_thread(owner):
        work()
        return
    if _dispatcher is not None:
        try:
            _dispatcher.queued.emit(work)
        except RuntimeError as exc:
            print(f"[JARVIS] Qt dispatcher stopped: {exc}")
        return
    try:
        from PyQt6.QtCore import QTimer
    except Exception:                              # noqa: BLE001
        work()
        return
    try:
        QTimer.singleShot(0, work)
    except Exception:                              # noqa: BLE001
        work()


def set_audio_level(shell, level: float) -> None:
    """Push a live level to the surfaces that show it. Called 20×/second.

    FROM THE AUDIO THREADS, SO IT IS MARSHALLED. It used to call
    `canvas.update()` on the orb directly — a Qt call on a foreign thread, for
    the reason this module exists. The float needs no lock: a plain assignment
    is atomic under the GIL, and the orb clamps what it is given because Qt
    refuses a gradient stop outside 0..1 and the failure shows up as a plain
    ring.

    NO QUEUE GROWTH. Twenty of these a second would be twenty queued lambdas a
    second behind a dispatcher that may be busy, and only the last one matters.
    `_pending_level` keeps the newest value and at most one flush is in flight.
    """
    shell._pending_level = float(level)
    if shell._level_flush_queued:
        return
    shell._level_flush_queued = True
    run_on_qt_thread(shell._ui_thread_id, lambda: _flush_level(shell))


def _flush_level(shell) -> None:
    """Paint the newest level. Qt thread only, at most one in flight."""
    shell._level_flush_queued = False
    level = shell._pending_level
    for attr in ("_orb", "_bubble", "_main_surface", "_voice_overlay"):
        target = getattr(shell, attr, None)
        callback = getattr(target, "set_audio_level", None)
        if callback is None:
            continue
        try:
            callback(level)
        except Exception:                          # noqa: BLE001
            # Cosmetic and 20×/second: a line per frame would be the problem,
            # not the report. Once per process is enough to find out the orb is
            # broken without writing 20 lines a second.
            from ui.shell import _note_once
            _note_once("audio-level", "the orb cannot show the audio level")


def push_visemes(shell, frames, hop: float, at: float) -> None:
    """Mouth frames for the face, if there is a face.

    MARSHALLED FOR THE SAME REASON as `set_audio_level`, but NOT throttled:
    mouth frames are ordered data, and dropping the middle of a sentence's
    visemes is a mouth that moves in the wrong places. The caller already sends
    them at hop intervals rather than per sample.
    """
    if getattr(shell, "_bubble", None) is None:
        return
    run_on_qt_thread(shell._ui_thread_id,
                     lambda: _apply_visemes(shell, frames, hop, at))


def _apply_visemes(shell, frames, hop: float, at: float) -> None:
    """Qt thread only."""
    callback = getattr(shell._bubble, "push_visemes", None)
    if callback is None:
        return
    try:
        callback(frames, hop, at)
    except Exception:                              # noqa: BLE001
        from ui.shell import _note_once
        _note_once("visemes", "the face cannot animate the mouth")
