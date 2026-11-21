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


def watch_for_another_launch(shell: "JarvisUI", interval_ms: int = 800) -> None:
    """Summon the window when a SECOND copy of the app was started and exited.

    `core/single_instance.py` makes a second launch a request — "come to the
    front" — written to a small file, rather than a second assistant holding
    the microphone. This is the other half of that: a timer on the Qt thread
    that notices the request.

    A timer rather than a socket for the reason given in that module: the
    asking process may be anything, on any of three platforms, and may already
    be gone. Polling a file costs one `exists()` every 800 ms and cannot fail
    in a way that keeps a request from being answered.

    Nothing here is started in HUD mode — the window is already on screen, and
    a request to bring it forward has nothing to do.
    """
    try:
        from PyQt6.QtCore import QTimer
        from core import single_instance
    except Exception:                               # noqa: BLE001
        return

    timer = QTimer(shell._win)
    timer.setInterval(interval_ms)

    def _check() -> None:
        try:
            request = single_instance.take_foreground_request()
            if request is None:
                return
            summon(shell)
            text = request.get("text") or ""
            if text:
                # The link said something. Delivered through the same door as a
                # typed message — `run_deeplink` owns that, and reusing it keeps
                # one place where "say this" is defined.
                _deliver_text(shell, text)
        except Exception as e:                      # noqa: BLE001
            # A poll that raises would stop the timer's usefulness silently.
            # Reported once, then the timer is left to try again.
            note(shell, f"could not answer a second launch — {type(e).__name__}: {e}")

    # `timer.timeout` is a SIGNAL on a real QTimer, not a method: it is bound
    # here for the same reason the tray binds `activated` — a stub that returns
    # a signal from a call would hide the difference, and this is the one line
    # where Qt's API shape matters.
    timer.timeout.connect(_check)
    timer.start()
    shell._launch_watch = timer


def _deliver_text(shell: "JarvisUI", text: str) -> bool:
    """Say something into the session, on a thread. False when there is none.

    One function, because there are now two ways to arrive here — a link at
    launch and a link sent to a copy that was already running — and two copies
    of "how to talk to the session" is how they drift apart.
    """
    send = getattr(shell, "on_text_command", None)
    if not callable(send):
        note(shell, "A link tried to send a message before the session was ready.")
        return False
    try:
        import threading
        # On a thread, exactly as a typed message is: the caller is a Qt slot
        # and the send blocks on the session.
        threading.Thread(target=send, args=(text,), daemon=True).start()
        return True
    except Exception as e:                          # noqa: BLE001
        note(shell, f"could not deliver a link — {type(e).__name__}: {e}")
        return False


