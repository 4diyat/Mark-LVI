"""Offer onboarding step 2 when the audio backend explicitly reports denial.

A backend error string is not an OS permission API. Unknown device errors must
not be presented as proof of permission denial.
"""


def explicitly_denied(problem):
    text = str(problem or '').lower()
    return any(term in text for term in (
        'permission denied', 'access denied', 'not authorized', 'not authorised',
        'not permitted', 'permissionerror',
    ))


def open_mic_guide(shell):
    """Called on Qt's thread; never changes the OS permission or opens audio."""
    from ui.desktop_navigation import open_desktop
    if not open_desktop(shell, 'welcome'):
        return False
    page = shell._desktop_workspace.welcome
    page.index = 1
    page.render()
    from ui.hud_pages import tr
    page.status.setText(tr('Mikrofon tidak dapat dibuka. Periksa izin dan perangkat di sistem.',
                           'Microphone could not be opened. Check OS permissions and the device.'))
    return True


def report_denial(shell, problem):
    if not explicitly_denied(problem):
        return False
    from ui.qt_thread import run_on_qt_thread
    run_on_qt_thread(getattr(shell, '_ui_thread_id', None), lambda: open_mic_guide(shell))
    return True
