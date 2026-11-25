"""What each control on the tray panel actually DOES.

WHY THIS IS A MODULE AND NOT TWELVE LAMBDAS IN `start_tray`
    The panel has nine kinds of control and five pages. Written inline in
    `ui/lifecycle.py` they would be a wall of closures that no test can reach —
    `lifecycle` needs a Qt application, and these need to be provable on a
    machine with no display.

    So each one is a function that takes the shell, calls the thing that already
    owns the behaviour, and REPORTS what happened on whatever surface exists. No
    new behaviour is invented here: `core.undo` owns undo, `presence_mode` owns
    the mode, `config_manager` owns plugin enablement. This module is the list of
    which function is behind which control, and it is deliberately boring.

WHAT IT MUST NOT DO
    It must not swallow a failure into silence. A panel whose switch flips and
    does nothing is worse than a panel whose switch is grey — the first is a
    bug the user cannot see, the second is a fact they can read. So every
    failure becomes a `note()` line, which is the shell's own log path.

THE TWO HONEST GAPS
    * "Susun jendela" has no snap implementation in this build. The control
      says so instead of pretending.
    * "Cari berkas" opens the command bar with a prefilled request rather than
      running a search itself: the search needs a query, and the honest place
      to type one is the bar the user already knows.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:                                   # pragma: no cover
    from ui.shell import AmbientShell


def _say(shell: "AmbientShell", text: str) -> None:
    """One line to the shell's log, via `lifecycle.note` so there is one path."""
    from ui.lifecycle import note

    note(shell, text)


# ── presence ─────────────────────────────────────────────────────────────────

def set_presence(shell: "AmbientShell", mode: str) -> bool:
    """A segment. The segment IS the mode — no cycling, unlike the menu item.

    That difference is the point of the segmented control: the menu cycles
    because a menu cannot show three states at once, and the panel does not
    because it can. Using the cycling function here would make "Senyap" mean
    "one step from wherever it is", which is how a user who pressed it twice
    ends up back in Aktif.
    """
    from ui.ambient_shell import apply_presence_mode

    return bool(apply_presence_mode(shell, mode))


# ── quick actions ────────────────────────────────────────────────────────────

def quick_action(shell: "AmbientShell", key: str) -> bool:
    """One quick row. False when the row cannot do anything.

    TWO BOARDS DRAW ROWS HERE. Board 5's four in Aktif and Senyap; board 05a's
    three in Fokus — "Lihat yang tertahan", "Akhiri fokus sekarang", "Jeda semua
    penjadwalan". One table, because the panel decides which rows to DREW and
    this decides what a row DOES: splitting them would let the two drift, and a
    row drawn but not routed is a button that answers nothing.
    """
    handler = {
        "screenshot": screenshot,
        "dictate": dictate,
        "find_file": find_file,
        "tidy_windows": tidy_windows,
        "held": show_held,
        "end_focus": end_focus,
        "pause_scheduling": toggle_scheduling,
    }.get(key)
    if handler is None:
        return False
    return bool(handler(shell))


# ── board 05a: the three rows Fokus draws ────────────────────────────────────

def show_held(shell: "AmbientShell") -> bool:
    """Say what is waiting, and how much. Does NOT release it.

    THE ARTBOARD'S ROW IS A LOOK, NOT A FLUSH — its own wording is "Lihat yang
    tertahan", and the panel above it promises the held items appear *after*
    Fokus ends. Draining the queue from here would break that promise the first
    time a user was curious about the count. So this reads and reports; leaving
    Fokus is what releases.
    """
    from core import presence_mode

    try:
        count = int(presence_mode.held_count())
    except Exception as e:                          # noqa: BLE001
        _say(shell, f"Tidak bisa membaca antrean — {type(e).__name__}: {e}")
        return False
    if count == 0:
        _say(shell, "Tidak ada yang tertahan.")
        return True
    _say(shell, f"{count} tertahan, muncul setelah Fokus berakhir.")
    return True


def end_focus(shell: "AmbientShell") -> bool:
    """Leave Fokus. Releasing the held queue is `presence_mode`'s job, not ours.

    `set_mode` already drains the queue when it moves to a mode that allows a
    banner (`_requeue`), so calling `take_held()` here as well would take the
    items out of the queue before the release path can deliver them — the user
    would press "Akhiri fokus sekarang" and lose exactly what was being held for
    them.
    """
    from core import presence_mode

    try:
        changed = bool(presence_mode.set_mode("active"))
    except Exception as e:                          # noqa: BLE001
        _say(shell, f"Fokus tidak bisa diakhiri — {type(e).__name__}: {e}")
        return False
    if not changed:
        return False
    _say(shell, "Fokus berakhir. Yang tertahan menyusul.")
    return True


