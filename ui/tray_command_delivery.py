"""Session-aware, asynchronous delivery for the tray command field."""
import threading

from ui.hud_pages import tr


def configure(panel, shell):
    panel._async_command = True
    panel._conversation_shell = shell
    from ui.conversation_state import hydrate
    hydrate(shell, panel)
    def send_to_session(text):
        callback = getattr(shell, 'on_text_command', None)
        return callback(text) if callable(callback) else False
    panel._actions['command'] = send_to_session


def send(panel, line):
    if getattr(panel, '_command_sending', False):
        return False
    callback = panel._actions.get('command')
    if not callable(callback):
        panel._labels['command_status'].setText(tr('Sesi belum siap; draf disimpan.', 'Session not ready; draft retained.'))
        return False
    from ui.command_delivery import dispatch
    owner = threading.get_ident()
    marker = object(); panel._command_marker = marker; panel._command_sending = True
    panel._field.setEnabled(False); panel._buttons['send'].setEnabled(False)
    status = panel._labels['command_status']
    status.setText(tr('Mengirim…', 'Sending…'))
    def finish(text, result):
        panel._command_sending = False
        panel._field.setEnabled(True); panel._buttons['send'].setEnabled(True)
        if result is True:
            if ' '.join(panel._field_text().split()) == text:
                panel._field.clear()
            from ui.conversation_state import publish
            publish(panel._conversation_shell, 'user', text)
            status.setText(tr('Terkirim ke sesi; hasil belum diketahui.', 'Sent to session; outcome unknown.'))
        elif result is False:
            status.setText(tr('Tidak terkirim; draf disimpan.', 'Not sent; draft retained.'))
        else:
            status.setText(tr('Pengiriman tidak pasti; jangan kirim ulang.', 'Delivery uncertain; do not retry blindly.'))
    def work(): dispatch(callback, line, owner, finish)
    try:
        threading.Thread(target=work, name='tray-command-send', daemon=True).start()
    except RuntimeError as exc:
        print(f'[JARVIS] Tray command worker unavailable: {exc}')
        finish(line, False)
        return False
    from PyQt6.QtCore import QTimer
    def pending():
        if panel._command_sending and panel._command_marker is marker:
            status.setText(tr('Masih menunggu; jangan kirim ulang.', 'Still pending; do not retry.'))
    QTimer.singleShot(15000, pending)
    return True
