"""The four undos that turned `risky` into `medium` — and had to earn it.

WHY THIS FILE EXISTS SEPARATELY FROM `test_tool_risk`
    That file asserts what the GATE decides. This one asserts that the thing the
    gate was told is true: that each of these four actions really does push a
    closure onto `core.undo`, that the closure really reverses the change, and
    that it reports honestly when there is nothing left to reverse.

    The distinction matters because "medium" is a promise, and a test that only
    checked the LEVEL would pass on a table entry with no code behind it —
    which is exactly how `open_app` spent its whole life being refused.

WHAT IS FAKED AND WHY
    `subprocess.run` (for the two schedulers), `appidentity` (for a process
    that is not on this Linux runner), `pyautogui` (no display), and the
    internal browser callback (a widget this process does not have). Everything
    else — `core.undo`'s stack, the closers, the sentence — is real.
"""
from __future__ import annotations

import subprocess
from types import SimpleNamespace

import pytest

from core import undo


@pytest.fixture(autouse=True)
def _empty_stack():
    undo.clear()
    yield
    undo.clear()


# ── open_app ─────────────────────────────────────────────────────────────────

def _app(label="Spotify", pid=4242):
    return SimpleNamespace(pid=pid, label=label)


def test_opening_an_app_registers_the_closure_and_the_gate_can_see_it():
    from actions import open_app

    open_app._register_undo(_app())
    assert undo.can_undo() is True
    assert "opened Spotify" in undo.peek()


def test_the_undo_closes_the_process_that_actually_appeared(monkeypatch):
    """It closes what `wait_for_launch` SAW, not the name the user said.

    The launcher resolves "vs code" to a real executable; closing the spoken
    name would close nothing, or the wrong thing.
    """
    from actions import open_app
    from core import appidentity

    closed = []

    def _is_running(pid):
        return pid == 4242

    def _request_close(match):
        closed.append(match)
        return True, ""

    monkeypatch.setattr(appidentity, "is_running", _is_running)
    monkeypatch.setattr(appidentity, "request_close", _request_close)

    open_app._register_undo(_app())
    sentence = undo.undo_last()

    assert [m.pid for m in closed] == [4242]
    assert "Closed Spotify" in sentence


def test_an_app_the_user_already_closed_is_reported_as_nothing_to_undo(monkeypatch):
    """An undo that claims success over a process that is not running is the
    same class of lie as an action that reports `done` over nothing."""
    from actions import open_app
    from core import appidentity

    called = []
    monkeypatch.setattr(appidentity, "is_running", lambda pid: False)
    monkeypatch.setattr(appidentity, "request_close",
                        lambda m: called.append(m) or (True, ""))

    open_app._register_undo(_app())
    sentence = undo.undo_last()

    assert called == [], "a process that is gone must not be closed again"
    assert "already closed" in sentence


def test_a_close_the_window_manager_refuses_is_not_reported_as_done(monkeypatch):
    from actions import open_app
    from core import appidentity

    monkeypatch.setattr(appidentity, "is_running", lambda pid: True)
    monkeypatch.setattr(appidentity, "request_close",
                        lambda m: (False, "the app ignored the request"))

    open_app._register_undo(_app())
    sentence = undo.undo_last()
    assert "did not close" in sentence and "ignored" in sentence


def test_focusing_an_already_running_app_registers_no_undo():
    """Raising a window changed the z-order and nothing else.

    "Undo" for that would be "put it back behind three windows", which the
    assistant cannot even observe. So the `already_running` branch must not
    register anything — asserted here on the source, because the branch returns
    from inside a Qt-free function whose other half needs a real process table.
    """
    from pathlib import Path

    source = (Path(__file__).resolve().parent.parent
              / "actions" / "open_app.py").read_text(encoding="utf-8")
    # The focus branch is a `return` inside the loop; the only registration is
    # on the launch path below it, inside `_launch_and_verify`.
    focus_block = source[source.index("for candidate in existing[:8]:"):
                         source.index("launcher_name = appidentity.launcher_name")]
    assert "_register_undo(" not in focus_block, (
        "raising an existing window must not register an undo")
    assert "            _register_undo(appeared)" in source, (
        "the launch path must still register one")


# ── reminder ────────────────────────────────────────────────────────────────

def test_setting_a_reminder_registers_the_closure():
    from actions import reminder

    reminder._register_undo(None, "JARVISReminder_x", "JARVISReminder_x",
                            __import__("pathlib").Path("/nonexistent"),
                            "minum obat",
                            __import__("datetime").datetime.now()
                            + __import__("datetime").timedelta(hours=1))
    assert undo.can_undo() is True
    assert "reminder at" in undo.peek()


