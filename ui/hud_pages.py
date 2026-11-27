"""Live system status and six honest entry points for the main HUD."""
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import (QFrame, QGridLayout, QHBoxLayout, QLabel, QProgressBar,
                             QPushButton, QVBoxLayout, QWidget)

from core import i18n
from ui.hud_icons import icon


def tr(id_text, en_text):
    return id_text if i18n.active_locale() == 'id' else en_text


def heading(text, name='sectionTitle'):
    label = QLabel(text)
    label.setObjectName(name)
    label.setTextFormat(Qt.TextFormat.PlainText)
    return label


class QuickAction(QPushButton):
    """A non-destructive draft suggestion, not an immediate action."""
    def __init__(self, title, description, symbol, colour, callback):
        super().__init__()
        self.setObjectName('quickCard')
        self.setMinimumHeight(180)
        self.setAccessibleName(title)
        self.setToolTip(description)
        self.clicked.connect(callback)
        box = QVBoxLayout(self)
        box.setContentsMargins(12, 12, 12, 10)
        box.setSpacing(5)
        badge = heading('', 'quickIcon')
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge.setFixedSize(46, 46)
        badge.setPixmap(icon(symbol, colour, 25).pixmap(QSize(25, 25)))
        tint = QColor(colour)
        badge.setStyleSheet(f'border:1px solid {colour}; background:rgba('
                            f'{tint.red()},{tint.green()},{tint.blue()},55); border-radius:10px;')
        title_label = heading(title, 'cardTitle')
        title_label.setWordWrap(True)
        desc = heading(description, 'quickDesc')
        desc.setWordWrap(True)
        self.title_label, self.desc_label = title_label, desc
        for widget in (badge, title_label, desc):
            widget.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            box.addWidget(widget)
        box.addStretch()

    def resizeEvent(self, event):  # noqa: N802
        super().resizeEvent(event)
        compact = self.width() < 150
        self.title_label.setStyleSheet(f'font-size:{13 if compact else 17}px; font-weight:600;')
        self.desc_label.setStyleSheet(f'font-size:{12 if compact else 14}px;')


class Metric(QFrame):
    def __init__(self, title, detail=''):
        super().__init__()
        self.setObjectName('metric')
        box = QVBoxLayout(self)
        box.setContentsMargins(16, 14, 16, 14)
        row = QVBoxLayout()
        row.setSpacing(4)
        row.addWidget(heading(title, 'eyebrow'))
        self.value = heading(tr('Tidak tersedia', 'Not available'), 'metricValue')
        row.addWidget(self.value)
        box.addLayout(row)
        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(5)
        box.addWidget(self.bar)
        if detail:
            box.addWidget(heading(detail, 'muted'))
        self.set_value(None)

    def set_value(self, value):
        self.value.setText(f'{value:.0f}%' if value is not None else tr('Tidak tersedia', 'Not available'))
        self.bar.setVisible(value is not None)
        if value is not None:
            self.bar.setValue(round(value))


class SystemCard(QFrame):
    def __init__(self):
        super().__init__()
        self.setObjectName('resultCard')
        outer = QVBoxLayout(self)
        outer.setContentsMargins(18, 15, 18, 14)
        header = QHBoxLayout()
        header.addWidget(heading('◉', 'accentIcon'))
        title = QVBoxLayout()
        title.addWidget(heading(tr('Status sistem', 'System status'), 'cardTitle'))
        title.addWidget(heading(tr('Pembacaan perangkat ini', 'This device’s readings'), 'muted'))
        header.addLayout(title)
        header.addStretch()
        header.addWidget(heading(tr('PEMBACAAN', 'READING'), 'eyebrow'))
        outer.addLayout(header)
        row = QHBoxLayout()
        self.cpu = Metric('CPU')
        self.ram = Metric('RAM')
        row.addWidget(self.cpu)
        row.addWidget(self.ram)
        outer.addLayout(row)
        actions = QHBoxLayout()
        self.clean = QPushButton(tr('Bersihkan', 'Clean up'))
        self.clean.setObjectName('secondary')
        self.clean.setEnabled(False)
        self.clean.setToolTip(tr('Tindakan pembersihan belum tersedia di sini.',
                                 'Cleanup is not yet available here.'))
        self.later = QPushButton(tr('Nanti', 'Later'))
        self.later.setObjectName('secondary')
        self.later.clicked.connect(self.hide)
        actions.addWidget(self.clean)
        actions.addWidget(self.later)
        actions.addStretch()
        outer.addLayout(actions)

    def update_values(self, cpu, ram):
        self.cpu.set_value(cpu)
        self.ram.set_value(ram)


