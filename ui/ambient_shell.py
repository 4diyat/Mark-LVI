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

    # BOARD 4: "KLIK KIRI — buka panel baki", "KLIK KANAN — menu cepat".
    # The left click used to open the command bar, which is a different surface
    # (board 3, one line) and left the 460x660 panel reachable only from the
    # tray icon. The bar keeps its own chord — Ctrl+Alt+B, below — so nothing is
    # orphaned by this, and the panel already has a command field of its own.
    orb = OrbOverlay(
        mode=mode,
        on_click=lambda: toggle_orb_panel(shell),
        on_menu=lambda: open_quick_menu(shell))
    if not orb.start():
        _note(shell, f"Orb unavailable ({orb.error}); the tray is still there.")
        return False
    shell._orb = orb
    return True


def start_toast(shell: "JarvisUI") -> bool:
    """Board 1's toast stack: the 340 px card in the top-left corner.

    WHY THIS IS A SEPARATE START, AND WHY IT WAS MISSING. `shell.notify`
    pushes to `shell._toaster`, and nothing ever created the stack — so the
    toast that `01-ambient-main.png` draws could not appear on a real run even
    though the painter, the queue and the window all existed. This is the
    surface's start, in the same shape as `start_orb`: built and hidden, and
    a failure is survivable (notifications still reach the OS).
    """
    from ui.toast_stack import ToastStack

    try:
        stack = ToastStack()
        if not stack.start():
            _note(shell, f"Toast unavailable ({stack.error}); "
                        "notifications go to the OS only.")
            return False
        shell._toaster = stack
        return True
    except Exception as e:                          # noqa: BLE001
        _note(shell, f"Toast stack unavailable — {type(e).__name__}: {e}")
        return False


# Keep the bar chord distinct from Ctrl+Space push-to-talk.
BAR_CHORD = ("ctrl", "alt", "b")


def toggle_orb_panel(shell: "JarvisUI") -> bool:
    """A left click on the orb: the tray panel, opened beside it.

    THE ANCHOR POINT IS THE ORB, not the cursor: `panel_position` opens the
    panel above and right-aligned to the point it is given, which is where a
    Windows tray menu opens. Passing the orb's own corner makes the panel appear
    attached to the thing that was clicked, rather than a knife's throw from it.
    """
    from ui import tray_panel_wiring

    orb = getattr(shell, "_orb", None)
    point = None
    try:
        point = orb.menu_point() if orb is not None else None
    except Exception as e:                          # noqa: BLE001
        _note(shell, f"panel anchor unavailable — {type(e).__name__}: {e}")
    return bool(tray_panel_wiring.toggle_panel(shell, point))


def open_quick_menu(shell: "JarvisUI") -> bool:
    """A right click on the orb: the short menu board 4 draws.

    "menu cepat" with no list in the artboard, so it carries what a user asks
    for at the orb and nothing else: the three presence modes, the two pages of
    the panel, and Quit. Everything longer already lives in the panel, and a
    menu that repeats it is a second place for the same action to be wrong.

    Built on demand and thrown away on close: it is five items, and a cached
    popup is a popup that shows yesterday's checkmark.
    """
    orb = getattr(shell, "_orb", None)
    if orb is None or not getattr(orb, "available", False):
        return False
    try:
        from PyQt6.QtGui import QCursor
        from PyQt6.QtWidgets import QMenu
    except Exception as e:                          # noqa: BLE001
        _note(shell, f"menu cepat tidak tersedia ({type(e).__name__}: {e})")
        return False

    from ui import tray_panel_wiring

    try:
        menu = QMenu()
        # The mode items are NOT a cycling toggle: the menu shows all three, so
        # it sets the one that was chosen. `set_presence` is the same call the
        # panel's segmented control makes, which is what keeps the two surfaces
        # telling the user the same truth.
        for mode, label in (("active", "Aktif"), ("focus", "Fokus"),
                            ("quiet", "Senyap")):
            menu.addAction(label).triggered.connect(
                lambda _checked=False, m=mode: tray_panel_wiring.set_presence(shell, m))
        menu.addSeparator()
        # THE PAGE LIST IS THE MENU'S, not a copy: the two the panel always had,
        # then the more-list that reaches the other thirteen. A menu that named
        # thirteen pages would be a menu of twenty items and board 4 draws a
        # SHORT one — so the long list lives in a page and the menu has one
        # entry for it.
        for page, label in (("history", "Riwayat"), ("privacy", "Privasi"),
                            ("more", "Lainnya…")):
            menu.addAction(label).triggered.connect(
                lambda _checked=False, p=page: _open_panel_page(shell, p))
        menu.addSeparator()
        menu.addAction(_t_main_home()).triggered.connect(lambda: _open_main(shell))
        menu.addAction("Keluar").triggered.connect(lambda: _quit_from_menu(shell))

        # BESIDE THE ORB, NOT AT THE CURSOR. The cursor is already on the orb
        # when this runs, and a menu that opens under the pointer can be
        # dismissed by the release of the very click that opened it.
        menu.popup(_qpoint(orb.menu_point() or QCursor.pos()))
        shell._quick_menu = menu               # keep a reference: Qt needs one
        return True
    except Exception as e:                          # noqa: BLE001
        _note(shell, f"menu cepat gagal ({type(e).__name__}: {e})")
        return False


