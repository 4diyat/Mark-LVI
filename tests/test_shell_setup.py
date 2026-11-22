"""The gate between "no key" and "JARVIS is listening".

WHY THIS FILE EXISTS AT ALL
    `_ready` had two writes, both `False`, and nothing anywhere set it `True`.
    `main.py` blocks in `ui.wait_for_api_key()` before it starts a session, and
    the recovery loop blocks in `while not self.ui._ready` after a rejected key
    — so BOTH wait loops had no exit. Nothing caught it because every test that
    touched the shell used a `_ready` it had set itself, which is the shape of
    the bug: a flag nobody writes looks exactly like a flag nobody reads.

    So the assertions here are about the two loops ending, and about what the
    user is shown while they are not ended.

NO QT IN THIS FILE
    `ui/setup_screen.open_setup` is faked, because what is being tested is
    `wait_for_api_key`'s decision and not Qt's. The setup window itself is
    covered by `tests/test_setup_window.py` against the stub.
"""
from __future__ import annotations

import threading

import pytest


@pytest.fixture()
def shell():
    from ui.shell import AmbientShell

    made = AmbientShell(face_path="", assistant_name="JARVIS")
    made.notify = lambda *a, **k: None        # no tray in this sandbox
    return made


@pytest.fixture()
def no_key(monkeypatch):
    from ui import setup_screen

    monkeypatch.setattr(setup_screen, "has_key", lambda: False)


@pytest.fixture()
def setup_screen():
    from ui import setup_screen as module

    return module


@pytest.fixture()
def asked(monkeypatch):
    """Record `open_setup` calls instead of building a window."""
    from ui import setup_screen

    calls = []
    monkeypatch.setattr(setup_screen, "open_setup", lambda s: calls.append(s) or True)
    return calls


# ── the flag that never got set ────────────────────────────────────────────

def test_the_shell_starts_not_ready(shell):
    assert shell._ready is False


def test_mark_ready_is_the_one_thing_that_sets_it(shell):
    shell.mark_ready()
    assert shell._ready is True


def test_mark_ready_is_idempotent(shell):
    shell.mark_ready()
    shell.mark_ready()
    assert shell._ready is True


# ── the wait with no key ───────────────────────────────────────────────────

def test_no_key_raises_the_setup_screen(shell, no_key, asked):
    """The whole point: a first run must ASK, not print where to edit JSON."""
    started = threading.Thread(target=shell.wait_for_api_key, daemon=True)
    started.start()
    started.join(timeout=2.0)
    assert asked == [shell]


def test_the_wait_ends_when_the_screen_reports_a_saved_key(shell, no_key, asked):
    """Driven end to end: the thread is inside `wait_for_api_key`, the screen's
    done handler runs on another thread, and the loop has to notice. A test that
    only checked `ask == [shell]` would pass on a loop that never exits."""
    started = threading.Thread(target=shell.wait_for_api_key, daemon=True)
    started.start()
    # The done handler is what `SetupWindow` calls after a save.
    shell._setup = object()
    shell._setup_done(_verdict("ok"))
    started.join(timeout=3.0)
    assert not started.is_alive(), "wait_for_api_key never returned after a save"


def _returns_promptly(shell, seconds: float = 2.0) -> bool:
    """True if `wait_for_api_key` came back. FAILS the test rather than hanging.

    Written because the first version of these two tests called it directly and
    the run hung for ten minutes: `wait_for_api_key` used to wait for `_ready`,
    which only a SAVED key sets, so a working install with a key already in the
    file waited forever. A test that hangs is a test that reports nothing.
    """
    started = threading.Thread(target=shell.wait_for_api_key, daemon=True)
    started.start()
    started.join(timeout=seconds)
    return not started.is_alive()


