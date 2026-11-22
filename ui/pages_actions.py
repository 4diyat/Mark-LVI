"""The board pages' actions: one function per control that reaches a store.

WHY THESE ARE SEPARATE FROM `tray_panel_wiring`
    That module carries the panel's own actions — presence, the four quick
    actions, the permission switches, undo, export, erase, theme, command — and
    it was 537 lines before the board pages existed. Thirteen more pages added
    eleven more handlers, which put it past the 600-line ceiling the whole
    package is held to.

    The split is not "misc": every function here exists because a BOARD PAGE
    needs it, and every one of them is a STORE WRITE reached by a click. The
    panel owns which page is open; `ui/pages_memory`, `pages_people` and
    `pages_admin` own the rules; these carry a rule across the click path and
    say what happened.

WHAT EVERY FUNCTION HERE HAS TO DO
    1. Reach the store through ITS OWN writer, never a second one. `forget()`
       takes the memory lock; `save_plugin_enabled()` is what the loader reads;
       `proactive._write_paused()` is what the scheduler reads. A page that wrote
       the file itself would be a second writer racing the first.
    2. Return a bool that means what it says, including on the sad path — the
       panel repaints from the result.
    3. Say one sentence in the user's language, through `_say`. A control that
       changes something and says nothing is the failure this whole build keeps
       removing.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:                                    # pragma: no cover
    from ui.shell import AmbientShell


def _say(shell: "AmbientShell", text: str) -> None:
    """One line to the user, through the ONE path the shell already has.

    NOT A SECOND LOGGER. `ui.lifecycle.note` is where every other surface's
    sentence goes, and a page action that printed to stdout instead would be
    invisible in the app's own log — which is the failure mode where the panel
    looks busy and the record shows nothing.
    """
    from ui.lifecycle import note

    note(shell, text)


def memory_forget(shell: "AmbientShell") -> bool:
    """Board 10's "Lupakan": delete the memory the detail page is showing."""
    from ui import pages_memory

    panel = getattr(shell, "_panel", None)
    target = panel.target_memory() if panel is not None else ("", "")
    if not all(target):
        _say(shell, "Tidak ada memori yang dipilih.")
        return False
    ok, message = pages_memory.forget(*target)
    _say(shell, message)
    if ok and panel is not None:
        # BACK TO THE LIST, because the thing this page described is gone:
        # staying on it would show "catatan ini sudah dihapus" and a button that
        # can only fail.
        panel.set_page("memory")
    return ok


def memory_clear(shell: "AmbientShell") -> bool:
    """Board 9's "Hapus semua": every remembered fact, one at a time.

    ONE AT A TIME THROUGH `forget()`, not by rewriting the file. `forget()` is
    the store's own writer — it takes the lock, loads strictly and saves
    atomically — and a page that wrote `long_term.json` itself would be a second
    writer racing the one the program already has.
    """
    from ui import pages_memory

    rows = pages_memory.entries()
    if not rows:
        _say(shell, "Tidak ada memori untuk dihapus.")
        return False
    gone = 0
    for row in rows:
        ok, _message = pages_memory.forget(str(row.get("category") or ""),
                                           str(row.get("key") or ""))
        gone += 1 if ok else 0
    _say(shell, f"{gone} dari {len(rows)} memori dihapus.")
    return gone == len(rows)


def routines_pause(shell: "AmbientShell") -> bool:
    """Board 11's pause, through the engine's own persisted flag.

    WRITTEN BY THE MODULE THAT READS IT. `actions.proactive` keeps the pause in
    the config file behind `PAUSE_KEY`; this calls its writer, so the toggle and
    the scheduler cannot disagree about whether suggestions are on.
    """
    from actions import proactive
    from ui import pages_people

    wanted = not pages_people.suggestion_paused()
    try:
        proactive._write_paused(wanted)
    except OSError as e:
        _say(shell, f"Jeda saran tidak bisa disimpan — {e}")
        return False
    _say(shell, "Saran dijeda." if wanted else "Saran dilanjutkan.")
    return True


