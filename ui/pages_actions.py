"""The board pages' actions: one function per store-write a board control reaches.

These were split out of `tray_panel_wiring`, which was near the 600-line
ceiling before the board pages added their handlers. The split is not "misc":
every function here exists because a BOARD PAGE needs it, and each is a store
write reached by a click — it reaches the store through its own writer, returns
a bool that means what it says, and says one sentence through `_say`.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ui.shell import AmbientShell


def _say(shell: "AmbientShell", text: str) -> None:
    """One line to the user, through the ONE path the shell already has."""
    from ui.lifecycle import note

    note(shell, text)


def _t(key: str, **fields) -> str:
    """`core.i18n.label` with a fallback, so a missing catalogue key still."""
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
    if ok and panel is not None:  # the detail page describes a memory that is gone
        panel.set_page("memory")
    return ok


def memory_clear(shell: "AmbientShell") -> bool:
    """Board 9's "Hapus semua": every remembered fact, one at a time."""
    from ui import pages_memory

    rows = pages_memory.entries()
    if not rows:
        _say(shell, "Tidak ada memori untuk dihapus.")
        return False
    gone = 0
    for row in rows:
        ok, _m = pages_memory.forget(str(row.get("category") or ""),
                                     str(row.get("key") or ""))
        gone += 1 if ok else 0
    _say(shell, f"{gone} dari {len(rows)} memori dihapus.")
    return gone == len(rows)


def routines_pause(shell: "AmbientShell") -> bool:
    """Board 11's pause, through the engine's own persisted flag."""
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
    """Board 12's "Salin": put the clipboard text back where it came from."""
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


def tools_layout(shell: "AmbientShell", index: int) -> bool:
    """Board 12's susun-jendela: pick one of the three layout thumbnails."""
    from actions.window_layout import apply, choose
    modes = ("columns2", "columns3", "focus")
    try:
        decision = choose(modes[int(index)])
    except (IndexError, TypeError, ValueError):
        return False
    if not apply(decision):
        _say(shell, decision.reason)
        return False
    panel = getattr(shell, "_panel", None)
    if panel is not None:
        panel.refresh()
    _say(shell, decision.reason)
    return decision.allowed


def tools_clear(shell: "AmbientShell") -> bool:
    """Board 12's "Bersihkan": empty the clipboard."""
    try:
        from actions import computer_control

        computer_control.pyperclip.copy("")
    except Exception as e:                       # noqa: BLE001
        _say(shell, f"Clipboard tidak bisa dikosongkan — {type(e).__name__}: {e}")
        return False
    _say(shell, "Clipboard dikosongkan.")
    return True


def tools_mark_safe(shell: "AmbientShell") -> bool:
    """Board 12's "Tandai aman" — a decision that lasts this session."""
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


def _onboarding_state(shell):
    """(panel, flow): the panel and its live walk, started fresh each open."""
    panel = getattr(shell, "_panel", None)
    if panel is None:
        return None, None
    flow = getattr(panel, "_onboarding", None)
    if flow is None:  # a walk is a transient fact, not a stored one
        from core.onboarding import Onboarding
        flow = Onboarding.start()
        panel._onboarding = flow
    return panel, flow


def _finish_onboarding(shell, flow, message: str) -> None:
    """Store the flow on the panel, say it, and repaint."""
    panel = getattr(shell, "_panel", None)
    if panel is None:
        return
    panel._onboarding = flow
    panel.refresh()
    _say(shell, message)


def onboard_next(shell: "AmbientShell") -> bool:
    """Board 7: advance the onboarding ladder to the next step."""
    from actions.onboarding import answer_step

    panel, flow = _onboarding_state(shell)
    if flow is None:
        return False
    step = flow.current
    if step == "presence":
        picked = getattr(panel, "_onboarding_picked", None) if panel else None
        if not picked:  # never record a default the user did not choose
            _say(shell, _t("ui.page.consent.presence.pick"))
            return False
        decision = str(picked)
    else:
        decision = {"welcome": "next", "done": "finish",
                    "mic": bool(_toggle_checked(shell))}.get(step)
    new_flow, ok = answer_step(flow, decision)
    if ok:
        _finish_onboarding(shell, new_flow, _t("ui.page.consent.done"))
    return ok


