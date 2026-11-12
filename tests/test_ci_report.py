"""The reporter that turns a red job into a readable annotation.

WHY THIS IS TESTED
    The first version was a heredoc inside the workflow. It passed on Linux and
    macOS and failed on Windows, where `run:` is PowerShell — so the check that
    exists to explain a failure produced one, and explained nothing. Now it is a
    script, and a script can be run here with a junit file this test builds.
"""
from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import annotate_junit  # noqa: E402


def write_junit(tmp_path: Path, cases: list[tuple[str, str, str]]) -> Path:
    """A minimal junit.xml: (test name, 'pass'|'fail'|'error'|'skip', message)."""
    suite = ET.Element("testsuite", name="pytest")
    for name, kind, message in cases:
        case = ET.SubElement(suite, "testcase", classname="tests.test_x",
                             name=name, file="tests/test_x.py", line="7")
        if kind != "pass":
            tag = {"fail": "failure", "error": "error", "skip": "skipped"}[kind]
            ET.SubElement(case, tag, message=message).text = message
    path = tmp_path / "junit.xml"
    ET.ElementTree(suite).write(path, encoding="utf-8", xml_declaration=True)
    return path


def test_a_passing_suite_produces_nothing(tmp_path):
    assert annotate_junit.annotations(write_junit(tmp_path, [("a", "pass", "")])) == []


def test_a_failure_names_the_test_file_and_line(tmp_path):
    path = write_junit(tmp_path, [("test_widget", "fail", "AssertionError: nope")])
    (line,) = annotate_junit.annotations(path)
    assert line.startswith("::error file=tests/test_x.py,line=7,")
    assert "tests.test_x.test_widget" in line
    assert line.endswith("AssertionError: nope")


def test_only_the_first_line_of_a_message_is_used(tmp_path):
    """A traceback in an annotation is unreadable; the log has the rest."""
    path = write_junit(tmp_path, [("t", "fail", "first line\nframe 2\nframe 3")])
    assert annotate_junit.annotations(path)[0].endswith("first line")


def test_a_percent_in_a_message_is_escaped(tmp_path):
    """Unescaped, GitHub reads `%` as the start of a command escape and the
    annotation renders as something else entirely — including a message that
    contains a workflow command."""
    path = write_junit(tmp_path, [("t", "fail", "50% of the time")])
    assert "50%25 of the time" in annotate_junit.annotations(path)[0]


def test_newlines_are_escaped_rather_than_printed():
    """A newline inside an annotation truncates it at that point: GitHub reads
    one command per line."""
    assert annotate_junit._escape("a\r\nb") == "a%0D%0Ab"
    # % first, or the escapes above would themselves be escaped again.
    assert annotate_junit._escape("%0A") == "%250A"


def test_an_error_counts_too(tmp_path):
    """A fixture that raises is not a 'failure' element; it is an 'error' one,
    and it is the more common shape in this repository (no Qt, no display)."""
    path = write_junit(tmp_path, [("t", "error", "ImportError: Qt")])
    assert len(annotate_junit.annotations(path)) == 1


def test_a_silent_skip_is_not_an_annotation(tmp_path):
    assert annotate_junit.annotations(write_junit(tmp_path, [("t", "skip", "")])) == []


def test_a_single_testsuite_root_is_handled_too(tmp_path):
    """`--junitxml` writes <testsuites> when pytest is involved, but a single
    suite at the root is legal XML and must not be silently ignored."""
    root = ET.Element("testsuite")
    case = ET.SubElement(root, "testcase", classname="c", name="n")
    ET.SubElement(case, "failure", message="boom")
    path = tmp_path / "one.xml"
    ET.ElementTree(root).write(path, encoding="utf-8")
    assert len(annotate_junit.annotations(path)) == 1


def test_a_missing_file_warns_instead_of_failing_the_job(tmp_path, capsys):
    """The step runs with `if: always()`. Turning a missing report into a second
    failure hides the first one."""
    assert annotate_junit.main(["prog", str(tmp_path / "nope.xml")]) == 0
    assert "no nope.xml" in capsys.readouterr().out


def test_broken_xml_warns_instead_of_raising(tmp_path, capsys):
    path = tmp_path / "junit.xml"
    path.write_text("<testsuite", encoding="utf-8")
    assert annotate_junit.main(["prog", str(path)]) == 0
    assert "not valid XML" in capsys.readouterr().out


def test_the_annotation_count_is_capped(tmp_path, capsys):
    """39,000 lines of legacy means a bad refactor can fail 200 tests at once;
    200 annotations on one PR is noise, and the runner caps them anyway."""
    cases = [(f"t{i}", "fail", "boom") for i in range(annotate_junit.MAX_ANNOTATIONS + 5)]
    assert annotate_junit.main(["prog", str(write_junit(tmp_path, cases))]) == 0
    out = capsys.readouterr().out
    assert out.count("::error") == annotate_junit.MAX_ANNOTATIONS
    assert "stopped at" in out


@pytest.mark.parametrize("name", ["test_a", "test_b"])
def test_every_case_is_visited(tmp_path, name):
    (line,) = annotate_junit.annotations(write_junit(tmp_path, [(name, "fail", "x")]))
    assert name in line
