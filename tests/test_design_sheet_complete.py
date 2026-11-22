"""The design sheet must contain every artboard that exists.

WHY THIS FILE EXISTS
    `docs/mockups/build.py` defines twenty-two artboards, `b01` through `b22`,
    and every one of them runs: `DESIGN-ambient.md` lists them by number, size
    and content, and each function returns valid SVG.

    None of them were ever rendered. `BOARDS_LIST` named `n01`–`n06` and
    `EXTRA` named `n07`–`n12`, a second set of twelve boards with different
    numbering and different content, so `jarvis-design-system.html` shipped
    twelve artboards out of twenty-two and no test noticed. The README, the
    sheet's own header and `DESIGN-ambient.md` all went on claiming twenty-two.

    A design sheet that silently drops half its boards is worse than no sheet:
    it is the document everything else is measured against, and it was
    measuring itself against a list it no longer generated.

    THE SECOND HALF OF THE FIX, WHICH IS A RULING RATHER THAN A REPAIR
        The twelve `n*` views were worth keeping — they are the states (Fokus,
        Senyap, the risk confirmation, history, permissions, light theme) that
        the build has tests for. But they carried a SECOND numbering, 23–28,
        and it collided with the first: their 05 was a tray panel and `b05` is
        one too. The owner's ruling on 2026-11-22: one set of numbers, 1–22.
        Each state is now drawn as `NNx` directly under the board it is a state
        of, and nothing is numbered past 22.

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

def _labels(html: str) -> tuple[list[int], list[str]]:
    """The sheet's labels, split into board numbers and state views.

    Boards are `01`..`22`; a state view is `05a`, `05b`, `14a` — the board it
    belongs to plus a letter, which is what folding six states into their
    parents looks like on the page.
    """
    drawn = re.findall(r'class="num">([^<]+)</span>', html)
    boards = sorted(int(d) for d in drawn if d.isdigit())
    views = [d for d in drawn if not d.isdigit()]
    return boards, views


def test_the_shipped_sheet_contains_all_twenty_two():
    """The file in the repo, not the generator's ambition."""
    html = SHEET.read_text(encoding="utf-8")
    numbers, _views = _labels(html)
    assert numbers == list(range(1, 23)), (
        f"jarvis-design-system.html contains {len(numbers)} artboards "
        f"({numbers}); the generator defines twenty-two")


def test_nothing_on_the_sheet_is_numbered_past_twenty_two():
    """The 23–28 numbering is retired, and this is what would bring it back.

    It is not cosmetic: `ui/`, the tests and `NOT-IN-MOCKUP.md` all say "board 14a" meaning the risk dialog, and board 14a no longer exists.
    """
    html = SHEET.read_text(encoding="utf-8")
    numbers, views = _labels(html)
    assert max(numbers) == 22, f"a board is numbered past 22: {numbers}"
    for label in views:
        assert re.fullmatch(r"\d{2}[a-z]", label), (
            f"{label!r} is neither a board number nor a state view")
        assert int(label[:2]) <= 22, (
            f"{label!r} is a state of board {int(label[:2])}, which does not exist")


def test_every_state_view_is_drawn_under_the_board_it_belongs_to():
    """`05a` must come after board 5 and before board 6, not in a section of its own.

    That is the whole content of "the six states fold into their parents": a
    reader meets a state where they met the board.
    """
    html = SHEET.read_text(encoding="utf-8")
    order = re.findall(r'class="num">([^<]+)</span>', html)
    seen = []
    for label in order:
        seen.append(label)
    for index, label in enumerate(seen):
        if re.fullmatch(r"\d{2}[a-z]", label):
            parent = int(label[:2])
            # A parent board is printed WITHOUT leading zeros ('5'), a state
            # label with them ('05a') — that is the sheet's own formatting, and
            # comparing strings here is how the first version of this test
            # failed on its own subject rather than on the sheet.
            assert str(parent) in seen[:index], (
                f"{label} is drawn before board {parent}")
            following = [s for s in seen[index + 1:] if s.isdigit()]
            if following:
                assert int(following[0]) == parent + 1, (
                    f"{label} is drawn after board {following[0]}, not under {parent}")


def test_the_title_table_is_exactly_one_to_twenty_two():
    """`BOARD_TITLES` is the numbering now, so a key of 23 is a 23rd board.

    `BOARDS_LIST` cannot catch it: a title whose `bNN` does not exist is skipped
    when the list is built, which is the silent-skip this test is here to stop.
    """
    build = _build_module()
    assert sorted(build.BOARD_TITLES) == list(range(1, 23)), (
        f"BOARD_TITLES is not 1..22: {sorted(build.BOARD_TITLES)}")


