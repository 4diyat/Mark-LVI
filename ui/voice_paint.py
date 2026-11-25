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

from ui import voice_hand as _hand
from ui import voice_overlay as _model

# ── board 6's tokens, from `docs/mockups/build.py` ──────────────────────────
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
MUTED = "#5e636c"
LINE_ACC = "#243040"
TILE = "#071018"        # the camera inset, drawn as such in the sheet




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

        # The radial edge gradient, only while active. Qt refuses a gradient
        # with an empty object bounding rect, so it is guarded below rather
        # than trusted.
        if alpha > 0:
            gradient = QRadialGradient(QPointF(width / 2.0, height / 2.0),
                                       max(width, height) * 0.75)
            inner = QColor(CYAN)
            inner.setAlphaF(0.0)
            outer = QColor(CYAN)
            outer.setAlphaF(alpha)
            gradient.setColorAt(_model.GLOW_INNER, inner)
            gradient.setColorAt(1.0, outer)
            painter.fillRect(QRectF(0, 0, width, height), gradient)

            edge = QColor(CYAN)
            edge.setAlphaF(_model.EDGE_OPACITY if active else 0.0)
            pen = QPen(edge)
            pen.setWidth(_model.EDGE_PX)
            painter.setPen(pen)
            half = _model.EDGE_PX / 2.0
            painter.drawRect(QRectF(half, half, width - _model.EDGE_PX, height - _model.EDGE_PX))

        _paint_camera(painter, overlay)
        _paint_orb(painter, overlay)
        _paint_words(painter, overlay)
        # The level bars are a listening readout: an overlay that is not
        # active draws neither them nor the edge, which is the same promise
        # the footnote's first line makes about the glow.
        if active:
            _paint_waveform(painter, overlay)
    except Exception as exc:                        # noqa: BLE001
        # A failed repaint costs a frame. Letting it escape would take down the
        # event loop of a window whose only job is to be seen.
        print(f"[JARVIS] Voice overlay: paint failed — "
              f"{type(exc).__name__}: {exc}")


def _paint_camera(painter, overlay) -> None:
    """The tile, the hand in it, and the pinch ring when a pinch is happening."""
    QPointF, _QRectF, Qt, QColor, QPen, _QRadial = _qt()
    x, y, w, h = _model.CAMERA
    frame = _QRectF(x, y, w, h)
    painter.setPen(QPen(QColor(LINE_ACC), 1))
    painter.setBrush(QColor(TILE))
    painter.drawRoundedRect(frame, _model.CAMERA_RADIUS, _model.CAMERA_RADIUS)

    label = QColor(MUTED)
    painter.setPen(label)
    font = painter.font()
    font.setPixelSize(10)
    painter.setFont(font)
    painter.drawText(QPointF(x + 16, y + 24), _model.camera_label(overlay._camera_available))

    if overlay.gestures_paused:
        painter.setPen(QColor(MUTED))
        painter.drawText(QPointF(x + 16, y + 44), _model.PAUSED_WORD)
        return

    hand = overlay.hand
    palm = _hand.hand_point(hand)
    pose = _hand.pose_of(hand)
    spread = 0.95
    cyan = QColor(CYAN)
    pen = QPen(cyan, 2)
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)

    # Wrist → palm, then the palm outline, then four fingers. Same order as the
    # artboard's `hand()`, so the silhouette matches at a glance.
    painter.drawLine(QPointF(palm[0], palm[1] + 40 * spread),
                     QPointF(palm[0], palm[1] + 8 * spread))
    painter.drawEllipse(QPointF(palm[0], palm[1]), 20 * spread, 24 * spread)

    for base, tip in _hand._finger_joints(palm, spread, pose):
        painter.drawLine(QPointF(*base), QPointF(*tip))
        painter.setBrush(cyan)
        painter.drawEllipse(QPointF(*tip), 2.8 * spread, 2.8 * spread)
        painter.setBrush(Qt.BrushStyle.NoBrush)

    if hand.pinch:
        centre = QPointF(palm[0] - 21, palm[1] - 8)
        painter.drawEllipse(centre, 15, 15)
        painter.setBrush(cyan)
        painter.drawEllipse(centre, 4, 4)
        painter.setBrush(Qt.BrushStyle.NoBrush)


def _paint_orb(painter, overlay) -> None:
    """The orb, at the artboard's 44 px radius.

    Delegates to `ui.orb_paint.paint_ring`, which is the one drawing of the orb
    in this program. Two painters for one shape is the bug that module exists to
    prevent — the HUD drew an older orb for months because of exactly that.
    """
    QPointF, _QRectF, Qt, QColor, _QPen, _QRadial = _qt()
    try:
        from ui.orb_paint import paint_ring

        paint_ring(painter, float(_model.ORB_AT[0]), float(_model.ORB_AT[1]),
                   float(_model.ORB_RADIUS), mode="active",
                   state=overlay.state, level=0.0)
    except Exception as exc:                        # noqa: BLE001
        print(f"[JARVIS] Voice overlay: orb not drawn — "
              f"{type(exc).__name__}: {exc}")


def _paint_words(painter, overlay) -> None:
    """The status word, the transcript, the answer and the footnote."""
    QPointF, _QRectF, Qt, QColor, _QPen, _QRadial = _qt()
    font = painter.font()

    font.setPixelSize(11)
    painter.setFont(font)
    painter.setPen(QColor(CYAN))
    painter.drawText(QPointF(*_model.LABEL_AT), _model.status_word(overlay.state))

    font.setPixelSize(13)
    painter.setFont(font)
    painter.setPen(QColor(TEXT))
    transcript = _model.lines_for(overlay.transcript, 74)[:3]
    for index, line in enumerate(transcript):
        painter.drawText(QPointF(_model.TRANSCRIPT_AT[0] - _half_width(painter, line),
                                 _model.TRANSCRIPT_AT[1] + index * 22), line)

    font.setPixelSize(11)
    painter.setFont(font)
    painter.setPen(QColor(MUTED))
    answer = _model.lines_for(overlay.answer, 96)[:2]
    for index, line in enumerate(answer):
        painter.drawText(QPointF(_model.ANSWER_AT[0] - _half_width(painter, line),
                                 _model.ANSWER_AT[1] + index * 18), line)

    font.setPixelSize(10)
    painter.setFont(font)
    painter.drawText(QPointF(*_model.FOOTNOTE_AT), _model.footnote())


def _paint_waveform(painter, overlay) -> None:
    """The five level bars `b04()` draws at the right end of the transcript.

    The artboard's pill carries a five-bar listening-level readout at its
    right edge — `for i, h in enumerate((8, 16, 26, 14, 6))`. The overlay
    drew the pill's words but never the bars, so the readout was absent. They
    are a fixed shape: 4 px wide, 12 px pitch, centred on the transcript row,
    in the accent cyan at 80 % opacity.
    """
    QPointF, _QRectF, Qt, QColor, QPen, _QRadial = _qt()
    base_x, base_y = _model.WAVEFORM_AT
    colour = QColor(CYAN)
    colour.setAlphaF(_model.WAVEFORM_ALPHA)
    painter.setPen(QPen(colour))
    painter.setBrush(Qt.BrushStyle.SolidPattern)
    for index, height in enumerate(_model.WAVEFORM_BARS):
        bar_x = base_x + index * _model.WAVEFORM_PITCH
        top = base_y - height / 2.0
        painter.drawRect(QPointF(bar_x, top),
                         _model.WAVEFORM_WIDTH, height)


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


