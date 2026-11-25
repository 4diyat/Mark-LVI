"""Helper painters shared by the board painters in :mod:`ui.pages_paint`.

These four routines are pure text/state writers — they read the panel's
labels (and, for the phone pairing, the panel's pairing session) and write
the right sentence or glyph. They are split out of ``pages_paint.py`` to keep
that module under the project's per-module line ceiling; they have no
rendering concerns of their own.
"""
from __future__ import annotations

from ui.tray_panel_model import _t


def _keyed(labels, prefix, count, text_key) -> None:
    """Write each row's text, reading its own i18n key off the label."""
    for index in range(count):
        widget = labels.get(f"{prefix}:{index}")
        if widget is None:
            continue
        key = getattr(widget, "_key", "") or text_key
        widget.setText(_t(key))


def _paint_phone_state(panel, labels, pal) -> None:
    """Board 16's phone card: paired device, or the idle sentence."""
    session = getattr(panel, "_phone_pair", None)
    devices = getattr(session, "devices", []) if session is not None else []
    paired = bool(devices)
    fill = pal["accent"] if paired else pal["panel"]
    labels["pl_phone"].setText(_t("ui.page.plugins.phone_paired", name=devices[-1].name)
                               if paired else _t("ui.page.plugins.phone_idle"))
    labels["pl_phone2"].setText(_t("ui.page.plugins.phone_connected_short") if paired else "")
    labels["pl_phone_shape"].setStyleSheet(
        f"background:{fill};border-radius:10px;border:1px solid {pal['line']};")


def _paint_phone_code(panel) -> str:
    """Board 16's pairing-code box: the live code, or the no-code sentence."""
    session = getattr(panel, "_phone_pair", None)
    code = getattr(session, "pending_code", None) if session is not None else None
    if code is None:
        return _t("ui.page.plugins.phone_no_code")
    remaining = max(0, int(code.expires_at - session._clock()))
    return _t("ui.page.plugins.phone_code_shown", code=code.code, secs=remaining)


def _paint_install_status(panel, labels) -> None:
    """Board 22's installer strip: the pending count, or the ready sentence."""
    labels["in_status_header"].setText(_t("ui.page.installer.status"))
    state = getattr(panel, "_install_state", None)
    if state is None:
        return
    status = state.get("status")
    if status == "installed":
        labels["in_status"].setText(_t("ui.page.installer.installed"))
    elif status == "running":
        labels["in_status"].setText(
            _t("ui.page.installer.installing", count=state.get("count", 0)))
    else:
        labels["in_status"].setText(
            _t("ui.page.installer.needs_review", count=state.get("count", 0)))
