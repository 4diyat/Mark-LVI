"""Undo history cards: identity-safe actions and non-blocking callbacks."""
from __future__ import annotations

from ui.tray_pages import PALETTES, PAGE_HISTORY, _at
from ui.tray_panel_model import _t


def build_history(panel, page) -> None:
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QLabel, QPushButton

    page.hide()
    panel._pages[PAGE_HISTORY] = page
    panel._labels['history_count'] = _at(page, QLabel, 24, 46, 412, 20, '')
    for index in range(4):
        y = 82 + index * 78
        panel._labels[f'history_card:{index}'] = _at(page, QLabel, 24, y, 412, 70, '')
        dot = _at(page, QLabel, 40, y + 18, 10, 10, '')
        panel._labels[f'history_dot:{index}'] = dot
        label = _at(page, QLabel, 60, y + 9, 248, 25, '')
        label.setTextFormat(Qt.TextFormat.PlainText)
        panel._labels[f'history:{index}'] = label
        panel._labels[f'history_meta:{index}'] = _at(page, QLabel, 60, y + 38, 248, 18, '')
        button = QPushButton('', page)
        button.setGeometry(320, y + 21, 100, 28)
        button.clicked.connect(lambda _checked=False: undo_clicked(panel))
        panel._buttons[f'undo:{index}'] = button
    panel._labels['history_page'] = _at(page, QLabel, 112, 399, 230, 24, '')
    def move_page(delta):
        panel._history_page = getattr(panel, '_history_page', 0) + delta
        panel.refresh()
    for key, x, delta in (('prev', 24, -1), ('next', 352, 1)):
        button = QPushButton('', page)
        button.setGeometry(x, 397, 84, 28)
        button.clicked.connect(lambda _checked=False, d=delta: move_page(d))
        panel._buttons[f'history_{key}'] = button
    panel._labels['audit_header'] = _at(page, QLabel, 24, 438, 300, 18, '')
    panel._labels['audit_card'] = _at(page, QLabel, 24, 462, 412, 80, '')
    audit = _at(page, QLabel, 40, 470, 380, 64, '')
    audit.setTextFormat(Qt.TextFormat.PlainText)
    audit.setWordWrap(True)
    panel._labels['audit'] = audit
    status = _at(page, QLabel, 24, 548, 412, 54, '')
    status.setTextFormat(Qt.TextFormat.PlainText)
    status.setWordWrap(True)
    panel._labels['history_status'] = status
    export = QPushButton('', page)
    export.setGeometry(24, 612, 200, 36)
    export.clicked.connect(lambda: _export(panel))
    panel._buttons['export'] = export
    clear = QPushButton('', page)
    clear.setGeometry(236, 612, 200, 36)
    clear.clicked.connect(lambda: _clear(panel))
    panel._buttons['clear'] = clear


def undo_clicked(panel) -> None:
    """Run the guarded reversal on a worker; complete only on the Qt thread."""
    import threading
    from ui import qt_thread

    token = getattr(panel, '_history_visible_token', None)
    action = panel._actions.get('undo_guarded')
    if token is None or not callable(action) or getattr(panel, '_history_busy', False):
        return
    qt_thread.init_dispatcher()
    if qt_thread._dispatcher is None:
        panel._history_status = _t('ui.panel.history.worker_unavailable')
        panel.refresh()
        return
    owner = threading.get_ident()
    panel._history_busy = True
    panel._history_status = _t('ui.panel.history.working')
    panel.refresh()

    def run():
        try:
            _ok, message = action(token)
        except Exception as exc:  # noqa: BLE001
            message = f'{type(exc).__name__}: {exc}'
        def finish():
            panel._history_busy = False
            panel._history_status = (_t('ui.panel.history.changed') if message == 'changed'
                                     else str(message))
            panel.refresh()
        qt_thread.run_on_qt_thread(owner, finish)
    try:
        threading.Thread(target=run, name='history-undo', daemon=True).start()
    except RuntimeError as exc:
        panel._history_busy = False
        panel._history_status = str(exc)
        panel.refresh()


def _export(panel) -> None:
    result = panel._call('history_export')
    panel._history_status = _t('ui.panel.history.export_requested' if result
                               else 'ui.panel.history.export_failed')
    panel.refresh()


