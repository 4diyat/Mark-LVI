"""A blocking surface must be on screen, and there is no window to put it in.

WHY THIS FILE EXISTS
    `core/confirm` holds an action open for 90 seconds and then REFUSES it. The
    gate is only fair if the question was actually put in front of the user, and
    the original implementation drew its banner as a child of the main window.
    In ambient mode that window was hidden, so the user was told to confirm
    something they could not see — and 90 seconds later nothing had happened,
    for no stated reason.

    The fix then was "raise the window first". The window is gone, so the fix
    now has to be structural: the banner is its OWN window, and nothing about
    where it is drawn can make it invisible.

WHAT IS ASSERTED, AND WHY EACH ONE CAN FAIL ON ITS OWN
    * the banner is not a child of the orb or the face (a 430 px widget
      parented to a 28-56 px window is clipped, not shown);
    * it is always-on-top and frameless, so it is not behind the user's work;
    * the shell creates it on the Qt thread, whatever thread `core/confirm`
      called from — building widgets off the Qt thread is undefined behaviour,
      and `core/confirm` calls from an action's worker thread;
    * CONFIRM and CANCEL both reach `core/confirm` with the right token;
    * a question that cannot be shown is SAID — `core/confirm` will refuse the
      action, and the user deserves to know why.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

from tests import qtstub

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture()
def qt(monkeypatch):
    stubs = qtstub.install_qt()
    saved = {k: v for k, v in sys.modules.items()
             if k == "PyQt6" or k.startswith("PyQt6.") or k == "ui" or k.startswith("ui.")}
    sys.modules.update(stubs)
    for name in [k for k in sys.modules if k == "ui" or k.startswith("ui.")]:
        sys.modules.pop(name, None)
    try:
        import ui
        import ui.confirm_banner
        yield ui
    finally:
        for name in list(sys.modules):
            if name == "ui" or name.startswith("ui."):
                sys.modules.pop(name, None)
        for name in [k for k in list(sys.modules) if k.startswith("PyQt6")]:
            if name not in saved:
                sys.modules.pop(name, None)
        sys.modules.update(saved)


def _shell(qt):
    """A shell with no surfaces at all — the hardest case to show anything on."""
    shell = qt.AmbientShell("face.png", "JARVIS")
    shell.notices = []
    shell.notify = lambda text, *a, **k: shell.notices.append(str(text))
    return shell


# ── where the banner lives ────────────────────────────────────────────────

def test_the_banner_is_its_own_window_not_a_child_of_the_orb(qt):
    """THE BUG THE OLD FIX COULD NOT FIX.

    A child widget is clipped to its parent's geometry. The orb is tens of
    pixels; this banner is 520. Parenting it anywhere in the ambient surfaces
    makes it invisible without making it any less blocking.

    THE WIDTH IS THE ARTBOARD'S, NOT A PIXEL COUNT THAT HAPPENED TO PASS. This
    pinned 430, which was never board 14a's number — the design is 520 wide
    (confirm-banner geometry; visual reference
    `design/new-ui-proposal/04-security-permissions.png`), so the
    test was recording the implementation's guess and would have failed the
    correct value. It now names the design, which is what it was always for.
    """
    from ui.confirm_banner import build_confirm_window

    banner = build_confirm_window()
    assert banner.parent() is None, (
        "the banner has a parent, so it can be clipped by one")
    assert banner._OW == 520, (
        "board 14a draws the dialog 520 px wide; this is a different dialog")


def test_the_banner_is_frameless_and_on_top(qt):
    """Artboard 14a: over whatever the user is doing, with no window chrome."""
    from PyQt6.QtCore import Qt

    from ui.confirm_banner import build_confirm_window

    flags = build_confirm_window().windowFlags()
    for wanted in ("Tool", "FramelessWindowHint", "WindowStaysOnTopHint"):
        assert flags & getattr(Qt.WindowType, wanted), f"{wanted} is missing"


def test_cancel_has_the_focus_so_a_stray_enter_is_safe(qt):
    """The safe-by-default rule, which SURVIVED board 14a's change.

    This test used to say something stronger and no longer true: it asserted
    that the banner had no Enter handler at all, so a stray Enter could never
    confirm. Board 14a writes "Enter · Esc" in the dialog's corner and the owner
    ruled the artboard wins, so Enter DOES confirm now.

    What keeps the old property is the INITIAL FOCUS: it starts on CANCEL, so an
    Enter pressed without touching anything is swallowed by the focused button
    and confirms nothing. Enter only confirms after the user has moved to
    Konfirmasi — which is a decision, not a stray keypress.
    """
    from ui.confirm_banner import build_confirm_window

    banner = build_confirm_window()
    assert banner._cancel_button.isDefault() is True, (
        "the CANCEL button must own the default answer")
    assert banner._confirm_button.isDefault() is False, (
        "a confirm button that is default by default is one Enter away from an "
        "irreversible action")


def test_a_second_question_reuses_the_banner_rather_than_stacking(qt):
    """Two windows would both be up, and only one of them answers."""
    from ui.confirm_banner import build_confirm_window

    banner = build_confirm_window()
    banner.set_title("Kirim laporan", "Lampiran: anggaran.xlsx")
    assert banner._title_label.text() == "Kirim laporan"
    banner.set_title("Hapus riwayat", "")
    assert banner._title_label.text() == "Hapus riwayat"


# ── the shell's side ──────────────────────────────────────────────────────

def test_the_banner_is_built_on_the_qt_thread(qt):
    """Real worker-to-Qt delivery is exercised in test_confirmation_real_qt."""
    source = (ROOT / "ui" / "shell.py").read_text(encoding="utf-8")
    start = source.index("def show_confirm(")
    body = source[start:source.index("def _show_confirm_now", start)]
    assert "ui.confirmation_flow import show" in body
    flow = (ROOT / "ui" / "confirmation_flow.py").read_text(encoding="utf-8")
    assert "run_on_qt_thread(shell._ui_thread_id, deliver)" in flow
    assert "confirm.is_pending(token)" in flow



def test_confirm_and_cancel_reach_core_confirm_with_the_token(qt, monkeypatch):
    """The whole point: a human finger decides, not the model."""
    from core import confirm

    seen = []
    monkeypatch.setattr(confirm, "resolve",
                        lambda token, accepted: seen.append((token, accepted)))
    shell = _shell(qt)
    shell._show_confirm_now("tok-1", "Kirim laporan", "3 penerima")
    shell._resolve_answered(True)
    shell._resolve_answered(False)
    assert seen == [("tok-1", True)], (
        "a second answer with no question outstanding must be ignored")


def test_the_answer_clears_the_dialog_before_core_confirm_is_told(qt, monkeypatch):
    """A dialog that outlives its question is one the user must dismiss blind."""
    from core import confirm

    order = []
    monkeypatch.setattr(confirm, "resolve",
                        lambda token, accepted: order.append("resolve"))
    shell = _shell(qt)

    class _Banner:
        def hide(self):
            order.append("hide")

    shell._confirm_banner = _Banner()
    shell._confirm_token = "tok-2"
    shell._resolve_answered(True)
    assert order == ["hide", "resolve"], order


def test_an_answer_to_an_expired_question_still_clears_the_dialog(qt):
    """`core/confirm` ignores a late resolve. The dialog must not stay up."""
    shell = _shell(qt)

    class _Banner:
        hidden = 0

        def hide(self):
            _Banner.hidden += 1

    shell._confirm_banner = _Banner()
    shell._confirm_token = ""
    shell._resolve_answered(True)
    assert _Banner.hidden == 1


def test_a_question_that_cannot_be_shown_is_said_out_loud(qt, monkeypatch):
    """`core/confirm` refuses when nothing can ask. Silence hides the refusal."""
    monkeypatch.setattr(qt.confirm_banner, "build_confirm_window", _refuse)
    shell = _shell(qt)
    shell._show_confirm_now("tok-3", "Hapus riwayat", "Tidak bisa diurungkan")
    assert any("Hapus riwayat" in n for n in shell.notices), shell.notices


def _refuse(*_a, **_k):
    raise RuntimeError("no display")


# ── and nothing may put the window back ───────────────────────────────────

def test_the_gate_is_never_drawn_into_a_parent_widget():
    """The regression, as a rule rather than as a review comment.

    The shell may only reach the banner through `build_confirm_window`, which
    makes its own top-level window. A `ConfirmBanner(...)` in `ui/shell.py`
    would mean a banner that can be clipped — the exact shape that made the old
    gate invisible while still blocking, and the thing this file exists for.
    """
    shell_src = (ROOT / "ui" / "shell.py").read_text(encoding="utf-8")
    assert "ConfirmBanner" not in shell_src, (
        "the shell builds a banner directly; it has a parent, so it can be clipped")
    assert "build_confirm_window" in shell_src

    # And the one place that does build one passes `parent`, which defaults to
    # None: no caller in the package may hand it a widget.
    for path in sorted((ROOT / "ui").glob("*.py")):
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith("ConfirmBanner(") and "parent=" in stripped:
                assert "parent=None" in stripped, f"{path.name}: {stripped}"