def run_deeplink(shell: "JarvisUI") -> bool:
    """Act on the `jarvis://` link this launch was started with, if any.

    Called once, after the interface exists. Returns whether a link was
    delivered — which is what lets a launch that was started BY a link exit
    with a status somebody can read (a shell alias, a script, a launcher).

    THE THREE HANDLERS ARE THE POINT
        `summon` and `hide` are the tray's own two actions, so a link can do
        nothing a person at the keyboard could not. `ask` hands text to the
        session as a user turn — the same entry point a typed message takes —
        and only if the session exists. Every other verb is refused in
        `core/deeplink.py` before this function is ever reached; there is no
        branch here that could be talked into running something else.
    """
    launch = getattr(shell, "_launch", None)
    link = getattr(launch, "link", None)
    error = getattr(launch, "link_error", "") or ""
    if not link and not error:
        return False

    if error:
        # Said out loud rather than swallowed: the user clicked something and
        # it did not work, and the alternative is a link that fails silently.
        note(shell, f"A link was refused — {error}")
        return False

    from core import deeplink
    try:
        delivered = deeplink.dispatch(link, summon=lambda: summon(shell),
                                      hide=lambda: dismiss(shell),
                                      ask=lambda text: _deliver_text(shell, text))
    except Exception as e:                          # noqa: BLE001
        note(shell, f"a link failed — {type(e).__name__}: {e}")
        return False
    note(shell, f"Link: {link.verb}" + (f" — {link.text[:60]}" if link.text else ""))
    return delivered


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

    # WHAT THE LAUNCH ITSELF ASKED FOR, and why it can outrank the saved mode
    # only in one direction.
    #
    #     `--hidden` is the login entry talking: start in the tray, whatever the
    #     user's saved mode is. That is a DOWNGRADE of visibility and it is safe
    #     in every case the mode already handles, because everything below
    #     (first run, no tray) still refuses to leave the user with no surface.
    #
    #     `--show` is a shortcut meaning "come and talk to me", which is an
    #     upgrade and is therefore just the ordinary path — it cannot ask for
    #     anything the mode does not already give.
    launch = getattr(shell, "_launch", None)
    if getattr(launch, "hidden", False):
        mode = "ambient"

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
    # A LINK IS AN INSTRUCTION TO THE RUNNING APP, so it is answered before the
    # mode is chosen: `jarvis://hide` on an ambient install must not be turned
    # into a window just because the saved mode is hud.
    if getattr(getattr(shell, "_launch", None), "link", None) is not None:
        run_deeplink(shell)

    if mode == "hud" or not getattr(shell._win, "_ready", False):
        shell._win.showFullScreen()
        # `--show` on a HUD install: the window is up, and asking for it to be
        # in front is the same call the tray makes when the user clicks Show.
        if getattr(launch, "force_window", False):
            raise_window(shell)
        return

    # Ambient (or bubble): the window may be hidden, so a second launch is
    # answered here. Started BEFORE the tray falls back to the window, because
    # the fallback still leaves the app running as the one instance.
    watch_for_another_launch(shell)

    if not start_tray(shell):
        # No notification area: there is nowhere else to be. See the docstring.
        shell._win.showFullScreen()
        return

    shell._ambient = True
    start_summon_hotkey(shell)
    if mode == "bubble":
        # A face that will not draw is not a reason to lose the mode — the tray
        # alone is a working ambient install, which is what phase 1 shipped.
        # DEGRADE TO LESS, NEVER TO A WINDOW: the user asked for no window.
        if not start_bubble(shell):
            shell._win._log_sig.emit(
                "SYS: Face bubble unavailable; staying in the tray.")

    # The orb and the command bar are ambient-only and independent of the
    # bubble: the orb says "the assistant is here", the bar is how you reach it
    # without the window. Both degrade to the tray on their own, so neither can
    # take the mode down with it.
    start_orb(shell)
    start_command_bar(shell)


# The summon chord. Ctrl+Shift+J is what does this INSIDE the window; the
# global version is the same shape so there is one thing to remember.
SUMMON_CHORD = ("ctrl", "shift", "j")


def start_summon_hotkey(shell: "JarvisUI") -> str:
    """Bind the global summon chord. Returns the scope actually achieved.

    WHY THIS IS NOT PART OF THE TRAY
        The tray icon is the way back to the interface, and on some desktops it
        is not there at all — a Wayland session without a StatusNotifier host, a
        GNOME install with the extension disabled, a Windows session where the
        notification area is hidden. Until now that user had NO way to summon
        the window: the in-window shortcut needs a focused window, which by
        definition they do not have. That is a one-way door, and this is the
        other handle.

    A 'window' scope is reported, not hidden: on Wayland there is genuinely no
    global hook available without a portal, and saying so is better than
    installing a chord that silently does nothing.
    """
    from core.hotkey import HotkeyTap

    tap = HotkeyTap(lambda: toggle_interface(shell), chord=SUMMON_CHORD)
    try:
        scope = tap.start()
    except Exception as e:                          # noqa: BLE001
        note(shell, f"summon shortcut unavailable — {type(e).__name__}: {e}")
        return "window"
    shell._summon_hotkey = tap
    if scope != "global":
        note(shell, "the summon shortcut only works while the interface is "
                    "focused — this desktop offers no global key hook.")
    return scope


def stop_summon_hotkey(shell: "JarvisUI") -> None:
    tap = getattr(shell, "_summon_hotkey", None)
    if tap is None:
        return
    tap.stop()
    shell._summon_hotkey = None


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
        "autostart": lambda: toggle_autostart(shell),
        "quit": lambda: quit_app(shell),
    }, app=shell._app, checked=lambda key: autostart_state()["enabled"])
    if not tray.start():
        # Reported, not swallowed: "the mode you asked for could not be given"
        # is exactly the kind of thing a log is for.
        note(shell, f"Ambient mode unavailable ({tray.error}); showing the window.")
        return False
    shell._tray = tray
    return True


