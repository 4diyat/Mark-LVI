"""Desktop routines: explicit daily scheduling on the existing local store."""
import re
import threading
from uuid import uuid4

from PyQt6.QtCore import QSize, Qt
from PyQt6.QtWidgets import (QFrame, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
                             QPushButton, QVBoxLayout, QWidget)

from ui.hud_icons import icon
from ui.hud_pages import heading, tr
from ui.qt_thread import run_on_qt_thread


def schedule_text(schedule):
    from core.routines import validate_schedule
    if validate_schedule(schedule):
        return tr('Jadwal tidak valid', 'Invalid schedule')
    names = ([tr('Sen', 'Mon'), tr('Sel', 'Tue'), tr('Rab', 'Wed'), tr('Kam', 'Thu'),
              tr('Jum', 'Fri'), tr('Sab', 'Sat'), tr('Min', 'Sun')])
    days = ', '.join(names[day] for day in schedule.days) if schedule.days else tr('Setiap hari', 'Every day')
    return f'{days} · {schedule.time} ' + tr('(waktu lokal)', '(local time)')


class RoutineCard(QFrame):
    def __init__(self, page, routine):
        super().__init__()
        self.routine = routine
        self.setObjectName('routineCard')
        box = QHBoxLayout(self); box.setContentsMargins(18, 15, 18, 15); box.setSpacing(14)
        glyph = QLabel(); glyph.setObjectName('workspaceIcon'); glyph.setFixedSize(44, 44)
        glyph.setAlignment(Qt.AlignmentFlag.AlignCenter)
        glyph.setPixmap(icon('calendar', '#72c0ff', 23).pixmap(QSize(23, 23))); box.addWidget(glyph)
        info = QVBoxLayout(); info.setSpacing(5)
        title = heading(routine.name or tr('Tanpa nama', 'Untitled'), 'desktopCardTitle')
        title.setWordWrap(True); info.addWidget(title)
        command = heading(routine.payload, 'desktopMuted'); command.setWordWrap(True); info.addWidget(command)
        timing = heading(schedule_text(routine.schedule), 'routineTime'); timing.setWordWrap(True); info.addWidget(timing)
        state = heading(tr('Aktif', 'Enabled') if routine.enabled else tr('Dijeda', 'Paused'), 'desktopHint')
        info.addWidget(state)
        box.addLayout(info, 1)
        buttons = QVBoxLayout()
        self.toggle = QPushButton(tr('Jeda', 'Pause') if routine.enabled else tr('Aktifkan', 'Enable'))
        self.toggle.setObjectName('workspaceButton')
        self.toggle.setAccessibleName((tr('Jeda: ', 'Pause: ') if routine.enabled else tr('Aktifkan: ', 'Enable: ')) + routine.name)
        self.toggle.clicked.connect(lambda: page.change_enabled(routine))
        buttons.addWidget(self.toggle)
        self.delete = QPushButton(tr('Hapus', 'Delete')); self.delete.setObjectName('danger')
        self.delete.setAccessibleName(tr('Hapus: ', 'Delete: ') + routine.name)
        self.delete.clicked.connect(lambda: page.confirm_delete(routine))
        buttons.addWidget(self.delete)
        box.addLayout(buttons)