def toggle_scheduling(shell: "AmbientShell") -> bool:
    """The real pause behind "Jeda semua penjadwalan".

    IT PAUSES THE ENGINE THE APP ACTUALLY USES — `shell._proactive`, the one
    `main.py` created — and the engine persists the change itself. A row that
    only changed a flag somewhere else would look identical in the panel and
    change nothing about whether a message arrives.
    """
    from core import presence_mode

    engine = getattr(shell, "_proactive", None)
    if engine is None or not hasattr(engine, "toggle_pause"):
        _say(shell, "Penjadwalan tidak bisa dijeda di sesi ini.")
        return False
    try:
        paused = bool(engine.toggle_pause())
    except Exception as e:                          # noqa: BLE001
        _say(shell, f"Jeda gagal — {type(e).__name__}: {e}")
        return False
    if paused:
        _say(shell, "Penjadwalan dijeda, dan tetap dijeda setelah restart.")
        return True
    # Resuming into Fokus is a contradiction the user should hear about: the
    # engine will trigger, and `presence_mode` will hold the result.
    if presence_mode.current() == "focus":
        _say(shell, "Penjadwalan jalan lagi — hasilnya tetap ditahan selama Fokus.")
    else:
        _say(shell, "Penjadwalan jalan lagi.")
    return True


def screenshot(shell: "AmbientShell") -> bool:
    """Grab the screen through the SAME path the model uses.

    Not `pyautogui.screenshot()` directly: `actions/computer_control.py` already
    owns the target folder and the naming, and a second screenshot implementation
    is a second place for the save path to be wrong on a machine with no
    Desktop folder.
    """
    try:
        from actions.computer_control import _screenshot

        result = _screenshot()
    except Exception as e:                          # noqa: BLE001
        _say(shell, f"Tangkap layar gagal — {type(e).__name__}: {e}")
        return False
    _say(shell, str(result))
    return True


def dictate(shell: "AmbientShell") -> bool:
    """Record a phrase with push-to-talk held for six seconds.

    THE HOLD IS THE WHOLE FEATURE. `ptt_hold(True)` opens the microphone and
    `ptt_hold(False)` closes it; calling only the first would leave the mic open
    for the rest of the session, which is why the release runs in a `finally`
    and on a timer rather than after the recording returns — there is no
    recording call to wait for.

    Six seconds is a sentence. A button cannot express "until I let go", so the
    panel's Dikte is a short dictation, and the chord on the same row is the
    press-and-hold version for anything longer.
    """
    hold = getattr(shell, "ptt_hold", None)
    if not callable(hold):
        _say(shell, "Dikte belum siap — sesi belum berjalan.")
        return False
    try:
        hold(True)
    except Exception as e:                          # noqa: BLE001
        _say(shell, f"Dikte gagal — {type(e).__name__}: {e}")
        return False
    _release_later(shell, 6.0)
    _say(shell, "Merekam 6 detik. Berbicaralah.")
    return True


def _release_later(shell: "AmbientShell", seconds: float) -> None:
    """Release push-to-talk after `seconds`, on a thread that cannot be lost.

    A daemon thread rather than a `QTimer`: this is called from the Qt thread
    but the release must happen even if the panel has been closed and its timers
    are gone, and a stuck microphone is the one failure here that the user
    cannot see and would not forgive.
    """
    import threading

    def _release() -> None:
        import time

        time.sleep(max(0.1, float(seconds)))
        hold = getattr(shell, "ptt_hold", None)
        if not callable(hold):
            return
        try:
            hold(False)
        except Exception as e:                      # noqa: BLE001
            _say(shell, f"Dikte tidak berhenti — {type(e).__name__}: {e}")

    try:
        threading.Thread(target=_release, daemon=True,
                         name="jarvis-ptt-release").start()
    except Exception as e:                          # noqa: BLE001
        # No thread means the microphone may stay open. Try the direct release
        # rather than leaving it, and say so either way.
        _say(shell, f"Dikte tidak bisa menjadwalkan pelepasan — {type(e).__name__}: {e}")
        hold = getattr(shell, "ptt_hold", None)
        if callable(hold):
            try:
                hold(False)
            except Exception as inner:              # noqa: BLE001
                _say(shell, f"Pelepasan langsung juga gagal — "
                            f"{type(inner).__name__}: {inner}")


