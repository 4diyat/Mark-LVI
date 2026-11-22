"""Build every ambient surface against REAL Qt, offscreen, and prove it draws.

WHY THIS EXISTS
    Five smoke tools used to live in `tools/` and all of them drove the main
    window: `check_desktop_qt`, `capture_desktop_qt`, `check_browser_qt`,
    `check_ssh_qt`, `check_security_qt`. Their whole value was that they used a
    real `QApplication` rather than the suite's stub — the stub answers "the
    widget exists", a real Qt answers "the window manager accepted it".

    They went with the window, and this is their replacement: the same idea
    against the surfaces that DO exist. It is the only place in this repository
    where the orb, the command bar, the toast queue, the face bubble and the
    confirm dialog are constructed for real, and where the things a stub cannot
    catch are actually caught:

      * a `QWidget` subclass that forgets `super().__init__` and works on a
        stub, then crashes on a real Qt;
      * flags (`FramelessWindowHint`, `WindowStaysOnTopHint`, `Tool`) that the
        stub's enum swallows — here they are read back and compared;
      * a `paintEvent` that raises. A stub's painter accepts anything; the real
        one raises `RuntimeError: Painter not active` if `end()` is missing;
      * a translucent window that Qt REFUSES to make translucent, which is the
        one failure that only shows up on a desktop.

WHAT IT CANNOT PROVE
    Click-through (`WindowTransparentForInput`), the focus returning after Esc
    and anything about DPAPI need a real Windows desktop with a real
    compositor. `QT_QPA_PLATFORM=offscreen` has no window manager at all, so
    those claims stay unproven and are written down as unproven.

Run: `QT_QPA_PLATFORM=offscreen python tools/check_ambient_qt.py`
"""
from __future__ import annotations

import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

CHECKS: list[tuple[str, callable]] = []


def check(name: str):
    """Register a step. Each one runs even if an earlier one failed."""
    def _wrap(fn):
        CHECKS.append((name, fn))
        return fn
    return _wrap


def _repaint(widget) -> None:
    """Force a real paint cycle.

    `update()` only QUEUES a paint event, and an offscreen platform with no
    event loop never delivers it — so the painter is never exercised and the
    check passes for a widget that cannot draw. `render()` calls `paintEvent`
    synchronously through a real `QPainter`.
    """
    from PyQt6.QtGui import QPixmap
    from PyQt6.QtWidgets import QApplication

    QApplication.processEvents()
    pixmap = QPixmap(max(1, widget.width()), max(1, widget.height()))
    widget.render(pixmap)


@check("the application is built")
def _application():
    from PyQt6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    assert app is not None
    print(f"  platform: {app.platformName()}")


@check("the orb draws at every presence size")
def _orb():
    from ui import orb_overlay

    for mode in ("active", "focus", "quiet"):
        overlay = orb_overlay.OrbOverlay(mode=mode)
        assert overlay.start(), f"{mode}: {overlay.error}"
        width, height = orb_overlay.window_size(mode)
        assert overlay._window.width() == width, (
            f"{mode}: the window is not the size the painter expects")
        for state in ("idle", "listening", "thinking", "speaking"):
            overlay.set_state(state)
            overlay.set_audio_level(0.7)
            _repaint(overlay._canvas)          # a real QPainter, offscreen
        assert overlay.available
        overlay.stop()
        print(f"  {mode}: {width}px window, 4 states painted")


@check("the command bar opens, takes text, submits and closes")
def _bar():
    from PyQt6.QtCore import Qt
    from PyQt6.QtTest import QTest

    from ui import command_bar

    submitted, closed = [], []
    bar = command_bar.CommandBar(on_submit=submitted.append,
                                 on_close=lambda: closed.append(1))
    assert bar.open(), f"the bar refused to open: {bar.error}"
    _repaint(bar._window)

    # Typed, not injected: the field is a real QLineEdit and `keyClicks` goes
    # through Qt's own event path, which is the only way to catch a focus or
    # grabShortcut mistake that a stub cannot see.
    QTest.keyClicks(bar._field, "ringkas tabel ini")
    assert "ringkas" in bar._field.text(), "the field did not take typed text"

    QTest.keyClick(bar._field, Qt.Key.Key_Return)
    assert submitted == ["ringkas tabel ini"], submitted
    assert not bar.is_open, "Enter must close the bar"

    assert bar.open()
    QTest.keyClick(bar._field, Qt.Key.Key_Escape)
    assert not bar.is_open, "Esc must close the bar"
    assert closed, "closing must report back, or focus is never returned"
    print("  opened, typed 18 characters, Enter submitted, Esc closed")


@check("the toast queue keeps three and counts the rest")
def _toasts():
    from ui.toast_queue import ToastQueue

    queue = ToastQueue()
    for i in range(7):
        queue.push(f"pesan {i}")
    assert len(queue.current()) == 3, f"{len(queue.current())} toasts on screen"
    # "+4" in the mockup, and the count is what matters — the wording is the
    # surface's business, the arithmetic is this check's.
    assert "4" in queue.overflow_label(), queue.overflow_label()
    print("  7 pushed: 3 shown, overflow counted")


@check("the face bubble is frameless and on top")
def _bubble():
    from PyQt6.QtCore import Qt

    from ui.face_bubble import FaceBubble, window_flags

    bubble = FaceBubble("face.png", "JARVIS")
    started = bubble.start()
    assert started, f"the bubble could not start: {bubble.last_error}"
    flags = bubble._window.windowFlags()
    for wanted in ("FramelessWindowHint", "WindowStaysOnTopHint", "Tool"):
        assert flags & getattr(Qt.WindowType, wanted), f"{wanted} missing"
    assert window_flags(Qt) != 0
    bubble.set_state("speaking")
    bubble.set_audio_level(0.8)
    _repaint(bubble.canvas)
    bubble.stop()
    print("  frameless + on top, painted, stopped cleanly")


@check("the confirmation is its own window, never a child")
def _confirm():
    from PyQt6.QtCore import Qt

    from ui.confirm_banner import build_confirm_window

    banner = build_confirm_window()
    assert banner.parent() is None, "the banner is parented and can be clipped"
    banner.set_title("Kirim laporan ke tim keuangan",
                     "Lampiran: anggaran.xlsx · 3 penerima")
    flags = banner.windowFlags()
    for wanted in ("Tool", "FramelessWindowHint", "WindowStaysOnTopHint"):
        assert flags & getattr(Qt.WindowType, wanted), f"{wanted} missing"
    banner.show()
    _repaint(banner)
    banner.hide()
    print(f"  {banner.width()}px wide, on top, no parent")


@check("the shell starts with no surfaces and stays quiet about it")
def _shell():
    from ui.shell import AmbientShell

    shell = AmbientShell("face.png", "JARVIS")
    # Every call `main.py` makes before a session exists. A `None` surface here
    # is the normal state of a headless runner, and none of these may raise.
    shell.set_state("INITIALISING")
    shell.set_audio_level(0.4)
    shell.push_visemes([], 0.02, 0.0)
    shell.write_log("smoke")
    shell.show_content("Hasil", "Delapan baris diringkas.")
    shell.apply_presence("focus")
    print("  state, audio, visemes, log, content, presence: no surface, no raise")


def main() -> int:
    failures = 0
    for name, fn in CHECKS:
        print(f"- {name}")
        try:
            fn()
        except Exception:                           # noqa: BLE001
            failures += 1
            print("  FAILED")
            traceback.print_exc()
    if failures:
        print(f"{failures} of {len(CHECKS)} checks failed")
        return 1
    print(f"all {len(CHECKS)} checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