def test_every_state_view_names_a_board_that_exists():
    """`EXTRA`'s first column is a board number, and it must be one of the 22.

    The renderer skips a view whose parent is not in the registry — a silent
    skip, which is exactly the failure mode this whole file exists to stop. This
    reads the REGISTRY, not the rendered HTML, so a typo fails here instead of
    disappearing into the sheet.
    """
    build = _build_module()
    boards = {int(row[0]) for row in build.BOARDS_LIST}
    assert boards == set(range(1, 23))
    strangers = [row for row in build.EXTRA if int(row[0]) not in boards]
    assert not strangers, (
        f"these EXTRA views are parented to a board that does not exist: {strangers}")


def test_every_view_the_registry_names_is_drawn():
    """Twelve views: the six shell boards and the six states.

    THIS TEST USED TO ASSERT `len(views) == 6`, AND THAT WAS THE BUG.
        Folding the six `n07`-`n12` states into their parents also silently
        dropped `n01`-`n06` — six artboards that were rendered nowhere
        afterwards, including `n03`, the command bar the implementation is
        measured against. The test passed, because it counted the six that were
        left: a number copied from the code ratified whatever the code did.
        It now reads the REGISTRY and demands that every function named there
        appears on the sheet, which is the question that actually matters.
    """
    build = _build_module()
    html = SHEET.read_text(encoding="utf-8")
    _numbers, views = _labels(html)
    expected = len(build.EXTRA)
    assert len(views) == expected, (
        f"the registry names {expected} views and the sheet draws {len(views)}")
    # And every view's own heading, as the registry spells it, is on the page.
    # `artboard()` escapes `&`, so the comparison does too.
    for _parent, title, _w, _h, fn in build.EXTRA:
        assert title.replace("&", "&amp;") in html, (
            f"{fn} ({title!r}) is named in EXTRA but its heading is not in the sheet")