class RoutinesPage(QWidget):
    def __init__(self, parent):
        super().__init__()
        self.setObjectName('desktopPage')
        self.dialog_parent = parent
        self.owner = threading.get_ident()
        self.loading = self.busy = self.reload_requested = False
        self.rows = None
        self.cards = []
        self.page_index = 0
        self._build()

    def _build(self):
        box = QVBoxLayout(self); box.setContentsMargins(0, 0, 0, 0); box.setSpacing(14)
        header = QHBoxLayout()
        head = QVBoxLayout(); head.addWidget(heading(tr('Rutinitas', 'Routines'), 'desktopHeading'))
        subtitle = heading(tr('Jadwalkan perintah untuk sesi asisten.', 'Schedule commands for the assistant session.'), 'desktopMuted')
        subtitle.setWordWrap(True); head.addWidget(subtitle); header.addLayout(head, 1)
        self.refresh_button = QPushButton(tr('Muat ulang', 'Refresh')); self.refresh_button.setObjectName('workspaceButton')
        self.refresh_button.clicked.connect(self.refresh); header.addWidget(self.refresh_button)
        box.addLayout(header)
        explain = heading(tr('Jadwal memakai waktu lokal. Jika waktunya sudah lewat saat sesi tersambung, perintah dapat segera dikirim. Kegagalan tidak dicoba lagi hari itu; jeda tidak membatalkan perintah yang sudah mulai diproses.',
                             'Schedules use local time. If the time has passed when a session connects, the command may be sent immediately. Failures are not retried that day; pausing cannot cancel a command already being processed.'), 'desktopHint')
        explain.setWordWrap(True); box.addWidget(explain)
        self.status = heading('', 'workspaceStatus'); self.status.setWordWrap(True); box.addWidget(self.status)
        self.operation_status = heading('', 'workspaceStatus'); self.operation_status.setWordWrap(True); box.addWidget(self.operation_status)
        self.status.hide(); self.operation_status.hide()
        self.list_layout = QVBoxLayout(); self.list_layout.setSpacing(10); box.addLayout(self.list_layout)
        pagination = QHBoxLayout()
        self.prev = QPushButton(tr('Sebelumnya', 'Previous')); self.prev.setObjectName('workspaceButton')
        self.prev.clicked.connect(lambda: self.change_page(-1)); pagination.addWidget(self.prev)
        self.page_label = heading('', 'desktopMuted'); pagination.addWidget(self.page_label, 1, Qt.AlignmentFlag.AlignCenter)
        self.next = QPushButton(tr('Berikutnya', 'Next')); self.next.setObjectName('workspaceButton')
        self.next.clicked.connect(lambda: self.change_page(1)); pagination.addWidget(self.next); box.addLayout(pagination)
        form = QFrame(); form.setObjectName('routineBuilder'); builder = QVBoxLayout(form)
        builder.setContentsMargins(20, 18, 20, 18); builder.setSpacing(9)
        builder.addWidget(heading(tr('Tambah rutinitas harian', 'Add a daily routine'), 'desktopSubheading'))
        info = heading(tr('Perintah dikirim ke model sebagai pesan pengguna; hasilnya tidak dijamin. Konfirmasi dapat tetap diperlukan untuk tindakan berisiko.',
                          'The command is sent to the model as a user message; results are not guaranteed. Risky actions may still require confirmation.'), 'desktopMuted')
        info.setWordWrap(True); builder.addWidget(info)
        fields = QHBoxLayout()
        self.time_field = QLineEdit(); self.time_field.setObjectName('routineInput')
        self.time_field.setPlaceholderText(tr('Waktu: HH:MM', 'Time: HH:MM')); self.time_field.setAccessibleName(tr('Waktu lokal HH:MM', 'Local time HH:MM'))
        self.time_field.setMaxLength(5); self.time_field.setMaximumWidth(180); fields.addWidget(self.time_field)
        self.command_field = QLineEdit(); self.command_field.setObjectName('routineInput')
        self.command_field.setPlaceholderText(tr('Perintah untuk asisten', 'Command for the assistant'))
        self.command_field.setAccessibleName(tr('Perintah untuk asisten', 'Command for the assistant')); fields.addWidget(self.command_field, 1)
        builder.addLayout(fields)
        self.create_button = QPushButton(tr('Tambah rutinitas', 'Add routine')); self.create_button.setObjectName('workspaceButton')
        self.create_button.clicked.connect(self.confirm_create); builder.addWidget(self.create_button, 0, Qt.AlignmentFlag.AlignLeft)
        box.addWidget(form)
        suggestions = QFrame(); suggestions.setObjectName('routineBuilder'); sb = QVBoxLayout(suggestions)
        sb.setContentsMargins(20, 18, 20, 18)
        sb.addWidget(heading(tr('Saran proaktif', 'Proactive suggestions'), 'desktopSubheading'))
        note = heading(tr('Saran berdasarkan kebiasaan belum tersedia di halaman ini. Tidak ada saran atau aktivitas yang direkayasa.',
                          'Habit-based suggestions are not available on this page. No suggestions or activity are fabricated.'), 'desktopMuted')
        note.setWordWrap(True); sb.addWidget(note); box.addWidget(suggestions); box.addStretch()
        self.render()

    def _set_status(self, text):
        self.status.setText(text)
        self.status.setVisible(bool(text))

    def _set_operation(self, text):
        self.operation_status.setText(text)
        self.operation_status.setVisible(bool(text))

    def refresh(self):
        if self.loading or self.busy:
            self.reload_requested = True
            return
        self.loading = True
        self._controls()
        self._set_status(tr('Memuat rutinitas…', 'Loading routines…'))
        def work():
            try:
                from memory.routine_store import default_store
                rows, error = default_store().all(), None
            except Exception as exc:  # noqa: BLE001
                rows, error = None, f'{type(exc).__name__}: {exc}'
            run_on_qt_thread(self.owner, lambda: self._loaded(rows, error))
        try:
            threading.Thread(target=work, name='desktop-routines-read', daemon=True).start()
        except RuntimeError as exc:
            self._loaded(None, str(exc))

    def _loaded(self, rows, error):
        self.loading = False; self.rows = rows
        if error:
            print(f'[JARVIS] Routine store unavailable: {error}')
            self._set_status(tr('Rutinitas tidak dapat dibaca; perubahan dinonaktifkan.',
                                   'Routines could not be read; changes are disabled.'))
        else:
            self._set_status(tr('Belum ada rutinitas.', 'No routines yet.') if not rows else '')
        self.render(); self._controls()
        if self.reload_requested:
            self.reload_requested = False; self.refresh()

    def _controls(self):
        idle = not self.loading and not self.busy
        self.refresh_button.setEnabled(idle)
        self.create_button.setEnabled(idle and self.rows is not None)
        for card in self.cards:
            card.toggle.setEnabled(idle); card.delete.setEnabled(idle)
        count = len(self.rows or [])
        self.prev.setEnabled(idle and self.page_index > 0)
        self.next.setEnabled(idle and (self.page_index + 1) * 4 < count)

    def render(self):
        while self.list_layout.count():
            widget = self.list_layout.takeAt(0).widget()
            if widget:
                widget.deleteLater()
        self.cards = []
        count = len(self.rows or [])
        pages = max(1, (count + 3) // 4)
        self.page_index = max(0, min(self.page_index, pages - 1))
        if self.rows is not None:
            for row in self.rows[self.page_index * 4:(self.page_index + 1) * 4]:
                card = RoutineCard(self, row); self.cards.append(card); self.list_layout.addWidget(card)
            self.page_label.setText(tr(f'Halaman {self.page_index + 1} / {pages} · {count} rutinitas',
                                       f'Page {self.page_index + 1} / {pages} · {count} routines'))
        else:
            self.page_label.setText(tr('Jumlah tidak diketahui', 'Count unknown'))
        self._controls()

    def change_page(self, delta):
        if self.loading or self.busy or self.rows is None:
            return
        self.page_index += delta; self.render()

    def _ask(self, title, message, yes):
        dialog = QMessageBox(self.dialog_parent); dialog.setIcon(QMessageBox.Icon.Warning)
        dialog.setTextFormat(Qt.TextFormat.PlainText); dialog.setWindowTitle(title); dialog.setText(message)
        dialog.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        dialog.button(QMessageBox.StandardButton.Yes).setText(yes)
        dialog.button(QMessageBox.StandardButton.No).setText(tr('Batal', 'Cancel'))
        dialog.setDefaultButton(QMessageBox.StandardButton.No)
        return dialog.exec() == QMessageBox.StandardButton.Yes

    def confirm_create(self):
        if self.loading or self.busy or self.rows is None:
            return
        time = self.time_field.text().strip(); command = self.command_field.text().strip()
        if not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d', time) or not command:
            self._set_status(tr('Isi waktu HH:MM yang valid dan perintah.', 'Enter a valid HH:MM time and command.'))
            return
        message = tr(f'Buat rutinitas aktif setiap hari {time} (waktu lokal)?\n\nPerintah: {command}\n\nJika waktu telah lewat, perintah dapat segera dikirim saat sesi tersambung.',
                     f'Create an enabled routine every day at {time} (local time)?\n\nCommand: {command}\n\nIf the time has passed, the command may be sent immediately when a session connects.')
        if not self._ask(tr('Buat rutinitas?', 'Create routine?'), message, tr('Buat', 'Create')):
            return
        from core.routines import Routine, Schedule
        routine = Routine(uuid4().hex, command[:60], Schedule(time), command, True)
        def work(store):
            if store.add(routine) != routine:
                raise RuntimeError('Duplicate id')
            return True
        self._start_write(work, 'create', (time, command))

    def change_enabled(self, routine):
        if self.loading or self.busy or self.rows is None:
            return
        enable = not routine.enabled
        if enable:
            from core.routines import validate_schedule
            if validate_schedule(routine.schedule) or not routine.payload.strip():
                self._set_operation(tr('Jadwal atau perintah tidak valid; rutinitas tidak dapat diaktifkan.', 'Invalid schedule or command; routine cannot be enabled.'))
                return
            message = tr(f'Aktifkan rutinitas ini? Jika waktunya sudah lewat, perintah dapat segera dikirim.\n\n{schedule_text(routine.schedule)}\n{routine.payload}',
                         f'Enable this routine? If its time has passed, the command may be sent immediately.\n\n{schedule_text(routine.schedule)}\n{routine.payload}')
            if not self._ask(tr('Aktifkan rutinitas?', 'Enable routine?'), message, tr('Aktifkan', 'Enable')):
                return
        self._start_write(lambda store: bool(store.set_enabled_if_unchanged(routine, enable)), 'toggle')

    def confirm_delete(self, routine):
        if self.loading or self.busy or self.rows is None:
            return
        message = tr(f'Hapus rutinitas ini?\n\n{routine.name}\n{schedule_text(routine.schedule)}\n{routine.payload}',
                     f'Delete this routine?\n\n{routine.name}\n{schedule_text(routine.schedule)}\n{routine.payload}')
        if self._ask(tr('Hapus rutinitas?', 'Delete routine?'), message, tr('Hapus', 'Delete')):
            self._start_write(lambda store: store.remove_if_unchanged(routine), 'delete')

    def _start_write(self, action, kind, fields=None):
        if self.loading or self.busy:
            return
        self.busy = True; self._controls()
        self._set_status(tr('Menyimpan…', 'Saving…'))
        def work():
            try:
                from memory.routine_store import default_store
                ok, error = action(default_store()), None
            except Exception as exc:  # noqa: BLE001
                ok, error = False, f'{type(exc).__name__}: {exc}'
            run_on_qt_thread(self.owner, lambda: self._written(kind, fields, ok, error))
        try:
            threading.Thread(target=work, name='desktop-routines-write', daemon=True).start()
        except RuntimeError as exc:
            self._written(kind, fields, False, str(exc))

    def _written(self, kind, fields, ok, error):
        self.busy = False
        if error:
            print(f'[JARVIS] Routine write failed: {error}')
            message = tr('Perubahan gagal disimpan; periksa data dan muat ulang.', 'Could not save the change; check the data and refresh.')
        elif not ok:
            message = tr('Rutinitas berubah atau sudah tidak ada; tidak ada perubahan.', 'Routine changed or no longer exists; no change was made.')
        else:
            message = tr('Perubahan tersimpan.', 'Change saved.')
            if kind == 'create' and fields == (self.time_field.text().strip(), self.command_field.text().strip()):
                self.time_field.clear(); self.command_field.clear()
        # Refresh from disk, retaining a truthful operation result even if that read fails.
        self.reload_requested = False
        self.refresh()
        self._set_operation(message)