def test_an_existing_key_does_not_raise_the_screen(shell, monkeypatch,
                                                   setup_screen, asked):
    """A working install must not be asked for a key it already has — the
    screen is a gate, and a gate in front of a working app is a bug."""
    monkeypatch.setattr(setup_screen, "has_key", lambda: True)
    assert _returns_promptly(shell), "a working install blocked on startup"
    assert asked == []


def test_a_config_that_cannot_be_read_does_not_pop_the_screen(shell, monkeypatch,
                                                             setup_screen, asked):
    """"Cannot tell" defaults to "has a key". A screen over a working install
    because a JSON file was momentarily locked is worse than a session that
    fails on its own and asks then."""
    import memory.config_manager as cm

    def boom():
        raise OSError("locked")

    monkeypatch.setattr(cm, "is_configured", boom)
    assert setup_screen.has_key() is True
    assert _returns_promptly(shell)
    assert asked == []


def test_with_no_qt_it_says_where_the_key_goes_and_keeps_waiting(shell, no_key):
    """`open_setup` False is the headless case. The app must not exit: a tray
    app that dies because it could not draw a dialog is worse than one that
    prints the path."""
    lines = []
    shell.notify = lambda text, *a, **k: lines.append(text)

    started = threading.Thread(target=shell.wait_for_api_key, daemon=True)
    started.start()
    for _ in range(40):
        if lines:
            break
        threading.Event().wait(0.01)
    assert started.is_alive(), "the wait gave up instead of waiting"
    assert lines and "api_keys.json" in lines[0]
    shell.mark_ready()
    started.join(timeout=3.0)


# ── the recovery loop after a rejected key ─────────────────────────────────

def test_prompt_reconfig_clears_ready_and_asks_for_a_new_key(shell, asked):
    shell.mark_ready()
    shell.prompt_reconfig()
    assert shell._ready is False, "the session would start against the same key"
    assert asked == [shell]


def test_prompt_reconfig_falls_back_to_the_old_notice_without_qt(shell, monkeypatch):
    """Never silent: if the screen cannot open, the user is still told."""
    from ui import setup_screen

    lines = []
    shell.notify = lambda text, *a, **k: lines.append(text)
    monkeypatch.setattr(setup_screen, "open_setup", lambda s: False)
    shell.prompt_reconfig()
    assert lines and "api_keys.json" in lines[0]


def test_the_recovery_loop_exits_after_a_new_key(shell, no_key, asked):
    """`main.py` does `while not self.ui._ready: await asyncio.sleep(1)`.
    Without `mark_ready()` that loop is the rest of the process's life."""
    shell.prompt_reconfig()
    assert shell._ready is False
    shell._setup_done(_verdict("ok"))
    assert shell._ready is True


def _verdict(kind):
    from core import key_check

    return key_check.Verdict(kind)


# ── the tray's Settings item ────────────────────────────────────────────────

def test_the_settings_item_opens_the_one_screen_that_exists(shell):
    """Before this, Settings told the user to edit JSON — an instruction that
    was correct for voice and accent and useless for the one setting that can
    stop the app from starting at all."""
    from ui import lifecycle

    lines = []
    shell.write_log = lines.append
    shell.open_setup = lambda: True
    lifecycle.summon_settings(shell)
    assert any("API key screen is open" in ln for ln in lines)


def test_the_settings_item_still_names_the_file_when_the_screen_cannot_open(shell):
    """A machine without Qt must not lose the only instruction it has."""
    from ui import lifecycle

    lines = []
    shell.write_log = lines.append
    shell.open_setup = lambda: False
    lifecycle.summon_settings(shell)
    assert any("api_keys.json" in ln for ln in lines)


def test_a_shell_with_no_open_setup_still_answers(shell):
    """`AmbientShell` always has the method; a test double may not, and an
    AttributeError from a tray menu is a tray menu that does nothing."""
    from ui import lifecycle

    lines = []
    shell.write_log = lines.append
    shell.open_setup = None
    lifecycle.summon_settings(shell)
    assert any("api_keys.json" in ln for ln in lines)
