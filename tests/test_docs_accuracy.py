"""The two numbers a reader trusts, checked against the repository itself.

WHY
    `readme.md` said "1,254 tests" while 1,669 were collected. Nobody wrote a
    lie: the suite grew and the sentence stayed. That is the same failure this
    project keeps designing against — a surface that states a fact it stopped
    reading years ago — and the fix is not "remember to update it", it is to
    read it.

    The check is deliberately a RANGE, not equality. The point is that the
    claim is not absurd — a stale number is caught, and nobody has to bump a
    digit on every new test. Whether CI actually ran is a different question,
    answered by CI.

WHAT IS NOT CHECKED
    The speed of the suite, the pass rate, or anything that depends on the
    machine. Only what is knowable by reading files.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _collected_test_functions() -> int:
    """How many test functions exist, counted without running them.

    Not pytest's collected count: that one skips files whose imports fail, and
    a documentation check must not depend on what this machine can import.
    """
    total = 0
    for path in (ROOT / "tests").glob("test_*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        total += sum(
            1 for node in ast.walk(tree)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name.startswith("test_")
        )
    return total


def test_the_readme_test_count_is_not_stale():
    text = (ROOT / "readme.md").read_text(encoding="utf-8")
    match = re.search(r"#\s*([\d,]+)\s+tests", text)
    assert match, "the Quick Start block no longer states a test count at all"
    claimed = int(match.group(1).replace(",", ""))

    functions = _collected_test_functions()
    # The README states what pytest COLLECTS, which is the function count plus
    # one case per parametrised parameter — always at least the functions, and
    # never wildly more (if it were, the claim would be about something else).
    assert claimed >= functions, (
        f"readme claims {claimed} tests but {functions} test functions exist")
    assert claimed <= functions * 2, (
        f"readme claims {claimed} tests for {functions} functions — stale or "
        f"counting something other than this suite")


def test_the_verification_doc_covers_every_os_surface_we_ship():
    """Every claim the README makes about the operating system needs a line in
    the manual checklist. Those features fail in ways no assertion can see —
    a taskbar group, a registry association, a login entry — so the document
    is the only place the gap can be admitted."""
    text = (ROOT / "docs" / "verification.md").read_text(encoding="utf-8")
    for surface in ("jarvis://", "taskbar", "Auto-start", "StartupWMClass"):
        assert surface.lower() in text.lower(), (
            f"{surface} ships but the manual checklist does not mention it")


def test_the_matrix_has_a_row_for_os_integration():
    text = (ROOT / "docs" / "verification.md").read_text(encoding="utf-8")
    rows = [line for line in text.splitlines() if line.startswith("| Integrasi OS")]
    assert rows, "no matrix row for the OS integration work"
    # The row must say what is NOT covered, not just what is.
    assert "belum" in rows[0].lower() or "diuji lewat shell palsu" in rows[0].lower()


def test_every_documented_test_count_lives_in_one_place():
    """Two documents stating the count is how they start disagreeing. If this
    fails, the count was copied into a second file: point it at the README."""
    claims = []
    for path in (ROOT / "readme.md", *(ROOT / "docs").glob("*.md")):
        for line_no, line in enumerate(
                path.read_text(encoding="utf-8").splitlines(), start=1):
            if re.search(r"\b[\d,]{4,}\s+tests\b", line):
                claims.append(f"{path.name}:{line_no}")
    assert len(claims) == 1, f"test counts stated in several places: {claims}"


def test_the_documented_count_is_reachable_by_running_the_suite():
    """A number a reader cannot reproduce is a number they must trust. The
    README's count has to be at least as large as the functions that exist,
    because parametrised cases only ever add."""
    claimed = int(re.search(
        r"#\s*([\d,]+)\s+tests",
        (ROOT / "readme.md").read_text(encoding="utf-8")).group(1).replace(",", ""))
    assert claimed >= _collected_test_functions()


@pytest.mark.parametrize("path", ["readme.md", "docs/verification.md"])
def test_the_documents_are_valid_utf8_and_keep_their_headings(path):
    """Both files are read by humans and now by tests. A file that became
    unreadable would take the accuracy checks above down with it."""
    text = (ROOT / path).read_text(encoding="utf-8")
    assert text.startswith("#") or text.startswith("\ufeff#")
    assert "\ufffd" not in text
