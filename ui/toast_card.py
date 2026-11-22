"""The toast card — board 2's 340 px rectangle, drawn.

WHY THIS MODULE EXISTS
    Board 2 draws a card: a 340 px rounded rectangle with a 3 px accent rule
    down its left edge, a title, a body, and up to two buttons. The build had
    the ARITHMETIC for stacking toasts (`ui/toast_queue.py`) and nothing that
    drew one — the only thing a user ever saw was the OS notification from
    `core/notify.py`, which is a different widget on a different surface and
    cannot say "2 dari 3 terpakai" in the panel's voice.

WHY THE NUMBERS ARE HERE AND NOT IN THE PAINT CALL
    `toast()` and `toast_queue()` in `docs/mockups/build.py` are the source of
    truth, and each of the constants below is one of their literals. A paint
    call carrying `20` inline is a number no test can fail on; a constant with
    an artboard reference beside it is one `tests/test_toast_card.py` can.

WHY THE TEXT IS FITTED BY COUNT AND NOT MEASURED
    `QFontMetrics` needs a real font and a real screen. This sandbox has neither,
    and more importantly the EFFORT is wrong: a title that is too long for a
    340 px card is a caller's mistake, not a typographic problem to solve at
    paint time. `fit_text` caps the length and adds an ellipsis, which is
    deterministic, testable, and never draws outside the card.

WHAT THIS DOES NOT DO
    It does not own a window, a timer, or a queue. `ui/toast_stack.py` is the
    window and `ui/toast_queue.py` is the data; this is the one function that
    turns one `Toast` into marks on a painter.
"""
from __future__ import annotations

# ── the card's geometry, from `toast()` in docs/mockups/build.py ───────────
# `def toast(x, y, w=340, ...)`; `n02()` calls `toast_queue(700, 330, 340, ...)`.
CARD_W = 340
CARD_RADIUS = 12          # R_CARD
RULE_W = 3                # rect(x, y+14, 3, h-28, accent, 1.5)
RULE_INSET = 14
PAD = 20                  # txt(x + 20, ...) for both lines and the buttons
TITLE_DY = 30             # txt(x + 20, y + 30, title, 13, ...)
TITLE_PX = 13
BODY_DY = 50              # txt(x + 20, y + 50, body, 11.5, ...)
BODY_PX = 11.5
BUTTON_DY = 64            # rect(ax, y + 64, aw, 22, ...)
BUTTON_H = 22
BUTTON_GAP = 10           # ax += aw + 10
BUTTON_PX_EM = 6.4        # aw = 12 + len(a) * 6.4
BUTTON_PAD = 12
GAP = 12                  # toast_queue: off += h + 12

# ── the two colours a card needs beyond its accent ────────────────────────
CARD_FILL = "#0C1B26"     # rect(x, y, w, h, "#0C1B26", R_CARD, LINE)
CARD_LINE = "#17323F"     # LINE
TEXT = "#E6F4F8"
MUTED = "#8FA9B5"


def fit_text(text, limit_px: int) -> str:
    """`text` shortened to fit `limit_px` at the card's character width.

    COUNTED, NOT MEASURED, and that is the honest version of this function: the
    width of a string depends on the font that ends up rendering it (Space
    Grotesk, falling back to Segoe UI), and a measurement here would be a guess
    dressed as a fact. `BUTTON_PX_EM` is the artboard's own estimate for the
    same job, so the same constant is used and the estimate stays in one place.

    Never raises: a toast's title can be anything a caller passed.
    """
    text = str(text or "")
    if not text:
        return ""
    budget = max(1, int(limit_px / BUTTON_PX_EM))
    if len(text) <= budget:
        return text
    return text[: max(0, budget - 1)].rstrip() + "…"


def button_width(label: str) -> float:
    """`aw = 12 + len(a) * 6.4` — `toast()`'s own button arithmetic."""
    return BUTTON_PAD + len(str(label or "")) * BUTTON_PX_EM