def find_file(shell: "AmbientShell") -> bool:
    """Open the command bar with a prefilled request.

    Prefilled, not focused: a search box with no query is a box, and the bar
    already knows how to send a line to the model. The user finishes the
    sentence — "cari berkas laporan" — which is also how the same request would
    be made by voice.
    """
    from ui.ambient_shell import open_command_bar

    bar = getattr(shell, "_command_bar", None)
    if bar is not None and getattr(bar, "is_open", False):
        return True
    opened = bool(open_command_bar(shell))
    if opened:
        prefill(shell, "Cari berkas ")
    return opened


def prefill(shell: "AmbientShell", text: str) -> bool:
    """Put text in the command bar's field without sending it.

    Reachable so the panel's "Cari berkas" row lands somewhere useful. Failures
    are reported, not raised: a bar that cannot be prefilled is still a bar.
    """
    bar = getattr(shell, "_command_bar", None)
    field = getattr(bar, "_field", None)
    if field is None:
        return False
    try:
        field.setText(text)
        field.setFocus()
        return True
    except Exception as e:                          # noqa: BLE001
        _say(shell, f"Bar tidak bisa diisi — {type(e).__name__}: {e}")
        return False


def tidy_windows(shell: "AmbientShell") -> bool:
    """Board 5's fourth row, which this build cannot honour.

    There is no window-snapping implementation anywhere in the tree — it was
    never written, not removed — and inventing one from the panel would be a new
    feature wearing a mockup's label. So the row says what is true: the chord is
    the way to ask the assistant, which can then attempt it through
    `computer_control`.
    """
    _say(shell, "Susun jendela belum ada di build ini — minta JARVIS lewat "
                "perintah, atau pakai Ctrl+Shift+J untuk membuka bar.")
    return False


# ── history and privacy ──────────────────────────────────────────────────────

def undo_last(shell: "AmbientShell") -> bool:
    """Board 08a's Urungkan, through `core.undo`'s own stack."""
    try:
        from core import undo

        result = undo.undo_last()
    except Exception as e:                          # noqa: BLE001
        _say(shell, f"Urungkan gagal — {type(e).__name__}: {e}")
        return False
    _say(shell, str(result))
    return True


def export_history(shell: "AmbientShell") -> bool:
    """Write the undo history to a file next to the config, and say where.

    The destination is the user's Desktop when it exists, because a file the
    panel wrote has to be findable without a file manager tour. Same rule, same
    fallback as the screenshot path.
    """
    try:
        from core import undo

        lines = list(undo.history())
    except Exception as e:                          # noqa: BLE001
        _say(shell, f"Ekspor gagal — {type(e).__name__}: {e}")
        return False
    target = _desktop_path() / "jarvis-history.txt"
    try:
        target.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    except OSError as e:
        _say(shell, f"Ekspor gagal menulis {target} — {e}")
        return False
    _say(shell, f"Riwayat diekspor ke {target}")
    return True


def export_audit(shell: "AmbientShell") -> bool:
    """Write the ACTIVITY LOG (the audit log) to a file, and say where.

    WHY THIS IS NOT `export_history`. Board 6 draws "Ekspor log" underneath an
    ACTIVITY LOG card; board 08a draws the same two words underneath the undo
    stack. `export_history` writes `undo.history()`, so using it here would
    export a different store than the one on screen. Same name, same place on
    the panel, different data — which is exactly why the action key is its own.
    """
    try:
        from core import audit_log

        entries = audit_log.shared().entries() or ()
    except Exception as e:                          # noqa: BLE001
        _say(shell, f"Ekspor log gagal — {type(e).__name__}: {e}")
        return False
    lines = []
    for item in entries:
        when = str(item.get("at") or item.get("time") or "")
        parts = [when] + [str(item.get(k) or "") for k in
                          ("tool", "level", "outcome", "detail")]
        lines.append(" · ".join(p for p in parts if p))
    target = _desktop_path() / "jarvis-activity-log.txt"
    try:
        target.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    except OSError as e:
        _say(shell, f"Ekspor log gagal menulis {target} — {e}")
        return False
    _say(shell, f"Log aktivitas diekspor ke {target}")
    return True


