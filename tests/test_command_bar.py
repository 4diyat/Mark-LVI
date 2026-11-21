"""The command bar: who gets focus back, and what Enter is allowed to send.

WHY THE FOCUS LEDGER IS THE THING UNDER TEST
    "Esc gives the window back" is the bar's entire promise to someone working in
    another program. Whether a window manager HONOURS `activateWindow()` cannot
    be seen from here — that needs Windows, X11 and macOS, and it is the same
    class of unprovable claim as click-through. What CAN be wrong here is the
    bookkeeping: restoring to the wrong window, restoring twice and fighting over
    it, or claiming success without knowing. Those are decided in `FocusLedger`
    and that is what these tests hold to.

    The Qt half runs over the repo's own stub, so a method name that PyQt6 does
    not have (`QLineEdit.setPlaceholderText`, `Qt.Key.Key_Escape`) fails here.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture()
def bar(monkeypatch):
    """`ui.command_bar` loaded over the repo's Qt stub."""
    spec = importlib.util.spec_from_file_location(
        "smoke_for_bar", ROOT / "tests" / "test_window_smoke.py")
    smoke = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(smoke)
    saved = {k: v for k, v in sys.modules.items()
             if k == "PyQt6" or k.startswith("PyQt6.") or k == "ui" or k.startswith("ui.")}
    sys.modules.update(smoke._install_qt())
    for name in [k for k in sys.modules if k == "ui" or k.startswith("ui.")]:
        sys.modules.pop(name, None)
    try:
        import ui.command_bar as module
        yield module
    finally:
        for name in list(sys.modules):
            if name == "ui" or name.startswith("ui."):
                sys.modules.pop(name, None)
        for name in [k for k in list(sys.modules) if k.startswith("PyQt6")]:
            if name not in saved:
                sys.modules.pop(name, None)
        sys.modules.update(saved)


class _Window:
    """A window that records what was asked of it."""

    def __init__(self, name="previous", refuse=False):
        self.name = name
        self.raised = 0
        self.activated = 0
        self.refuse = refuse

    def raise_(self):
        self.raised += 1

    def activateWindow(self):
        self.activated += 1
        if self.refuse:
            raise RuntimeError("window manager refused")


# ── the ledger ────────────────────────────────────────────────────────────

def test_esc_restores_the_window_that_was_named(bar):
    ledger = bar.FocusLedger()
    target = _Window()
    ledger.capture(target)
    assert ledger.take() is target


def test_the_handle_is_handed_back_only_once(bar):
    """Esc then a lost-focus close must not fight over which window to raise."""
    ledger = bar.FocusLedger()
    ledger.capture(_Window())
    assert ledger.take() is not None
    assert ledger.take() is None


def test_with_nothing_to_restore_the_ledger_says_so(bar):
    ledger = bar.FocusLedger()
    ledger.capture(None)
    assert ledger.captured is False
    assert ledger.take() is None
    assert ledger.last_result


def test_a_restoration_is_recorded_even_when_it_fails(bar):
    """`activateWindow()` returns nothing; saying 'restored' without knowing is
    the dishonest version of this feature."""
    ledger = bar.FocusLedger()
    ledger.capture(_Window())
    ledger.restored(False)
    assert ledger.restore_attempted is True
    assert "refused" in ledger.last_result


# ── the bar ───────────────────────────────────────────────────────────────

def test_opening_a_closed_bar_captures_focus(bar):
    previous = _Window()
    b = bar.CommandBar()
    assert b.open(previous) is True
    assert b.is_open is True
    assert b.ledger.captured is True


def test_closing_gives_focus_back_to_that_same_window(bar):
    previous = _Window()
    b = bar.CommandBar()
    b.open(previous)
    b.close()
    assert previous.activated == 1
    assert b.is_open is False


def test_closing_twice_does_not_raise_the_window_twice(bar):
    previous = _Window()
    b = bar.CommandBar()
    b.open(previous)
    b.close()
    b.close()
    assert previous.activated == 1


def test_a_refusing_window_manager_does_not_break_the_close(bar):
    b = bar.CommandBar()
    b.open(_Window(refuse=True))
    b.close()
    assert b.is_open is False
    assert b.ledger.restore_attempted is True
    assert "refused" in b.ledger.last_result