def start_bubble(shell: "JarvisUI") -> bool:
    """Create the always-on-top face. False if this desktop will not have it."""
    from ui.face_bubble import FaceBubble

    try:
        from memory.config_manager import get_assistant_name
        name = get_assistant_name()
    except Exception:                               # noqa: BLE001
        name = "J.A.R.V.I.S"

    bubble = FaceBubble(
        shell._face_path_or_default(),
        name,
        on_double_click=lambda: summon(shell),
    )
    if not bubble.start():
        note(shell, "Face bubble could not be created; staying in the tray.")
        return False
    shell._bubble = bubble
    return True


def start_orb(shell: "JarvisUI") -> bool:
    """Show the ring in the corner. False if this desktop will not have it.

    Started AFTER the tray, always: the orb is the least capable surface here,
    and a machine that cannot draw a 96 px window can still hold an icon. It is
    also started with the saved presence mode already applied, so a user who
    left the assistant in Senyap does not see it light up for a frame first.
    """
    from ui.orb_overlay import OrbOverlay

    try:
        from core import presence_mode
        mode = presence_mode.current()
    except Exception:                               # noqa: BLE001
        mode = "active"

    orb = OrbOverlay(mode=mode, on_click=lambda: open_command_bar(shell))
    if not orb.start():
        note(shell, f"Orb unavailable ({orb.error}); the tray is still there.")
        return False
    shell._orb = orb
    return True


# Ctrl+Space: the chord the artboard promises, and the one thing about this
# feature a user is told. Kept next to the bar's own code rather than in
# `core.hotkey`, because that module's DEFAULT_CHORD is push-to-talk's.
BAR_CHORD = ("ctrl", "space")


def start_bar_hotkey(shell: "JarvisUI") -> str:
    """Bind Ctrl+Space to the bar. Returns the scope actually achieved.

    Separate from the summon chord: that one brings the WINDOW back, this one
    opens a line without it. Two chords because they answer two different
    wishes, and collapsing them would make the bar unreachable in `hud` mode.
    """
    from core.hotkey import HotkeyTap

    tap = HotkeyTap(lambda: toggle_command_bar(shell), chord=BAR_CHORD)
    try:
        scope = tap.start()
    except Exception as e:                          # noqa: BLE001
        note(shell, f"command bar shortcut unavailable — {type(e).__name__}: {e}")
        return "window"
    shell._bar_hotkey = tap
    return scope


def stop_bar_hotkey(shell: "JarvisUI") -> None:
    tap = getattr(shell, "_bar_hotkey", None)
    if tap is None:
        return
    tap.stop()
    shell._bar_hotkey = None


def toggle_command_bar(shell: "JarvisUI") -> None:
    """Ctrl+Space: open the bar, or close it if it is already up."""
    bar = getattr(shell, "_command_bar", None)
    if bar is not None and bar.is_open:
        bar.close()
        return
    open_command_bar(shell)


def start_command_bar(shell: "JarvisUI") -> bool:
    """Create the bar, unshown, and its chord. False if the chord cannot bind.

    The bar is built now and opened later: building a window on the first
    keystroke would put Qt's construction cost on the user's first Ctrl+Space,
    which is the one moment the feature is being judged.
    """
    from ui.command_bar import CommandBar

    bar = CommandBar(on_submit=lambda text: submit_from_bar(shell, text))
    shell._command_bar = bar
    scope = start_bar_hotkey(shell)
    if scope != "global":
        note(shell, "the command bar shortcut only works while the orb or the "
                    "interface has focus — this desktop offers no global hook.")
    return bar is not None


def open_command_bar(shell: "JarvisUI") -> bool:
    """Open the bar over whatever the user is doing. The orb's click lands here.

    `previous` is the window the assistant can see, not the one the user is
    typing in — Qt cannot see another application's window, and pretending
    otherwise would make Esc restore focus to the wrong program. On a desktop
    where the assistant has no window of its own, the ledger honestly records
    "nothing to restore".
    """
    bar = getattr(shell, "_command_bar", None)
    if bar is None:
        from ui.command_bar import CommandBar
        bar = CommandBar(on_submit=lambda text: submit_from_bar(shell, text))
        shell._command_bar = bar
    previous = getattr(shell, "_win", None)
    if previous is not None and not previous.isVisible():
        previous = None
    if not bar.open(previous):
        note(shell, f"Command bar unavailable ({bar.error}).")
        return False
    return True


