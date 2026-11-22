"""Getting `ui/setup_window.py` onto the screen, from whichever thread asks.

WHY THIS IS NOT A METHOD ON THE SHELL
    `ui/shell.py` has a 600-line ceiling and the setup screen pushed it to 641.
    The tempting fix — trim the docstrings — is the one that has to be paid for
    again on the next change; moving the Qt marshalling out is what is actually
    smaller. `AmbientShell.open_setup()` is three lines that call this.

WHY THE MARSHALLING NEEDS A MODULE AT ALL
    Two callers ask for this screen and they are on different threads:

      * `wait_for_api_key()` — `main.py`'s runner thread, started with
        `threading.Thread`;
      * `prompt_reconfig()` — the asyncio loop, after `session_policy` says the
        key was rejected.

    Qt may only create widgets on the thread that owns them, and
    `QTimer.singleShot(0, ...)` is the same mechanism the confirmation banner
    already uses (`ui/shell.py::show_confirm`) for exactly this reason. It is
    safe to call from any thread as long as the receiving event loop is running
    — which it is, because `main.py` starts the runner from inside
    `_run_event_loop`.

WHY IT KEEPS ONE INSTANCE
    The screen is a gate, not a dialog: two of them is one too many, and the
    second would be behind the first while both call `mark_ready()`. The
    instance lives on the shell (`shell._setup`) so it survives between the
    two call sites — this module owns no global state of its own.
"""
from __future__ import annotations


def has_key() -> bool:
    """Whether a key is stored. Never raises, and defaults to "yes".

    TRUE IS THE SAFE DIRECTION, and it is why this lives here rather than in the
    shell: a config file that cannot be read for an unrelated reason must not
    pop a setup screen over a working install. The session fails on its own and
    `prompt_reconfig()` asks then, when the user has already been told why.
    """
    try:
        from memory.config_manager import is_configured

        return bool(is_configured())
    except Exception as e:                          # noqa: BLE001
        print(f"[JARVIS] could not read the key state — {type(e).__name__}: {e}",
              flush=True)
        return True


def open_setup(shell) -> bool:
    """Queue `ui.setup_window.SetupWindow` onto the Qt thread. Never raises.

    False means Qt is not importable here (a headless test, a broken install),
    and the caller is expected to say where the key file is instead.
    """
    try:
        from PyQt6.QtCore import QTimer
    except Exception as e:                          # noqa: BLE001
        note(shell, f"no Qt: cannot open the setup screen — {type(e).__name__}: {e}")
        return False
    try:
        QTimer.singleShot(0, lambda: build(shell))
        return True
    except Exception as e:                          # noqa: BLE001
        note(shell, f"the setup screen could not be queued — {type(e).__name__}: {e}")
        return False


def build(shell) -> None:
    """Qt thread only: make the window once, then show it."""
    try:
        from ui.setup_window import SetupWindow

        window = getattr(shell, "_setup", None)
        if window is None:
            window = SetupWindow(on_done=getattr(shell, "_setup_done", None),
                                 app=getattr(shell, "_app", None))
            shell._setup = window
        if not window.show():
            note(shell, f"the setup screen could not open — {window.error}")
            shell._setup = None
    except Exception as e:                          # noqa: BLE001
        note(shell, f"the setup screen could not be built — {type(e).__name__}: {e}")
        shell._setup = None


def note(shell, text: str) -> None:
    """One line, on the shell's log if it has one, on stdout otherwise."""
    write = getattr(shell, "write_log", None)
    if callable(write):
        try:
            write(f"SETUP: {text}")
            return
        except Exception as e:                      # noqa: BLE001
            # The shell's log path failed; stdout is the fallback and the
            # reason is carried into the line rather than dropped.
            print(f"[JARVIS] (log failed: {type(e).__name__}) {text}", flush=True)
            return
    print(f"[JARVIS] {text}", flush=True)


__all__ = ["build", "has_key", "note", "open_setup"]