class ModulesPage(QWidget):
    def __init__(self, on_draft, on_memory=None):
        super().__init__()
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(16)
        outer.addWidget(heading(tr('Modul', 'Modules'), 'pageTitle'))
        outer.addWidget(heading(tr('Ringkasan perangkat dan akses cepat ke kemampuan JARVIS.',
                                   'Device overview and quick access to JARVIS capabilities.'), 'muted'))
        metrics = QHBoxLayout()
        self.cpu = Metric('CPU')
        self.ram = Metric('RAM')
        self.ping = Metric('PING')
        self.ping_value = self.ping.value
        for item in (self.cpu, self.ram, self.ping):
            metrics.addWidget(item, 1)
        outer.addLayout(metrics)
        outer.addWidget(heading(tr('MODUL INTI', 'CORE MODULES'), 'eyebrow'))
        grid = QGridLayout()
        grid.setSpacing(12)
        self.cards = {}
        specs = [
            ('agenda', 'calendar-days', tr('Agenda', 'Schedule'), tr('Rencana dan jadwal', 'Plans and schedule'), 'agenda'),
            ('home', 'house', tr('Rumah Pintar', 'Smart Home'), tr('Belum tersedia', 'Not available yet'), None),
            ('code', 'file-text', tr('Kode', 'Code'), tr('Bantuan pengembangan', 'Development help'), 'code'),
            ('markets', 'chart-no-axes-column-increasing', tr('Pasar', 'Markets'), tr('Informasi pasar', 'Market information'), 'markets'),
            ('search', 'search', tr('Pencarian', 'Search'), tr('Cari informasi', 'Find information'), 'search'),
            ('memory', 'brain', tr('Memori', 'Memory'), tr('Lihat memori tersimpan', 'View stored memories'), None),
        ]
        for i, (key, symbol, title, desc, draft) in enumerate(specs):
            card = QPushButton()
            card.setObjectName('moduleCard')
            card.setAccessibleName(title)
            card.setMinimumHeight(115)
            layout = QVBoxLayout(card)
            layout.setContentsMargins(16, 13, 16, 13)
            glyph = heading('', 'accentIcon')
            glyph.setPixmap(icon(symbol, '#70bdff', 24).pixmap(QSize(24, 24)))
            layout.addWidget(glyph)
            layout.addWidget(heading(title, 'cardTitle'))
            description = heading(desc, 'muted')
            description.setWordWrap(True)
            layout.addWidget(description)
            for j in range(layout.count()):
                layout.itemAt(j).widget().setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            if key == 'memory' and callable(on_memory):
                card.clicked.connect(on_memory)
            elif draft:
                card.clicked.connect(lambda checked=False, k=draft: on_draft(k))
                card.setToolTip(tr('Siapkan draf di Obrolan', 'Prepare a draft in Chat'))
            else:
                card.setEnabled(False)
            self.cards[key] = card
            grid.addWidget(card, i // 3, i % 3)
        outer.addLayout(grid)
        outer.addStretch()

    def update_values(self, cpu, ram):
        self.cpu.set_value(cpu)
        self.ram.set_value(ram)