def stack_offsets(toasts) -> list[int]:
    """Where each card starts, in a stack that grows downward. `n02()`'s pitch."""
    out, offset = [], 0
    for toast in toasts:
        out.append(offset)
        offset += toast.height + GAP
    return out


def stack_heights(toasts) -> list[int]:
    return [toast.height for toast in toasts]


def window_size(visible_max: int = 3) -> tuple[int, int]:
    """The window the stack is drawn in: as wide as a card, as tall as the worst
    case of three full cards.

    SIZED FOR THE MAXIMUM, NOT FOR WHAT IS ON SCREEN. A window that grows as
    toasts arrive moves every existing card under the cursor, which is a button
    that runs away from the click. The same argument the orb window's fixed size
    already makes.
    """
    from ui.toast_queue import HEIGHT_WITH_ACTIONS

    count = max(1, int(visible_max))
    return (CARD_W, count * HEIGHT_WITH_ACTIONS + (count - 1) * GAP)


def paint_card(painter, x: float, y: float, toast) -> None:
    """Draw one toast at (x, y), top-left of its card.

    ORDER MATTERS AND IT IS THE ARTBOARD'S: card, rule, title, body, buttons.
    The rule is drawn after the card so it sits on top of the fill rather than
    under it — drawing it first would hide it in the fill's own colour.
    """
    from PyQt6.QtCore import QRectF, Qt
    from PyQt6.QtGui import QColor, QFont, QPen

    height = toast.height
    left = CARD_W - 2 * PAD

    # 1. the card
    pen = QPen(QColor(CARD_LINE), 1)
    painter.setPen(pen)
    painter.setBrush(QColor(CARD_FILL))
    painter.drawRoundedRect(QRectF(x, y, CARD_W, height),
                            CARD_RADIUS, CARD_RADIUS)

    # 2. the accent rule, inset at both ends
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(toast.accent))
    painter.drawRoundedRect(
        QRectF(x, y + RULE_INSET, RULE_W, height - 2 * RULE_INSET), 1.5, 1.5)

    # 3. the title
    title_font = QFont()
    title_font.setPixelSize(TITLE_PX)
    title_font.setBold(True)
    painter.setFont(title_font)
    painter.setPen(QColor(TEXT))
    painter.drawText(QRectF(x + PAD, y + TITLE_DY - TITLE_PX,
                            left, TITLE_PX * 1.6),
                     Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                     fit_text(toast.text, left))

    # 4. the body, when there is one
    if toast.body:
        body_font = QFont()
        body_font.setPixelSize(BODY_PX)
        painter.setFont(body_font)
        painter.setPen(QColor(MUTED))
        painter.drawText(QRectF(x + PAD, y + BODY_DY - BODY_PX,
                                left, BODY_PX * 1.6),
                         Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                         fit_text(toast.body, left))

    # 5. the buttons — the first one in cyan, the rest in the text colour, which
    #    is how `toast()` marks the primary action
    ax = x + PAD
    for index, label in enumerate(toast.actions):
        width = button_width(label)
        painter.setPen(QPen(QColor("#2A6477" if index else toast.accent), 1))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(
            QRectF(ax, y + BUTTON_DY, width, BUTTON_H), 11, 11)
        button_font = QFont()
        button_font.setPixelSize(11)
        painter.setFont(button_font)
        painter.setPen(QColor(toast.accent if index == 0 else TEXT))
        painter.drawText(
            QRectF(ax, y + BUTTON_DY, width, BUTTON_H),
            Qt.AlignmentFlag.AlignCenter,
            fit_text(label, width - 2))
        ax += width + BUTTON_GAP


__all__ = ["CARD_W", "CARD_RADIUS", "GAP", "PAD", "RULE_W", "button_width",
           "fit_text", "paint_card", "stack_heights", "stack_offsets",
           "window_size"]
