"""ui/wake_sleep.py — baris input "tidur otomatis setelah N menit".

Dipisah dari ui/window.py karena berkas itu mencoret batas 7.000 baris;
setiap surface baru harus tinggal di berkasnya sendiri (lihat AGENTS.md dan
ujian test_ui_split.py). Logika inti (simpan ke config, perbarui sleep
watcher) ada di main.py (`_ui_wake_sleep_timeout`); berkas ini hanya menyedia
kan tampilan.
"""

from __future__ import annotations

from PyQt6.QtWidgets import QHBoxLayout, QLabel, QSpinBox

from core.i18n import label as _t
from memory.config_manager import get_wake_sleep_timeout


def build_wake_sleep_row(on_change) -> QHBoxLayout:
    """Baris horizontal: label + spinbox (menit, 1–120).

    `on_change(minutes: float)` dipanggil setiap kali nilai berubah. Nilai
    awal dibaca dari config (default 5 menit / 300 detik).
    """
    row = QHBoxLayout()
    row.setContentsMargins(0, 0, 0, 0)
    row.addWidget(QLabel(_t("ui.wake.sleep_after")))
    spin = QSpinBox()
    spin.setRange(1, 120)
    spin.setSuffix(" " + _t("ui.wake.minutes"))
    spin.setValue(int(get_wake_sleep_timeout() / 60))
    spin.setFixedHeight(26)
    spin.setFixedWidth(90)
    spin.valueChanged.connect(lambda m: on_change(float(m)))
    row.addWidget(spin)
    row.addStretch(1)
    return row
