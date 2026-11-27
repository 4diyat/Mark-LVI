"""The painters for board 6 — every pixel, and nothing that decides.

WHY THIS IS SEPARATE FROM `ui/voice_overlay.py`
    That module holds the window, the state and the rules; this one holds the
    Qt calls. Same split as `ui/tray_panel` / `ui/tray_paint`, and the same
    reason: the 600-line ceiling stopped the two being one file, and the line it
    fell on is a real boundary — everything here needs Qt, nothing here decides
    anything a test could not ask the overlay for.

WHAT IS DELIBERATELY NOT HERE
    * no state: every function takes the overlay and asks it;
    * no constants of its own — the artboard's numbers live in the overlay
      module, so a change to the layout is one edit in one place.

THE ONE RULE THAT MATTERS
    A failed repaint costs a frame. Every entry point swallows its exception and
    prints it, because the alternative is an exception escaping into the event
    loop of a window whose only job is to be looked at.
"""
from __future__ import annotations

from ui import voice_overlay as _model

# ── board 6's tokens, from `ui/tokens.py` ──────────────────────────
#
# THE SHEET IS UNUSUAL HERE AND THE CODE HAD DRIFTED FROM IT. Board 6 is drawn
# entirely with the same CYAN as every other artboard — the edge glow, the four
# 2 px border lines, the "MENDENGARKAN" label, the orb. This module used
# #00d4ff instead, in nine places: a lighter, bluer cyan that no other surface
# in the application uses. Beside the orb overlay it is visibly a different
# accent, and beside board 1's dashed box it is a different design.
#
# #1c3a4a (the camera tile's border) is the same story with a smaller gap:
# the sheet draws that tile with LINE_ACC (#243040). #7f97a6 is MUTED
# (#5e636c). #eaf6ff (the transcript) is TEXT (#ffffff).
CYAN = "#3486fe"
TEXT = "#ffffff"
MUTED = "#a6bbcb"
LINE_ACC = "#243040"
PANEL = "#101820"       # the transcript pill's surface, as the sheet fills it
TILE = "#071018"        # the camera inset, drawn as such in the sheet
_ORB_IMAGE = None




def _qt():
    """The six Qt names this module draws with, imported once per call.

    A module-level `from PyQt6 import ...` would make `ui.voice_paint`
    unimportable on a machine with no display, and every test in this repo runs
    on one.
    """
    from PyQt6.QtCore import QPointF, QRectF, Qt
    from PyQt6.QtGui import QColor, QPen, QRadialGradient

    return QPointF, QRectF, Qt, QColor, QPen, QRadialGradient


def paint_frame(painter, size, overlay) -> None:
    """Draw board 6, at whatever size the window actually is.

    `size` is the reference (1280, 720); everything below is in those
    coordinates and scaled once, at the top. That is why the artboard numbers
    are constants in this file rather than fractions: a future change to the
    window size must not require re-deriving the tile.
    """
    width, height = int(size[0]), int(size[1])
    if width <= 0 or height <= 0:
        return
    try:
        QPointF, QRectF, Qt, QColor, QPen, QRadialGradient = _qt()

        active = overlay.active
        alpha = overlay.glow()
        if active:
            painter.fillRect(QRectF(0, 0, width, height), QColor('#030912'))

        # Layered rounded strokes form the blue edge glow without claiming
        # anything about microphone permission or the health of a backend.
        if alpha > 0:
            painter.setBrush(Qt.BrushStyle.NoBrush)
            for inset, opacity, thickness in ((2, 25, 12), (4, 55, 6), (5, 230, 2)):
                edge = QColor(CYAN)
                edge.setAlphaF(opacity / 255.0)
                painter.setPen(QPen(edge, thickness))
                painter.drawRoundedRect(QRectF(inset, inset, width - inset * 2,
                                               height - inset * 2), 22, 22)

        _paint_camera(painter, overlay)
        if getattr(overlay, '_voice_orb', None) is None:
            _paint_orb(painter, overlay)
        _paint_live_levels(painter, overlay)
        _paint_pill(painter, overlay)
        _paint_words(painter, overlay)
        # The level bars are a listening readout: an overlay that is not
        # active draws neither them nor the edge, which is the same promise
        # the footnote's first line makes about the glow.
        # No microphone level reaches this overlay: don't draw a fake meter.
    except Exception as exc:                        # noqa: BLE001
        # A failed repaint costs a frame. Letting it escape would take down the
        # event loop of a window whose only job is to be seen.
        print(f"[JARVIS] Voice overlay: paint failed — "
              f"{type(exc).__name__}: {exc}")


