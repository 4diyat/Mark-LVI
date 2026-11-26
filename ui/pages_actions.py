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


def _refresh(shell) -> None:
    """Repaint the panel if it is attached, or do nothing if it is not."""
    panel = getattr(shell, "_panel", None)
    if panel is not None:
        panel.refresh()


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


def _clipboard_set(shell, text, done, fail) -> bool:
    """Write `text` to the clipboard, reporting the result either way."""
    try:
        from actions import computer_control

        computer_control.pyperclip.copy(text)
    except Exception as e:                       # noqa: BLE001
        _say(shell, f"{fail} — {type(e).__name__}: {e}")
        return False
    _say(shell, done)
    return True


def tools_copy(shell: "AmbientShell") -> bool:
    """Board 12's "Salin": put the clipboard text back where it came from."""
    from ui import pages_people
    text = pages_people.clipboard_text()
    if not text:
        _say(shell, "Clipboard tidak tersedia." if text is None else "Clipboard teks kosong.")
        return False
    return _clipboard_set(shell, text, "Disalin.", "Clipboard tidak bisa ditulis")


def tools_layout(shell: "AmbientShell", index: int) -> bool:
    from actions.window_layout import apply, choose
    modes = ("columns2", "columns3", "focus")
    try:
        index = int(index)
        if not 0 <= index < len(modes):
            return False
        decision = choose(modes[index])
    except (TypeError, ValueError):
        return False
    if not apply(decision):
        _say(shell, decision.reason)
        return False
    _refresh(shell)
    from ui.tray_panel_model import _t
    _say(shell, _t("ui.page.tools.snap_saved"))
    return decision.allowed


def tools_clear(shell: "AmbientShell") -> bool:
    """Board 12's "Bersihkan": empty the clipboard."""
    from ui import clipboard_view
    return clipboard_view.clear_current(shell, _say, _clipboard_set)


def tools_mark_safe(shell: "AmbientShell") -> bool:
    """Board 12's "Tandai aman" — a decision that lasts this session."""
    from ui import clipboard_view
    return clipboard_view.mark_safe(shell, _say)


def plugin_toggle(shell: "AmbientShell", name: str, expected_on: bool,
                  permissions: tuple[str, ...]) -> bool:
    """Change the displayed plugin only if the reviewed registry state is current."""
    from ui import pages_admin

    try:
        provider = getattr(shell, "get_plugins", None)
        records = provider() if callable(provider) else None
        matches = [row for row in records if isinstance(row, dict) and row.get("name") == name]
        row = matches[0] if len(matches) == 1 else None
        if (not row or row.get("valid") is not True
                or bool(row.get("enabled")) != expected_on
                or tuple(row.get("permissions") or ()) != permissions):
            raise ValueError("plugin state changed or is unavailable")
    except Exception as exc:  # noqa: BLE001
        _say(shell, _t("ui.page.plugins.changed"))
        print(f"[JARVIS] Plugin change refused: {type(exc).__name__}: {exc}")
        return False
    if not pages_admin.set_plugin(name, not expected_on):
        _say(shell, _t("ui.page.plugins.save_failed"))
        return False
    reconnect = getattr(shell, "on_plugins_changed", None)
    try:
        if callable(reconnect):
            reconnect()
        else:
            _say(shell, _t("ui.page.plugins.reconnect_unavailable"))
    except Exception as exc:  # noqa: BLE001
        _say(shell, _t("ui.page.plugins.reconnect_unavailable"))
        print(f"[JARVIS] Plugin reconnect failed: {type(exc).__name__}: {exc}")
    return True


def consent_answer(shell: "AmbientShell", allowed: bool) -> bool:
    """Board 7's Allow / Not now, recorded once."""
    from ui import pages_people

    ok = pages_people.record_consent(bool(allowed))
    _say(shell, "Izin mikrofon tercatat." if ok and allowed
        else ("Dilewati." if ok else "Izin tidak bisa disimpan."))
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
        checked = panel._buttons.get("cn_toggle") if panel else None
        decision = {"welcome": "next", "done": "finish",
                    "mic": bool(checked and checked.isChecked())}.get(step)
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
                          max(0, flow.current_index - 1))  # back, recorded nothing
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


def language_set(shell: "AmbientShell", code: str) -> bool:
    """Board 15's language segment. Returns whether the switch took."""
    from ui import pages_admin
    active = pages_admin.set_language(str(code))
    ok = active == str(code)
    _refresh(shell)
    _say(shell, f"Bahasa: {active}." if ok else f"Bahasa {code!r} tidak tersedia.")
    return ok