def _desktop_path():
    """Where a file the panel wrote goes: Desktop if it exists, else home."""
    from pathlib import Path

    desktop = Path.home() / "Desktop"
    return desktop if desktop.is_dir() else Path.home()


def clear_history(shell: "AmbientShell") -> bool:
    """Empty the undo stack. Does NOT erase the audit log — that is board 06a.

    Two buttons on two pages for two different things: "Hapus riwayat" forgets
    what can be undone, "Hapus semua data lokal" forgets what happened. Merging
    them would make the smaller button do the larger thing.
    """
    try:
        from core import undo

        undo.clear()
    except Exception as e:                          # noqa: BLE001
        _say(shell, f"Hapus riwayat gagal — {type(e).__name__}: {e}")
        return False
    _say(shell, "Riwayat urungkan dikosongkan.")
    return True


def erase_local(shell: "AmbientShell") -> bool:
    """Board 06a's erase: the audit log, on this machine, now.

    WHAT IT DOES NOT DO, SAID PLAINLY. It does not delete `config/api_keys.json`
    (that holds the user's API key, and a privacy button that logs them out is a
    button nobody presses twice), it does not touch the conversation history
    files, and it does not reach anything already sent to the model. It is the
    audit log — the record of what the assistant DID — because that is the one
    store this panel owns.
    """
    try:
        from core import audit_log

        ok = audit_log.shared().erase()
    except Exception as e:                          # noqa: BLE001
        _say(shell, f"Hapus data lokal gagal — {type(e).__name__}: {e}")
        return False
    _say(shell, "Audit log dihapus." if ok else
               "Audit log tidak bisa dihapus — lihat pesan di atas.")
    return bool(ok)


def set_permission(shell: "AmbientShell", key: str, on: bool) -> bool:
    """A board 06a switch. Only the two that are real can ever reach here.

    `screen` is disabled in the panel (always on when asked) and `microphone` is
    disabled too (a device either exists or it does not), so this handles the
    two plugin-backed ones and refuses anything else by name rather than
    silently doing nothing.
    """
    from memory import config_manager

    plugin = {"files": "file_controller", "apps": "computer_control"}.get(key)
    if plugin is None:
        _say(shell, f"Izin {key!r} bukan pengaturan di build ini.")
        return False
    ok = bool(config_manager.save_plugin_enabled(plugin, bool(on)))
    _say(shell, f"Izin {key}: {'aktif' if on else 'mati'}." if ok else
               f"Izin {key} tidak bisa disimpan.")
    return ok


def set_theme(shell: "AmbientShell", name: str) -> bool:
    """Persist the panel theme the user cycled to (board 17a).

    `memory.config_manager` validates the value — an unknown name collapses to
    `auto` there, not here — so this function only carries it across and says
    what happened. It runs on the click path, which is why the write is one
    small config update and not a rewrite of the whole file.
    """
    from memory import config_manager

    try:
        config_manager.save_ui_theme(name)
    except Exception as e:                          # noqa: BLE001
        _say(shell, f"Tema tidak tersimpan — {type(e).__name__}: {e}")
        return False
    # Read it back rather than trusting what was asked for: the config layer
    # may have collapsed an unknown value, and the sentence has to match disk.
    saved = config_manager.get_ui_theme()
    _say(shell, f"Tema panel: {saved}.")
    return saved == str(name or "").strip().lower()


# ── the field ────────────────────────────────────────────────────────────────

def send_command(shell: "AmbientShell", text: str) -> bool:
    """Board 5's field. The same door the command bar uses, on purpose."""
    from ui.ambient_shell import submit_from_bar

    if not str(text or "").strip():
        return False
    try:
        submit_from_bar(shell, text)
    except Exception as e:                          # noqa: BLE001
        _say(shell, f"Perintah tidak terkirim — {type(e).__name__}: {e}")
        return False
    return True


