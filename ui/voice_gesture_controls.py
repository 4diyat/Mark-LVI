"""Explicit camera tracking controls for the voice surface, separate from OS control."""


def install(shell):
    overlay = getattr(shell, '_voice_overlay', None)
    window = getattr(overlay, '_window', None)
    if window is None:
        return
    from PyQt6.QtWidgets import QPushButton
    from ui.hud_pages import tr

    start = QPushButton(window)
    start.setGeometry(50, 629, 112, 25)
    pause = QPushButton(window)
    pause.setGeometry(168, 629, 112, 25)
    desktop = QPushButton(window)
    desktop.setGeometry(40, 667, 250, 25)
    for button in (start, pause, desktop):
        button.setStyleSheet('QPushButton { background:#15283c; color:#e7f2ff; border:1px solid #456887; '
                             'border-radius:5px; font-size:11px; } '
                             'QPushButton:focus { border:2px solid #8bcbff; } '
                             'QPushButton:disabled { color:#8292a3; }')
        button.show()
    start.setToolTip(tr('Kamera untuk pelacakan tangan dan pratinjau lokal saat tampilan suara terbuka. Kontrol OS diatur terpisah.',
                        'Camera for hand tracking and local preview while voice view is open. OS control is configured separately.'))
    pause.setToolTip(tr('Jeda pelacakan gestur tanpa menutup kamera.',
                        'Pause gestures without closing the camera.'))
    start.clicked.connect(lambda: toggle_tracking(shell))
    pause.clicked.connect(lambda: toggle_pause(shell))
    desktop.clicked.connect(lambda: toggle_desktop(shell))
    desktop.setToolTip(tr('Kontrol pointer desktop memerlukan konfirmasi fisik dan pintasan jeda global.',
                          'Desktop pointer control requires physical confirmation and a global pause shortcut.'))
    overlay._gesture_buttons = (start, pause)
    overlay._gesture_feed = getattr(shell, '_hand_feed', None)
    overlay._desktop_button = desktop
    refresh(shell)


def refresh(shell):
    overlay = getattr(shell, '_voice_overlay', None)
    if overlay is None:
        return
    feed = getattr(shell, '_hand_feed', None)
    started = bool(getattr(feed, '_started', False))
    status = str(getattr(feed, 'status', 'off')) if feed else 'off'
    from core import i18n
    def text(id_text, en_text):
        return id_text if i18n.active_locale() == 'id' else en_text
    messages = {'off': text('GESTUR NONAKTIF', 'GESTURES OFF'),
                'starting': text('MENYIAPKAN KAMERA', 'STARTING CAMERA'),
                'windows_only': text('HANYA TERSEDIA DI WINDOWS', 'WINDOWS ONLY'),
                'camera_busy': text('KAMERA SEDANG DIGUNAKAN', 'CAMERA BUSY'),
                'error': text('KAMERA ATAU DETEKTOR GAGAL', 'CAMERA OR TRACKER FAILED'),
                'active': text('MENUNGGU TANGAN', 'WAITING FOR HAND')}
    message = messages.get(status, messages['off'])
    if overlay.gestures_paused and status == 'active':
        message = text('GESTUR DIJEDA · KAMERA AKTIF', 'PAUSED · CAMERA ACTIVE')
    elif overlay.gestures_paused and started:
        message = text('GESTUR DIJEDA', 'GESTURES PAUSED')
    elif status == 'active' and getattr(overlay, '_has_hand', False):
        message = text('TANGAN TERDETEKSI', 'HAND DETECTED')
    overlay._gesture_message = message
    buttons = getattr(overlay, '_gesture_buttons', None)
    if buttons:
        from ui.hud_pages import tr
        start, pause = buttons
        start.setText(tr('Hentikan', 'Stop') if started else tr('Aktifkan', 'Start'))
        start.setAccessibleName(tr('Hentikan pelacakan tangan', 'Stop hand tracking') if started else
                                tr('Aktifkan pelacakan tangan', 'Start hand tracking'))
        pause.setText(tr('Lanjutkan', 'Resume') if overlay.gestures_paused else tr('Jeda', 'Pause'))
        pause.setAccessibleName(tr('Lanjutkan gestur', 'Resume gestures') if overlay.gestures_paused else
                                tr('Jeda gestur', 'Pause gestures'))
        pause.setEnabled(started)
    desktop = getattr(overlay, '_desktop_button', None)
    if desktop:
        active = bool(getattr(feed, '_voice_desktop_control', False))
        desktop.setText(text('Matikan kontrol desktop', 'Stop desktop control') if active else
                        text('Kontrol desktop…', 'Desktop control…'))
        desktop.setAccessibleName(desktop.text())
        desktop.setEnabled(started and status == 'active')
    if hasattr(overlay, '_refresh'):
        overlay._refresh()


def toggle_tracking(shell):
    feed = getattr(shell, '_hand_feed', None)
    overlay = getattr(shell, '_voice_overlay', None)
    if feed is None or overlay is None or not overlay.active:
        return
    if feed._started:
        feed.stop()
        feed._voice_owned = False
        overlay.set_camera_available(False)
        overlay.set_hand(None)
        overlay._gesture_points = ()
    else:
        overlay.set_gestures_paused(False)
        from ui.hand_feed import gesture_bridge_enabled
        started = feed.start()
        feed._voice_owned = started and not gesture_bridge_enabled()
    refresh(shell)