def tools_copy(shell: "AmbientShell") -> bool:
    """Board 12's "Salin": put the clipboard text back where it came from.

    The text is ALREADY the clipboard's, so copying it again looks pointless —
    and that is why the artboard draws the button: "Salin" means "use this,
    now", and the honest implementation is to leave the clipboard holding exactly
    what the card showed when the user pressed it, even if something else has
    taken the clipboard since.
    """
    from ui import pages_people

    text = pages_people.clipboard_text()
    if not text:
        _say(shell, "Clipboard kosong.")
        return False
    try:
        from actions import computer_control

        computer_control.pyperclip.copy(text)
    except Exception as e:                       # noqa: BLE001
        _say(shell, f"Clipboard tidak bisa ditulis — {type(e).__name__}: {e}")
        return False
    _say(shell, "Disalin.")
    return True


def tools_clear(shell: "AmbientShell") -> bool:
    """Board 12's "Bersihkan": empty the clipboard.

    IT SAYS WHAT IT DID AND TO WHAT. Emptying a clipboard destroys whatever the
    user had — the one destructive thing on this page — so the sentence names
    the store rather than saying "dibersihkan".
    """
    try:
        from actions import computer_control

        computer_control.pyperclip.copy("")
    except Exception as e:                       # noqa: BLE001
        _say(shell, f"Clipboard tidak bisa dikosongkan — {type(e).__name__}: {e}")
        return False
    _say(shell, "Clipboard dikosongkan.")
    return True


def tools_mark_safe(shell: "AmbientShell") -> bool:
    """Board 12's "Tandai aman" — a decision that lasts this session.

    WHAT IT CANNOT BE: a scan of the clipboard that clears a secret. There is no
    secret scanner, and marking a card number "safe" would be this program
    vouching for something it never inspected. What the button honestly does is
    stop the page from calling the text sensitive while the panel is open, which
    is a display decision and is exactly what "tandai" means.
    """
    panel = getattr(shell, "_panel", None)
    if panel is None:
        return False
    panel._marked_safe = True
    panel.refresh()
    _say(shell, "Ditandai aman untuk sesi ini.")
    return True


def plugin_toggle(shell: "AmbientShell", index: int) -> bool:
    """Board 16's switch for row `index`, through the loader's own store."""
    from ui import pages_admin

    rows = pages_admin.plugin_rows()
    try:
        row = rows[int(index)]
    except (IndexError, TypeError, ValueError):
        return False
    ok = pages_admin.set_plugin(str(row["name"]), not row["on"])
    _say(shell, f"Plugin {row['name']}: {'aktif' if not row['on'] else 'mati'}."
         if ok else f"Plugin {row['name']} tidak bisa disimpan.")
    return ok


def consent_answer(shell: "AmbientShell", allowed: bool) -> bool:
    """Board 7's Allow / Not now, recorded once."""
    from ui import pages_people

    ok = pages_people.record_consent(bool(allowed))
    _say(shell, "Izin mikrofon tercatat." if ok and allowed else
               ("Dilewati." if ok else "Izin tidak bisa disimpan."))
    return ok


def language_set(shell: "AmbientShell", code: str) -> bool:
    """Board 15's language segment. Returns whether the switch took."""
    from ui import pages_admin

    active = pages_admin.set_language(str(code))
    ok = active == str(code)
    _say(shell, f"Bahasa: {active}." if ok else f"Bahasa {code!r} tidak tersedia.")
    return ok


def text_scale_set(shell: "AmbientShell", scale: float) -> bool:
    """Board 15's text size, stored and applied to the panel at once."""
    from ui import pages_admin

    ok = pages_admin.set_text_scale(float(scale))
    panel = getattr(shell, "_panel", None)
    if panel is not None:
        panel.refresh()
    _say(shell, "Ukuran teks disimpan." if ok else "Ukuran teks tidak bisa disimpan.")
    return ok


def motion_toggle(shell: "AmbientShell") -> bool:
    """Board 15's motion switch. The orb reads the same flag on its next frame."""
    from ui import pages_admin

    wanted = not pages_admin.reduced_motion()
    ok = pages_admin.set_reduced_motion(wanted)
    _say(shell, ("Gerak dikurangi." if wanted else "Gerak aktif kembali.")
         if ok else "Pilihan gerak tidak bisa disimpan.")
    return ok


def install_mode(shell: "AmbientShell", index: int) -> bool:
    """Board 22's mode choice, through `presence_mode` like every other switch."""
    from ui import pages_admin

    modes = pages_admin.modes()
    try:
        mode = str(modes[int(index)][0])
    except (IndexError, TypeError, ValueError):
        return False
    from ui.tray_panel_wiring import set_presence

    return bool(set_presence(shell, mode))
