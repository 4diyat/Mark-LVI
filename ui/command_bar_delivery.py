"""Nonblocking command-bar send and strict audit refresh for the live shell."""
import threading

from ui.hud_pages import tr
from ui.qt_thread import run_on_qt_thread


def refresh_audit(bar):
    if bar._audit_running:
        bar._audit_reload = True
        return
    bar._audit_running = True
    bar.set_rows([])
    bar.set_audit_state('loading')
    def work():
        try:
            from ui.command_paint import default_rows
            rows, error = default_rows(strict=True), None
        except Exception as exc:  # noqa: BLE001
            rows, error = [], f'{type(exc).__name__}: {exc}'
        run_on_qt_thread(bar._owner, lambda: _audit_done(bar, rows, error))
    try:
        threading.Thread(target=work, name='command-audit-read', daemon=True).start()
    except RuntimeError as exc:
        _audit_done(bar, [], str(exc))


def _audit_done(bar, rows, error):
    bar._audit_running = False
    if error:
        print(f'[JARVIS] Command bar audit unavailable: {error}')
    bar.set_rows(rows)
    bar.set_audit_state('error' if error else 'done')
    if bar._audit_reload:
        bar._audit_reload = False
        refresh_audit(bar)


def send(bar, raw):
    from ui.command_bar import MAX_CHARS
    from ui.command_delivery import dispatch
    if bar.sending:
        return False
    bar.set_retry()
    line = ' '.join(str(raw or '').split())
    if not line:
        return False
    if len(line) > MAX_CHARS:
        bar.set_hint(tr('Perintah terlalu panjang; belum dikirim.', 'Command is too long; not sent.'))
        return False
    if not callable(bar._on_submit):
        bar.set_hint(tr('Sesi belum siap; draf disimpan.', 'Session not ready; draft retained.'))
        bar.set_retry(line)
        return False
    marker = object()
    bar._send_marker = marker
    bar.sending = True
    bar._field.setEnabled(False)
    bar.set_hint(tr('Mengirim…', 'Sending…'))
    def finish(text, result):
        bar.sending = False
        bar._field.setEnabled(True)
        if result is True:
            bar._remember(text)
            if ' '.join(bar._field.text().split()) == text:
                bar._field.clear()
            bar.set_hint(tr('Terkirim ke sesi; hasil tindakan belum diketahui.', 'Sent to session; action outcome is not yet known.'))
            if callable(bar._on_sent):
                try:
                    bar._on_sent(text)
                except Exception as exc:  # noqa: BLE001
                    print(f'[JARVIS] Command history update failed: {exc}')
        elif result is False:
            bar.set_hint(tr('Tidak terkirim: sesi menolak.', 'Not sent: session rejected.'))
            if ' '.join(bar._field.text().split()) == text:
                bar.set_retry(text)
        else:
            bar.set_hint(tr('Pengiriman tidak pasti; draf disimpan. Jangan kirim ulang sembarangan.',
                            'Delivery uncertain; draft retained. Do not retry blindly.'))
    def work(): dispatch(bar._on_submit, line, bar._owner, finish)
    try:
        threading.Thread(target=work, name='command-bar-send', daemon=True).start()
    except RuntimeError as exc:
        print(f'[JARVIS] Command bar worker unavailable: {exc}')
        finish(line, False)
        return False
    from PyQt6.QtCore import QTimer
    def pending():
        if bar.sending and bar._send_marker is marker:
            bar.set_hint(tr('Pengiriman masih menunggu; jangan kirim ulang.', 'Send still pending; do not retry.'))
    QTimer.singleShot(15000, pending)
    return True
