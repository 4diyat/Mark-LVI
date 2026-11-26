"""Helper painters shared by the board painters in :mod:`ui.pages_paint`.

These routines write text and state to the panel widgets. They are split out of ``pages_paint.py`` to keep
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
    """The panel is not connected to the dashboard's pairing transport."""
    labels["pl_phone"].setText(_t("ui.page.plugins.phone_panel_unavailable"))
    labels["pl_phone2"].setText(_t("ui.page.plugins.phone_status_unknown"))
    labels["pl_phone2"].setWordWrap(True)
    labels["pl_phone_shape"].setStyleSheet(
        f"background:{pal['panel']};border-radius:10px;border:1px solid {pal['line']};")
    for key in ("pl_phone_make", "pl_phone_pair", "pl_phone_unpair"):
        panel._buttons[key].setEnabled(False)
        panel._buttons[key].hide()


def _paint_phone_code(panel) -> str:
    """No dashboard-issued code is connected to this panel."""
    return _t("ui.page.plugins.phone_code_unavailable")


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
