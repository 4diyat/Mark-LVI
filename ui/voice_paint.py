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
            inner = QColor("#00d4ff")
            inner.setAlphaF(0.0)
            outer = QColor("#00d4ff")
            outer.setAlphaF(alpha)
            gradient.setColorAt(_model.GLOW_INNER, inner)
            gradient.setColorAt(1.0, outer)
            painter.fillRect(QRectF(0, 0, width, height), gradient)

            edge = QColor("#00d4ff")
            edge.setAlphaF(_model.EDGE_OPACITY if active else 0.0)
            pen = QPen(edge)
            pen.setWidth(_model.EDGE_PX)
            painter.setPen(pen)
            half = _model.EDGE_PX / 2.0
            painter.drawRect(QRectF(half, half, width - _model.EDGE_PX, height - _model.EDGE_PX))

        _paint_camera(painter, overlay)
        _paint_orb(painter, overlay)
        _paint_words(painter, overlay)
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
    painter.setPen(QPen(QColor("#1c3a4a"), 1))
    painter.setBrush(QColor("#071018"))
    painter.drawRoundedRect(frame, _model.CAMERA_RADIUS, _model.CAMERA_RADIUS)

    label = QColor("#7f97a6")
    painter.setPen(label)
    font = painter.font()
    font.setPixelSize(10)
    painter.setFont(font)
    painter.drawText(QPointF(x + 16, y + 24), _model.camera_label(overlay._camera_available))

    if overlay.gestures_paused:
        painter.setPen(QColor("#7f97a6"))
        painter.drawText(QPointF(x + 16, y + 44), _model.PAUSED_WORD)
        return

    hand = overlay.hand
    palm = _hand.hand_point(hand)
    pose = _hand.pose_of(hand)
    spread = 0.95
    cyan = QColor("#00d4ff")
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
    painter.setPen(QColor("#00d4ff"))
    painter.drawText(QPointF(*_model.LABEL_AT), _model.status_word(overlay.state))

    font.setPixelSize(13)
    painter.setFont(font)
    painter.setPen(QColor("#eaf6ff"))
    transcript = _model.lines_for(overlay.transcript, 74)[:3]
    for index, line in enumerate(transcript):
        painter.drawText(QPointF(_model.TRANSCRIPT_AT[0] - _half_width(painter, line),
                                 _model.TRANSCRIPT_AT[1] + index * 22), line)

    font.setPixelSize(11)
    painter.setFont(font)
    painter.setPen(QColor("#7f97a6"))
    answer = _model.lines_for(overlay.answer, 96)[:2]
    for index, line in enumerate(answer):
        painter.drawText(QPointF(_model.ANSWER_AT[0] - _half_width(painter, line),
                                 _model.ANSWER_AT[1] + index * 18), line)

    font.setPixelSize(10)
    painter.setFont(font)
    painter.drawText(QPointF(*_model.FOOTNOTE_AT), _model.footnote())


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


