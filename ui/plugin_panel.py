"""Plugin manager presentation and consent on the Qt thread."""
from __future__ import annotations

from ui.page_kit import at, text_box
from ui.tray_pages import PALETTES, _at
from ui.tray_panel_model import _t
from ui.pages_paint_util import _paint_phone_code, _paint_phone_state


def build_plugins(panel, page) -> None:
    """Build the plugin and unavailable-phone sections of board 16."""
    from PyQt6.QtWidgets import QLabel, QPushButton

    page.hide()
    panel._pages["plugins"] = page

    panel._labels["pl_section"] = at(page, QLabel, text_box(24, 92, 10, width=240), "")
    # Three visible rows per page leave room for the phone section.
    panel._labels["pl_more"] = _at(page, QLabel, 95, 311, 270, 24, "")
    def move_page(delta):
        panel._plugin_page = getattr(panel, "_plugin_page", 0) + delta
        panel.refresh()
    for key, x, delta in (("prev", 24, -1), ("next", 374, 1)):
        button = QPushButton("", page)
        button.setGeometry(x, 309, 62, 26)
        button.clicked.connect(lambda _c=False, d=delta: move_page(d))
        panel._buttons[f"pl_{key}"] = button
    for index in range(3):
        y = 106 + index * 70
        panel._labels[f"pl_card:{index}"] = _at(page, QLabel, 24, y, 412, 60, "")
        panel._labels[f"pl_name:{index}"] = at(
            page, QLabel, text_box(44, y + 26, 12.5, width=300), "")
        panel._labels[f"pl_desc:{index}"] = at(
            page, QLabel, text_box(44, y + 45, 10, width=300), "")
        button = QPushButton("", page)
        button.setGeometry(364, y + 17, 60, 26)
        button.clicked.connect(
            lambda _checked=False, i=index: click_plugin(panel, i))
        panel._buttons[f"pl_toggle:{index}"] = button

    # SINKRON PONSEL at 346, the 412x130 card at 360, the phone silhouette at
    # (44,380) and (50,390), the "Putuskan" pill at (120,458).
    panel._labels["pl_phone_header"] = at(page, QLabel, text_box(24, 346, 10, width=300), "")
    panel._labels["pl_phone_card"] = _at(page, QLabel, 24, 360, 412, 130, "")
    panel._labels["pl_phone_shape"] = _at(page, QLabel, 44, 380, 56, 90, "")
    panel._labels["pl_phone"] = _at(page, QLabel, 120, 390, 300, 20, "")
    panel._labels["pl_phone2"] = _at(page, QLabel, 120, 408, 300, 40, "")

    # The divider and the pairing-code box: the box is drawn, the code is not.
    rule = QLabel(page)
    rule.setGeometry(24, 506, 412, 1)
    rule.setStyleSheet(f"background:{PALETTES['dark']['line']};")
    panel._labels["pl_rule"] = rule
    panel._labels["pl_code_header"] = at(page, QLabel, text_box(24, 536, 10, width=300), "")
    # No dashboard-issued pairing code is connected to this panel.
    panel._labels["pl_code_box"] = _at(page, QLabel, 24, 550, 412, 46, "")

    # Retained for wiring compatibility, but hidden and disabled by the painter.
    make_button = QPushButton("", page)
    make_button.setGeometry(24, 604, 138, 28)
    make_button.setObjectName("pl_phone_make")
    make_button.clicked.connect(lambda: panel._call("phone_make_code"))
    panel._buttons["pl_phone_make"] = make_button
    pair_button = QPushButton("", page)
    pair_button.setGeometry(166, 604, 138, 28)
    pair_button.setObjectName("pl_phone_pair")
    pair_button.clicked.connect(lambda: panel._call("phone_pair"))
    panel._buttons["pl_phone_pair"] = pair_button
    unpair_button = QPushButton("", page)
    unpair_button.setGeometry(308, 604, 128, 28)
    unpair_button.setObjectName("pl_phone_unpair")
    unpair_button.clicked.connect(lambda: panel._call("phone_unpair"))
    panel._buttons["pl_phone_unpair"] = unpair_button



def registry_rows(panel):
    """Read the existing runtime registry, never infer loadability from files."""
    provider = panel._actions.get("plugins_list")
    if not callable(provider):
        return None
    try:
        value = provider()
        if not isinstance(value, list) or not all(isinstance(r, dict) for r in value):
            return None
        return [dict(row) for row in value]
    except Exception as exc:  # noqa: BLE001
        print(f"[JARVIS] Plugin registry unavailable: {type(exc).__name__}: {exc}")
        return None


def confirm_enable(panel, row):
    """Ask explicitly with the complete declared permissions; not a sandbox."""
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QMessageBox
    permissions = row.get("permissions") or []
    descriptions = {key: _t(f"ui.page.plugins.permission.{key}") for key in (
        "network", "files", "audio", "input", "shell", "clipboard")}
    details = "\n".join(f"• {permission} — {descriptions[permission]}"
                        if permission in descriptions else f"• {permission}"
                        for permission in permissions)
    if not details:
        details = _t("ui.page.plugins.no_permissions")
    dialog = QMessageBox(panel._window)
    dialog.setIcon(QMessageBox.Icon.Warning)
    dialog.setWindowTitle(_t("ui.page.plugins.confirm_title"))
    dialog.setTextFormat(Qt.TextFormat.PlainText)
    body = _t("ui.page.plugins.confirm_body", name=row["name"], permissions=details)
    if row.get("description"):
        body += "\n\n" + _t("ui.page.plugins.description", description=row["description"])
    if row.get("manifest_note"):
        body += "\n\n" + _t("ui.page.plugins.manifest_note", note=row["manifest_note"])
    dialog.setText(body)
    dialog.setInformativeText(_t("ui.page.plugins.not_sandbox"))
    dialog.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
    dialog.setDefaultButton(QMessageBox.StandardButton.No)
    return dialog.exec() == QMessageBox.StandardButton.Yes


