"""A blocking surface must be visible, in every interface mode.

WHY THIS FILE EXISTS
    Ambient mode hides the window. Two things inside that window are not
    decoration — they are the only way to finish what the assistant started:

      * the confirmation banner. `core/confirm` holds the action open for 90
        seconds and then REFUSES it. Drawn inside a hidden window it is silent:
        the user is told to confirm something they cannot see, and 90 seconds
        later nothing happened for no stated reason.
      * the setup screen, shown when the API key is rejected. `main.py` then
        waits in `while not self._win._ready` — an unbounded wait. Hidden, the
        assistant stops answering for good with nothing on screen to say why.

    Both were introduced by phase 1 (`5d2e9a1`) and both are worse than the
    window that mode replaced, so the mode yields instead.

WHAT THE FIRST TEST ACTUALLY PROVES
    It walks `core/confirm` through a full request against a hidden parent
    widget, and shows that the banner is created and never laid out — which is
    exactly what "invisible but blocking" means, and why the fix cannot be
    "wait, the banner still counts as shown".
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture()
def qt(monkeypatch):
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "smoke_for_blocking", ROOT / "tests" / "test_window_smoke.py")
    smoke = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(smoke)
    saved = {k: v for k, v in sys.modules.items()
             if k == "PyQt6" or k.startswith("PyQt6.") or k == "ui" or k.startswith("ui.")}
    sys.modules.update(smoke._install_qt())
    for name in [k for k in sys.modules if k == "ui" or k.startswith("ui.")]:
        sys.modules.pop(name, None)
    try:
        import ui
        import ui.lifecycle
        import ui.face_bubble
        yield ui
    finally:
        for name in list(sys.modules):
            if name == "ui" or name.startswith("ui."):
                sys.modules.pop(name, None)
        for name in [k for k in list(sys.modules) if k.startswith("PyQt6")]:
            if name not in saved:
                sys.modules.pop(name, None)
        sys.modules.update(saved)


class _Event:
    def __init__(self):
        self.outcome = []

    def ignore(self):
        self.outcome.append("ignored")

    def accept(self):
        self.outcome.append("accepted")


def _shell(qt, monkeypatch, *, visible=False, mode="ambient"):
    """A JarvisUI-shaped object, enough for the attention rule."""
    from memory import config_manager as cm
    import importlib
    tray_mod = importlib.import_module("ui.tray")

    state = {"visible": visible, "full": 0, "maxed": 0, "mode": mode, "ready": True,
             "log": []}
    monkeypatch.setattr(qt.MainWindow, "showFullScreen",
                        lambda self: state.__setitem__("full", state["full"] + 1))
    monkeypatch.setattr(qt.MainWindow, "showMaximized",
                        lambda self: (state.__setitem__("maxed", state["maxed"] + 1),
                                      state.__setitem__("visible", True)))
    monkeypatch.setattr(qt.MainWindow, "hide",
                        lambda self: state.__setitem__("visible", False))
    monkeypatch.setattr(qt.MainWindow, "isVisible", lambda self: state["visible"])
    monkeypatch.setattr(qt.MainWindow, "isFullScreen", lambda self: False)
    monkeypatch.setattr(qt.MainWindow, "raise_", lambda self: None)
    monkeypatch.setattr(qt.MainWindow, "activateWindow", lambda self: None)
    monkeypatch.setattr(qt.MainWindow, "write_log",
                        lambda self, line: state["log"].append(line), raising=False)
    monkeypatch.setattr(cm, "get_ui_mode", lambda: state["mode"])
    monkeypatch.setattr(cm, "save_ui_mode", lambda m: state.__setitem__("mode", m))
    monkeypatch.setattr(cm, "get_assistant_name", lambda: "JARVIS")
    # A configured install, or `start_interface` would take the first-run branch
    # and show the window — which is a different feature, tested elsewhere.
    monkeypatch.setattr(qt.MainWindow, "_check_config", lambda self: True)
    monkeypatch.setattr(tray_mod.TrayIcon, "start", lambda self: True)
    monkeypatch.setattr(tray_mod.TrayIcon, "available", property(lambda self: True))
    monkeypatch.setattr(qt.face_bubble.FaceBubble, "start", lambda self: True)
    shell = qt.JarvisUI("face.png")
    shell.state = state
    return shell


# ── the rule, directly ────────────────────────────────────────────────────

def test_needs_attention_shows_the_window_and_says_why(qt, monkeypatch):
    shell = _shell(qt, monkeypatch, visible=False)
    assert shell.ambient is True

    assert shell._lifecycle.needs_attention(shell, "an action needs confirming") is True
    assert shell.state["visible"] is True
    assert shell.ambient is False, "the mode must yield while something is waiting"
    assert any("confirming" in line for line in shell.state["log"]), (
        "the window appeared with no explanation of why it interrupted")


def test_a_visible_window_is_left_alone_by_the_helper(qt, monkeypatch):
    """The `isVisible()` check moved into `window_needs_attention` with the
    rest of the rule; it must still stop a hud-mode window being re-raised."""
    source = (ROOT / "ui" / "lifecycle.py").read_text(encoding="utf-8")
    start = source.index("def window_needs_attention(window")
    body = source[start:source.index("def note(shell", start)]
    assert "if shell is None or window.isVisible():" in body


def test_needs_attention_reports_failure_instead_of_pretending(qt, monkeypatch):
    shell = _shell(qt, monkeypatch, visible=False)

    def _refuse(self):
        raise RuntimeError("no window manager")
    monkeypatch.setattr(qt.MainWindow, "showMaximized", _refuse)

    assert shell._lifecycle.needs_attention(shell, "the API key needs re-entering") is False
    assert any("could not show the interface" in line for line in shell.state["log"])


# ── the confirmation banner, driven through core/confirm ───────────────────

def test_a_hidden_confirmation_banner_blocks_invisibly(qt):
    """THE BUG, demonstrated. Not the fix — the reason for it.

    `core/confirm` asks the interface to draw a banner, then holds the action
    open. If the banner is parented to a window that is not on screen, nothing
    is shown, nothing is ever answered, and the action expires. This walks the
    real module far enough to show that: the banner is built and `isVisible()`
    is false, while `is_pending()` says the action is still waiting.
    """
    from PyQt6.QtWidgets import QWidget
    from ui.confirm_banner import ConfirmBanner

    import core.confirm as confirm
    hidden_parent = QWidget()                 # never shown: the ambient window
    ran = []
    seen = {}

    def _ask(token, title, detail):
        # The real handler decides where the banner goes; here the question is
        # only whether that parent can be seen.
        banner = ConfirmBanner(title, detail, parent=hidden_parent)
        seen["visible"] = banner.isVisible()

    confirm.bind(show=_ask, hide=lambda token: None)
    confirm.request("power.shutdown", "Shut down", "Shut down the machine?",
                    lambda: ran.append(1))
    try:
        assert seen["visible"] is False, (
            "premise broken: a banner in a hidden parent is somehow visible")
        assert confirm.pending_title() == "Shut down", (
            "premise broken: the action is no longer waiting, so nothing is blocked")
        assert ran == [], "nothing should have run without an answer"
    finally:
        # Leave no request parked: `core/confirm` keeps ONE pending action for
        # the whole process, and this test parked one on purpose. Left set, the
        # next test that asks for a confirmation is told "another action is
        # already awaiting confirmation" — which is how this file broke
        # tests/test_dev_agent_deps.py, alphabetically downstream of it.
        # `resolve` needs the token, which is generated inside `request`, so the
        # module's own state is cleared directly. Nothing else can: there is no
        # reset hook, and adding one to production code for a test would be the
        # tail wagging the dog.
        confirm._pending = None
        confirm.bind(show=None, hide=None)


def test_the_banner_raises_the_window_before_it_is_drawn(qt, monkeypatch):
    """The fix, at the seam: `_show_confirm_banner` calls for attention first."""
    source = (ROOT / "ui" / "window.py").read_text(encoding="utf-8")
    start = source.index("def _show_confirm_banner(self, token: str")
    body = source[start:source.index("    def _hide_confirm_banner", start)]
    # The call moved behind `ui.lifecycle.window_needs_attention` when
    # window.py hit its line ceiling — the check on both ends is that the call
    # is there and that it precedes the banner being built.
    assert "window_needs_attention" in body, (
        "the banner is drawn into whatever is on screen")
    assert body.index("window_needs_attention") < body.index("ov = ConfirmBanner("), (
        "the window has to be up BEFORE the banner is parented to it")


def test_the_setup_screen_raises_the_window_too(qt):
    source = (ROOT / "ui" / "window.py").read_text(encoding="utf-8")
    start = source.index("def _show_setup(self):")
    body = source[start:start + 3000]
    assert "window_needs_attention" in body, (
        "an invalid API key waits in an unbounded loop on a screen that "
        "ambient mode would keep hidden")
    assert body.index("window_needs_attention") < body.index("SetupOverlay("), (
        "the overlay must be built into a window that is already visible")


# ── and the mode must survive being interrupted ───────────────────────────

def test_putting_the_window_away_again_still_works_after_attention(qt, monkeypatch):
    """The interruption must be reversible. A confirm that permanently left the
    window up would make ambient mode a one-way door."""
    shell = _shell(qt, monkeypatch, visible=False)
    shell._lifecycle.needs_attention(shell, "an action needs confirming")
    assert shell.state["visible"] is True

    shell.dismiss()
    assert shell.state["visible"] is False
    assert shell.ambient is True


def test_a_visible_window_is_not_re_raised(qt, monkeypatch):
    """In hud mode the banner is already on screen; nothing should move."""
    shell = _shell(qt, monkeypatch, visible=True, mode="hud")
    before = shell.state["maxed"]
    shell._lifecycle.needs_attention(shell, "an action needs confirming")
    assert shell.state["maxed"] == before