def actions_for(shell: "AmbientShell") -> dict:
    """The whole mapping `TrayPanel` takes, built from one shell.

    One function so a test can assert that every key the panel can press has a
    handler — a missing key is a control that does nothing, and the panel
    reports it, but the report is not a substitute for the wiring existing.
    """
    from ui import pages_actions

    return {
        "presence_set": lambda mode: set_presence(shell, mode),
        "quick": lambda key: quick_action(shell, key),
        "permission": lambda key, on: set_permission(shell, key, on),
        "undo": lambda: undo_last(shell),
        "history_export": lambda: export_history(shell),
        "history_clear": lambda: clear_history(shell),
        "erase": lambda: erase_local(shell),
        "export_audit": lambda: export_audit(shell),
        "theme": lambda name: set_theme(shell, name),
        "command": lambda text: send_command(shell, text),
        # ── the board pages (ui/pages_actions.py) ────────────────────────
        "memory_forget": lambda: pages_actions.memory_forget(shell),
        "memory_clear": lambda: pages_actions.memory_clear(shell),
        "routines_pause": lambda: pages_actions.routines_pause(shell),
        "routine_create": lambda: pages_actions.routine_create(shell),
        "routine_toggle": lambda i: pages_actions.routine_toggle(shell, i),
        "routine_delete": lambda i: pages_actions.routine_delete(shell, i),
        "tools_copy": lambda: pages_actions.tools_copy(shell),
        "tools_clear": lambda: pages_actions.tools_clear(shell),
        "tools_safe": lambda: pages_actions.tools_mark_safe(shell),
        "plugin_toggle": lambda index: pages_actions.plugin_toggle(shell, index),
        "consent": lambda allowed: pages_actions.consent_answer(shell, allowed),
        # Board 7's four-step onboarding ladder: advance, back, and the
        # presence-mode toggle the presence step reuses the consent switch for.
        "onboard_next": lambda: pages_actions.onboard_next(shell),
        "onboard_back": lambda: pages_actions.onboard_back(shell),
        "onboard_toggle": lambda: pages_actions.onboard_toggle(shell),
        "language": lambda code: pages_actions.language_set(shell, code),
        "text_scale": lambda scale: pages_actions.text_scale_set(shell, scale),
        "contrast_set": lambda level: pages_actions.contrast_set(shell, level),
        "motion_toggle": lambda: pages_actions.motion_toggle(shell),
        "install_mode": lambda index: pages_actions.install_mode(shell, index),
        "voice_auth_toggle": lambda on: pages_actions.voice_auth_toggle(shell, on),
        "voice_auth_enroll": lambda: pages_actions.voice_auth_enroll(shell),
        "voice_auth_delete": lambda: pages_actions.voice_auth_delete(shell),
        "form_fill_apply": lambda: pages_actions.form_fill_apply(shell),
        # Board 16's phone pairing: mint a code, pair a device, disconnect.
        "phone_make_code": lambda: pages_actions.phone_make_code(shell),
        "phone_pair": lambda: pages_actions.phone_pair(shell),
        "phone_unpair": lambda: pages_actions.phone_unpair(shell),
        # Board 22's installer: build a reviewed dependency plan and run it.
        "installer_run": lambda: pages_actions.installer_run(shell),
        # Board 14's OS-control switch: a gated toggle plus the physical confirm.
        "os_control_toggle": lambda: pages_actions.os_control_toggle(shell),
        "os_control_confirm": lambda: pages_actions.os_control_confirm(shell),
    }


def open_panel(shell: "AmbientShell", point=None) -> bool:
    """Open the panel, building it and its actions the first time.

    Built lazily and cached on the shell, because the panel is opened by a
    click: constructing twelve pages of widgets before the user has asked for
    them would put that cost on startup, where the orb is competing for the
    first frame.
    """
    from ui.tray_panel import TrayPanel

    panel = getattr(shell, "_panel", None)
    if panel is None:
        panel = TrayPanel(actions_for(shell), app=getattr(shell, "_app", None),
                          logger=lambda line: _say(shell, line))
        shell._panel = panel
    if not panel.open(point):
        _say(shell, f"Panel baki tidak bisa dibuka ({panel.error}).")
        return False
    return True


def toggle_panel(shell: "AmbientShell", point=None) -> bool:
    """What a LEFT click on the tray icon does (board 5, by way of the icon)."""
    from ui.tray_panel import TrayPanel

    panel = getattr(shell, "_panel", None)
    if panel is None:
        return open_panel(shell, point)
    if isinstance(panel, TrayPanel) and panel.available and panel._visible():
        panel.close()
        return False
    return open_panel(shell, point)


__all__ = [
    "actions_for", "clear_history", "dictate", "erase_local", "export_history",
    "find_file", "open_panel", "quick_action", "screenshot", "send_command",
    "set_permission", "set_presence", "set_theme", "tidy_windows",
    "toggle_panel", "undo_last",
]
