"""Accessible, keyboard-focusable descriptions for the painted audit rows."""
from ui.command_paint import GEOMETRY


def install(window):
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QLabel

    labels = []
    x, _, width, height = GEOMETRY['row_hl']
    for index in range(3):
        label = QLabel(window)
        label.setGeometry(x, GEOMETRY['rows_y'] + index * GEOMETRY['rows_pitch'], width, height)
        label.setFocusPolicy(Qt.FocusPolicy.TabFocus)
        label.setStyleSheet('QLabel { background:transparent; border:0; } '
                            'QLabel:focus { border:1px solid #58aaff; border-radius:10px; }')
        label.hide()
        labels.append(label)
    window._audit_accessible_labels = labels


def update(window, rows):
    for label, row in zip(window._audit_accessible_labels, list(rows) + [None] * 3):
        if row is None:
            label.hide()
            continue
        description = f'{row.label}: {row.state}. {row.subtitle}'
        label.setAccessibleName(description)
        label.setToolTip(description)
        label.show()
