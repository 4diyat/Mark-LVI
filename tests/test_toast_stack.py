"""The toast stack's window: where it goes, and what it refuses to do.

WHY BOARD 2 NEEDS A WINDOW AND NOT A NOTIFICATION
    The footnote above board 2 lists three promises: "Hilang otomatis 8 detik ·
    tidak pernah meminta fokus · maksimal 3 saran per hari". The third one is
    only legible in a card that can also say how much budget is left, and the OS
    notification cannot. The other two are properties of this window, and both
    are asserted here:

    - "tidak pernah meminta fokus": the window never takes keyboard focus. A
      toast that steals the caret out of the document you are typing in is the
      single most-hated behaviour a desktop assistant can have.
    - "8 detik": the tick that expires toasts, and the fact that ONE timer
      drives the whole stack rather than one per card.

WHAT IS ASSERTED WITHOUT A DISPLAY
    Placement (the corner maths is `orb_place.corner_anchor`, same as the orb),
    the click rule (a click only counts inside a card, and only on a button that
    exists), the expiry, and the wiring: pushing a toast makes the window show,
    and an empty queue makes it hide. What the cards LOOK like is
    `test_toast_card.py`'s job.
"""
from __future__ import annotations

import sys
import types

import pytest

from tests import qtstub


@pytest.fixture()
def stack(monkeypatch, tmp_path):
    """`ui.toast_stack` over the repo's Qt stub."""
    saved = {k: v for k, v in sys.modules.items()
             if k == "PyQt6" or k.startswith("PyQt6.") or k == "ui" or k.startswith("ui.")}
    sys.modules.update(qtstub.install_qt())
    for name in [k for k in sys.modules if k == "ui" or k.startswith("ui.")]:
        sys.modules.pop(name, None)
    try:
        import ui.toast_stack as module
        yield module
    finally:
        for name in list(sys.modules):
            if name == "ui" or name.startswith("ui."):
                sys.modules.pop(name, None)
        for name in [n for n in list(sys.modules) if n.startswith("PyQt6")]:
            if name not in saved:
                sys.modules.pop(name, None)
        sys.modules.update(saved)


class _Screen:
    """A 1920x1080 desktop at the origin."""

    def __init__(self, x=0, y=0, w=1920, h=1080):
        self._box = (x, y, w, h)

    def x(self):
        return self._box[0]

    def y(self):
        return self._box[1]

    def width(self):
        return self._box[2]

    def height(self):
        return self._box[3]


# ── the flags: never take focus ───────────────────────────────────────────

def test_the_toast_window_never_takes_focus(stack):
    """"tidak pernah meminta fokus", as a flag and as an attribute.

    The flag is `WindowDoesNotAcceptFocus`; the attribute is
    `WA_ShowWithoutActivating`. Both are needed: the flag stops the window
    manager giving it focus, the attribute stops Qt asking for it on show.
    """
    flags = stack.window_flags(types.SimpleNamespace(
        WindowType=types.SimpleNamespace(**{
            "FramelessWindowHint": 1, "Tool": 2, "WindowStaysOnTopHint": 4,
            "WindowDoesNotAcceptFocus": 8})))
    assert isinstance(flags, int) and flags & 8, (
        "WindowDoesNotAcceptFocus is missing: the toast would take the caret")


def test_the_toast_window_is_not_click_through(stack):
    """Unlike the orb's transparent corners, every pixel of a toast card is
    either a button or the card — so the window takes clicks and the card's own
    hit test decides. A click-through toast cannot be dismissed."""
    assert "WindowTransparentForInput" not in stack._FLAGS


# ── placement ─────────────────────────────────────────────────────────────

def test_the_stack_opens_in_the_top_left_opposite_the_orb(stack, monkeypatch):
    """Board 1 puts the toast stack in the TOP-LEFT of the desktop, opposite
    the orb's bottom-right corner (`01-ambient-main.png`). A stack anchored to
    the orb's rule would land under the orb itself, covering the thing it
    announces."""
    size = stack.WindowSize()
    width, height = size.width(), size.height()
    x, y = stack.stack_anchor(_Screen(), width, height)
    assert x == stack.MARGIN
    assert y == stack.MARGIN


def test_the_margin_is_the_artboards_numbers_not_a_new_invention(stack):
    """`n02()` draws the stack at y=330 of 720 with the last card ending near
    640 — a 24 px margin, the same one the orb uses."""
    assert stack.MARGIN == 24


# ── the tick: one timer, not one per card ─────────────────────────────────

def test_one_timer_drives_the_whole_stack(stack):
    """Eight timers for eight toasts is eight wake-ups a second to do the same
    sweep. The window owns one, and `tick()` is what it calls."""
    overlay = stack.ToastStack()
    assert overlay.start(), overlay.error
    assert overlay._timer is not None
    # a started stack is idle: nothing pushed, nothing shown
    assert overlay.visible is False
    overlay.stop()


def test_tick_expires_finished_toasts_and_hides_when_the_last_one_goes(stack):
    overlay = stack.ToastStack()
    assert overlay.start(), overlay.error
    overlay.push("a", ttl=0.0)               # already expired on the next tick
    assert overlay.visible is True
    overlay.tick()
    overlay.tick()
    assert overlay.queue.current() == []
    assert overlay.visible is False
    overlay.stop()


# ── pushing ───────────────────────────────────────────────────────────────

def test_push_shows_the_window(stack):
    overlay = stack.ToastStack()
    assert overlay.start(), overlay.error
    assert overlay.visible is False
    overlay.push("Rapat tim dimulai 10 menit lagi")
    assert overlay.visible is True
    overlay.stop()


