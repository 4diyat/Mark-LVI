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


def _t(key: str, **fields) -> str:
    """`core.i18n.label` with a fallback, so a missing catalogue key still
    shows the key rather than raising inside a click handler."""
    from ui.tray_panel_model import _t as _i18n_t

    return _i18n_t(key, **fields)


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


def contrast_set(shell: "AmbientShell", level: str) -> bool:
    """Board 15's contrast level. High contrast is a modifier on the palette.

    The choice is persisted and applied to the panel at once: turning it on
    swaps every painted colour to the high-contrast palette, turning it off
    restores whatever dark/light theme was underneath. A level that saved to
    the file but did not change what is on screen would be a toggle that
    looks right and does nothing.
    """
    from memory import config_manager

    name = str(level or "").strip().lower()
    high = name == "high"
    try:
        ok = config_manager.save_high_contrast(high)
    except Exception as e:                          # noqa: BLE001
        _say(shell, f"Kontras tidak tersimpan — {type(e).__name__}: {e}")
        return False
    panel = getattr(shell, "_panel", None)
    if panel is not None:
        try:
            panel.set_high_contrast(high)
        except Exception as e:                      # noqa: BLE001
            _say(shell, f"Kontras tidak diterapkan — {type(e).__name__}: {e}")
            return False
    _say(shell, "Kontras tinggi aktif." if high else "Kontras standar.")
    return ok


def motion_toggle(shell: "AmbientShell") -> bool:
    """Board 15's motion switch. The orb reads the same flag on its next frame."""
    from ui import pages_admin

    wanted = not pages_admin.reduced_motion()
    ok = pages_admin.set_reduced_motion(wanted)
    _say(shell, ("Gerak dikurangi." if wanted else "Gerak aktif kembali.")
         if ok else "Pilihan gerak tidak bisa disimpan.")
    return ok


def voice_auth_toggle(shell: "AmbientShell", enabled: bool) -> bool:
    """Board 14's voice-verification switch. Reaches the session, not a store.

    The gate state lives in the running session (main.py), so this calls the
    shell's handler — the same shape `on_wake_toggle` uses. A control that
    flips a switch in the file but never reaches the live session would be a
    toggle that looks on and does nothing.
    """
    handler = getattr(shell, "on_voice_auth_toggle", None)
    if not callable(handler):
        _say(shell, "Verifikasi suara belum tersedia: sesi belum berjalan.")
        return False
    try:
        _say(shell, handler(bool(enabled)))
        return True
    except Exception as e:                      # noqa: BLE001
        _say(shell, f"Verifikasi suara gagal — {type(e).__name__}: {e}")
        return False


def voice_auth_enroll(shell: "AmbientShell") -> bool:
    """Board 14's register-voice button: start collecting samples."""
    handler = getattr(shell, "on_voice_auth_enroll", None)
    if not callable(handler):
        _say(shell, "Verifikasi suara belum tersedia: sesi belum berjalan.")
        return False
    try:
        _say(shell, handler())
        return True
    except Exception as e:                      # noqa: BLE001
        _say(shell, f"Pendaftaran gagal — {type(e).__name__}: {e}")
        return False


def routine_create(shell: "AmbientShell") -> bool:
    """Board 11's builder: turn the schedule field into a stored routine.

    Reads the one-line schedule phrase from the builder field, parses it with
    the pure policy, and writes it through the store — the store is the only
    writer of `memory/routines.json`. A phrase the parser cannot read is
    refused with a sentence rather than stored as a routine that fires wrong.
    """
    from core.routines import Routine, parse_schedule_or_raise
    from memory.routine_store import default_store

    panel = getattr(shell, "_panel", None)
    phrase = ""
    if panel is not None:
        edit = panel._inputs.get("rt_builder_edit")
        if edit is not None:
            try:
                phrase = str(edit.text() or "").strip()
            except Exception:                      # noqa: BLE001
                phrase = ""
    if not phrase:
        _say(shell, "Masukkan jadwal, contoh: setiap hari jam 07")
        return False
    try:
        sched = parse_schedule_or_raise(phrase)
    except ValueError as e:
        _say(shell, str(e))
        return False

    import uuid as _uuid
    routine = Routine(
        id=_uuid.uuid4().hex[:8],
        name=_t("ui.page.routines.named"),
        schedule=sched,
        payload="",
        enabled=True,
    )
    try:
        default_store().add(routine)
    except Exception as e:                          # noqa: BLE001
        _say(shell, f"Rutinitas tidak tersimpan — {type(e).__name__}: {e}")
        return False
    if panel is not None:
        panel.refresh()
    _say(shell, _t("ui.page.routines.created"))
    return True


def routine_toggle(shell: "AmbientShell", index: int) -> bool:
    """Board 11's pause toggle for the routine at `index` in the store."""
    from memory.routine_store import default_store

    routines = default_store().all()
    if index < 0 or index >= len(routines):
        _say(shell, "Tidak ada rutinitas di slot itu.")
        return False
    routine = routines[index]
    toggled = default_store().set_enabled(routine.id, not routine.enabled)
    if toggled is None:
        _say(shell, "Rutinitas tidak bisa diubah.")
        return False
    panel = getattr(shell, "_panel", None)
    if panel is not None:
        panel.refresh()
    _say(shell, _t("ui.page.routines.resumed") if toggled.enabled
        else _t("ui.page.routines.toggled"))
    return True


