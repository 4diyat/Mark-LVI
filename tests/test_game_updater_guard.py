"""game_updater must not claim it did something it never looked at.

The bug this covers is a `try/except ImportError: pass` sitting directly above
"Profile selection detected — clicking the first profile". Without pyautogui or
numpy — a normal install on Linux, or a headless machine — the detection never
ran, fell through, and clicked the middle of the Steam window while reporting
that a profile dialog had been found.

Nothing here touches a real window: everything that would look at the screen is
stubbed, and the question each test asks is only "did the code admit it could
not tell?".
"""
from __future__ import annotations

import builtins

import pytest

from actions import game_updater


@pytest.fixture()
def steam_window(monkeypatch):
    monkeypatch.setattr(game_updater, "_get_steam_window_rect",
                        lambda: (100, 100, 800, 600))


def test_a_missing_library_does_not_become_a_blind_click(steam_window, monkeypatch,
                                                         capsys):
    """ImportError used to fall through into the click."""
    clicked = []
    monkeypatch.setattr(game_updater, "_click_first_profile_by_screenshot",
                        lambda: clicked.append(True) or True)

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name in ("pyautogui", "numpy"):
            raise ImportError(f"no module named {name}")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    assert game_updater._handle_steam_profile_selection() is False
    assert clicked == [], "it must not click when it could not look"
    assert "Cannot inspect the window" in capsys.readouterr().out


def test_a_failing_screenshot_does_not_become_a_blind_click(steam_window,
                                                            monkeypatch, capsys):
    clicked = []
    monkeypatch.setattr(game_updater, "_click_first_profile_by_screenshot",
                        lambda: clicked.append(True) or True)

    import sys, types
    fake_pyautogui = types.SimpleNamespace(
        screenshot=lambda **kw: (_ for _ in ()).throw(OSError("no display")))
    monkeypatch.setitem(sys.modules, "pyautogui", fake_pyautogui)
    monkeypatch.setitem(sys.modules, "numpy", types.SimpleNamespace(array=lambda x: x))

    assert game_updater._handle_steam_profile_selection() is False
    assert clicked == []
    assert "Profile detection failed" in capsys.readouterr().out


def test_no_steam_window_means_no_work(monkeypatch):
    monkeypatch.setattr(game_updater, "_get_steam_window_rect", lambda: None)
    assert game_updater._handle_steam_profile_selection() is False