def onboard_back(shell: "AmbientShell") -> bool:
    """Board 7: go back to the previous step, or skip the microphone step."""
    from core.onboarding import MIC, Onboarding

    panel, flow = _onboarding_state(shell)
    if flow is None or flow.current_index <= 0:
        return False
    if flow.current == MIC:  # a skip records a refused consent
        from actions.onboarding import answer_step
        new_flow, ok = answer_step(flow, False)
        if ok:
            _finish_onboarding(shell, new_flow, _t("ui.page.consent.deny"))
        return ok
    new_flow = Onboarding(flow._done, flow._skipped, flow.presence_mode,
                          max(0, flow.current_index - 1))  # back, nothing recorded
    _finish_onboarding(shell, new_flow, "")
    return True


def onboard_toggle(shell: "AmbientShell") -> bool:
    """Board 7: the presence-mode selector on the presence step."""
    from core.onboarding import PRESENCE

    panel, flow = _onboarding_state(shell)
    if flow is None or flow.current != PRESENCE:
        return False
    modes = ("active", "focus", "quiet")
    current = getattr(panel, "_onboarding_picked", None) or "active"
    idx = modes.index(current) if current in modes else 0
    picked = modes[(idx + 1) % len(modes)]
    panel._onboarding_picked = picked
    panel._labels["cn_ack"].setText(_t("ui.page.consent.presence.selected",
                                       mode=_t(f"ui.page.consent.presence.{picked}")))
    return True


def _toggle_checked(shell) -> bool:
    """Whether the consent toggle is checked, read off the panel widget."""
    panel = getattr(shell, "_panel", None)
    button = panel._buttons.get("cn_toggle") if panel else None
    return bool(button and button.isChecked())


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
    """Board 15's contrast level. High contrast is a modifier on the palette."""
    from memory import config_manager

    high = str(level or "").strip().lower() == "high"
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


def _voice_auth_call(shell, method: str, *args, fail: str = "Verifikasi suara gagal") -> bool:
    """One voice-auth handler: reach the session, report every failure path."""
    handler = getattr(shell, method, None)
    if not callable(handler):  # the session, not the store, owns the voiceprint
        _say(shell, "Verifikasi suara belum tersedia: sesi belum berjalan.")
        return False
    try:
        _say(shell, handler(*args))
        return True
    except Exception as e:                      # noqa: BLE001
        _say(shell, f"{fail} — {type(e).__name__}: {e}")
        return False


def voice_auth_toggle(shell: "AmbientShell", enabled: bool) -> bool:
    """Board 14's voice-verification switch. Reaches the session, not a store."""
    return _voice_auth_call(shell, "on_voice_auth_toggle", bool(enabled))


def voice_auth_enroll(shell: "AmbientShell") -> bool:
    """Board 14's register-voice button: start collecting samples."""
    return _voice_auth_call(shell, "on_voice_auth_enroll")


def routine_create(shell: "AmbientShell") -> bool:
    """Board 11's builder: turn the schedule field into a stored routine."""
    from core.routines import Routine, parse_schedule_or_raise
    from memory.routine_store import default_store

    panel = getattr(shell, "_panel", None)
    phrase = ""
    edit = panel._inputs.get("rt_builder_edit") if panel else None
    try:
        phrase = str(edit.text() or "").strip() if edit else ""
    except Exception:                              # noqa: BLE001
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
    toggled = default_store().set_enabled(routines[index].id,
                                          not routines[index].enabled)
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
    return _voice_auth_call(shell, "on_voice_auth_delete",
                            fail="Voiceprint gagal dihapus")


def install_mode(shell: "AmbientShell", index: int) -> bool:
    """Board 22's mode choice, through `presence_mode` like every other switch."""
    from ui import pages_admin
    from ui.tray_panel_wiring import set_presence

    try:
        mode = str(pages_admin.modes()[int(index)][0])
    except (IndexError, TypeError, ValueError):
        return False
    return bool(set_presence(shell, mode))