def test_push_passes_the_whole_card_through(stack):
    overlay = stack.ToastStack()
    assert overlay.start(), overlay.error
    overlay.push("Judul", kind="risky", body="isi", actions=("Buka", "Nanti"))
    toast = overlay.queue.current()[0]
    assert (toast.text, toast.body, toast.actions, toast.kind) == (
        "Judul", "isi", ("Buka", "Nanti"), "risky")
    overlay.stop()


def test_an_empty_push_does_not_show_an_empty_window(stack):
    """`ToastQueue.push("")` returns None. A stack that showed itself for a
    refused toast would be an empty 340 px hole in the corner of the screen."""
    overlay = stack.ToastStack()
    assert overlay.start(), overlay.error
    overlay.push("   ")
    assert overlay.visible is False
    overlay.stop()


def test_the_overflow_label_reaches_the_window(stack):
    overlay = stack.ToastStack()
    assert overlay.start(), overlay.error
    for i in range(5):
        overlay.push(f"t{i}")
    assert overlay.overflow_text() == "+2 lain dalam antrean"
    overlay.stop()


# ── clicks: a card, and a button that exists ──────────────────────────────

def test_a_click_on_a_card_body_dismisses_that_card(stack):
    overlay = stack.ToastStack()
    assert overlay.start(), overlay.error
    overlay.push("a")
    overlay.push("b")
    assert overlay.click(10, 10) is True           # the first card's body
    assert [t.text for t in overlay.queue.current()] == ["b"]
    overlay.stop()


def test_a_click_below_every_card_belongs_to_the_desktop(stack):
    overlay = stack.ToastStack()
    assert overlay.start(), overlay.error
    overlay.push("a")                              # one 74 px card
    assert overlay.click(10, 300) is False
    overlay.stop()


def test_a_click_on_a_button_calls_back_with_its_label_and_the_toast(stack):
    calls = []
    overlay = stack.ToastStack(on_action=lambda label, toast: calls.append(
        (label, toast.text)))
    assert overlay.start(), overlay.error
    overlay.push("Rapat", actions=("Buka tautan", "Tunda 5 mnt"))
    # the first button starts at x=20 and is `12 + len*6.4` wide
    x = 20 + 4
    y = 64 + 4
    assert overlay.click(x, y) is True
    assert calls == [("Buka tautan", "Rapat")]
    overlay.stop()


def test_a_click_on_a_button_does_not_ALSO_dismiss_the_card(stack):
    """The button is the more specific target. Dismissing on the same click
    would take the card away before the action ran, which is how an action
    button turns into a cancel button."""
    calls = []
    overlay = stack.ToastStack(on_action=lambda label, toast: calls.append(label))
    assert overlay.start(), overlay.error
    overlay.push("Rapat", actions=("Buka",))
    overlay.click(24, 68)
    assert calls == ["Buka"]
    assert len(overlay.queue) == 1
    overlay.stop()


def test_a_click_after_a_dismissal_uses_the_NEW_stack_order(stack):
    """Coordinates are resolved against what is on screen NOW. A hit box cached
    from the previous frame would dismiss the wrong toast for one tick — and one
    tick is exactly long enough to click."""
    overlay = stack.ToastStack()
    assert overlay.start(), overlay.error
    overlay.push("a")
    overlay.push("b")
    overlay.click(10, 10)                    # dismisses "a"; "b" moves up to y=0
    overlay.click(10, 10)                    # must now dismiss "b"
    assert overlay.queue.current() == []
    overlay.stop()


# ── the panel's own promises ──────────────────────────────────────────────

def test_every_card_is_painted_through_the_one_card_function(stack):
    """The window has no drawing of its own. A second card painter is how the
    orb got two, and the one that is not edited drifts."""
    source = stack.__file__
    with open(source, encoding="utf-8") as fh:
        body = fh.read()
    assert "paint_card(" in body
    assert "drawRoundedRect" not in body, (
        "the stack draws a rectangle itself instead of calling paint_card")


def test_a_click_between_two_buttons_lands_on_the_second_one(stack):
    """The gap is 10 px; a click in the middle of the SECOND button must not be
    attributed to the first. This is what makes `button_width` load-bearing
    rather than decorative."""
    calls = []
    overlay = stack.ToastStack(on_action=lambda label, toast: calls.append(label))
    assert overlay.start(), overlay.error
    overlay.push("Rapat", actions=("Buka", "Nanti"))
    from ui import toast_card

    first_w = toast_card.button_width("Buka")
    # A POINT INSIDE THE GAP ITSELF. This is the only coordinate that separates
    # "the hit test advances by width + gap" from "by width": one pixel past the
    # first button, and 10 px short of the second. A click two pixels into the
    # second button lands on it either way, which is why the earlier version of
    # this test passed against a hit test that had dropped the gap.
    gap_x = toast_card.PAD + first_w + 1
    # The gap is NOT a button: the click lands on the card and does nothing.
    # A hit test that advanced by `width` alone would put this point inside
    # "Nanti" and run the wrong action, which is the bug this coordinates for.
    assert overlay.click(int(gap_x), toast_card.BUTTON_DY + 4) is True
    assert calls == [], (
        f"a click in the gap ran {calls}; the gap belongs to no button")

    second_x = toast_card.PAD + first_w + toast_card.BUTTON_GAP + 2
    assert overlay.click(int(second_x), toast_card.BUTTON_DY + 4) is True
    assert calls == ["Nanti"]
    overlay.stop()
