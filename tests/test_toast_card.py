"""The toast CARD — board 2's shape, as numbers and as paint calls.

WHY THIS FILE EXISTS SEPARATELY FROM `test_toast_board2.py`
    That file holds the DATA: what a toast knows, how long it lives, what the
    overflow label says. A scheduler thread can produce a toast, so all of it is
    answerable with no Qt at all.

    This file holds the DRAWING, and the drawing has no such luxury: it needs a
    painter. Every assertion therefore goes through a recorder — what was asked
    for, in what order, with which numbers — because that is the only part of a
    painting that can be checked on a machine with no display.

WHAT BOARD 2 DRAWS, AS COORDINATES
    `toast(x, y, w, title, body, actions, accent)`:
      - card `rect(x, y, w, h, #0C1B26, R_CARD=12, LINE)` where h is 96 or 74
      - an accent rule `rect(x, y+14, 3, h-28, accent, 1.5)`
      - the title at `(x+20, y+30)`, 13 px, weight 500
      - the body at `(x+20, y+50)`, 11.5 px, MUTED
      - buttons at `y+64`, 22 px tall, from `x+20`, each `12 + len*6.4` wide,
        10 px apart; the first one in CYAN, the rest in TEXT

WHAT CANNOT BE CHECKED HERE
    Whether the text FITS. A `QFontMetrics` measurement needs a real font, and
    this sandbox has no Qt. What is checked is that a long title is truncated
    rather than drawn past the card's edge — the arithmetic, not the pixels.
"""
from __future__ import annotations

import sys

import pytest

from tests import qtstub


@pytest.fixture()
def card(monkeypatch):
    stubs = qtstub.install_qt()
    saved = {k: v for k, v in sys.modules.items()
             if k == "PyQt6" or k.startswith("PyQt6.") or k == "ui" or k.startswith("ui.")}
    sys.modules.update(stubs)
    for name in [k for k in sys.modules if k == "ui" or k.startswith("ui.")]:
        sys.modules.pop(name, None)
    try:
        import ui.toast_card as module
        yield module
    finally:
        for name in list(sys.modules):
            if name == "ui" or name.startswith("ui."):
                sys.modules.pop(name, None)
        for name in [k for k in list(sys.modules) if k.startswith("PyQt6")]:
            if name not in saved:
                sys.modules.pop(name, None)
        sys.modules.update(saved)


class Recorder:
    """A painter that remembers every call, in order."""

    def __init__(self):
        self.calls = []
        self._pen = None
        self._brush = None

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)

        def record(*a, **k):
            self.calls.append((name, a, k))
            return None
        return record

    def setPen(self, pen):
        self._pen = pen
        self.calls.append(("setPen", (pen,), {}))

    def setBrush(self, brush):
        self._brush = brush
        self.calls.append(("setBrush", (brush,), {}))

    def setFont(self, font):
        self.calls.append(("setFont", (font,), {}))

    def setOpacity(self, value):
        self.calls.append(("setOpacity", (value,), {}))

    def kinds(self):
        return [name for name, _a, _k in self.calls]

    def texts(self):
        """Every string handed to `drawText`, in order.

        THE TEXT IS THE LAST ARGUMENT, not the second: `paint_card` calls
        `drawText(QRectF, flags, text)`, so `a[1]` is an alignment flag. This
        accessor read `a[1]` at first and the tests compared an enum to a
        string, which failed for a reason that had nothing to do with the card.
        """
        return [a[-1] for name, a, _k in self.calls if name == "drawText"]


def _qs(size=96):
    from ui.toast_queue import Toast

    return Toast(text="Rapat tim dimulai 10 menit lagi",
                 body="Ruang Rapat 2 · 5 peserta sudah masuk",
                 actions=("Buka tautan", "Tunda 5 mnt") if size == 96 else ())


# ── the box ───────────────────────────────────────────────────────────────

def test_the_card_is_340_wide_by_the_artboards_height(card):
    """`n02()` calls `toast_queue(700, 330, 340, items)` — 340 px wide."""
    assert card.CARD_W == 340
    assert card.CARD_RADIUS == 12          # R_CARD in build.py
    assert card.RULE_W == 3                # the accent rule