def click_plugin(panel, index):
    rows = getattr(panel, "_plugin_visible", [])
    if not 0 <= index < len(rows):
        return
    row = rows[index]
    if not row.get("available"):
        return
    if not row["enabled"] and not confirm_enable(panel, row):
        panel.refresh()
        return
    panel._call("plugin_toggle", row["name"], row["enabled"], tuple(row["permissions"]))
    panel.refresh()


def paint_plugins(panel, snap) -> None:
    from collections import Counter
    from PyQt6.QtCore import Qt
    from ui.plugin_labels import label_for

    labels, buttons = panel._labels, panel._buttons
    rows = registry_rows(panel)
    unavailable = rows is None
    rows = rows or []
    counts = Counter(str(row.get("name") or "") for row in rows)
    total_pages = max(1, (len(rows) + 2) // 3)
    page = max(0, min(getattr(panel, "_plugin_page", 0), total_pages - 1))
    panel._plugin_page = page
    visible = []
    pal = PALETTES[getattr(panel, "_theme", "dark")]
    labels["pl_section"].setText(_t("ui.page.plugins.section"))
    labels["subtitle"].setText(_t("ui.page.plugins.registry_unavailable") if unavailable else
                               _t("ui.page.plugins.subtitle", on=sum(
                                   bool(row.get("valid") and row.get("enabled")) for row in rows),
                                  total=len(rows)))
    for index in range(3):
        row = rows[page * 3 + index] if page * 3 + index < len(rows) else None
        for part in ("card", "name", "desc"):
            labels[f"pl_{part}:{index}"].setVisible(row is not None)
        button = buttons[f"pl_toggle:{index}"]
        button.setVisible(row is not None)
        if row is None:
            button.setEnabled(False)
            labels[f"pl_name:{index}"].setText("")
            labels[f"pl_desc:{index}"].setText("")
            continue
        name = str(row.get("name") or "")
        permissions = row.get("permissions")
        valid_permissions = isinstance(permissions, (list, tuple)) and all(
            isinstance(p, str) for p in permissions)
        available = bool(name and row.get("valid") is True and counts[name] == 1 and valid_permissions)
        enabled = bool(row.get("enabled")) if available else False
        visible.append({"name": name, "available": available, "enabled": enabled,
                        "permissions": list(permissions) if valid_permissions else [],
                        "description": str(row.get("description") or ""),
                        "manifest_note": str(row.get("manifest_note") or "")})
        name_label = labels[f"pl_name:{index}"]
        name_label.setTextFormat(Qt.TextFormat.PlainText)
        name_label.setText(_t(label_for(name)) if label_for(name) else name)
        desc = labels[f"pl_desc:{index}"]
        desc.setTextFormat(Qt.TextFormat.PlainText)
        desc.setText(_t("ui.page.plugins.declared", permissions=", ".join(permissions))
                     if available and permissions else _t("ui.page.plugins.no_permissions")
                     if available else _t("ui.page.plugins.unavailable"))
        detail = str(row.get("error") or row.get("description") or "")
        desc.setToolTip(detail)
        labels[f"pl_card:{index}"].setStyleSheet(
            f"background:{pal['card']};border:1px solid {pal['line']};border-radius:12px;")
        button.setCheckable(True)
        button.setChecked(enabled)
        button.setEnabled(available and callable(panel._actions.get("plugin_toggle")))
        button.setText("ON" if enabled else "OFF" if available else "—")
        edge = pal["accent"] if enabled else pal["line"]
        button.setStyleSheet(f"text-align:center;padding:0;border:1px solid {edge};"
                             f"border-radius:10px;background:{pal['card']};color:{pal['text']};")
        button.setAccessibleName(f"{name}: {button.text()}")
        button.setToolTip(detail if not available else _t("ui.page.plugins.toggle_hint"))
    panel._plugin_visible = visible
    labels["pl_more"].setText(_t("ui.page.plugins.page", page=page + 1,
                                    total=total_pages, count=len(rows)) if not unavailable else "")
    for key, enabled in (("prev", page > 0), ("next", page + 1 < total_pages)):
        button = buttons[f"pl_{key}"]
        label = _t(f"ui.page.routines.{key}")
        button.setText("‹" if key == "prev" else "›")
        button.setToolTip(label)
        button.setAccessibleName(label)
        button.setEnabled(enabled and not unavailable)
        button.setStyleSheet("text-align:center;padding:0;")
    labels["pl_rule"].setStyleSheet(f"background:{pal['line']};")
    labels["pl_phone_header"].setText(_t("ui.page.plugins.phone"))
    labels["pl_phone_card"].setStyleSheet(
        f"background:{pal['card']};border:1px solid {pal['line']};border-radius:12px;")
    _paint_phone_state(panel, labels, pal)
    labels["pl_code_header"].setText(_t("ui.page.plugins.code"))
    labels["pl_code_box"].setStyleSheet(
        f"background:{pal['card']};border-radius:10px;border:1px solid {pal['line']};"
        f"padding-left:18px;color:{pal['muted']};")
    labels["pl_code_box"].setText(_paint_phone_code(panel))