def submit_from_bar(shell: "JarvisUI", text: str) -> None:
    """Hand one line to the assistant, the same way typing into the HUD does."""
    try:
        shell._win._submit_text(text)
    except Exception as e:                          # noqa: BLE001
        note(shell, f"the command bar could not send: {type(e).__name__}: {e}")


def apply_presence_mode(shell: "JarvisUI", mode: str) -> bool:
    """Switch Aktif / Fokus / Senyap and dim the orb to match.

    This is the wiring behind the answered product question: Fokus and Senyap
    dim the ORB, not only the notifications. The mode itself is held in
    `core.presence_mode` so the scheduler thread, which has no widget, reads the
    same value the panel writes.
    """
    from core import presence_mode
    from memory.config_manager import save_presence_mode

    if not presence_mode.set_mode(mode):
        return False
    try:
        save_presence_mode(presence_mode.current())
    except Exception as e:                          # noqa: BLE001
        note(shell, f"presence mode not saved: {type(e).__name__}: {e}")
    orb = getattr(shell, "_orb", None)
    if orb is not None:
        orb.set_mode(presence_mode.current())
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
    # THE FACE STEPS ASIDE WHILE THE WINDOW IS UP.
    #
    # Both are always-on-top, and two copies of the same avatar — one in the
    # window's centre, one floating over it — reads as a rendering fault rather
    # than as two surfaces. Hidden rather than stopped: the animation state is
    # kept, so it picks up mid-motion when the window goes away again, which is
    # the same rule the window's own canvas follows (`_on_screen`).
    bubble = getattr(shell, "_bubble", None)
    if bubble is not None and bubble.available:
        _hide_bubble(bubble)
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
    bubble = getattr(shell, "_bubble", None)
    if bubble is not None and bubble.available:
        _show_bubble(bubble)


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
        _stop_bubble(shell)
        _stop_orb(shell)
        stop_summon_hotkey(shell)
        # The bar's chord goes with the orb: in HUD mode the window is the way
        # in, and a Ctrl+Space that still opened a floating line would be a
        # second, unexplained surface over a full-screen interface.
        stop_bar_hotkey(shell)
        if getattr(shell, "_tray", None) is not None:
            shell._tray.stop()
            shell._tray = None
        shell._win.showFullScreen()
        shell._ambient = False
        save_ui_mode("hud")
        return True
    if mode not in ("ambient", "bubble"):
        return False

    # The tray comes first in every ambient variant: it is the only surface
    # that can always get the user back, so a mode that cannot create one is a
    # mode this machine cannot have.
    if getattr(shell, "_tray", None) is None and not start_tray(shell):
        return False

    start_orb(shell)
    start_command_bar(shell)

    if mode == "bubble":
        if getattr(shell, "_bubble", None) is None and not start_bubble(shell):
            # Refused rather than saved-and-ignored: the user picked this mode,
            # and a stored value that does nothing is a setting they will
            # re-toggle forever. The tray mode is still offered, one click away.
            return False
        if getattr(shell, "_bubble", None) is not None:
            _show_bubble(shell._bubble)
    else:
        _stop_bubble(shell)

    shell._win.hide()
    shell._ambient = True
    save_ui_mode(mode)
    return True


def _hide_bubble(bubble) -> None:
    try:
        bubble._window.hide()
    except Exception as e:                          # noqa: BLE001
        note_quiet(f"could not hide the face — {type(e).__name__}: {e}")


def _show_bubble(bubble) -> None:
    try:
        bubble._window.show()
    except Exception as e:                          # noqa: BLE001
        note_quiet(f"could not show the face — {type(e).__name__}: {e}")


def raise_window(shell: "JarvisUI") -> None:
    """Bring the window up without touching the mode.

    Raises BEFORE `raise_()` on purpose: `summon` also sets `_ambient` and hides
    the bubble, and `raise_` is the one call a window manager may refuse. Doing
    the mode change first would leave the shell believing it had summoned a
    window that is not on screen.
    """
    try:
        shell._win.showMaximized()
    except Exception:                          # noqa: BLE001
        raise                                  # the caller reports it
    bubble = getattr(shell, "_bubble", None)
    if bubble is not None and bubble.available:
        _hide_bubble(bubble)
    shell._ambient = False
    try:
        shell._win.raise_()
        shell._win.activateWindow()
    except Exception as e:                          # noqa: BLE001
        note(shell, f"could not raise the window — {type(e).__name__}: {e}")


