"""Launch, summon, dismiss — what the interface IS, as opposed to what it draws.

WHAT CHANGED, AND WHY THIS FILE IS SHORTER THAN IT WAS
    This module used to move a WINDOW between "on screen" and "in the tray".
    That is gone with `ui/window.py`: the mockup draws no window, and a
    full-screen HUD next to an ambient orb is two different products sharing a
    process. Summon now means "bring every ambient surface forward" — the orb
    and the face — and dismiss means "let them settle back".

    The functions that only existed to serve a window went with it:
    `set_interface_mode` (switching into `hud`), `raise_window` (showing a
    window), and `window_needs_attention` (opening one when something was
    wrong). A surface that does not exist cannot be shown, and a fallback to
    "show the window" in a build with no window is not a fallback.

THE ONE RULE THAT SURVIVES ALL OF IT
    An interface the user cannot reach is worse than no interface. Everything
    here that could hide something first checks that there is somewhere else to
    get back from, and says so rather than pretending when there is not. With
    the tray gone there is no way back, so the tray is not allowed to go: that
    is checked at creation, not at use.
"""
from __future__ import annotations

from pathlib import Path

import threading
from typing import TYPE_CHECKING

if TYPE_CHECKING:                                   # pragma: no cover
    from ui.shell import AmbientShell


def watch_for_another_launch(shell: "AmbientShell", interval_ms: int = 800) -> None:
    """Answer a SECOND launch by bringing the surfaces forward.

    `core/single_instance.py` makes a second launch a request — "come to the
    front" — written to a small file, rather than a second assistant holding
    the microphone. This is the other half of that: a timer on the Qt thread
    that notices the request.

    A timer rather than a socket for the reason given in that module: the
    asking process may be anything, on any of three platforms, and may already
    be gone. Polling a file costs one `exists()` every 800 ms.
    """
    try:
        from PyQt6.QtCore import QTimer
        from core import single_instance
    except Exception:                               # noqa: BLE001
        return

    timer = QTimer()
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
                deliver_text(shell, text)
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


def deliver_text(shell: "AmbientShell", text: str) -> bool:
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
        # On a thread, exactly as a typed message is: the caller is a Qt slot
        # and the send blocks on the session.
        threading.Thread(target=send, args=(text,), daemon=True).start()
        return True
    except Exception as e:                          # noqa: BLE001
        note(shell, f"could not deliver a link — {type(e).__name__}: {e}")
        return False