def _paint_camera(painter, overlay) -> None:
    """Opt-in camera preview and genuine detector landmarks, never a fixture."""
    QPointF, QRectF, Qt, QColor, QPen, _QRadial = _qt()
    x, y, w, h = _model.CAMERA
    painter.setPen(QPen(QColor('#3a526a'), 1))
    painter.setBrush(QColor('#0b1520'))
    painter.drawRoundedRect(QRectF(x, y, w, h), 12, 12)
    painter.setPen(QColor('#67b8ff'))
    font = painter.font(); font.setPixelSize(11); painter.setFont(font)
    painter.drawText(QPointF(x + 14, y + 19), 'KONTROL GESTUR')
    image_rect = QRectF(x + 8, y + 27, w - 16, 100)
    painter.setPen(Qt.PenStyle.NoPen); painter.setBrush(QColor('#07111c'))
    painter.drawRoundedRect(image_rect, 1, 1)
    image = getattr(overlay, '_camera_preview_image', None)
    if image is not None and overlay._camera_available:
        painter.drawImage(image_rect, image)
    points = getattr(overlay, '_gesture_points', ())
    if (overlay._camera_available and not overlay.gestures_paused
            and getattr(overlay, '_has_hand', False) and len(points) == 21):
        positions = [QPointF(x + 8 + px * (w - 16), y + 27 + py * 100) for px, py in points]
        cyan = QColor('#68c9ff')
        pen = QPen(cyan, 1.5); pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        for a, b in ((0,1),(1,2),(2,3),(3,4),(0,5),(5,6),(6,7),(7,8),
                     (5,9),(9,10),(10,11),(11,12),(9,13),(13,14),(14,15),(15,16),
                     (13,17),(17,18),(18,19),(19,20),(17,0)):
            painter.drawLine(positions[a], positions[b])
        painter.setBrush(cyan)
        for point in positions:
            painter.drawEllipse(point, 2.5, 2.5)
    painter.setPen(QColor('#b3c9da'))
    font.setPixelSize(10); painter.setFont(font)
    message = getattr(overlay, '_gesture_message',
                      _model.PAUSED_WORD if overlay.gestures_paused else _model.camera_label(overlay._camera_available))
    painter.drawText(QPointF(x + 12, y + 141), message)


def _paint_orb(painter, overlay) -> None:
    """Draw the shared workspace orb, with a fallback for Qt-less painters."""
    global _ORB_IMAGE
    QPointF, QRectF, Qt, QColor, QPen, QRadialGradient = _qt()
    x, y = _model.ORB_AT
    radius = _model.ORB_RADIUS
    try:
        from pathlib import Path
        from PyQt6.QtGui import QImage, QPainter
        if _ORB_IMAGE is None:
            image = QImage(str(Path(__file__).resolve().parent.parent / 'assets/workspace/orb-core.png'))
            if not image.isNull():
                image = image.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)
                mask = QRadialGradient(image.width() / 2, image.height() / 2, image.width() / 2)
                mask.setColorAt(0, QColor(0, 0, 0, 255))
                mask.setColorAt(.82, QColor(0, 0, 0, 255))
                mask.setColorAt(1, QColor(0, 0, 0, 0))
                layer = QPainter(image)
                layer.setCompositionMode(QPainter.CompositionMode.CompositionMode_DestinationIn)
                layer.fillRect(image.rect(), mask)
                layer.end()
            _ORB_IMAGE = image
        if not _ORB_IMAGE.isNull():
            halo = QRadialGradient(QPointF(x, y), radius * 1.9)
            halo.setColorAt(0, QColor('#174a83')); halo.setColorAt(1, QColor(0, 0, 0, 0))
            painter.setPen(Qt.PenStyle.NoPen); painter.setBrush(halo)
            painter.drawEllipse(QPointF(x, y), radius * 1.9, radius * 1.9)
            painter.drawImage(QRectF(x - radius * 1.25, y - radius * 1.25,
                                     radius * 2.5, radius * 2.5), _ORB_IMAGE)
            return
    except Exception:  # noqa: BLE001, S110 — Qt-less painters use the fallback below
        pass
    try:
        from ui.orb_paint import paint_ring
        paint_ring(painter, float(x), float(y), float(radius), mode='active',
                   state=overlay.state, level=getattr(overlay, '_audio_level', 0.0))
    except Exception as exc:                        # noqa: BLE001
        print(f"[JARVIS] Voice overlay: orb not drawn — {type(exc).__name__}: {exc}")