def test_cancelling_on_linux_through_at_uses_the_job_number(monkeypatch, tmp_path):
    """`at` is the one scheduler whose identifier cannot be derived.

    The handle carries it (`<task>|at:12`) because `atrm` needs the number and
    no other identifier exists. Without this the reminder was impossible to
    cancel — which is the same as no undo at all.
    """
    from actions import reminder

    calls = []
    monkeypatch.setattr(reminder, "_get_os", lambda: "linux")
    monkeypatch.setattr(subprocess, "run",
                        lambda argv, **k: calls.append(argv) or SimpleNamespace(
                            returncode=0, stdout="", stderr=""))

    script = tmp_path / "notify.py"
    script.write_text("print('hi')", encoding="utf-8")
    reminder._register_undo(None, "task123|at:12", "task123", script,
                            "minum obat", _future())

    sentence = undo.undo_last()

    assert ["atrm", "12"] in calls
    assert script.exists() is False, "the notify script must go with the entry"
    assert "cancelled" in sentence


def test_cancelling_on_windows_deletes_the_task_by_name(monkeypatch, tmp_path):
    from actions import reminder

    calls = []
    monkeypatch.setattr(reminder, "_get_os", lambda: "windows")
    monkeypatch.setattr(subprocess, "run",
                        lambda argv, **k: calls.append(argv) or SimpleNamespace(
                            returncode=0, stdout="", stderr=""))

    script = tmp_path / "notify.py"
    script.write_text("x", encoding="utf-8")
    reminder._register_undo(None, "JARVISReminder_1", "JARVISReminder_1", script,
                            "x", _future())
    undo.undo_last()

    assert calls[0][:2] == ["schtasks", "/Delete"]
    assert "JARVISReminder_1" in calls[0]


def test_a_failed_cancellation_says_so_and_names_the_scheduler(monkeypatch, tmp_path):
    from actions import reminder

    monkeypatch.setattr(reminder, "_get_os", lambda: "windows")
    monkeypatch.setattr(subprocess, "run",
                        lambda argv, **k: SimpleNamespace(
                            returncode=1, stdout="", stderr="Access is denied."))

    script = tmp_path / "notify.py"
    script.write_text("x", encoding="utf-8")
    reminder._register_undo(None, "JARVISReminder_1", "JARVISReminder_1", script,
                            "x", _future())
    sentence = undo.undo_last()

    assert "could not be removed" in sentence and "Access is denied" in sentence


def test_a_reminder_that_already_fired_cannot_be_un_fired(monkeypatch):
    """The one case that is not a failure, named as what it is."""
    from actions import reminder

    monkeypatch.setattr(reminder, "_get_os", lambda: "linux")
    reminder._register_undo(None, "task123|at:12", "task123",
                            __import__("pathlib").Path("/nonexistent"),
                            "x", _past())
    sentence = undo.undo_last()

    assert "already fired" in sentence and "nothing to cancel" in sentence


def _future():
    from datetime import datetime, timedelta

    return datetime.now() + timedelta(hours=1)


def _past():
    from datetime import datetime, timedelta

    return datetime.now() - timedelta(minutes=1)


# ── youtube_video ───────────────────────────────────────────────────────────

def test_playing_a_video_registers_a_back_not_a_close(monkeypatch):
    """Closing a tab this process did not create is a change to somebody else's
    window; going back is the reversal the user would perform."""
    from actions import youtube_video

    pressed = []
    fake = SimpleNamespace(hotkey=lambda *keys: pressed.append(keys))
    monkeypatch.setitem(__import__("sys").modules, "pyautogui", fake)
    monkeypatch.setattr("core.lazyimport.installed",
                        lambda name: (lambda: name == "pyautogui"))

    youtube_video._register_undo("https://youtu.be/x", "laporan keuangan")
    sentence = undo.undo_last()

    assert pressed and pressed[0][1] == "Left", "the undo must be a browser back"
    assert "went back" in sentence


def test_a_back_that_cannot_be_pressed_is_reported_not_claimed(monkeypatch):
    from actions import youtube_video

    monkeypatch.setattr("core.lazyimport.installed", lambda name: (lambda: False))
    youtube_video._register_undo("https://youtu.be/x", "q")
    sentence = undo.undo_last()

    assert "pyautogui" in sentence and "went back" not in sentence


# ── browser_control ─────────────────────────────────────────────────────────

def test_the_internal_browser_undo_asks_the_window_and_repeats_its_answer():
    from actions import browser_control

    asked = []

    class Player:
        def browser_back(self):
            asked.append(1)
            return True

    browser_control._register_undo(Player(), lambda spec: None,
                                   "https://example.com", "go_to")
    sentence = undo.undo_last()

    assert asked == [1]
    assert "went back" in sentence


def test_a_browser_with_no_history_is_nothing_to_undo():
    from actions import browser_control

    class Player:
        def browser_back(self):
            return False

    browser_control._register_undo(Player(), lambda spec: None,
                                   "https://example.com", "new_tab")
    sentence = undo.undo_last()
    assert "nothing to undo" in sentence


def test_a_host_with_no_browser_back_says_so_instead_of_pretending():
    from actions import browser_control

    browser_control._register_undo(None, lambda spec: None, "https://x", "go_to")
    sentence = undo.undo_last()
    assert "cannot be asked to go back" in sentence
