"""Track the actual asynchronous send, without blocking the Qt event loop."""
from ui.qt_thread import run_on_qt_thread


def dispatch(callback, text, owner, finish):
    """Deliver on a worker; report accepted, rejected, or delivery unknown."""
    def deliver(value):
        run_on_qt_thread(owner, lambda: finish(text, value))

    try:
        outcome = callback(text)
        if callable(getattr(outcome, 'add_done_callback', None)) and callable(getattr(outcome, 'result', None)):
            def completed(future):
                try:
                    future.result()
                except Exception as exc:  # noqa: BLE001
                    print(f'[JARVIS] Command delivery uncertain: {type(exc).__name__}: {exc}')
                    deliver(None)
                else:
                    deliver(True)
            outcome.add_done_callback(completed)
        else:
            deliver(outcome is not False)
    except Exception as exc:  # noqa: BLE001
        print(f'[JARVIS] Command delivery uncertain: {type(exc).__name__}: {exc}')
        deliver(None)


def schedule_pending(surface):
    from PyQt6.QtCore import QTimer
    from ui.hud_pages import tr
    marker = object()
    surface._send_marker = marker
    def warn():
        if surface.sending and surface._send_marker is marker:
            surface.show_feedback(tr('Pengiriman masih menunggu; jangan kirim ulang sampai statusnya jelas.',
                                     'Send is still pending; do not retry until its status is known.'))
    QTimer.singleShot(15000, warn)