def run_deeplink(shell: "AmbientShell") -> bool:
    """Act on the `jarvis://` link this launch was started with, if any.

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
                                      ask=lambda text: deliver_text(shell, text))
    except Exception as e:                          # noqa: BLE001
        note(shell, f"a link failed — {type(e).__name__}: {e}")
        return False
    note(shell, f"Link: {link.verb}" + (f" — {link.text[:60]}" if link.text else ""))
    return delivered


# ── the ambient shell, re-exported ───────────────────────────────────────────
# `main.py` and the tests call these through `lifecycle`, and the surface code
# lives in a module of its own so this file stays readable. One import line is
# the whole cost of the split on every caller's side.
from ui.ambient_shell import (                      # noqa: F401
    BAR_CHORD, apply_presence_mode, current_presence, cycle_presence_mode,
    open_command_bar,
    presence_label, start_bar_hotkey, start_command_bar, start_orb,
    stop_bar_hotkey, submit_from_bar, toggle_command_bar,
)


def start_interface(shell: "AmbientShell") -> None:
    """Bring up every surface this machine can hold, and say what it could not.

    THE ORDER IS THE PRIORITY ORDER, most capable last.
        The tray is the only surface that can always get the user back, so it
        is created first and its failure is the one that matters. The face is
        next (it is the most information-dense). The orb is last because a
        machine that cannot draw a 96 px window can still hold an icon.

    A FAILED SURFACE IS NOT AN ERROR STATE.
        Each one degrades on its own and reports why. An assistant with a
        tray and nothing else is a working ambient install — that is what
        phase 1 shipped. What must never happen is a build where NOTHING came
        up: that is a process the user has to find in Task Manager.
    """
    # A LINK IS AN INSTRUCTION TO THE RUNNING APP, so it is answered before the
    # surfaces exist: `jarvis://hide` on an install with no orb must not be
    # turned into a summon by the order of these calls.
    if getattr(getattr(shell, "_launch", None), "link", None) is not None:
        run_deeplink(shell)

    watch_for_another_launch(shell)

    started = []
    if start_tray(shell):
        started.append("tray")
    if start_bubble(shell):
        started.append("face")
    if start_orb(shell):
        started.append("orb")
    if start_command_bar(shell):
        started.append("bar")

    # `--hidden` MEANS "START, BUT DO NOT APPEAR ON SOMEONE'S SCREEN" — a login
    # entry runs while the user is working, and a face that pops up on the first
    # frame is the thing the flag exists to prevent. The face is still BUILT:
    # nothing built means nothing to summon, and the chord would bring up
    # nothing at all.
    if getattr(getattr(shell, "_launch", None), "hidden", False):
        _set_bubble_visible(shell, False)

    # THE WAY BACK. With no window, the summon chord is the only global key
    # this program owns: without it the tray is the sole way to reach the
    # assistant, and on a desktop with no notification area there is none. It
    # is bound after the tray because the notice about a window-scoped chord
    # goes through the tray's own log.
    start_summon_hotkey(shell)

    if not started:
        # Nothing came up. This is the one outcome worth shouting about: the
        # assistant is running, holding the microphone, and invisible.
        note(shell, "No ambient surface could be created on this desktop. "
                    "JARVIS is running and listening but cannot show itself; "
                    "use the tray icon if one appears, or quit and check the "
                    "log for the reason each surface gave.")
    shell._ambient = True


# The summon chord. Ctrl+Shift+J is what does this; the global version is the
# same shape so there is one thing to remember.
SUMMON_CHORD = ("ctrl", "shift", "j")


def start_summon_hotkey(shell: "AmbientShell") -> str:
    """Bind Ctrl+Shift+J to `summon`. Returns the scope actually achieved."""
    from core.hotkey import HotkeyTap

    tap = HotkeyTap(lambda: summon(shell), chord=SUMMON_CHORD)
    try:
        scope = tap.start()
    except Exception as e:                          # noqa: BLE001
        note(shell, f"summon shortcut unavailable — {type(e).__name__}: {e}")
        return "window"
    shell._summon_hotkey = tap
    if scope != "global":
        note(shell, "the summon shortcut only works while a JARVIS surface has "
                    "focus — this desktop offers no global key hook.")
    return scope


def stop_summon_hotkey(shell: "AmbientShell") -> None:
    tap = getattr(shell, "_summon_hotkey", None)
    if tap is None:
        return
    tap.stop()
    shell._summon_hotkey = None


def start_tray(shell: "AmbientShell") -> bool:
    """Create the notification-area icon. False if this desktop has none."""
    from ui import tray_panel_wiring
    from ui.tray import TrayIcon

    tray = TrayIcon({
        # A LEFT CLICK opens the panel (board 5). Wired here rather than inside
        # `ui/tray.py` so the tray keeps knowing nothing about what the panel
        # is — see that module's docstring, which is still true.
        "panel": lambda: tray_panel_wiring.toggle_panel(shell),
        "show": lambda: summon(shell),
        "wake": lambda: request_wake(shell),
        "sleep": lambda: request_sleep(shell),
        # One item that walks Aktif → Fokus → Senyap. The label is asked for
        # after the mode changes, so the menu never shows the previous one.
        "presence": lambda: cycle_presence_mode(shell),
        "settings": lambda: summon_settings(shell),
        "autostart": lambda: toggle_autostart(shell),
        "quit": lambda: quit_app(shell),
    }, app=shell._app, checked=lambda key: autostart_state()["enabled"],
       label=lambda key: presence_label(current_presence()))
    if not tray.start():
        # Reported, not swallowed: "the mode you asked for could not be given"
        # is exactly the kind of thing a log is for.
        note(shell, f"Tray unavailable ({tray.error}).")
        return False
    shell._tray = tray
    return True


def start_bubble(shell: "AmbientShell") -> bool:
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


def summon(shell: "AmbientShell") -> None:
    """Bring every surface forward — from the tray, a shortcut, or a caller.

    WITH NO WINDOW, "FORWARD" MEANS THREE SMALL THINGS
        the face shown if it was hidden, the orb shown, and the tray menu's
        Show item doing the same. There is no window to raise and no
        full-screen mode to enter, which is exactly why this function is now
        shorter than its docstring used to be.
    """
    bubble = getattr(shell, "_bubble", None)
    if bubble is not None and getattr(bubble, "available", False):
        _set_bubble_visible(shell, True)
    orb = getattr(shell, "_orb", None)
    if orb is not None:
        try:
            orb.show()
        except Exception as e:                      # noqa: BLE001
            note(shell, f"could not show the orb — {type(e).__name__}: {e}")
    shell._ambient = True


def dismiss(shell: "AmbientShell") -> None:
    """Settle the surfaces back — the face hides, the orb stays.

    THE ORB IS NEVER HIDDEN BY A PLAIN DISMISS. It is the one mark that says
    the assistant is there, and hiding it from a menu item would leave the user
    with a process they cannot see. "Senyap" is how the user asks for a quieter
    orb, and it dims rather than disappears.
    """
    bubble = getattr(shell, "_bubble", None)
    if bubble is not None and getattr(bubble, "available", False):
        _set_bubble_visible(shell, False)


def toggle_interface(shell: "AmbientShell") -> None:
    """What the shortcut calls: the face up if it is down, down if it is up."""
    bubble = getattr(shell, "_bubble", None)
    if bubble is None or not getattr(bubble, "available", False):
        summon(shell)
        return
    if getattr(bubble, "visible", False):
        dismiss(shell)
    else:
        summon(shell)


def _set_bubble_visible(shell: "AmbientShell", visible: bool) -> None:
    bubble = getattr(shell, "_bubble", None)
    window = getattr(bubble, "_window", None)
    if window is None:
        return
    try:
        window.setVisible(visible)
    except Exception as e:                          # noqa: BLE001
        note(shell, f"could not show or hide the face — {type(e).__name__}: {e}")


def note_quiet(text: str) -> None:
    """A note for the case where there is no shell to write a log line on.

    Show/hide failures happen while the user is watching the thing not appear,
    so silence is the one response that would be wrong — stdout costs nothing
    and shows up in the log file main.py opens at startup.
    """
    print(f"[JARVIS] {text}", flush=True)


def program_path(shell: "AmbientShell") -> str:
    """The command line to register for autostart. `main.py` is the only source.

    IT REFUSES RATHER THAN GUESSING, and the difference is a login entry that
    works versus one that silently does not. Deriving the path from `__file__`
    inside `ui/` produced `ui/main.py` — a path that has never existed,
    registered on every platform and failing at the next login. Falling back to
    `sys.executable` is no better: it launches a bare interpreter, which is
    more confusing than nothing at all. A caller that has not been told has
    nothing honest to register.
    """
    override = getattr(shell, "_program_path", "") or ""
    if override:
        return override
    raise RuntimeError(
        "autostart needs the path main.py was run from; nothing has set it")


def autostart_state() -> dict:
    """Whether JARVIS starts with the machine, as the tray checkbox needs it.

    THREE STATES, NOT TWO. "Registered" and "will actually start" are different
    facts: an entry can survive the file it points at, which is what the old
    toggle could not see. Reporting only `enabled` leaves a tick that promises a
    launch that cannot happen.
    """
    try:
        from core import autostart
        status = autostart.status()
    except Exception as e:                          # noqa: BLE001
        not_quiet = f"autostart state unavailable — {type(e).__name__}: {e}"
        note_quiet(not_quiet)
        return {"enabled": False, "broken": False, "script": ""}
    script = str(status.get("script") or "")
    enabled = bool(status.get("enabled"))
    broken = bool(enabled and script and not Path(script).is_file())
    return {"enabled": enabled and not broken, "broken": broken, "script": script}


def toggle_autostart(shell: "AmbientShell") -> bool:
    """Turn auto-start on or off, and SAY what happened.

    Returns the new state, which is what the tray's tick is set to — a
    checkable menu item that flips itself regardless of the outcome is a switch
    that lies. Every failure is written to the log rather than raised: this runs
    from a menu, and a menu item that throws looks like a menu item that worked.

    THE THIRD STATE is the one the old toggle could not see: registered but
    pointing at a file that is gone. Treating it as "on" leaves a switch that
    promises a launch that cannot happen; treating it as "off" and calling
    `enable` fails on the same missing file. So it is removed, and said out
    loud. A stale entry is not something anybody keeps.
    """
    from core import autostart

    before = autostart_state()
    if before["broken"]:
        try:
            autostart.disable()
            note(shell, "Auto-start removed — it pointed at a file that is no "
                        f"longer there: {before['script']}")
        except Exception as e:                      # noqa: BLE001
            note(shell, f"Auto-start failed — {type(e).__name__}: {e}")
        return False

    try:
        if before["enabled"]:
            autostart.disable()
            note(shell, "Auto-start disabled.")
        else:
            script = program_path(shell)
            autostart.enable(script, icon=_icon_or_none())
            note(shell, f"Auto-start enabled — {script}")
    except Exception as e:                          # noqa: BLE001
        note(shell, f"Auto-start failed — {type(e).__name__}: {e}")

    after = autostart_state()
    if after["broken"]:
        note(shell, f"Auto-start points at a file that is not there: {after['script']}")
    return bool(after["enabled"])


def _icon_or_none():
    """The tray icon file, if this install has one. A missing icon is not an error."""
    try:
        from ui.tray import icon_path
        path = icon_path()
        return path if path.exists() else None
    except Exception:                               # noqa: BLE001
        return None


def request_wake(shell: "AmbientShell") -> None:
    """Ask the session to wake. The interface does not decide this."""
    handler = getattr(shell, "on_wake_manual", None)
    if not callable(handler):
        note(shell, "Wake is not available yet: the session is not running.")
        return
    try:
        handler()
    except Exception as e:                          # noqa: BLE001
        note(shell, f"could not wake — {type(e).__name__}: {e}")


def request_sleep(shell: "AmbientShell") -> None:
    """Ask the session to sleep."""
    handler = getattr(shell, "on_wake_toggle", None)
    if not callable(handler):
        note(shell, "Sleep is not available yet: the session is not running.")
        return
    try:
        handler(False)
    except Exception as e:                          # noqa: BLE001
        note(shell, f"could not sleep — {type(e).__name__}: {e}")


def summon_settings(shell: "AmbientShell") -> None:
    """There is no settings window. Say what the setting IS instead.

    The tray keeps a Settings item because a menu with a hole in it reads as
    broken, and an item that does nothing is worse than one that tells you
    where the setting lives. The values it used to edit (voice, accent, audio
    device) are all in `config/api_keys.json` and are read at startup.
    """
    note(shell, "Settings are in config/api_keys.json — there is no settings "
                "screen in this build. Edit the file and restart JARVIS.")


def quit_app(shell: "AmbientShell", code: int = 0) -> None:
    """Stop every surface, then quit the application.

    `os._exit` is the last resort and it is here on purpose: a surface that
    fails to stop must not be able to keep the process alive after the user
    asked it to quit. An assistant that ignores Quit is one somebody ends with
    Task Manager, and then they stop trusting the tray.
    """
    for attr, stop_name in (("_panel", "stop"), ("_orb", "stop"),
                            ("_bubble", "stop"), ("_tray", "stop"),
                            ("_command_bar", "close")):
        target = getattr(shell, attr, None)
        if target is None:
            continue
        try:
            getattr(target, stop_name)()
        except Exception as e:                      # noqa: BLE001
            note_quiet(f"could not stop {attr} — {type(e).__name__}: {e}")
    stop_summon_hotkey(shell)
    stop_bar_hotkey(shell)
    try:
        shell._app.quit()
    except Exception as e:                          # noqa: BLE001
        note_quiet(f"could not quit cleanly — {type(e).__name__}: {e}")
    import os
    os._exit(code)


def note(shell: "AmbientShell", text: str) -> None:
    """A line the user may need to read, on whatever surface exists."""
    write = getattr(shell, "write_log", None)
    if callable(write):
        try:
            write(f"SYS: {text}")
            return
        except Exception as e:                      # noqa: BLE001
            # The shell's own log path failed. Fall through to stdout rather
            # than lose the sentence — this function exists to report failures.
            print(f"[JARVIS] log failed ({type(e).__name__}: {e}); {text}", flush=True)
            return
    print(f"[JARVIS] {text}", flush=True)


def needs_attention(shell: "AmbientShell", why: str) -> bool:
    """Tell the user something needs them. Always returns True now.

    It used to return whether it could OPEN A WINDOW to say so. There is no
    window, so the answer is the toast — and a toast is not something the
    caller has to wait to be seen.
    """
    note(shell, f"{why} — this needs you.")
    return True
