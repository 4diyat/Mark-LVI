"""Where the desktop orb sits: the corner, the drag, and what is remembered.

WHY THIS IS A SEPARATE FILE FROM `test_orb_overlay_board1.py`
    The code under test moved to `ui/orb_place.py` when `ui/orb_overlay.py`
    reached the 600-line ceiling, and a test file that keeps asserting another
    module's job is how the two drift apart. What is left here is pure: no
    widget, no window, no paint.

WHY THE CONFIG MUST BE REDIRECTED
    `memory.config_manager` resolves its file path ONCE, at import, from the
    repository root. A fixture that set an environment variable and hoped
    would leave every drag test writing into the developer's real
    `config/api_keys.json` — and the next test would then fail because the orb
    came back where the previous one left it. That happened here; the suite's
    `isolated_config` fixture is the fix, not a smaller assertion.
"""
from __future__ import annotations


import pytest


class _Area:
    """A 1920x1080 desktop at the origin, in the shape Qt's geometry has."""

    def x(self):
        return 0

    def y(self):
        return 0

    def width(self):
        return 1920

    def height(self):
        return 1080


@pytest.fixture()
def place(isolated_config, monkeypatch):
    import importlib

    import ui.orb_place as module

    module = importlib.reload(module)

    # A SCREEN BY DEFAULT, and this is the fixture's job rather than each
    # test's: `read_position` refuses a saved point when it cannot check it
    # against a screen, and this file does not install the Qt stub, so without
    # this every test would exercise the headless path and the placement rules
    # would never run at all. The tests that are ABOUT having no screen
    # override this explicitly.
    monkeypatch.setattr(module, "screen_area", _Area)
    return module


def test_a_fresh_orb_has_no_saved_position(place):
    assert place.read_position() is None


def test_a_drag_is_remembered(place):
    """The user chose free placement. A position forgotten on restart is a
    position the user has to set every morning."""
    assert place.save_position(300, 200) is True
    assert place.read_position() == (300, 200)


def test_a_position_off_every_screen_is_not_restored(place, monkeypatch):
    """A monitor can be unplugged between sessions. Restoring a position on a
    screen that no longer exists puts the orb where nobody can reach it, which
    is indistinguishable from "the orb is gone"."""
    place.save_position(9000, 9000)
    assert place.read_position() is None


def test_a_position_on_a_second_monitor_is_restored(place, monkeypatch):
    """The other side of the same rule: a point that IS on the available area
    must survive, or a two-monitor user loses their placement every launch."""
    place.save_position(1500, 300)
    assert place.read_position() == (1500, 300)


@pytest.mark.parametrize("raw", ["not a pair", [12], [1, 2, 3], ["a", "b"],
                                 None, 7])
def test_a_corrupt_saved_position_is_ignored_not_raised(place, raw):
    """`api_keys.json` is a file the user can edit, and this is two integers in
    it. A string where a pair belongs must not stop the orb from appearing."""
    place.write_position({place.POSITION_KEY: raw})
    assert place.read_position() is None


def test_no_screen_at_all_falls_back_to_the_corner(place, monkeypatch):
    """`screen_area()` returns None before a QApplication exists or on a
    headless box. Validating against nothing must not reject the saved point
    AND must not raise — the caller places the orb in the corner either way."""
    place.save_position(300, 200)
    monkeypatch.setattr(place, "screen_area", lambda: None)
    assert place.read_position() is None