def _stop_orb(shell) -> None:
    orb = getattr(shell, "_orb", None)
    if orb is None:
        return
    orb.stop()
    shell._orb = None


def _stop_bubble(shell) -> None:
    bubble = getattr(shell, "_bubble", None)
    if bubble is None:
        return
    bubble.stop()
    shell._bubble = None


def note_quiet(text: str) -> None:
    """A note for the case where there is no shell to write a log line on.

    Show/hide failures happen while the user is watching the thing not appear,
    so silence is the one response that would be wrong — stdout costs nothing
    and shows up in the log file main.py opens at startup.
    """
    print(f"[JARVIS] {text}")


# ── what the tray menu asks for ───────────────────────────────────────────

def program_path(shell: "JarvisUI") -> str:
    """The file that auto-start should launch. The one that is actually running.

    NOT derived from `__file__`. The old toggle did that from inside
    `ui/window.py`, which produced `ui/main.py` — a path that has never
    existed — on all three platforms, and the failure only showed up at the
    next login. `main.py` records its own path on the shell at startup; this
    asks for it and refuses to guess.
    """
    path = getattr(shell, "_program_path", "")
    if not path:
        raise RuntimeError("the program path was never recorded by main.py")
    return path


def autostart_state() -> dict:
    """`{"enabled", "script", "broken"}` — read from disk, never remembered."""
    from core import autostart
    try:
        return autostart.status()
    except Exception as e:                          # noqa: BLE001
        return {"enabled": False, "script": "",
                "broken": False, "error": f"{type(e).__name__}: {e}"}


def toggle_autostart(shell: "JarvisUI") -> bool:
    """Turn auto-start on or off, and SAY what happened.

    Returns the new state, which is what the tray's tick is set to — a
    checkable menu item that flips itself regardless of the outcome is a switch
    that lies. Every failure is written to the log rather than raised: this runs
    from a menu, and a menu item that throws looks like a menu item that worked.
    """
    from core import autostart

    before = autostart_state()
    # Three states, not two, and the third is the one the old toggle could not
    # see: registered but pointing at a file that is gone. Treating that as
    # "on" leaves a switch that promises a launch that cannot happen; treating
    # it as "off" and calling `enable` fails on the same missing file. So it is
    # removed, and said out loud. A stale entry is not something anybody keeps.
    if before["enabled"] and before["broken"]:
        try:
            autostart.disable()
            note(shell, "Auto-start removed — it pointed at a file that is no "
                        f"longer there: {before['script']}")
        except Exception as e:                      # noqa: BLE001
            note(shell, f"Auto-start failed — {type(e).__name__}: {e}")
        return False

    was_on = bool(before["enabled"])
    try:
        if was_on:
            autostart.disable()
            note(shell, "Auto-start disabled.")
        else:
            script = program_path(shell)
            autostart.enable(script, icon=_icon_or_none())
            note(shell, f"Auto-start enabled — {script}")
    except Exception as e:                          # noqa: BLE001
        note(shell, f"Auto-start failed — {type(e).__name__}: {e}")

    after = autostart_state()
    # The state that gets reported is the state READ BACK. "Enabled" is only
    # true if an entry exists AND the file it points at exists, which is the
    # pair of facts the old toggle never checked.
    if after["broken"]:
        note(shell, f"Auto-start points at a file that is not there: {after['script']}")
    return bool(after["enabled"]) and not after["broken"]


def _icon_or_none():
    """The tray icon file, if it exists. A missing icon is not an error."""
    try:
        from ui.tray import icon_path
        path = icon_path()
        return path if path.exists() else None
    except Exception:                               # noqa: BLE001
        return None


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
    # `wake_state()["awake"]` is the state main.py actually gates the mic on, so
    # asking it directly is exact. An earlier draft read the wake BUTTON, which
    # only agrees with this when the last repaint happened to be right.
    getter = getattr(shell._win, "_wake_state", None)
    try:
        awake = bool(getter()["awake"]) if getter is not None else None
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