def _t_main_home():
    from ui.tray_panel_model import _t
    return _t("ui.main.open")


def _open_main(shell):
    from ui.main_surface import open_main
    return open_main(shell)


def _qpoint(point):
    """A QPoint from an (x, y) pair or from a QPoint, which `QCursor.pos()` is."""
    if hasattr(point, "x") and hasattr(point, "y"):
        return point                           # already a QPoint
    from PyQt6.QtCore import QPoint

    return QPoint(int(point[0]), int(point[1]))


def _open_panel_page(shell: "JarvisUI", page: str) -> None:
    """Open the panel on one of its pages, from the quick menu."""
    from ui import tray_panel_wiring

    orb = getattr(shell, "_orb", None)
    point = orb.menu_point() if orb is not None else None
    if not tray_panel_wiring.open_panel(shell, point):
        return
    panel = getattr(shell, "_panel", None)
    if panel is not None:
        try:
            panel.set_page(page)
        except Exception as e:                      # noqa: BLE001
            _note(shell, f"page {page} tidak bisa dibuka — {type(e).__name__}: {e}")


def _quit_from_menu(shell: "JarvisUI") -> None:
    """Quit through the shell's own quit path, if it has one.

    A menu action that calls `sys.exit` directly would skip the shutdown that
    stops the orb's timer and writes the config — the difference between a clean
    exit and a window left on screen after the process is gone.
    """
    quit_fn = getattr(shell, "quit", None) or getattr(shell, "_quit", None)
    if callable(quit_fn):
        try:
            quit_fn()
            return
        except Exception as e:                      # noqa: BLE001
            _note(shell, f"quit failed — {type(e).__name__}: {e}")
    try:
        from PyQt6.QtWidgets import QApplication

        QApplication.quit()
    except Exception as e:                          # noqa: BLE001
        _note(shell, f"quit unavailable — {type(e).__name__}: {e}")


def start_bar_hotkey(shell: "JarvisUI") -> str:
    """Bind Ctrl+Alt+B to the bar. Returns the scope actually achieved.

    Separate from the summon chord: that one brings the WINDOW back, this one
    opens a line without it. Two chords because they answer two different
    wishes, and collapsing them would make the bar unreachable in `hud` mode.
    """
    from core.hotkey import HotkeyTap

    from ui.qt_thread import run_on_qt_thread
    tap = HotkeyTap(lambda: run_on_qt_thread(getattr(shell, '_ui_thread_id', None),
                                             lambda: toggle_command_bar(shell)), chord=BAR_CHORD)
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
    """Ctrl+Alt+B: open the bar, or close it if it is already up."""
    bar = getattr(shell, "_command_bar", None)
    if bar is not None and bar.is_open:
        bar.close()
        return
    open_command_bar(shell)


def _make_live_command_bar(shell):
    from ui.command_bar import CommandBar
    def submit(text):
        callback = getattr(shell, 'on_text_command', None)
        return callback(text) if callable(callback) else False
    def accepted(text):
        from ui.conversation_state import publish
        publish(shell, 'user', text)
    return CommandBar(on_submit=submit, asynchronous=True, on_sent=accepted)


def start_command_bar(shell: "JarvisUI") -> bool:
    """Create the bar, unshown, and its chord. False if the chord cannot bind.

    The bar is built now and opened later: building a window on the first
    keystroke would put Qt's construction cost on the user's first Ctrl+Alt+B,
    which is the one moment the feature is being judged.
    """
    bar = _make_live_command_bar(shell)
    shell._command_bar = bar
    scope = start_bar_hotkey(shell)
    if scope != "global":
        _note(shell, "command bar global shortcut unavailable; open it from the workspace instead.")
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
        bar = _make_live_command_bar(shell)
        shell._command_bar = bar
    if not bar.open(None):
        _note(shell, f"Command bar unavailable ({bar.error}).")
        return False
    return True


def submit_command_bar(shell: "JarvisUI", text: str) -> bool:
    """The standalone bar also contributes its typed requests to chat."""
    if not submit_from_bar(shell, text):
        return False
    panel = getattr(shell, "_panel", None)
    if panel is not None:
        panel.add_message("user", text)
    main = getattr(shell, "_main_surface", None)
    if main is not None:
        main.add_message("user", text)
    return True


def submit_from_bar(shell: "JarvisUI", text: str) -> bool:
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
        return False
    try:
        import threading
        threading.Thread(target=send, args=(text,), daemon=True).start()
        return True
    except Exception as e:                          # noqa: BLE001
        _note(shell, f"the command bar could not send: {type(e).__name__}: {e}")
        return False


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
    # The 460 px panel shows the same three modes as segments. Refreshed here,
    # not only when the panel is opened, because the mode can change from the
    # tray menu and from a chord while the panel is on screen — and a panel
    # with the previous segment lit is the one bug a user reads as "it did not
    # take". Cheap: `refresh()` is a handful of reads and a repaint.
    panel = getattr(shell, "_panel", None)
    if panel is not None:
        try:
            panel.refresh()
        except Exception as e:                      # noqa: BLE001
            _note(shell, f"panel not refreshed — {type(e).__name__}: {e}")
    return True


# ── summon / dismiss ──────────────────────────────────────────────────────
