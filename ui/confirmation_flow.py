"""Thread-safe, token-aware delivery of confirmation requests to Qt."""
from ui.qt_thread import run_on_qt_thread


def show(shell, token, title, detail):
    def deliver():
        from core import confirm
        if not confirm.is_pending(token):
            return
        existing = getattr(shell, '_confirm_banner', None)
        if existing is not None:
            existing._cancel_button.setFocus()
        shell._show_confirm_now(token, title, detail)
        if shell._confirm_token != token:
            return
        # A reused banner must not keep the previous confirmation focused.
        banner = shell._confirm_banner
        banner._cancel_button.setFocus()
        from PyQt6.QtCore import QTimer
        QTimer.singleShot(0, lambda: banner._cancel_button.setFocus()
                          if shell._confirm_token == token else None)
        timer = getattr(shell, '_confirm_expiry_timer', None)
        if timer is None:
            timer = QTimer(banner)
            timer.setInterval(500)
            timer.timeout.connect(lambda: _expire(shell))
            shell._confirm_expiry_timer = timer
        timer.start()
    run_on_qt_thread(shell._ui_thread_id, deliver)


def hide(shell, token):
    def deliver():
        if token != shell._confirm_token:
            return
        shell._confirm_token = ''
        timer = getattr(shell, '_confirm_expiry_timer', None)
        if timer is not None:
            timer.stop()
        if shell._confirm_banner is not None:
            shell._confirm_banner.hide()
    run_on_qt_thread(shell._ui_thread_id, deliver)


def _expire(shell):
    from core import confirm
    token = shell._confirm_token
    if token and not confirm.is_pending(token):
        # Resolving an expired token never runs the action; this also reports
        # expiry in the existing log and clears the UI through the hide callback.
        confirm.resolve(token, False)
        hide(shell, token)