def form_fill_apply(shell: "AmbientShell") -> bool:
    """Board 13's review-and-apply button."""
    from actions.browser_form import fill_form_to_page
    from core.form_fill import FormFillError, FormFillPlan

    panel = getattr(shell, "_panel", None)
    if panel is None:
        return False

    def _read(key: str) -> str:
        edit = panel._inputs.get(key)
        try:
            return str(edit.text() or "").strip() if edit is not None else ""
        except Exception:                          # noqa: BLE001
            return ""

    values = {f"hp_form_input:{i}": _read(f"hp_form_input:{i}") for i in range(3)}
    url = _read("hp_form_url")
    if not url:
        _say(shell, _t("ui.page.help.form_no_url"))
        return False
    fields = {f"#field{i}": v for i, v in enumerate(values.values())}
    try:
        plan = FormFillPlan.build(url, fields).review()
    except FormFillError as e:
        panel._form_fill = {"status": "failed", "detail": str(e), "values": {}}
        panel.refresh()
        _say(shell, str(e))
        return False

    failed = [r for r in fill_form_to_page(
        plan.page_url, {e.selector: e.value for e in plan.entries}) if not r.ok]
    panel._form_fill = {
        "status": "failed" if failed else "applied",
        "detail": "; ".join(r.detail for r in failed),
        "values": values,
    }
    panel.refresh()
    if failed:
        _say(shell, _t("ui.page.help.form_failed", detail=panel._form_fill["detail"]))
        return False
    _say(shell, _t("ui.page.help.form_applied"))
    return True


def _phone_session(shell):
    """The panel's pairing session, created on first use."""
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
    """Board 16: mint a fresh one-time pairing code."""
    panel, session = _phone_session(shell)
    if session is None:
        return False
    session.mint_code()
    panel.refresh()
    code = session.pending_code
    _say(shell, _t("ui.page.plugins.phone_code_shown", code=code.code,
                  secs=int(code.expires_at - session._clock())))
    return True


def phone_pair(shell: "AmbientShell") -> bool:
    """Board 16: pair a device against the pending code."""
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
    """Board 16: disconnect the most recently paired device."""
    panel, session = _phone_session(shell)
    if session is None or not session.devices:
        _say(shell, _t("ui.page.plugins.phone_idle"))
        return False
    removed = session.devices.pop()
    if session.handoff_target == removed.name:
        session.handoff_target = (session.devices[-1].name
                                  if session.devices else None)
    panel.refresh()
    _say(shell, _t("ui.page.plugins.phone_unpaired"))
    return True


def installer_run(shell: "AmbientShell") -> bool:
    """Board 22: build, review, and run the dependency install plan."""
    from actions.installer_plan import run_install_plan
    from core.install_plan import InstallError, InstallPlan
    from core.installer import _available
    from memory.config_manager import load_api_keys
    panel = getattr(shell, "_panel", None)
    if panel is None:
        return False
    try:
        plan = InstallPlan.build(load_api_keys() or {}, _available).review()
    except InstallError as e:
        panel._install_state = {"status": "failed", "count": 0, "detail": str(e)}
        panel.refresh()
        _say(shell, str(e))
        return False

    count = len(plan.missing)
    panel._install_state = {"status": "installed", "count": count}
    panel.refresh()
    if not plan.needs_install:
        _say(shell, _t("ui.page.installer.all_present"))
        return True
    failed = [r for r in run_install_plan(plan) if not r.ok]
    panel._install_state = {"status": "installed" if not failed else "failed",
                            "count": count,
                            "detail": "; ".join(r.detail for r in failed)}
    panel.refresh()
    if failed:
        _say(shell, f"Instal gagal: {panel._install_state['detail']}")
        return False
    _say(shell, _t("ui.page.installer.installed"))
    return True


def _os_control_apply(shell, decision) -> bool:
    """Store a switch decision on the panel and report it; False if unwired."""
    panel = getattr(shell, "_panel", None)
    if panel is None:
        return False
    panel._os_control = {"enabled": decision.desired if decision.allowed
                         else decision.current, "reason": decision.reason}
    panel.refresh()
    _say(shell, decision.reason)
    return decision.allowed


def os_control_toggle(shell: "AmbientShell") -> bool:
    """Board 14's OS-control switch: request a change, gated by policy."""
    from actions.os_control import read_state, toggle

    return _os_control_apply(shell, toggle(not read_state(), confirmed=False))


def os_control_confirm(shell: "AmbientShell") -> bool:
    """Board 14's physical confirmation: the keystroke that arms OS control."""
    from actions.os_control import enable

    return _os_control_apply(shell, enable(confirmed=True))