def test_the_card_draws_one_rounded_rectangle_at_its_own_size(card):
    from PyQt6.QtCore import QRectF

    painter = Recorder()
    toast = _qs()
    card.paint_card(painter, 0, 0, toast)
    rects = [a for name, a, _k in painter.calls if name == "drawRoundedRect"]
    # Four rounded rects: the card, the accent rule, and two buttons. The CARD
    # is the one at full width — the others are 3 px and two ~80 px pills.
    card_rects = [a for a in rects if round(a[0].width()) == card.CARD_W]
    assert len(card_rects) == 1, "the card is one rounded rect, not two boxes"
    frame = card_rects[0][0]
    assert isinstance(frame, QRectF)
    assert round(frame.height()) == toast.height == 96


def test_a_card_without_actions_is_short(card):
    from ui.toast_queue import Toast

    assert Toast(text="x").height == 74
    painter = Recorder()
    card.paint_card(painter, 0, 0, Toast(text="x"))
    # no button row means no button text at all
    assert painter.texts() == ["x"]


# ── the accent rule ───────────────────────────────────────────────────────

def test_the_accent_rule_runs_down_the_left_edge_inset_14_px(card):
    """`rect(x, y+14, 3, h-28, accent)` — inset at both ends, so the rule reads
    as a marker on the card rather than as the card's own border."""
    painter = Recorder()
    toast = _qs()
    card.paint_card(painter, 100, 200, toast)
    draws = [a for name, a, _k in painter.calls if name == "drawRoundedRect"]
    # first the card, then the rule
    rule = draws[1][0]
    assert round(rule.x()) == 100
    assert round(rule.y()) == 200 + 14
    assert round(rule.width()) == 3
    assert round(rule.height()) == toast.height - 28


def test_a_risky_card_is_amber_and_an_info_card_is_cyan(card):
    """The accent comes from the toast, so board 14a's confirmation colour and
    board 2's danger card cannot drift apart."""
    from ui.toast_queue import KIND_INFO, KIND_RISKY, Toast

    seen = {}

    class ColourSpy:
        def __init__(self, value):
            self.value = value
            seen.setdefault("colours", []).append(str(value))

        def setAlpha(self, *_a):
            pass

        def setAlphaF(self, *_a):
            pass

    import sys as _sys

    gui = _sys.modules["PyQt6.QtGui"]
    saved = gui.__dict__.get("QColor")
    gui.__dict__["QColor"] = ColourSpy
    try:
        painter = Recorder()
        card.paint_card(painter, 0, 0, Toast(text="x", kind=KIND_RISKY))
        card.paint_card(painter, 0, 0, Toast(text="x", kind=KIND_INFO))
    finally:
        if saved is None:
            gui.__dict__.pop("QColor", None)
        else:
            gui.__dict__["QColor"] = saved
    colours = seen.get("colours", [])
    assert "#ff9a40" in colours, "a risky card must draw with the amber accent"
    assert "#3486fe" in colours, "an info card must draw with the cyan accent"


# ── the words ─────────────────────────────────────────────────────────────

def test_the_title_body_and_every_button_are_drawn(card):
    painter = Recorder()
    card.paint_card(painter, 0, 0, _qs())
    texts = painter.texts()
    assert "Rapat tim dimulai 10 menit lagi" in texts
    assert "Ruang Rapat 2 · 5 peserta sudah masuk" in texts
    assert "Buka tautan" in texts
    assert "Tunda 5 mnt" in texts


def test_a_toast_with_no_body_draws_only_its_title(card):
    from ui.toast_queue import Toast

    painter = Recorder()
    card.paint_card(painter, 0, 0, Toast(text="Selesai"))
    assert painter.texts() == ["Selesai"]


