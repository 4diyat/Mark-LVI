"""The generated app icon, tested as the plain function it now is.

WHY THIS IS POSSIBLE NOW
    `_build_jarvis_icon` was a `@staticmethod` on `MainWindow`, so reaching it
    meant importing `ui`, which needs PyQt6 and — on a machine without it — the
    whole test dies before the first assertion. `ui/icons.py` imports nothing
    but the standard library at module level (Pillow is imported inside, for the
    same reason it always was: it is optional), so the drawing can be checked
    here instead of only being eyeballed once by whoever created a shortcut.

WHAT IS WORTH ASSERTING
    Not the pixels — nobody can review a pixel hash. The things that would
    actually break: that it produces a file Pillow can reopen, that it holds
    several sizes (a single-size .ico is blurry on every Windows surface except
    the one size it was drawn for), and that it fails by RETURNING False rather
    than raising, because it runs during shortcut creation where an exception
    would take the menu action down with it.
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
ICONS = ROOT / "ui" / "icons.py"

pytest.importorskip("PIL", reason="Pillow is optional; the icon is drawn with it")


def load_icons():
    """Load ui/icons.py WITHOUT the `ui` package.

    `import ui.icons` pulls in ui/__init__.py, which imports the window and
    therefore PyQt6. This module deliberately needs neither, and proving that
    is half the point of the test.
    """
    spec = importlib.util.spec_from_file_location("icons_under_test", ICONS)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_icon_module_needs_no_qt():
    """If this ever imports PyQt6, `ui.icons` becomes unusable where it matters."""
    source = ICONS.read_text(encoding="utf-8")
    top = source.split("def build_jarvis_icon")[0]
    assert "PyQt6" not in top, "ui/icons.py must stay independent of Qt"


def test_it_writes_a_readable_multi_resolution_ico(tmp_path):
    from PIL import Image

    icons = load_icons()
    out = tmp_path / "jarvis.ico"

    assert icons.build_jarvis_icon(out) is True
    assert out.is_file() and out.stat().st_size > 0

    with Image.open(out) as image:
        assert image.format == "ICO"
        # A single-size .ico is blurry on every surface except the one size it
        # was drawn for. Six sizes is what the renderer produces.
        sizes = image.ico.sizes()
        assert len(sizes) > 1, f"only one resolution stored: {sizes}"
        assert (16, 16) in sizes and (256, 256) in sizes, (
            f"missing a size Windows actually asks for: {sorted(sizes)}")


def test_it_reports_failure_instead_of_raising(tmp_path):
    """It runs while the user is creating a shortcut; a raise loses the action.

    An unwritable path is the realistic failure: a read-only folder, or a
    Desktop that a policy has locked down.
    """
    icons = load_icons()
    # A directory cannot be opened for writing as if it were the icon file.
    assert icons.build_jarvis_icon(tmp_path) is False


def test_it_refuses_to_be_a_method_again():
    """`self`-free functions do not belong on a 2,900-line class."""
    icons = load_icons()
    import inspect
    assert "self" not in inspect.signature(icons.build_jarvis_icon).parameters
