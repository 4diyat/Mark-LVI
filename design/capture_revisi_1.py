"""Capture the actual Qt surfaces with synthetic local data, no Live or devices.

Run with QT_QPA_PLATFORM=offscreen. These are application screenshots, not
proof of native hotkeys, audio, camera, OS permissions, or server execution.
"""
import io
import math
import os
import sys
import tempfile
import time
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PyQt6.QtCore import QTimer
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QMessageBox

from core import audit_log, i18n
from memory import memory_manager
from ui import ambient_shell
from ui.conversation_state import publish
from ui.main_surface import open_main
from ui.shell import AmbientShell
from ui.voice_overlay import VoiceOverlay

OUT = Path(__file__).resolve().parent / 'snapshots'


def wait(app, predicate, timeout=5):
    deadline = time.monotonic() + timeout
    while not predicate() and time.monotonic() < deadline:
        app.processEvents(); QTest.qWait(10)
    if not predicate():
        raise RuntimeError('timed out waiting for application state')
    app.processEvents(); QTest.qWait(100)


def save(widget, name):
    path = OUT / f'revisi-1-{name}-simulasi.png'
    if not widget.grab().save(str(path)):
        raise RuntimeError(f'could not save {path}')
    print(path)


def save_voice_animation(app, overlay):
    """Capture real widget frames with explicitly simulated audio levels."""
    from PIL import Image
    from PyQt6.QtCore import QByteArray, QBuffer, QIODevice
    frames = []
    overlay.set_state('listening')
    for index in range(28):
        level = .65 * abs(math.sin(index * .42)) if 4 <= index < 20 else 0.0
        overlay.set_audio_level(level)
        app.processEvents(); QTest.qWait(120)
        data = QByteArray(); buffer = QBuffer(data)
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        if not overlay._window.grab().save(buffer, 'PNG'):
            raise RuntimeError('could not capture voice animation frame')
        buffer.close()
        image = Image.open(io.BytesIO(bytes(data))).convert('RGB')
        image.thumbnail((960, 540), Image.Resampling.LANCZOS)
        frames.append(image.convert('P', palette=Image.Palette.ADAPTIVE, colors=128))
    path = OUT / 'revisi-1-orb-suara-simulasi.gif'
    frames[0].save(path, save_all=True, append_images=frames[1:], duration=120, loop=0, optimize=True)
    print(path)


