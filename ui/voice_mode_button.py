"""Explicit entry to the voice presentation; does not unmute the microphone."""


def audio_level(value):
    try:
        value = float(value)
        return max(0.0, min(1.0, value)) if value == value else 0.0
    except (TypeError, ValueError):
        return 0.0


def install_escape(window, handler):
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QKeySequence, QShortcut
    shortcut = QShortcut(QKeySequence(Qt.Key.Key_Escape), window)
    shortcut.activated.connect(handler)
    return shortcut


def install(surface, layout):
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QPushButton
    from ui.hud_pages import tr
    from ui.voice_wiring import activate_voice_mode

    button = QPushButton(tr('Buka mode suara', 'Open voice mode'))
    button.setObjectName('secondary')
    button.setToolTip(tr('Buka tampilan suara saat sesi dan mikrofon siap.',
                         'Open the voice view when the session and microphone are ready.'))
    def open_mode():
        if not activate_voice_mode(surface.shell):
            surface.show_feedback(tr('Mode suara belum siap. Periksa sesi dan mikrofon.',
                                     'Voice mode is not ready. Check the session and microphone.'))
    button.clicked.connect(open_mode)
    layout.addWidget(button, 0, Qt.AlignmentFlag.AlignHCenter)
    surface.voice_mode_button = button