def needs_attention(shell: "JarvisUI", why: str) -> bool:
    """Bring the window out because something is WAITING for the user.

    THE RULE THIS ENFORCES: a surface that blocks must be visible.
        Ambient mode hides the window, and two things inside it are not
        decoration — they are the only way to finish what the assistant started:

          * the confirmation banner, for shutdown, restart and anything else
            irreversible. `core/confirm` holds the action open for 90 seconds
            and then REFUSES it. Hidden, that is silent: the user is told to
            confirm something they cannot see, and 90 seconds later nothing has
            happened for no stated reason.
          * the setup screen, shown when the API key is rejected. `main.py`
            waits in `while not self._win._ready` — that is an unbounded wait,
            so the assistant simply stops answering, forever, with no visible
            cause.

        Both are worse than the window this mode was supposed to replace. So
        the mode yields: the window is shown, the banner is on it, and putting
        it away again is one keystroke or one tray click.

    Returns whether the window was actually raised, so the caller can log the
    difference between "shown" and "should have been".
    """
    # Already on screen: in hud mode the banner simply appears, and raising a
    # window the user is looking at would move it (showMaximized on a windowed
    # HUD would also change the mode they were in). Nothing to do.
    try:
        if shell._win.isVisible():
            return True
    except Exception as e:                          # noqa: BLE001
        note(shell, f"could not check visibility — {type(e).__name__}: {e}")
    try:
        raise_window(shell)
    except Exception as e:                          # noqa: BLE001
        note(shell, f"could not show the interface for {why} — "
                    f"{type(e).__name__}: {e}")
        return False
    try:
        visible = bool(shell._win.isVisible())
    except Exception as e:                          # noqa: BLE001
        note(shell, f"could not show the interface for {why} — "
                    f"{type(e).__name__}: {e}")
        return False
    if visible:
        note(shell, f"The interface opened because {why}. "
                    "Press Ctrl+Shift+J or use the tray to put it away again.")
    return visible


def announce_if_finished(shell: "JarvisUI", state: str) -> None:
    """Desktop notification for an answer that arrived while nobody watched.

    `shell._pending_state` is the status `JarvisUI.set_state` just forwarded;
    the rest is `core/notify.py`'s policy. Three conditions, all of them
    "no" by default, because a notification nobody asked for is the fastest way
    to get the feature switched off for good:

      * the mode is ambient — in the full-screen HUD the answer is already on
        the screen being read;
      * the user has not turned it off (config, default on only for ambient);
      * the policy agrees this is a completed turn, not a status cycle.
    """
    if not getattr(shell, "_ambient", False) or not state:
        return
    from core.notify import Notifier
    from memory.config_manager import get_desktop_notifications

    if not get_desktop_notifications():
        return
    notifier = getattr(shell, "_notifier", None)
    if notifier is None:
        notifier = Notifier(visible=lambda: bool(shell._win.isVisible()))
        shell._notifier = notifier
    log = getattr(shell._win, "_log", None)
    text = getattr(log, "last_answer", "") if log is not None else ""
    try:
        notifier.observe(state, text)
    except Exception as e:                          # noqa: BLE001
        # A status update must never be the thing that raises. Said rather than
        # swallowed, because "notifications never appear" is otherwise
        # unanswerable.
        print(f"[JARVIS] Notifier: {type(e).__name__}: {e}")


def window_needs_attention(window, why: str) -> None:
    """Called by a widget inside the window that is about to BLOCK the user.

    THE SHORT VERSION OF THE RULE, AND WHY IT LIVES HERE
        Ambient mode hides the window. Anything inside it that waits for the
        user — the confirmation banner (90 s, then refuses) and the setup screen
        (unbounded, `while not self._win._ready`) — would then wait invisibly.
        Both callers want the identical three lines, and `ui/window.py` is at
        4,245 of a 4,250-line ceiling, so they share this instead of each
        spelling it out: the ceiling said "extract", and it was right.

    `window` is a `MainWindow`; it reaches its shell through `_shell`. A window
    built without one (the widget tests do exactly that) is left alone — it is
    already on screen in those cases by construction.
    """
    shell = getattr(window, "_shell", None)
    if shell is None or window.isVisible():
        return
    try:
        needs_attention(shell, why)
    except Exception as e:                          # noqa: BLE001
        try:
            window.write_log(f"ERR: could not show the interface for {why} — "
                             f"{type(e).__name__}: {e}")
        except Exception:                           # noqa: BLE001
            note_quiet(f"could not show the interface for {why} — {e}")


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
