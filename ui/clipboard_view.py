"""Clipboard card rendering and the session-only acknowledgement."""
from __future__ import annotations

from ui.tray_panel_model import _t


def paint_clipboard(panel, text: str | None) -> None:
    from ui.pages_people import sensitive_kind

    if text != getattr(panel, "_marked_text", None):
        panel._marked_text = text
        panel._marked_safe = False
    if text is None:
        preview = _t("ui.page.tools.unavailable_clip")
    elif not text:
        preview = _t("ui.page.tools.empty_clip")
    else:
        # A single-line preview, bounded so a huge clipboard doesn't clog Qt.
        preview = " ".join(text.splitlines())[:40]
        if len(text) > 40:
            preview += "…"
    panel._labels["tl_clip"].setText(preview)
    kind = sensitive_kind(text) if text and not getattr(panel, "_marked_safe", False) else ""
    panel._labels["tl_kind"].setText(
        _t("ui.page.tools.sensitive", what=_t(kind)) if kind
        else (_t("ui.page.tools.marked_safe") if text and getattr(panel, "_marked_safe", False)
              else (_t("ui.page.tools.not_sensitive") if text else "")))
    for name, key in (("copy", "copy"), ("safe", "mark_safe"), ("clear", "clear")):
        button = panel._buttons[f"tl_{name}"]
        button.setText(_t(f"ui.page.tools.{key}"))
        button.setEnabled(bool(text))


def mark_safe(shell, say) -> bool:
    """Acknowledge only the exact text that was visible when the user clicked."""
    from ui import pages_people

    panel = getattr(shell, "_panel", None)
    if panel is None:
        return False
    current = pages_people.clipboard_text()
    if not current or current != getattr(panel, "_marked_text", None):
        panel.refresh()
        say(shell, _t("ui.page.tools.clipboard_changed"))
        return False
    panel._marked_safe = True
    panel.refresh()
    say(shell, _t("ui.page.tools.marked_safe"))
    return True


def clear_current(shell, say, write) -> bool:
    """Refuse to clear when the last preview is no longer current."""
    from ui import pages_people

    panel = getattr(shell, "_panel", None)
    if panel is None:
        return False
    current = pages_people.clipboard_text()
    if not current or current != getattr(panel, "_marked_text", None):
        panel.refresh()
        say(shell, _t("ui.page.tools.clipboard_changed"))
        return False
    ok = write(shell, "", _t("ui.page.tools.cleared"), _t("ui.page.tools.clear_failed"))
    panel.refresh()
    return ok