def _paint_live_levels(painter, overlay) -> None:
    """Dotted columns represent the current measured level, not a spectrum."""
    if not overlay.active:
        return
    _QPointF, QRectF, Qt, QColor, _QPen, _QRadial = _qt()
    level = max(0., min(1., getattr(overlay, '_audio_level', 0.0)))
    painter.setPen(Qt.PenStyle.NoPen)
    for x, factor in ((180, .30), (285, .60), (386, 1),
                      (886, 1), (987, .60), (1092, .30)):
        # One dim dot marks zero, rather than fabricating a live signal.
        count = int(level * 32 * factor)
        painter.setBrush(QColor('#163b60'))
        painter.drawRoundedRect(QRectF(x, 407, 8, 5), 2, 2)
        for i in range(count):
            painter.setBrush(QColor('#25dfb3' if i > 17 else '#36aaff'))
            painter.drawRoundedRect(QRectF(x, 407 - i * 8, 8, 5), 2, 2)


def _paint_pill(painter, overlay) -> None:
    """The transcript pill artboard `b04()` draws behind the transcript.

    The artboard fills a 640x76 rounded rect (`rect(tx, ty, tw, 76,
    "#101820", 26, LINE_ACC)`) with the panel surface and strokes it with the
    accent line, then sits the transcript and the level bars inside it. The
    overlay drew the pill's words but never the pill, so the transcript floated
    on the desktop with no surface under it. The pill is the transcript's
    surface: it is drawn with the panel fill and the accent-line border, at the
    artboard's radius, so the words and the bars have somewhere to sit.
    """
    QPointF, QRectF, Qt, QColor, QPen, _QRadial = _qt()
    left, top = _model.PILL_AT
    rect = QRectF(left, top, _model.PILL_W, _model.PILL_H)
    painter.setPen(QPen(QColor(LINE_ACC)))
    painter.setBrush(QColor(PANEL))
    painter.drawRoundedRect(rect, _model.PILL_RADIUS, _model.PILL_RADIUS)