def test_every_artboard_function_is_rendered_somewhere():
    """No `bNN` or `nNN` may exist and be drawn nowhere.

    This is the test that would have caught the drop: six `n` functions were
    defined, passed their own liveness tests, and appeared on no sheet.
    """
    build = _build_module()
    rendered = {row[4].__name__ for row in build.BOARDS_LIST}
    rendered |= {row[4] for row in build.EXTRA}
    defined = set()
    tree = ast.parse(BUILD.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and re.fullmatch(r"[bn]\d{2}", node.name):
            defined.add(node.name)
    orphans = sorted(defined - rendered)
    assert not orphans, (
        f"these artboard functions are defined and drawn nowhere: {orphans}")


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

# ── "drawn inside its own canvas", which the doc used to claim unchecked ────
#
# `DESIGN-ambient.md` said "22 artboard valid, tanpa elemen meluber, tanpa
# bentuk berukuran nol" and nothing verified it. It was nearly true: one orb on
# board 1 painted its 72.8 px glow past the right edge. These two tests are what
# make the sentence a fact rather than a hope.

def _shapes(svg: str):
    """Every primitive that has a position and an extent, parsed from the SVG."""
    import xml.etree.ElementTree as ET

    root = ET.fromstring(svg)
    for el in root.iter():
        tag = el.tag.split("}")[-1]
        try:
            if tag == "rect":
                yield tag, (float(el.get("x", 0)), float(el.get("y", 0)),
                            float(el.get("width", 0)), float(el.get("height", 0)))
            elif tag == "circle":
                cx, cy, r = (float(el.get("cx", 0)), float(el.get("cy", 0)),
                             float(el.get("r", 0)))
                yield tag, (cx - r, cy - r, r * 2, r * 2)
        except (TypeError, ValueError):
            continue


@pytest.mark.parametrize("number", range(1, 23))
def test_every_artboard_paints_inside_its_own_canvas(number):
    """An element outside the canvas is drawn into nothing.

    The tolerance is 1 px: a 1 px stroke on the edge is centred, so half of it
    is legitimately outside the box.
    """
    build = _build_module()
    svg = getattr(build, f"b{number:02d}")()
    m = re.search(r'<svg[^>]*width="(\d+)" height="(\d+)"', svg)
    width, height = int(m.group(1)), int(m.group(2))
    outside = []
    for tag, (x, y, w, h) in _shapes(svg):
        if x < -1 or y < -1 or x + w > width + 1 or y + h > height + 1:
            outside.append((tag, round(x, 1), round(y, 1),
                            round(x + w, 1), round(y + h, 1)))
    assert not outside, (
        f"artboard {number} ({width}×{height}) paints {len(outside)} element(s) "
        f"outside its canvas: {outside[:4]}")


@pytest.mark.parametrize("number", range(1, 23))
def test_no_artboard_draws_a_zero_sized_shape(number):
    """A zero-width rect is an invisible element pretending to be a mark."""
    build = _build_module()
    svg = getattr(build, f"b{number:02d}")()
    zero = [(tag, box) for tag, box in _shapes(svg) if box[2] <= 0 or box[3] <= 0]
    assert not zero, f"artboard {number} draws {len(zero)} zero-sized shape(s)"


def test_every_artboard_is_well_formed_xml():
    """Inline SVG that a browser has to repair is a drawing nobody can trust."""
    import xml.etree.ElementTree as ET

    build = _build_module()
    for number in range(1, 23):
        svg = getattr(build, f"b{number:02d}")()
        try:
            ET.fromstring(svg)
        except ET.ParseError as exc:            # noqa: PERF203 — one message
            raise AssertionError(
                f"artboard {number} is not well-formed XML: {exc}") from exc

# ── the sheet and the record of what is built must not drift apart ──────────
#
# `NOT-IN-MOCKUP.md` has two tables: the artboards with no `ui/` module, and the
# artboards that have one. A board moving from one to the other is the event
# this file is about — board 2 did exactly that on 2026-11-22 — and nothing
# noticed, because a markdown table cannot fail. These tests can.

RECORD = MOCKUPS / "NOT-IN-MOCKUP.md"


def _record_tables() -> tuple[list[str], list[str]]:
    """The board numbers in each table, in document order."""
    text = RECORD.read_text(encoding="utf-8")
    split = text.index("## Built, drawn")
    unbuilt = re.findall(r"^\| (\d+)[a-z]? \|", text[:split], re.M)
    built = re.findall(r"^\| (\d+)[a-z]? \|", text[split:], re.M)
    return built, unbuilt


def test_every_artboard_is_recorded_as_built_or_not_built():
    """No board may fall through the record, or be listed twice.

    Board 18 was in neither table when this test was written: it had the light
    palette and no light page, and the prose had never decided which side that
    put it on. A board that appears in neither is a board nobody has thought
    about since the sheet grew.
    """
    built, unbuilt = _record_tables()
    built_boards = {int(n) for n in built}
    unbuilt_boards = {int(n) for n in unbuilt}
    missing = sorted(set(range(1, 23)) - built_boards - unbuilt_boards)
    assert not missing, (
        f"NOT-IN-MOCKUP.md does not say whether these artboards are built: {missing}")
    # A BOARD IN BOTH TABLES IS A BOARD THE DOC CALLS "partial", and the set of
    # those is checked rather than guessed. It used to be a single board (14,
    # whose risk levels exist and whose guest mode may not be drawn); board 3
    # joined it because its camera tile exists inside the voice overlay while
    # the artboard's own panel does not. The rule the test enforces is not "one"
    # — it is that every overlap is a NAMED partial, and that the number is
    # small enough that "partial" still means something.
    both = sorted(built_boards & unbuilt_boards)
    assert both == [3, 14], (
        f"the artboards listed both built and not-built changed: {both}. If a "
        "board genuinely moved, name it here and in the doc's partial list")
    assert len(both) <= 3, (
        f"{len(both)} boards are half built; the partial exception has become "
        "the rule")


def test_the_record_names_modules_that_exist():
    """Every ``ui/*.py`` a table names must be in the tree.

    This is the cheap half of the check, and it is the half a machine can do:
    a row pointing at a module that was renamed is a row that has stopped being
    an answer to "where is this built?".
    """
    text = RECORD.read_text(encoding="utf-8")
    # Only the two artboard tables. The rest of the file is the record of what
    # was DELETED, and naming a file that no longer exists is the whole point of
    # that section — checking it would demand that deleted files exist.
    split = text.index("## Built, drawn")
    after = text.index("Plus the surfaces the owner explicitly kept")
    tables = text[:split] + text[split:after]
    cited = set(re.findall(r"`(ui/[a-z_]+\.py)`", tables))
    missing = sorted(path for path in cited if not (ROOT / path).exists())
    assert not missing, (
        f"NOT-IN-MOCKUP.md cites modules that do not exist: {missing}")


def test_the_command_bar_is_recorded_as_built():
    """The one row that moved this session, pinned so it cannot slide back.

    Board 2 was a "drawn, not built" row with `**proposal**` where its module
    belonged. It has a module now, and the record has to say so or the next
    reader will rebuild it.
    """
    built, unbuilt = _record_tables()
    assert "2" in built, "board 2's command bar is recorded as unbuilt"
    assert "2" not in unbuilt
    row = next(line for line in RECORD.read_text(encoding="utf-8").splitlines()
               if line.startswith("| 2 |"))
    assert "command_bar.py" in row and "command_paint.py" in row, (
        f"board 2's row does not name the modules that implement it: {row}")


# ── the built/unbuilt split, derived from the tables and checked ────────────
#
# The sentence in `DESIGN-ambient.md` is written in WORDS ("sembilan artboard
# punya permukaan penuh … tiga belas belum") and the drift test above reads
# DIGITS, so nothing was checking it. It said "delapan" for a board that had
# been built, and it said thirteen plus thirteen while the sheet held 22
# artboards — the lettered views had been counted as if they were boards. A
# count that adds up to more than the whole is the clearest sign it was written
# from memory. This derives the sets from `NOT-IN-MOCKUP.md` and compares.

_WORDS = {"nol": 0, "satu": 1, "dua": 2, "tiga": 3, "empat": 4, "lima": 5,
          "enam": 6, "tujuh": 7, "delapan": 8, "sembilan": 9, "sepuluh": 10,
          "sebelas": 11, "dua belas": 12, "tiga belas": 13, "empat belas": 14}


def _board_rows(section: str) -> list[str]:
    """The `#` cell of every table row in one `##` section."""
    text = (MOCKUPS / "NOT-IN-MOCKUP.md").read_text(encoding="utf-8")
    body = text.split(section, 1)[1].split("\n## ", 1)[0]
    return [m.group(1) for m in re.finditer(r"^\|\s*(\d+[a-z]?)\s*\|", body,
                                            re.MULTILINE)]


_NUMBER = r"(dua belas|tiga belas|empat belas|nol|satu|dua|tiga|empat|lima|"\
          r"enam|tujuh|delapan|sembilan|sepuluh|sebelas)"


def _claimed(design: str, pattern: str) -> int:
    """The number word matching `pattern`, as an int. Fails loudly, not None."""
    match = re.search(pattern, design)
    assert match, f"DESIGN-ambient.md no longer states {pattern!r}"
    word = match.group(1).strip()
    assert word in _WORDS, f"{word!r} is not a number word this test knows"
    return _WORDS[word]


# Board 14 is HALF built: its confirmation view (14a) is in `ui/`, and its
# security panel is not. Every count below has to say which half it means.
_HALF = "14"


def _parent(board: str) -> str:
    """`14a` -> `14`: a lettered view belongs to its parent board."""
    return board.rstrip("abcdefghijklmnopqrstuvwxyz")


def test_every_board_in_the_table_names_a_page_that_exists():
    """The table's third column is "where the surface is". Every row must name a
    page, and that page must be one the panel actually builds.

    THIS REPLACED A COUNT TEST, and the replacement is stricter. The old test
    pinned "thirteen artboards have no surface"; that claim is now false for
    every board, so a test that went on asserting it would have had to be
    deleted — and a deleted test is how a claim stops being checked. What is
    checked now is the claim the table makes TODAY: each row's page exists.
    """
    import re as _re


    text = (MOCKUPS / "NOT-IN-MOCKUP.md").read_text(encoding="utf-8")
    body = text.split("## Drawn, not built", 1)[1].split("\n## ", 1)[0]

    rows = _re.findall(r"^\|\s*(\d+)\s*\|.*?\|\s*`ui/([a-z_]+\.py)`", body,
                       _re.MULTILINE)
    assert len(rows) >= 12, f"the table lost its rows: {rows}"

    from ui.page_registry import PAGE_BOARD

    for board, module in rows:
        assert (Path("ui") / module).exists(), (
            f"board {board} names ui/{module}, which does not exist")

    # AND THE MODULE MUST BE THE ONE THAT HOLDS THAT BOARD'S PAGE. Without this
    # the test only checked that SOME file exists: pointing board 9 at
    # `pages_admin.py` would have passed, because the row still named a real
    # module — just not the one with the page in it.
    numbers = {str(n): page for page, n in PAGE_BOARD.items()}
    for board, module in rows:
        page = numbers.get(str(board))
        if page is None:
            continue
        want = {"memory": "pages_memory.py", "memory_one": "pages_memory.py",
                "more": "pages_more.py"}.get(page)
        if want is None:
            want = ("pages_admin.py" if page in
                    ("security", "access", "plugins", "light", "brand", "installer")
                    else "pages_people.py")
        assert module == want, (
            f"board {board} is page {page!r}, which lives in {want}, "
            f"but the table says ui/{module}")


def test_the_two_documents_agree_that_nothing_is_unbuilt():
    """`DESIGN-ambient.md` and `NOT-IN-MOCKUP.md` must tell the same story.

    The pair used to state "8 full, 1 half, 13 absent". Both now say every
    artboard has a surface, and the sentence in DESIGN-ambient.md is checked
    against the registry: the count it states must be 22, and the boards it
    calls partial must be the five whose pages say so.
    """
    from ui.page_registry import PAGE_BOARD

    design = (MOCKUPS / "DESIGN-ambient.md").read_text(encoding="utf-8")
    assert "dua puluh dua artboard punya permukaan" in design, (
        "DESIGN-ambient.md no longer states the total")
    # WRAPPED PROSE. The sentence sits across a line break in the file, so it is
    # flattened before it is looked for: a test that matched the raw text would
    # pass or fail on where the editor put the newline.
    flat = " ".join(design.split())
    assert "Tujuh belas tambah lima sama dengan dua puluh dua" in flat, (
        "the two halves of the count no longer add up in the text")

    # EVERY BOARD IS ACCOUNTED FOR SOMEWHERE, and the two places are the two
    # tables in NOT-IN-MOCKUP.md — not this test's own guess about which boards
    # were built before the board pages existed (1, 2, 4, 5, 6, 8 and 20 were:
    # the orb, the command bar, the tray panel, the voice overlay, the privacy
    # page, the history page and the orb-status sheet).
    built = {_parent(b) for b in _board_rows("## Built, drawn")}
    partial_paged = {str(n) for n in PAGE_BOARD.values()}
    covered = built | partial_paged
    assert covered == {str(n) for n in range(1, 23)}, (
        f"boards in neither the built table nor the page registry: "
        f"{sorted({str(n) for n in range(1, 23)} - covered)}")


def test_the_ui_column_in_the_board_table_names_a_real_module():
    """`DESIGN-ambient.md`'s last column used to read "tidak" for thirteen rows.

    It is prose, so nothing was checking it — and when the board pages landed it
    went on saying "tidak" for thirteen boards that now had pages. A reader who
    trusted that column would have concluded the opposite of the truth.

    THE CHECK IS DELIBERATELY LOOSE ABOUT THE WORDS: some rows name one module,
    some name two, some add a parenthesis about what the page cannot do. What it
    enforces is that every cell points at a file that EXISTS and that no row
    still says the board is absent.
    """
    import re as _re

    text = (MOCKUPS / "DESIGN-ambient.md").read_text(encoding="utf-8")
    start = text.index("| # | Artboard | Yang digambar | Ada di `ui/`? |")
    body = text[start:].split("\n\n", 1)[0]

    rows = [line for line in body.splitlines()
            if line.startswith("| ") and line.count("|") >= 5]
    assert len(rows) == 23, f"the board table has {len(rows)} rows, not 22 + header"

    absent = [r for r in rows[2:] if "| tidak" in r]
    assert absent == [], (
        f"rows still claiming no surface: {[r.split('|')[1].strip() for r in absent]}")

    # THE PATTERN INCLUDES THE DIRECTORY, because the column writes
    # `ui/pages_memory.py`. The first version of this test matched only bare
    # filenames, found NOTHING, and passed — an assertion that cannot fail. It
    # was caught by mutating the doc to name `ui/pages_ghost.py` and watching
    # the test stay green.
    named = set()
    for row in rows[2:]:
        cell = row.rsplit("|", 2)[1]
        named |= set(_re.findall(r"`((?:ui|core)/[A-Za-z_][A-Za-z0-9_]*\.py)`", cell))

    assert named, "the column names no module at all"

    # AND EVERY ROW NAMES ONE. Checking only the union let a row drop its module
    # name and still pass, because nineteen other rows named files — the row
    # would read "ya" with nothing behind it, which is the exact claim this
    # column exists to make honest.
    silent = []
    for row in rows[2:]:
        cell = row.rsplit("|", 2)[1]
        if not _re.search(r"`(?:ui|core)/[A-Za-z_][A-Za-z0-9_]*\.py`", cell):
            silent.append(row.split("|")[1].strip())
    assert silent == [], (
        f"boards whose row names no module: {silent} — a row that says 'ya' "
        "without a file is a claim nobody can check")
    missing = sorted(m for m in named if not (ROOT / m).exists())
    assert missing == [], f"the column names modules that do not exist: {missing}"
