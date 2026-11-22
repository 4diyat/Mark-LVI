"""The design sheet must contain every artboard that exists.

WHY THIS FILE EXISTS
    `docs/mockups/build.py` defines twenty-two artboards, `b01` through `b22`,
    and every one of them runs: `DESIGN-ambient.md` lists them by number, size
    and content, and each function returns valid SVG.

    None of them were ever rendered. `BOARDS_LIST` names `n01`–`n06` and
    `EXTRA` names `n07`–`n12`, a second set of twelve boards with different
    numbering and different content, so `jarvis-design-system.html` shipped
    twelve artboards out of twenty-two and no test noticed. The README, the
    sheet's own header and `DESIGN-ambient.md` all went on claiming twenty-two.

    A design sheet that silently drops half its boards is worse than no sheet:
    it is the document everything else is measured against, and it was
    measuring itself against a list it no longer generated.

WHAT IS PROVEN HERE
    That every `bNN` function exists, runs, returns SVG of the size the
    documentation states, and is registered in the generated sheet. That the
    counts three different files claim agree with the code.

    Not proven: that the drawn artboards look right. That needs eyes on the
    sheet, and `docs/verification.md` carries it.
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
MOCKUPS = ROOT / "docs" / "mockups"
BUILD = MOCKUPS / "build.py"
SHEET = MOCKUPS / "jarvis-design-system.html"


def _build_module():
    """Import the generator without running its `__main__` block."""
    sys.path.insert(0, str(MOCKUPS))
    try:
        for name in [n for n in sys.modules if n == "build"]:
            del sys.modules[name]
        import build

        return build
    finally:
        sys.path.pop(0)


def _artboard_functions() -> list[str]:
    tree = ast.parse(BUILD.read_text(encoding="utf-8"))
    names = [n.name for n in tree.body if isinstance(n, ast.FunctionDef)]
    found = [n for n in names if re.fullmatch(r"b\d{2}", n)]
    return sorted(found)


# ── the twenty-two ──────────────────────────────────────────────────────────

def test_the_generator_defines_twenty_two_artboards():
    """`DESIGN-ambient.md` says 22, by number. This is the code's answer."""
    found = _artboard_functions()
    assert len(found) == 22, (
        f"build.py defines {len(found)} artboard functions ({found}); the "
        f"documentation describes twenty-two, numbered 1 to 22")


def test_every_artboard_numbers_from_one_to_twenty_two_without_a_gap():
    found = _artboard_functions()
    expected = [f"b{n:02d}" for n in range(1, 23)]
    assert found == expected, f"missing or extra: {set(expected) ^ set(found)}"


@pytest.mark.parametrize("number", range(1, 23))
def test_each_artboard_actually_draws_something(number):
    """A function that raises or returns nothing is a hole in the sheet.

    This is the test that would have caught the ten missing boards: they were
    never called, so nothing failed, and nothing was drawn.
    """
    build = _build_module()
    fn = getattr(build, f"b{number:02d}")
    svg = fn()
    assert isinstance(svg, str) and len(svg) > 500, (
        f"artboard {number} produced {len(svg) if isinstance(svg, str) else svg!r} "
        f"bytes of SVG")
    assert "<text" in svg, f"artboard {number} draws no text"


# ── sizes, as `DESIGN-ambient.md` states them ───────────────────────────────

def test_each_artboard_is_the_size_the_documentation_states():
    """1280×720 desktop, 460×640 panels, 720×640 gesture map, and so on.

    The numbers come from the documentation's own table, not from whatever the
    code happens to emit — otherwise this test would ratify a mistake.
    """
    expected = {
        **{n: (1280, 720) for n in (1, 2, 3, 4)},
        **{n: (460, 640) for n in range(5, 19)},
        19: (720, 640),
        20: (1280, 300),
        21: (1280, 640),
        22: (720, 480),
    }
    build = _build_module()
    wrong = {}
    for number, size in expected.items():
        svg = getattr(build, f"b{number:02d}")()
        m = re.search(r'<svg[^>]*width="(\d+)" height="(\d+)"', svg)
        assert m, f"artboard {number} has no <svg> dimensions"
        got = (int(m.group(1)), int(m.group(2)))
        if got != size:
            wrong[number] = (size, got)
    assert not wrong, f"artboard {number}: documented vs drawn {wrong}"


# ── and the sheet the repo ships must contain them ─────────────────────────

def test_the_shipped_sheet_contains_all_twenty_two():
    """The file in the repo, not the generator's ambition."""
    html = SHEET.read_text(encoding="utf-8")
    drawn = re.findall(r'class="num">([^<]+)</span>', html)
    numbers = sorted(int(d) for d in drawn if d.isdigit())
    assert numbers == list(range(1, 23)), (
        f"jarvis-design-system.html contains {len(numbers)} artboards "
        f"({numbers}); the generator defines twenty-two")


def test_the_sheet_is_what_the_generator_produces():
    """A committed sheet that has drifted from `build.py` is a document that
    disagrees with its own source."""
    build = _build_module()
    generated = build.build_html()
    shipped = SHEET.read_text(encoding="utf-8")
    assert generated.strip() == shipped.strip(), (
        "jarvis-design-system.html is stale; run `python docs/mockups/build.py`")


# ── the three files that state a count must agree ───────────────────────────

def test_every_document_that_states_a_count_states_the_same_one():
    """README, DESIGN-ambient.md and the sheet's own header all print a number.

    They printed twenty-two while the sheet held twelve. A count written in
    three places and verified in none is three chances to be wrong.
    """
    total = len(_artboard_functions())

    readme = (MOCKUPS / "README.md").read_text(encoding="utf-8")
    design = (MOCKUPS / "DESIGN-ambient.md").read_text(encoding="utf-8")
    html = SHEET.read_text(encoding="utf-8")

    for label, text in (("README.md", readme), ("DESIGN-ambient.md", design),
                        ("jarvis-design-system.html", html)):
        claimed = re.findall(r"(\d+)\s*artboard", text)
        assert claimed, f"{label} no longer states a count"
        for value in claimed:
            assert int(value) == total, (
                f"{label} claims {value} artboards; build.py defines {total}")