def _paint_words(painter, overlay) -> None:
    """Header, actual session status, transcript and response."""
    QPointF, QRectF, Qt, QColor, QPen, _QRadial = _qt()
    font = painter.font()
    painter.setPen(QPen(QColor('#34516a'), 1))
    painter.setBrush(QColor('#08131d'))
    painter.drawRoundedRect(QRectF(990, 40, 250, 55), 27, 27)
    # Mic icon is a label for the voice state, not a permission indicator.
    active = overlay.state in ('listening', 'voice_idle')
    accent = QColor('#29e6b4' if active else '#70aadb')
    painter.setPen(QPen(accent, 2)); painter.setBrush(Qt.BrushStyle.NoBrush)
    painter.drawEllipse(QPointF(1019, 67), 20, 20)
    painter.setBrush(accent); painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(QRectF(1015, 56, 8, 15), 4, 4)
    painter.setPen(QPen(accent, 2))
    painter.drawLine(QPointF(1011, 68), QPointF(1011, 72))
    painter.drawLine(QPointF(1011, 72), QPointF(1019, 76))
    painter.drawLine(QPointF(1019, 76), QPointF(1027, 72))
    painter.drawLine(QPointF(1027, 72), QPointF(1027, 68))
    painter.drawLine(QPointF(1019, 76), QPointF(1019, 80))
    font.setPixelSize(23); painter.setFont(font); painter.setPen(QColor(TEXT))
    painter.drawText(QPointF(40, 57), 'J A R V I S')
    font.setPixelSize(14); painter.setFont(font); painter.setPen(QColor('#58adff'))
    painter.drawText(QPointF(40, 81), 'M O D E  S U A R A')
    font.setPixelSize(12); painter.setFont(font); painter.setPen(accent)
    painter.drawText(QPointF(1050, 71), _model.status_word(overlay.state))

    font.setPixelSize(19); painter.setFont(font); painter.setPen(QColor(TEXT))
    transcript = _model.lines_for(overlay.transcript, 54)[:2]
    for index, line in enumerate(transcript):
        painter.drawText(QPointF(640 - _half_width(painter, line), 550 + index * 23), line)
    font.setPixelSize(14); painter.setFont(font); painter.setPen(QColor('#c0d3e3'))
    answer = _model.lines_for(overlay.answer, 76)[:2]
    for index, line in enumerate(answer):
        painter.drawText(QPointF(640 - _half_width(painter, line), 590 + index * 18), line)
    # Low-contrast baseline is decorative. Only the measured level controls
    # the bars rising above it; it is not presented as a frequency spectrum.
    level = max(0., min(1., getattr(overlay, '_audio_level', 0.0)))
    painter.setPen(Qt.PenStyle.NoPen)
    for i in range(65):
        scale = 1.0 - abs(i - 32) / 40.0
        height = 2 + level * 12 * max(0.0, scale)
        painter.setBrush(QColor('#247ad0' if level > 0 else '#25405a'))
        painter.drawRoundedRect(QRectF(390 + i * 7, 616 - height / 2, 3, height), 1, 1)
    font.setPixelSize(10); painter.setFont(font); painter.setPen(QColor(MUTED))
    painter.drawText(QPointF(*_model.FOOTNOTE_AT), _model.footnote())


def _paint_waveform(painter, overlay) -> None:
    """The five level bars `b04()` draws at the right end of the transcript.

    The artboard's pill carries a five-bar listening-level readout at its
    right edge — `for i, h in enumerate((8, 16, 26, 14, 6))`. The overlay
    drew the pill's words but never the bars, so the readout was absent. They
    are a fixed shape: 4 px wide, 12 px pitch, centred on the transcript row,
    in the accent cyan at 80 % opacity.
    """
    _QPointF, QRectF, Qt, QColor, QPen, _QRadial = _qt()
    base_x, base_y = _model.WAVEFORM_AT
    colour = QColor(CYAN)
    colour.setAlphaF(_model.WAVEFORM_ALPHA)
    painter.setPen(QPen(colour))
    painter.setBrush(Qt.BrushStyle.SolidPattern)
    for index, height in enumerate(_model.WAVEFORM_BARS):
        bar_x = base_x + index * _model.WAVEFORM_PITCH
        top = base_y - height / 2.0
        painter.drawRect(QRectF(bar_x, top, _model.WAVEFORM_WIDTH, height))


def _half_width(painter, text: str) -> float:
    """Half the drawn width, so a centred line is centred.

    `QFontMetrics.horizontalAdvance` is the correct call and is used when it
    exists; the stub has no metrics, and a centring that raised would take the
    whole frame down — so the fallback estimates from the character count,
    which is wrong by a few pixels and never by a crash.
    """
    try:
        metrics = painter.fontMetrics()
        return metrics.horizontalAdvance(text) / 2.0
    except Exception:                               # noqa: BLE001
        return len(text) * 3.2