def main():
    with tempfile.TemporaryDirectory(prefix='jarvis-revision1-') as temp:
        os.environ['JARVIS_STATE_DIR'] = temp
        audit_log.reset_shared()
        memory_manager.MEMORY_PATH = Path(temp) / 'memory.json'
        memory_manager.update_memory({'notes': {'contoh': 'Data uji, bukan memori pengguna'}})
        audit = audit_log.shared()
        for tool, level, outcome, detail in (
            ('web_search', 'safe', 'requested', 'Contoh permintaan'),
            ('web_search', 'safe', 'done', 'Hasil uji'),
            ('file_controller:delete', 'medium', 'requested', 'Contoh'),
            ('file_controller:delete', 'medium', 'awaiting', 'Menunggu persetujuan'),
            ('send_message', 'risky', 'requested', 'Contoh'),
            ('send_message', 'risky', 'held', 'Diblokir pada data uji'),
        ):
            audit.record(tool, level, outcome, detail)
        # Three terminal outcomes are sample audit records for this screenshot.
        for tool, level, outcome, detail in (
            ('Akses jaringan · contoh', 'risky', 'failed', 'Koneksi uji gagal (data simulasi)'),
            ('Sinkronisasi data · contoh', 'medium', 'unverified', 'Hasil uji belum terverifikasi'),
            ('Diagnostik sistem · contoh', 'safe', 'done', 'Pemeriksaan contoh tercatat selesai'),
        ):
            audit.record(tool, level, outcome, detail)
        app = QApplication([]); app.setQuitOnLastWindowClosed(False)
        i18n.set_locale('id')
        shell = AmbientShell(face_path='', assistant_name='JARVIS', app=app)
        assert open_main(shell)
        home = shell._main_surface
        publish(shell, 'user', 'Tampilkan status sistem. (data uji)')
        publish(shell, 'assistant', 'Permintaan contoh diterima. Hasil belum diverifikasi.')
        app.processEvents(); QTest.qWait(150)
        save(home.window, 'chat')

        assert ambient_shell.open_command_bar(shell)
        bar = shell._command_bar
        wait(app, lambda: not bar._audit_running)
        # Render the actual window at its reference size to illustrate a
        # sufficiently large display; normal opening fits the current screen.
        from ui.command_layout import apply
        apply(bar, 1.0)
        app.processEvents()
        save(bar._window, 'command-bar')
        example_rows = bar.rows
        bar.set_rows([])
        app.processEvents()
        save(bar._window, 'command-bar-kosong')
        bar.set_rows(example_rows)
        shell.on_text_command = lambda text: False
        bar._field.setText('Perintah contoh — sesi uji tidak tersambung')
        assert bar.submit()
        wait(app, lambda: not bar.sending and not bar._audit_running)
        save(bar._window, 'command-bar-gagal')
        menu = bar._suggestions.menu()
        menu.popup(bar._suggestions.mapToGlobal(bar._suggestions.rect().bottomLeft()))
        app.processEvents(); QTest.qWait(100)
        save(menu, 'saran-command')
        menu.hide(); bar.close()

        home.workspace_button.click(); app.processEvents()
        workspace = shell._desktop_workspace
        workspace.window.resize(1500, 1050)
        workspace.navigate('security')
        wait(app, lambda: not workspace.security.loading)
        save(workspace.window, 'keamanan')

        workspace.navigate('memory')
        wait(app, lambda: not workspace.memory._loading)
        row = workspace.memory.memory_cards[0].row
        def second_dialog():
            modal = QApplication.activeModalWidget()
            if modal is None:
                raise RuntimeError('confirmation dialog missing')
            app.processEvents(); QTest.qWait(80)
            save(modal, 'konfirmasi-kedua')
            modal.done(QMessageBox.StandardButton.No.value)
        def first_dialog():
            modal = QApplication.activeModalWidget()
            app.processEvents(); QTest.qWait(80)
            save(modal, 'konfirmasi-pertama')
            QTimer.singleShot(0, second_dialog)
            modal.done(QMessageBox.StandardButton.Yes.value)
        QTimer.singleShot(0, first_dialog)
        workspace.memory.confirm_forget(row)
        assert memory_manager.all_entries_for_ui(strict=True)

        # Capture the confirmation without changing state; then illustrate the
        # scoped controls, not real OS permissions.
        workspace.navigate('security'); app.processEvents()
        def guest_dialog():
            modal = QApplication.activeModalWidget()
            app.processEvents(); QTest.qWait(80)
            save(modal, 'konfirmasi-tamu')
            modal.done(QMessageBox.StandardButton.No.value)
        QTimer.singleShot(0, guest_dialog)
        workspace.security._enable_guest()
        from core import guest_mode
        guest_mode.enable()
        workspace.navigate('security'); app.processEvents()
        workspace.security._update_guest()
        workspace.security.vision_checks['camera'].setChecked(False)
        scroll = workspace.stack.currentWidget()
        scroll.verticalScrollBar().setValue(scroll.verticalScrollBar().maximum())
        app.processEvents(); QTest.qWait(100)
        save(workspace.window, 'kontrol-vision-dan-tamu')

        overlay = VoiceOverlay(state='thinking')
        assert overlay.start(active=True)
        shell._voice_overlay = overlay
        shell._hand_feed = SimpleNamespace(status='off', _started=False,
                                            _timer=SimpleNamespace(isActive=lambda: True))
        shell._pause_hotkey = SimpleNamespace(scope='global')
        from ui.voice_gesture_controls import install, refresh, toggle_desktop
        install(shell)
        overlay.set_transcript('Contoh transkripsi suara')
        overlay.set_answer('Menyiapkan respons contoh…')
        app.processEvents(); QTest.qWait(150)
        save(overlay._window, 'suara-thinking')
        # A hand landmark fixture is shown only for this snapshot; no camera
        # or MediaPipe is opened. Production frames come from the controller.
        shell._hand_feed.status = 'active'; shell._hand_feed._started = True
        overlay.set_camera_available(True); overlay.set_hand((.5, .5, False))
        overlay._gesture_points = (
            (.50,.92), (.40,.80), (.32,.70), (.23,.62), (.16,.54),
            (.43,.65), (.40,.44), (.39,.30), (.38,.16),
            (.52,.62), (.52,.35), (.52,.20), (.52,.08),
            (.60,.64), (.63,.40), (.64,.26), (.65,.15),
            (.68,.69), (.73,.52), (.76,.40), (.79,.32),
        )
        refresh(shell)
        overlay.set_state('listening')
        overlay.set_transcript('Simulasi · contoh transkripsi suara')
        overlay.set_audio_level(.8)  # synthetic, not microphone input
        overlay._gesture_message = 'SIMULASI · TANGAN TERDETEKSI'
        app.processEvents(); QTest.qWait(100)
        save(overlay._window, 'suara-gestur')
        def desktop_dialog():
            modal = QApplication.activeModalWidget()
            app.processEvents(); QTest.qWait(80)
            save(modal, 'konfirmasi-gestur-desktop')
            modal.done(QMessageBox.StandardButton.No.value)
        from ui import hand_feed
        saved_setting = hand_feed.gesture_bridge_enabled
        hand_feed.gesture_bridge_enabled = lambda: False
        try:
            QTimer.singleShot(0, desktop_dialog)
            assert not toggle_desktop(shell)  # no pointer driver is activated
        finally:
            hand_feed.gesture_bridge_enabled = saved_setting
        overlay.set_state('voice_idle')
        app.processEvents(); QTest.qWait(100)
        save(overlay._window, 'suara-siaga')
        save_voice_animation(app, overlay)
        overlay.stop(); workspace.close(); home.close()
        audit_log.reset_shared()


if __name__ == '__main__':
    main()