def toggle_pause(shell):
    overlay = getattr(shell, '_voice_overlay', None)
    feed = getattr(shell, '_hand_feed', None)
    if overlay is None or not getattr(feed, '_started', False):
        return
    overlay.handle_toggle_gestures()
    if overlay.gestures_paused:
        overlay._gesture_points = ()
        # Release a held button immediately, rather than waiting for a frame.
        feed._pump_bridge(None)
    refresh(shell)


def toggle_desktop(shell):
    """Opt into desktop input for this session, after an explicit decision."""
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QMessageBox
    from core import os_control
    from ui.desktop_confirm import style_dialog
    from ui.hand_feed import gesture_bridge_enabled
    from ui.hud_pages import tr

    feed = getattr(shell, '_hand_feed', None)
    overlay = getattr(shell, '_voice_overlay', None)
    if feed is None or overlay is None or not overlay.active:
        return False
    if getattr(feed, '_voice_desktop_control', False):
        feed._voice_desktop_control = False
        feed.bridge.disable()  # releases any held button immediately
        feed._voice_owned = True
        refresh(shell)
        return True
    if gesture_bridge_enabled():
        QMessageBox.information(overlay._window, tr('Kontrol desktop', 'Desktop control'),
            tr('Kontrol OS sudah diaktifkan dalam pengaturan terpisah. Gunakan pengaturan itu untuk mematikannya.',
               'OS control is already enabled in separate settings. Use those settings to turn it off.'))
        return False
    tap = getattr(shell, '_pause_hotkey', None)
    timer = getattr(feed, '_timer', None)
    if (not feed._started or feed.status != 'active' or overlay.gestures_paused or
            timer is None or not timer.isActive() or getattr(tap, 'scope', 'window') != 'global'):
        QMessageBox.information(overlay._window, tr('Kontrol desktop belum siap', 'Desktop control is not ready'),
            tr('Pelacakan harus aktif dan tidak dijeda. Pintasan global Ctrl+Alt+G juga harus tersedia.',
               'Tracking must be active and unpaused. The global Ctrl+Alt+G shortcut must also be available.'))
        return False
    dialog = QMessageBox(overlay._window); style_dialog(dialog)
    dialog.setTextFormat(Qt.TextFormat.PlainText)
    dialog.setWindowTitle(tr('Aktifkan kontrol desktop?', 'Enable desktop control?'))
    dialog.setText(tr('Aktifkan kontrol desktop?', 'Enable desktop control?'))
    dialog.setInformativeText(tr(
        'Gestur dapat menggerakkan pointer, menekan klik dan menggulir di aplikasi lain. '
        'Tampilan suara akan ditutup; kamera tetap aktif. Ctrl+Alt+G menjeda gestur. '
        'Kontrol dibekukan saat JARVIS atau dialog konfirmasi aktif. '
        'Buka kembali mode suara untuk mematikan kontrol. Berlaku hanya selama sesi ini.',
        'Gestures can move the pointer, press a click and scroll in other applications. '
        'The voice view will close; the camera stays active. Ctrl+Alt+G pauses gestures. '
        'Control is frozen when JARVIS or a confirmation dialog is active. '
        'Reopen voice mode to stop control. This lasts only for this session.'))
    dialog.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
    dialog.button(QMessageBox.StandardButton.Yes).setText(tr('Aktifkan', 'Enable'))
    dialog.button(QMessageBox.StandardButton.No).setText(tr('Batal', 'Cancel'))
    dialog.setDefaultButton(QMessageBox.StandardButton.No)
    if dialog.exec() != QMessageBox.StandardButton.Yes:
        return False
    if (not os_control.request(False, True, confirmed=True).allowed or feed.status != 'active' or
            overlay.gestures_paused or feed._timer is not timer or not timer.isActive() or
            getattr(tap, 'scope', 'window') != 'global'):
        return False
    if not feed.bridge.enable():
        QMessageBox.information(overlay._window, tr('Kontrol desktop gagal', 'Desktop control failed'),
                                tr('Penggerak pointer tidak tersedia.', 'The pointer driver is unavailable.'))
        return False
    feed._voice_desktop_control = True
    overlay.handle_escape()
    main = getattr(shell, '_main_surface', None)
    if main is not None:
        main.show_feedback(tr('Kontrol desktop aktif untuk sesi ini. Ctrl+Alt+G menjeda; buka mode suara untuk mematikan.',
                              'Desktop control active for this session. Ctrl+Alt+G pauses; reopen voice mode to stop.'))
    return True


def close_voice(shell):
    feed = getattr(shell, '_hand_feed', None)
    if (feed is not None and getattr(feed, '_voice_owned', False)
            and not getattr(feed, '_voice_desktop_control', False)):
        feed.stop()
        feed._voice_owned = False
    overlay = getattr(shell, '_voice_overlay', None)
    if overlay is not None:
        overlay._gesture_points = ()
        overlay.set_hand(None)
        if not getattr(feed, '_started', False):
            overlay.set_camera_available(False)
        refresh(shell)