def test_toggle_opens_then_closes(bar):
    b = bar.CommandBar()
    assert b.toggle(_Window()) is True
    assert b.toggle() is False
    assert b.is_open is False


def test_enter_sends_the_flattened_line(bar):
    seen = []
    b = bar.CommandBar(on_submit=seen.append)
    b.open(_Window())
    assert b.submit("  buka   laporan\nq3  ") is True
    assert seen == ["buka laporan q3"]


def test_enter_on_an_empty_line_sends_nothing_and_still_closes(bar):
    seen = []
    b = bar.CommandBar(on_submit=seen.append)
    b.open(_Window())
    assert b.submit("   ") is False
    assert seen == []
    assert b.is_open is False


def test_a_submit_handler_that_raises_does_not_reach_the_keyboard(bar):
    def boom(_line):
        raise RuntimeError("the assistant is not running")

    b = bar.CommandBar(on_submit=boom)
    b.open(_Window())
    assert b.submit("halo") is False
    assert b.is_open is False


def test_the_line_is_capped_by_flattening_not_by_cutting_mid_sentence(bar):
    long_line = "a" * (bar.MAX_CHARS + 500)
    assert len(bar.flatten(long_line)) == bar.MAX_CHARS
    assert bar.flatten("x\ny").count(" ") == 1


# ── history ───────────────────────────────────────────────────────────────

def test_sent_lines_are_remembered_newest_first(bar):
    b = bar.CommandBar()
    b.open(_Window())
    b.submit("satu")
    b.open(_Window())
    b.submit("dua")
    assert b.history == ["dua", "satu"]


def test_the_same_line_twice_is_remembered_once(bar):
    b = bar.CommandBar()
    for _ in range(3):
        b.open(_Window())
        b.submit("ulangi")
    assert b.history == ["ulangi"]


def test_the_history_is_bounded(bar):
    b = bar.CommandBar()
    for i in range(bar.HISTORY_MAX + 5):
        b.open(_Window())
        b.submit(f"cmd{i}")
    assert len(b.history) == bar.HISTORY_MAX
    assert b.history[0] == f"cmd{bar.HISTORY_MAX + 4}"


def test_recall_walks_backwards_and_stops_at_the_oldest(bar):
    b = bar.CommandBar()
    for line in ("satu", "dua"):
        b.open(_Window())
        b.submit(line)
    b.open(_Window())
    assert b.recall(-1) == "dua"
    assert b.recall(-1) == "satu"
    assert b.recall(-1) == "satu", "the oldest stops rather than wrapping"


def test_recall_forwards_returns_to_an_empty_field(bar):
    b = bar.CommandBar()
    b.open(_Window())
    b.submit("satu")
    b.open(_Window())
    assert b.recall(-1) == "satu"
    assert b.recall(+1) == ""


def test_recall_on_an_empty_history_returns_nothing(bar):
    assert bar.CommandBar().recall(-1) == ""


def test_opening_again_resets_the_recall_position(bar):
    b = bar.CommandBar()
    b.open(_Window())
    b.submit("satu")
    b.open(_Window())
    b.recall(-1)
    b.close()
    b.open(_Window())
    assert b.recall(-1) == "satu"


# ── geometry ──────────────────────────────────────────────────────────────

def test_the_field_fits_inside_the_window(bar):
    assert bar.FIELD_MARGIN + bar.FIELD_HEIGHT <= bar.BAR_HEIGHT
    assert bar.BAR_WIDTH - bar.FIELD_MARGIN * 2 > 0


def test_the_bar_is_the_size_the_artboard_draws(bar):
    """Board 3 draws 640 × 184 at (320, 268) on a 1280 × 720 desktop."""
    assert (bar.BAR_WIDTH, bar.BAR_HEIGHT) == (640, 184)


def test_the_bar_is_not_transparent_to_the_keyboard(bar):
    """`WA_ShowWithoutActivating` would let the field appear without focus,
    which reads as a bar that ignores typing."""
    source = (ROOT / "ui" / "command_bar.py").read_text(encoding="utf-8")
    assert "WA_ShowWithoutActivating, False" in source