def test_the_title_is_set_at_13_px_and_the_body_at_11_5(card):
    """`txt(x+20, y+30, title, 13, ...)` and `txt(x+20, y+50, body, 11.5, ...)`.
    A body drawn at the title's size makes the two lines one paragraph."""
    sizes = []

    class FontSpy:
        def __init__(self, *_a):
            self._size = None

        def setPixelSize(self, size):
            self._size = size
            sizes.append(size)

        def setBold(self, *_a):
            pass

        def setWeight(self, *_a):
            pass

        def setPointSize(self, *_a):
            pass

    import sys as _sys

    gui = _sys.modules["PyQt6.QtGui"]
    saved = gui.__dict__.get("QFont")
    gui.__dict__["QFont"] = FontSpy
    try:
        card.paint_card(Recorder(), 0, 0, _qs())
    finally:
        if saved is None:
            gui.__dict__.pop("QFont", None)
        else:
            gui.__dict__["QFont"] = saved
    assert 13 in sizes, f"no 13 px title; sizes were {sizes}"
    assert 11.5 in sizes, f"no 11.5 px body; sizes were {sizes}"


def test_a_title_too_long_for_the_card_is_truncated_not_drawn_past_the_edge(card):
    """`txt()` in build.py does not wrap; the card is 340 px and the text starts
    at x+20. A title longer than the card can hold is ellipsised HERE, because a
    painter that overflows draws over the wallpaper."""

    card_w = card.CARD_W
    limit = card.fit_text("x" * 400, card_w - 2 * card.PAD)
    assert limit.endswith("…")
    assert len(limit) < 400

    short = "Rapat"
    assert card.fit_text(short, card_w - 2 * card.PAD) == short


def test_fitting_a_text_never_raises_on_a_weird_label(card):
    for value in ("", None, "   ", 12, "a\nb"):
        out = card.fit_text(value, 100)
        assert isinstance(out, str)


# ── the stack: where the cards go ─────────────────────────────────────────

def test_the_stack_is_the_artboards_12_px_gap(card):
    """`toast_queue()` advances by `height + 12` for each card."""
    assert card.GAP == 12


def test_the_stack_heights_follow_the_cards(card):
    from ui.toast_queue import Toast

    toasts = [Toast(text="a", actions=("x",)), Toast(text="b")]
    heights = card.stack_heights(toasts)
    assert heights == [96, 74]
    offsets = card.stack_offsets(toasts)
    assert offsets == [0, 96 + 12]


def test_the_window_is_wide_enough_for_the_cards_and_tall_enough_for_three(card):
    """The window is sized from the artboard, not from the number of toasts on
    screen: a stack that resizes as toasts come and go moves every card under
    the cursor, which is a button that runs away."""
    from ui.toast_queue import VISIBLE_MAX, Toast

    w, h = card.window_size()
    assert w == card.CARD_W
    tallest = VISIBLE_MAX * 96 + (VISIBLE_MAX - 1) * card.GAP
    assert h == tallest
    # and that is at least the artboard's measured stack
    assert h >= VISIBLE_MAX * 74 + (VISIBLE_MAX - 1) * card.GAP
    assert Toast(text="x").height == 74


# ── the button arithmetic, which decides where a click lands ──────────────

def test_a_button_is_as_wide_as_its_label(card):
    """`aw = 12 + len(a) * 6.4` from `toast()`.

    THIS IS NOT COSMETIC. `hits()` walks the same arithmetic to decide which
    button a click belongs to, so a fixed width — or a wrong one — puts the
    click on the neighbour. M16 made every button 100 px and the whole suite
    still passed, because nothing asserted a width at all.
    """
    assert card.button_width("Buka") == 12 + 4 * 6.4
    assert card.button_width("Tunda 5 mnt") == 12 + 11 * 6.4
    assert card.button_width("A") < card.button_width("AAAAAAAA")


def test_the_second_button_starts_after_the_first_and_the_gap(card):
    """`ax += aw + 10`. A hit test that assumed a constant stride would send a
    click on "Nanti" to "Buka"."""
    first = card.button_width("Buka tautan")
    second_x = card.PAD + first + card.BUTTON_GAP
    assert second_x == 20 + (12 + 11 * 6.4) + 10
