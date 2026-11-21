"""The FLOAT DOCUMENTS row in the CONTROLS drawer.

WHY THIS IS A SEPARATE ROW FROM `FLOAT WIDGETS`
    They look alike and answer different questions. `FLOAT WIDGETS` is one
    switch for the captions — a widget that exists for the whole run. A document
    is created LATER, by a plugin, and there may be none, one, or five. A single
    on/off button would have to mean something different every time it was
    drawn, which is how a status light starts lying.

    So this row reports and acts on a LIST: it says how many documents could
    float and how many are out, it floats everything that can when pressed, and
    it never claims a number it did not count.

WHY IT ASKS THE WINDOW EVERY TIME IT IS PAINTED
    The drawer is rebuilt on every open (`ui/window.py`), and documents come and
    go between opens. Caching the list here would be a row that offers to float
    an editor that was closed ten minutes ago.
"""
from __future__ import annotations

from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QPushButton

from core.i18n import label as _t


def _panel(window):
    panel = getattr(window, "_floating_docs", None)
    if panel is not None:
        return panel
    from ui.floating_documents import FloatingDocuments

    panel = FloatingDocuments(window)
    window._floating_docs = panel
    return panel


def candidates(window) -> list[tuple[str, object, str]]:
    """`(doc_id, subwindow, kind)` for every document that may float.

    Read from the window's own registry, which is what `show_document` fills
    in — no second list to keep in step.
    """
    found = []
    documents = getattr(window, "_workspace_documents", None)
    if not isinstance(documents, dict):
        return found
    for doc_id, entry in list(documents.items()):
        try:
            kind, sub = entry
        except (TypeError, ValueError):
            continue
        if sub is None:
            continue
        found.append((str(doc_id), sub, str(kind)))
    return found


def candidates_for(window, kind: str) -> list[tuple]:
    """The open documents of ONE kind — for the plugin manager's row labels."""
    return [item for item in candidates(window) if item[2] == kind]


def _floatable(window) -> list[tuple[str, object, str]]:
    panel = _panel(window)
    return [item for item in candidates(window) if panel.may_float(item[2]).allowed]


def paint(button: QPushButton, window) -> None:
    """Repaint from what is open and what is out. Called on build and on press."""
    from ui.theme import C

    panel = _panel(window)
    out = panel.count()
    ready = len(_floatable(window))
    button.setFont(QFont("Courier New", 7))
    button.setStyleSheet(f"""
        QPushButton {{ background: {'#001a20' if out else 'transparent'};
            color: {C.PRI if out else C.TEXT_DIM};
            border: 1px solid {C.PRI if out else C.BORDER}; border-radius: 3px;
            text-align: left; padding: 0 8px; }}
        QPushButton:hover {{ color: {C.WHITE if out else C.TEXT};
            border: 1px solid {C.BORDER_B}; }}""")
    key = "ui.floating_documents.on" if out else "ui.floating_documents.off"
    button.setText(_t(key).replace("{n}", str(out)).replace("{ready}", str(ready)))
    button.setToolTip(_t("ui.floating_documents.hint"))
    # Nothing to float and nothing out: disabled, because a live button that
    # reports "0 of 0" is a button whose only possible outcome is a log line.
    button.setEnabled(bool(out or ready))


def toggle(button: QPushButton, window) -> int:
    """Float every document that may float; if any are out, bring them all back.

    ALL OR NOTHING, and that is deliberate: a per-document menu inside a drawer
    row would need a submenu the drawer does not have, and the user can always
    drop them all and float the one they wanted again.
    """
    panel = _panel(window)
    if panel.count():
        panel.recall_all()
    else:
        floatable = _floatable(window)
        if not floatable:
            panel.say(_t("ui.floating_documents.none"))
        for doc_id, sub, kind in floatable:
            panel.float(doc_id, sub, kind)
    paint(button, window)
    return panel.count()


def build_floating_documents_button(layout, row_factory, window) -> QPushButton:
    """Add the FLOAT DOCUMENTS row to `layout` and return the button."""
    button = row_factory(QPushButton())
    button.clicked.connect(lambda: toggle(button, window))
    paint(button, window)
    return button


__all__ = ["build_floating_documents_button", "candidates", "candidates_for",
           "paint", "toggle"]
