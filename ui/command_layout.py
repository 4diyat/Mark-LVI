"""Fit the command surface to the current screen without clipping controls.

The painter uses a 960x490 reference artboard; real child widgets and their
fonts use the same scale. This keeps the large mockup proportions on desktop
while preserving the complete interface on smaller displays.
"""
from ui.command_paint import BAR_HEIGHT, BAR_WIDTH, FONT, GEOMETRY


def rect(scale, values):
    return tuple(round(value * scale) for value in values)


def scale_for(width, height):
    """Keep a small margin and never enlarge beyond the reference artboard."""
    return min(1., max(1, width - 24) / BAR_WIDTH,
               max(1, height - 24) / BAR_HEIGHT)


def apply(bar, scale):
    from PyQt6.QtCore import QSize
    from PyQt6.QtGui import QFont

    scale = max(.01, min(1.0, float(scale)))
    window = bar._window
    window._layout_scale = scale
    window.setFixedSize(*rect(scale, (BAR_WIDTH, BAR_HEIGHT)))
    bar._field.setGeometry(*rect(scale, GEOMETRY['title']))
    font = QFont(FONT.split(',')[0].strip().strip("'"))
    font.setPointSizeF(max(1, 14 * scale))
    bar._field.setFont(font)
    suggestion = getattr(bar, '_suggestions', None)
    if suggestion is not None:
        suggestion.setGeometry(*rect(scale, (BAR_WIDTH - 104, 82, 60, 52)))
        size = max(1, round(28 * scale))
        suggestion.setIconSize(QSize(size, size))
    retry = getattr(bar, '_retry_button', None)
    if retry is not None:
        retry.setGeometry(*rect(scale, (BAR_WIDTH - 153, 147, 120, 22)))
    x, _, width, height = GEOMETRY['row_hl']
    for index, label in enumerate(getattr(window, '_audit_accessible_labels', ())):
        label.setGeometry(*rect(scale, (x, GEOMETRY['rows_y'] + index * GEOMETRY['rows_pitch'], width, height)))
    window.update()


def fit_screen(bar):
    """Use the screen under the pointer; if unavailable, retain the reference."""
    try:
        from PyQt6.QtGui import QCursor, QGuiApplication
        screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        if screen is None:
            return
        available = screen.availableGeometry()
        scale = scale_for(available.width(), available.height())
        apply(bar, scale)
        bar._window.move(available.x() + (available.width() - bar._window.width()) // 2,
                         available.y() + (available.height() - bar._window.height()) // 2)
    except Exception as exc:  # noqa: BLE001 — painting still works without screen information
        print(f'[JARVIS] Command bar: screen sizing unavailable — {type(exc).__name__}: {exc}')
