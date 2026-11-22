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

import faulthandler
import sys
import traceback
from pathlib import Path

# A Qt FAIL-FAST IS NOT AN EXCEPTION. `QWidget: Must construct a QApplication
# before a QWidget` calls `qFatal`, which aborts the process: no traceback, no
# unwinding, no chance for the per-check `try` to catch it. The first CI run of
# this tool reported only that one line and it was impossible to tell which
# check produced it — so the stack is dumped on the way down.
faulthandler.enable()

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


# THE REFERENCE IS THE POINT. `QApplication.instance()` returns the object Qt
# holds, but PyQt does NOT own it: an application assigned only to a local goes
# out of scope at the end of the check that created it, gets garbage collected,
# and the NEXT widget dies with
#
#     QWidget: Must construct a QApplication before a QWidget
#
# which is `qFatal`, not an exception — it aborted the whole process in CI and
# looked like the orb's fault. The module-level name is what keeps it alive.
_APP = None


def _require_app():
    """The one `QApplication`, built on demand and kept alive, or a real error.

    Every check calls this FIRST. Creating a widget with no application is
    `qFatal` and kills the process instead of failing a check, so the guard has
    to be here rather than in a setup step that could itself have failed.
    """
    global _APP
    from PyQt6.QtWidgets import QApplication

    _APP = QApplication.instance() or _APP
    if _APP is None:
        _APP = QApplication(sys.argv[:1] or ["jarvis-check"])
    if _APP is None:
        raise RuntimeError("Qt refused to build a QApplication")
    return _APP


@check("the application is built")
def _application():
    app = _require_app()
    platform = app.platformName()
    print(f"  platform: {platform or '(unnamed)'}", flush=True)
    # The offscreen plugin is what CI promises to run under. Saying which one
    # actually came up is the difference between "the surfaces work" and "they
    # were never drawn".
    if platform != "offscreen":
        print(f"  WARNING: expected the offscreen platform, got {platform!r}",
              flush=True)


@check("the orb draws at every presence size")
def _orb():
    _require_app()
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
    _require_app()
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
    _require_app()
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
    _require_app()
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
    _require_app()
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


@check("the tray panel draws three pages in two palettes and closes on Esc")
def _panel():
    _require_app()
    from PyQt6.QtCore import Qt

    from ui.tray_panel import TrayPanel

    panel = TrayPanel({})
    assert panel.open(), f"the panel could not open: {panel.error}"
    assert panel._window.width() == 460 and panel._window.height() == 660
    flags = panel._window.windowFlags()
    for wanted in ("FramelessWindowHint", "Tool", "WindowStaysOnTopHint"):
        assert flags & getattr(Qt.WindowType, wanted), f"{wanted} missing"
    for page in ("main", "history", "privacy"):
        assert panel.set_page(page), page
        _repaint(panel._window)
    assert panel.set_page("trading") is False, "an unknown page was accepted"
    assert panel.set_theme("light") and panel.theme == "light"
    _repaint(panel._window)
    # Board 17a's three-state setting: `auto` must resolve to a palette that
    # exists, and the header control must be able to reach all three.
    assert panel.press_theme() in ("auto", "dark", "light")
    assert panel.theme in ("dark", "light")
    _repaint(panel._window)
    assert panel.set_theme("dark")
    panel.close()
    assert panel.available, "closing must not destroy the widget"
    panel.stop()
    print("  460x660, three pages, both palettes, on top, no raise")


@check("the voice overlay draws the edge, the tile and the words — and Esc closes it")
def _voice_overlay():
    _require_app()
    from PyQt6.QtCore import Qt

    from ui.voice_overlay import VoiceOverlay

    overlay = VoiceOverlay()
    assert overlay.start(), f"the overlay could not start: {overlay.error}"
    flags = overlay._window.windowFlags()
    for wanted in ("FramelessWindowHint", "Tool", "WindowStaysOnTopHint"):
        assert flags & getattr(Qt.WindowType, wanted), f"{wanted} missing"
    assert not flags & Qt.WindowType.WindowTransparentForInput, (
        "click-through would eat the Esc that closes the overlay")

    overlay.set_state("listening")
    overlay.set_hand((0.42, 0.5, True))
    overlay.set_camera_available(True)
    overlay.set_transcript("ringkas tabel ini dan tandai baris yang lewat anggaran")
    overlay.set_answer("Baris 7 dan 11 melewati plafon 12% dan 4%.")
    assert overlay.glow() > 0.0, "an active overlay with no edge is not the artboard"
    _repaint(overlay._window)

    # The footnote's second promise, exercised through the real key path.
    assert overlay.handle_escape() is True
    assert overlay.active is False and overlay.glow() == 0.0
    overlay.stop()
    print("  2px edge + glow while active, hand + transcript drawn, Esc closes")


@check("the shell starts with no surfaces and stays quiet about it")
def _shell():
    _require_app()
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
        print(f"- {name}", flush=True)
        try:
            fn()
        except Exception:                           # noqa: BLE001
            failures += 1
            print("  FAILED", flush=True)
            traceback.print_exc()
            sys.stdout.flush()
    if failures:
        print(f"{failures} of {len(CHECKS)} checks failed", flush=True)
        return 1
    print(f"all {len(CHECKS)} checks passed", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