def text_scale_set(shell: "AmbientShell", scale: float) -> bool:
    """The stored preference is not yet applied by the panel renderer."""
    _say(shell, _t("ui.page.access.size.unavailable"))
    return False


def contrast_set(shell: "AmbientShell", level: str) -> bool:
    """Board 15's contrast level. High contrast is a modifier on the palette."""
    from memory import config_manager

    level = str(level or "").strip().lower()
    if level not in ("standard", "high"):
        _say(shell, "Pilihan kontras tidak dikenal.")
        return False
    high = level == "high"
    try:
        ok = config_manager.save_high_contrast(high)
    except Exception as e:                          # noqa: BLE001
        _say(shell, f"Kontras tidak tersimpan — {type(e).__name__}: {e}")
        return False
    if not ok:
        _say(shell, "Kontras tidak tersimpan.")
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
    """No orb animation reads the persisted preference yet."""
    _say(shell, _t("ui.page.access.motion.unavailable"))
    return False


def gesture_rebind(shell: "AmbientShell", index: int) -> bool:
    """Gesture controllers do not consume the saved binding table."""
    _say(shell, _t("ui.page.access.gesture.unavailable"))
    return False


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
    """Save an explicit daily local time and non-empty assistant command."""
    import re
    from uuid import uuid4
    from core.routines import Routine, Schedule
    from memory.routine_store import default_store

    panel = getattr(shell, "_panel", None)
    if panel is None:
        return False
    time_field = panel._inputs.get("rt_builder_edit")
    command_field = panel._inputs.get("rt_builder_command")
    if time_field is None or command_field is None:
        return False
    def report(key):
        message = _t(key)
        panel._labels["rt_builder_status"].setText(message)
        _say(shell, message)

    time_text = str(time_field.text() or "").strip()
    command = str(command_field.text() or "").strip()
    if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", time_text):
        report("ui.page.routines.invalid_time")
        return False
    if not command:
        report("ui.page.routines.command_required")
        return False
    routine = Routine(id=uuid4().hex, name=command[:60],
                      schedule=Schedule(time_text), payload=command, enabled=True)
    try:
        store = default_store()
        if store.add(routine) != routine:
            raise RuntimeError("duplicate routine id")
    except Exception as exc:  # noqa: BLE001
        report("ui.page.routines.create_failed")
        _say(shell, f"Routine store: {type(exc).__name__}")
        return False
    try:
        rows = store.all()
        index = next(i for i, row in enumerate(rows) if row.id == routine.id)
        panel._routine_page = index // 3
    except Exception as exc:  # the write succeeded; do not claim it failed
        _say(shell, f"Routine list refresh: {type(exc).__name__}")
    time_field.clear()
    command_field.clear()
    panel.refresh()
    report("ui.page.routines.created")
    return True


def routine_toggle(shell: "AmbientShell", routine_id: str, enabled: bool) -> bool:
    """Change the routine identified by the painted row, not a moving index."""
    from memory.routine_store import default_store
    if not isinstance(routine_id, str) or not routine_id:
        return False
    try:
        toggled = default_store().set_enabled(routine_id, bool(enabled))
    except Exception as exc:  # noqa: BLE001
        _say(shell, f"Rutinitas tidak bisa diubah — {type(exc).__name__}.")
        return False
    if toggled is None:
        _say(shell, "Rutinitas tidak ditemukan.")
        return False
    _refresh(shell)
    _say(shell, _t("ui.page.routines.resumed") if toggled.enabled
        else _t("ui.page.routines.toggled"))
    return True


def routine_delete(shell: "AmbientShell", routine_id: str) -> bool:
    """Delete only the identity shown in the row at the time it was painted."""
    from memory.routine_store import default_store
    if not isinstance(routine_id, str) or not routine_id:
        return False
    try:
        removed = default_store().remove(routine_id)
    except Exception as exc:  # noqa: BLE001
        _say(shell, f"Rutinitas tidak bisa dihapus — {type(exc).__name__}.")
        return False
    if not removed:
        _say(shell, "Rutinitas tidak ditemukan.")
        return False
    _refresh(shell)
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
    """The panel has no reviewed, same-page form filling integration."""
    _say(shell, _t("ui.page.help.form_unavailable"))
    return False


def _phone_unavailable(shell) -> bool:
    # A local policy object is not a network pairing or a connected device.
    _say(shell, _t("ui.page.plugins.phone_panel_unavailable"))
    return False


def phone_make_code(shell: "AmbientShell") -> bool:
    return _phone_unavailable(shell)


def phone_pair(shell: "AmbientShell") -> bool:
    return _phone_unavailable(shell)


def phone_unpair(shell: "AmbientShell") -> bool:
    return _phone_unavailable(shell)


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