def _clear(panel) -> None:
    from PyQt6.QtWidgets import QMessageBox

    if getattr(panel, '_history_busy', False):
        return
    tokens = getattr(panel, '_history_all_tokens', ())
    if not tokens:
        return
    answer = QMessageBox.question(panel._window, _t('ui.panel.history.clear_title'),
                                  _t('ui.panel.history.clear_confirm'),
                                  QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                  QMessageBox.StandardButton.No)
    if answer != QMessageBox.StandardButton.Yes:
        return
    result = panel._call('history_clear_guarded', tokens)
    panel._history_status = _t('ui.panel.history.cleared' if result
                               else 'ui.panel.history.clear_changed')
    panel.refresh()


def paint_history(panel, snap) -> None:
    from PyQt6.QtCore import Qt

    labels, buttons = panel._labels, panel._buttons
    rows = list(snap.history)
    panel._history_all_tokens = tuple(row.get('token') for row in rows)
    pages = max(1, (len(rows) + 3) // 4)
    page = max(0, min(getattr(panel, '_history_page', 0), pages - 1))
    panel._history_page = page
    visible = rows[page * 4:page * 4 + 4]
    panel._history_visible_token = visible[0].get('token') if page == 0 and visible else None
    pal = PALETTES[panel._theme]
    labels['history_count'].setText(snap.history_subtitle)
    for index in range(4):
        row = visible[index] if index < len(visible) else None
        show_card = row is not None or (not rows and index == 0)
        for part in ('history_card', 'history', 'history_meta'):
            labels[f'{part}:{index}'].setVisible(show_card)
        labels[f'history_dot:{index}'].setVisible(row is not None)
        labels[f'history_card:{index}'].setStyleSheet(
            f"background:{pal['card']};border:1px solid {pal['line']};border-radius:12px;")
        labels[f'history_dot:{index}'].setStyleSheet(
            f"background:{pal['amber']};border-radius:5px;")
        name = labels[f'history:{index}']
        name.setTextFormat(Qt.TextFormat.PlainText)
        name.setText(str(row['label']) if row else
                     _t('ui.panel.history.empty' if snap.history_available
                        else 'ui.panel.history.unavailable') if show_card else '')
        name.setToolTip(str(row['label']) if row else '')
        labels[f'history_meta:{index}'].setText(
            _t('ui.panel.history.state.undoable' if page == 0 and index == 0
               else 'ui.panel.history.after_newer') if row else '')
        button = buttons[f'undo:{index}']
        button.setText(_t('ui.panel.undo'))
        button.setVisible(bool(row) and page == 0 and index == 0)
        button.setEnabled(bool(row) and page == 0 and index == 0
                          and row.get('token') is not None
                          and callable(panel._actions.get('undo_guarded'))
                          and not getattr(panel, '_history_busy', False))
        if row:
            button.setAccessibleName(f"{_t('ui.panel.undo')}: {row['label']}")
    labels['history_page'].setText(_t('ui.panel.history.page', page=page + 1, total=pages,
                                      count=len(rows)) if snap.history_available else '')
    for key, enabled in (('prev', page > 0), ('next', page + 1 < pages)):
        button = buttons[f'history_{key}']
        text = _t(f'ui.page.routines.{key}')
        button.setText('‹' if key == 'prev' else '›')
        button.setAccessibleName(text)
        button.setToolTip(text)
        button.setEnabled(enabled)
        button.setStyleSheet('text-align:center;padding:0;')
    labels['audit_header'].setText(_t('ui.panel.history.recent_audit'))
    labels['audit_card'].setStyleSheet(
        f"background:{pal['card']};border:1px solid {pal['line']};border-radius:12px;")
    labels['audit'].setText('\n'.join(snap.audit) or _t('ui.panel.audit.empty'))
    labels['history_status'].setText(getattr(panel, '_history_status', ''))
    buttons['export'].setText(_t('ui.panel.history.export_undo'))
    buttons['clear'].setText(_t('ui.panel.history.clear_undo'))
    buttons['export'].setEnabled(callable(panel._actions.get('history_export')))
    buttons['clear'].setEnabled(bool(rows) and callable(panel._actions.get('history_clear_guarded'))
                                and not getattr(panel, '_history_busy', False))
