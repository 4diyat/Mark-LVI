"""The ambient shell: the orb, the command bar, and the presence mode.

WHY THIS IS A MODULE OF ITS OWN
    `ui/lifecycle.py` reached 1,009 lines, and `tests/test_ui_split.py` refuses
    any `ui/` module over 600 — a ceiling that exists because this project has
    already had one 7,500-line `ui.py`. The split is not cosmetic. Everything
    here is the ambient SHELL: the ring on the desktop, the one line you type
    into, and the mode that decides how loudly the assistant may interrupt.
    None of it is about getting the main window on and off the screen, which is
    what the rest of `lifecycle.py` does.

WHY THE IMPORT GOES ONE WAY
    `lifecycle` re-exports every name below, so the start-up path keeps calling
    `lifecycle.start_orb` and nothing outside this file has to know the module
    moved. The direction is ambient → lifecycle → shell, never back, so there is
    no import cycle and no second definition of "summon".
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:                                    # pragma: no cover
    from ui.shell import AmbientShell as JarvisUI


def _note(shell, text: str) -> None:
    """`lifecycle.note`, imported at call time.

    A module-level `from ui.lifecycle import note` would make the two modules
    import each other — `lifecycle` re-exports this one — and the cycle would
    only fail on whichever of them was imported second. This is the one edge,
    it is four lines, and it is called on a failure path where the extra import
    costs nothing.
    """
    from ui.lifecycle import note
    note(shell, text)


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
        _note(shell, f"Orb unavailable ({orb.error}); the tray is still there.")
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
        _note(shell, f"command bar shortcut unavailable — {type(e).__name__}: {e}")
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
        _note(shell, "the command bar shortcut only works while the orb or the "
                    "interface has focus — this desktop offers no global hook.")
    return bar is not None


def open_command_bar(shell: "JarvisUI") -> bool:
    """Open the bar over whatever the user is doing. The orb's click lands here.

    `previous` is the window the assistant can see, not the one the user is
    typing in — Qt cannot see another application's window, and pretending
    otherwise would make Esc restore focus to the wrong program.

    THERE IS NO `previous` IN THIS BUILD. The surface that used to be restorable
    was JARVIS's own window; the mockup has none, so the bar always opens over
    whatever the user was doing and Esc simply closes it. That is recorded
    honestly rather than faked, and `ui.command_bar` already accepts None.
    """
    bar = getattr(shell, "_command_bar", None)
    if bar is None:
        from ui.command_bar import CommandBar
        bar = CommandBar(on_submit=lambda text: submit_from_bar(shell, text))
        shell._command_bar = bar
    if not bar.open(None):
        _note(shell, f"Command bar unavailable ({bar.error}).")
        return False
    return True


def submit_from_bar(shell: "JarvisUI", text: str) -> None:
    """Hand one line to the assistant, exactly as a typed message arrives.

    `on_text_command` is what main.py assigns for that (`_on_text_command`), and
    it is the same entry point the deeplink `ask` verb uses — so the bar cannot
    drift into being a second door into the session.

    It runs on a thread because the bar's own signal is emitted on the Qt
    thread and the send blocks on the session: doing it inline would freeze the
    bar the user is typing into until the model answered.
    """
    send = getattr(shell, "on_text_command", None)
    if not callable(send):
        _note(shell, "the command bar cannot send yet: the session is not ready")
        return
    try:
        import threading
        threading.Thread(target=send, args=(text,), daemon=True).start()
    except Exception as e:                          # noqa: BLE001
        _note(shell, f"the command bar could not send: {type(e).__name__}: {e}")


def cycle_presence_mode(shell: "JarvisUI") -> str:
    """Aktif → Fokus → Senyap → Aktif. Returns the mode now in force.

    A single cycling command rather than three menu items: the tray menu is
    already six entries and the three modes are one decision ("how loud is it"),
    so one item that walks them is shorter to read and impossible to choose
    wrongly. The label carries the current mode; see `presence_label()`.
    """
    from core import presence_mode

    order = presence_mode.MODES
    current = presence_mode.current()
    index = order.index(current) if current in order else 0
    mode = order[(index + 1) % len(order)]
    apply_presence_mode(shell, mode)
    return mode


def current_presence() -> str:
    """The mode in force, from the one place that holds it.

    Public rather than underscore-prefixed: `lifecycle.start_tray` asks for it
    to build the menu label, and a cross-module call to a private name is the
    kind of thing that gets "cleaned up" by the next reader.
    """
    from core import presence_mode

    return presence_mode.current()


def presence_label(mode: str) -> str:
    """The tray item's text for a mode. Indonesian, like the rest of the UI."""
    return {
        "active": "Aktif — boleh menyela",
        "focus": "Fokus — saran ditahan",
        "quiet": "Senyap — orb meredup",
    }.get(str(mode or "").lower(), "Aktif — boleh menyela")


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
        _note(shell, f"presence mode not saved: {type(e).__name__}: {e}")
    orb = getattr(shell, "_orb", None)
    if orb is not None:
        orb.set_mode(presence_mode.current())
    return True


# ── summon / dismiss ──────────────────────────────────────────────────────