def routine_delete(shell: "AmbientShell", index: int) -> bool:
    """Board 11's delete for the routine at `index` in the store."""
    from memory.routine_store import default_store

    routines = default_store().all()
    if index < 0 or index >= len(routines):
        _say(shell, "Tidak ada rutinitas di slot itu.")
        return False
    removed = default_store().remove(routines[index].id)
    if not removed:
        _say(shell, "Rutinitas tidak bisa dihapus.")
        return False
    panel = getattr(shell, "_panel", None)
    if panel is not None:
        panel.refresh()
    _say(shell, _t("ui.page.routines.deleted"))
    return True


def voice_auth_delete(shell: "AmbientShell") -> bool:
    """Board 14's delete-voiceprint button (confirm-gated by the page)."""
    handler = getattr(shell, "on_voice_auth_delete", None)
    if not callable(handler):
        _say(shell, "Verifikasi suara belum tersedia: sesi belum berjalan.")
        return False
    try:
        _say(shell, handler())
        return True
    except Exception as e:                      # noqa: BLE001
        _say(shell, f"Voiceprint gagal dihapus — {type(e).__name__}: {e}")
        return False


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


def form_fill_apply(shell: "AmbientShell") -> bool:
    """Board 13's review-and-apply button.

    Reads the page URL and the three field values from the board's inputs,
    builds a :class:`FormFillPlan` with the pure policy, reviews it (the
    "tinjau dulu" gate), then drives the approved plan into the browser session
    through the adapter. The panel's preview strip and field echo are updated
    from the result so the board states what happened.
    """
    from actions.browser_form import fill_form_to_page
    from core.form_fill import FormFillError, FormFillPlan

    panel = getattr(shell, "_panel", None)
    if panel is None:
        return False

    def _read(key: str) -> str:
        edit = panel._inputs.get(key)
        if edit is None:
            return ""
        try:
            return str(edit.text() or "").strip()
        except Exception:                          # noqa: BLE001
            return ""

    url = _read("hp_form_url")
    if not url:
        _say(shell, _t("ui.page.help.form_no_url"))
        return False
    fields = {f"#field{i}": _read(f"hp_form_input:{i}") for i in range(3)}
    try:
        plan = FormFillPlan.build(url, fields).review()
    except FormFillError as e:
        panel._form_fill = {"status": "failed", "detail": str(e), "values": {}}
        panel.refresh()
        _say(shell, str(e))
        return False

    results = fill_form_to_page(plan.page_url, {e.selector: e.value for e in plan.entries})
    failed = [r for r in results if not r.ok]
    panel._form_fill = {
        "status": "failed" if failed else "applied",
        "detail": "; ".join(r.detail for r in failed),
        "values": {str(i): _read(f"hp_form_input:{i}") for i in range(3)},
    }
    panel.refresh()
    if failed:
        _say(shell, _t("ui.page.help.form_failed", detail=panel._form_fill["detail"]))
        return False
    _say(shell, _t("ui.page.help.form_applied"))
    return True


def _phone_session(shell):
    """The panel's pairing session, created on first use.

    The session is a pure-policy :class:`PairingSession` stored on the panel;
    it is the same object the painter reads, so a generate or pair and the
    next repaint agree on state without a second store.
    """
    from core.phone_pairing import PairingSession

    panel = getattr(shell, "_panel", None)
    if panel is None:
        return None, None
    session = getattr(panel, "_phone_pair", None)
    if session is None:
        session = PairingSession()
        panel._phone_pair = session
    return panel, session


def phone_make_code(shell: "AmbientShell") -> bool:
    """Board 16: mint a fresh one-time pairing code.

    A new mint supersedes any pending code, so the box always shows the one
    live code the policy will accept. The code is generated by the policy, not
    typed, so it is one the server's pairing endpoint would accept.
    """
    panel, session = _phone_session(shell)
    if session is None:
        return False
    session.mint_code()
    panel.refresh()
    _say(shell, _t("ui.page.plugins.phone_code_shown",
                  code=session.pending_code.code,
                  secs=int(session.pending_code.expires_at - session._clock())))
    return True


def phone_pair(shell: "AmbientShell") -> bool:
    """Board 16: pair a device against the pending code.

    The device name is a fixed label ("Ponsel") — the panel is the desktop
    side issuing the code, and the phone is the device that consumes it. A
    missing or expired code, or a wrong one, is refused with a sentence.
    """
    panel, session = _phone_session(shell)
    if session is None:
        return False
    code = session.pending_code
    if code is None:
        _say(shell, _t("ui.page.plugins.phone_no_code"))
        return False
    try:
        device = session.consume_code(code.code, "Ponsel")
    except Exception as e:                          # noqa: BLE001
        panel.refresh()
        _say(shell, _t("ui.page.plugins.phone_pair_failed", detail=str(e)))
        return False
    panel.refresh()
    _say(shell, _t("ui.page.plugins.phone_paired_ok", name=device.name))
    return True


def phone_unpair(shell: "AmbientShell") -> bool:
    """Board 16: disconnect the most recently paired device.

    Removes the device from the session so the card returns to the idle state
    and a new code must be minted before another device can pair.
    """
    panel, session = _phone_session(shell)
    if session is None:
        return False
    if not session.devices:
        _say(shell, _t("ui.page.plugins.phone_idle"))
        return False
    removed = session.devices.pop()
    if session.handoff_target == removed.name:
        session.handoff_target = (session.devices[-1].name
                                  if session.devices else None)
    panel.refresh()
    _say(shell, _t("ui.page.plugins.phone_unpaired"))
    return True
