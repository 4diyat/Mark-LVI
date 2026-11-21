"""Launch, summon, dismiss — what the interface IS, as opposed to what it draws.

WHY THIS IS NOT ON `JarvisUI`
    It was, for about 200 lines, and `tests/test_ui_split.py` refused it:
    `ui/window.py` has a ceiling because it was already 7,504 lines once and the
    split exists to stop that happening again. Raising the ceiling for new code
    is the one thing the rule is there to prevent, so the ceiling stayed and the
    code moved.

    These functions take the `JarvisUI` instance (called `shell` here) and use
    only four things from it: `_win`, `_tray`, `_ambient`, `_app`. That is not a
    coincidence — it is the whole surface this concern has, which is why it can
    live in a file of its own and be read without the other 4,000 lines.

WHAT LIVES HERE
    Starting in one of the two modes, and moving between them afterwards:
    summon, dismiss, the toggle a shortcut drives, and the five things the tray
    menu can ask for. `JarvisUI` keeps thin methods that delegate here, so every
    caller — `main.py`, plugins, `ui/__init__` — is unaffected.

THE ONE RULE THAT MATTERS
    An interface the user cannot reach is worse than a window. Every function
    here that could hide something first checks that there is somewhere else to
    get back from, and says so rather than pretending when there is not.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:                                   # pragma: no cover
    from ui.window import JarvisUI


def start_interface(shell: "JarvisUI") -> None:
    """Pick a mode, then either fill the screen or go to the tray.

    A FAILED TRAY IS NOT AN ERROR STATE, IT IS A REASON TO SHOW THE WINDOW.
        Ambient mode with no notification area would leave an assistant the
        user cannot see, reach or quit — a process to be hunted down in Task
        Manager. If the icon cannot be created, the window is shown instead and
        the reason is logged. The mode degrades; it never becomes a ghost.
    """
    mode = "hud"
    try:
        from memory.config_manager import get_ui_mode
        mode = get_ui_mode()
    except Exception:                               # noqa: BLE001
        mode = "hud"

    # FIRST RUN OUTRANKS THE MODE.
    #
    # The setup screen (API key) is an overlay INSIDE the window. In ambient
    # mode the window is not shown, so that overlay would be invisible, the key
    # could never be entered, and `main.py`'s `wait_for_api_key` loop would wait
    # forever behind a tray icon. Nothing about that is recoverable by the user
    # — they would see a tray icon and an assistant that never answers.
    #
    # So a configuration that cannot start a session always gets the window,
    # whatever `ui_mode` says. The mode takes effect from the next launch, once
    # there is something to run headlessly.
    if mode != "ambient" or not getattr(shell._win, "_ready", False):
        shell._win.showFullScreen()
        return

    if start_tray(shell):
        shell._ambient = True
        return
    shell._win.showFullScreen()


def start_tray(shell: "JarvisUI") -> bool:
    """Create the notification-area icon. False if this desktop has none."""
    from ui.tray import TrayIcon, icon_path

    try:
        from ui.icons import build_jarvis_icon
        ico = icon_path()
        if not ico.exists():
            build_jarvis_icon(ico)
    except Exception:                               # noqa: BLE001
        # The icon is drawn on demand; a machine without Pillow gets Qt's
        # default instead. Not a reason to give up the tray.
        ico = None

    tray = TrayIcon({
        "show": lambda: summon(shell),
        "wake": lambda: request_wake(shell),
        "sleep": lambda: request_sleep(shell),
        "settings": lambda: summon_settings(shell),
        "quit": lambda: quit_app(shell),
    }, app=shell._app)
    if not tray.start():
        # Reported, not swallowed: "the mode you asked for could not be given"
        # is exactly the kind of thing a log is for.
        note(shell, f"Ambient mode unavailable ({tray.error}); showing the window.")
        return False
    shell._tray = tray
    return True


# ── summon / dismiss ──────────────────────────────────────────────────────

def summon(shell: "JarvisUI") -> None:
    """Bring the interface up — from the tray, a shortcut, or the caller.

    Maximised rather than full screen. The old launch filled the screen, which
    is right for the full-screen HUD but wrong for a window you asked for on
    purpose: full screen hides the desktop the user was working on and takes an
    extra gesture to get out of. F11 still switches to full screen for anyone
    who wants it — see `MainWindow._toggle_fullscreen`.
    """
    if shell._win.isFullScreen():
        shell._win.showFullScreen()
    else:
        shell._win.showMaximized()
    try:
        shell._win.raise_()
        shell._win.activateWindow()
    except Exception as e:                          # noqa: BLE001
        # Some window managers refuse these. The window is already shown, which
        # is the part that matters — but a summon that came up BEHIND another
        # window looks like nothing happened, so it is worth a line.
        note(shell, f"could not raise the window — {type(e).__name__}: {e}")
    shell._ambient = False


def dismiss(shell: "JarvisUI") -> None:
    """Send the interface back to the tray, if the tray can hold it.

    Refuses when there is no tray: hiding the only surface would leave the
    process unreachable. A user who wants the window gone in that situation
    closes it, which ends the program.
    """
    if getattr(shell, "_tray", None) is None:
        return
    shell._win.hide()
    shell._ambient = True


def toggle_interface(shell: "JarvisUI") -> None:
    """What the in-window shortcut calls."""
    if shell._win.isVisible():
        dismiss(shell)
    else:
        summon(shell)


def set_interface_mode(shell: "JarvisUI", mode: str) -> bool:
    """Switch between the full-screen HUD and ambient mode.

    Returns False when the requested mode is not something this machine can
    actually deliver — no notification area, or an ordinary window that cannot
    hold itself open. Reported rather than accepted-and-ignored, because a saved
    setting that quietly does nothing is a setting the user will re-toggle
    forever.
    """
    from memory.config_manager import save_ui_mode

    mode = str(mode or "").strip().lower()
    if mode == "hud":
        if getattr(shell, "_tray", None) is not None:
            shell._tray.stop()
            shell._tray = None
        shell._win.showFullScreen()
        shell._ambient = False
        save_ui_mode("hud")
        return True
    if mode != "ambient":
        return False
    if getattr(shell, "_tray", None) is None and not start_tray(shell):
        return False
    shell._win.hide()
    shell._ambient = True
    save_ui_mode("ambient")
    return True


# ── what the tray menu asks for ───────────────────────────────────────────

def request_wake(shell: "JarvisUI") -> None:
    """Tray menu: wake the assistant without a word."""
    cb = getattr(shell._win, "on_wake_manual", None)
    if cb is None:
        return
    try:
        cb()
    except Exception as e:                          # noqa: BLE001
        note(shell, f"wake failed — {type(e).__name__}: {e}")


def request_sleep(shell: "JarvisUI") -> None:
    """Tray menu: stand the assistant down.

    `on_wake_manual` is a toggle in the window, so this only acts when it would
    move the state in the direction the menu item promises. A "Go to sleep" that
    sometimes wakes it up would be worse than no item at all.
    """
    btn = getattr(shell._win, "_wake_btn", None)
    try:
        awake = bool(btn.isChecked()) if btn is not None else None
    except Exception:                               # noqa: BLE001
        awake = None
    if awake is False:
        return
    cb = getattr(shell._win, "on_wake_manual", None)
    if cb is None:
        return
    try:
        cb()
    except Exception as e:                          # noqa: BLE001
        note(shell, f"sleep failed — {type(e).__name__}: {e}")


def summon_settings(shell: "JarvisUI") -> None:
    """Tray menu: show the interface with the SETTINGS drawer open."""
    summon(shell)
    # The drawer opens by checking its own button, so that is what is driven —
    # the same path a click takes. Calling the handler directly would leave the
    # button unchecked, and the next click would then close a drawer the button
    # believed was already shut.
    btn = getattr(shell._win, "_drawer_btn", None)
    if btn is None:
        return
    try:
        if not btn.isChecked():
            btn.setChecked(True)
            shell._win._toggle_drawer(True)
    except Exception as e:                          # noqa: BLE001
        note(shell, f"could not open settings — {type(e).__name__}: {e}")


def quit_app(shell: "JarvisUI") -> None:
    """Tray menu: end the program.

    `close()` on the window runs its `closeEvent`, which asks about unsaved
    documents — the same guard as clicking the X. Quitting from the tray must
    not be a way around that.
    """
    try:
        shell._win.close()
    finally:
        tray = getattr(shell, "_tray", None)
        if tray is not None:
            tray.stop()
            shell._tray = None


def note(shell: "JarvisUI", text: str) -> None:
    """Record a survived failure where somebody can see it.

    The tray is the surface for a windowless app, so a menu item that silently
    did nothing looks exactly like one that worked.
    """
    line = f"SYS: {text}"
    try:
        shell._win.write_log(line)
        return
    except Exception as e:                          # noqa: BLE001
        first = f"{type(e).__name__}: {e}"
    try:
        shell._win._log_sig.emit(line)
    except Exception as e:                          # noqa: BLE001
        # Both routes are gone; stdout is the last one. The first failure is
        # included because "write_log raised" is itself the interesting part
        # when the log is what is broken.
        print(f"[JARVIS] {line} (log unavailable — {first}; "
              f"signal unavailable — {type(e).__name__}: {e})")
