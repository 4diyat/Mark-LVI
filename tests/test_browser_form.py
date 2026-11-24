"""Tests for the board 13 form-fill adapter.

`parse_fill_results` is pure and fully tested here.  `fill_form_to_page` is
the I/O edge; its only testable branch without a real browser is the
"no session" path, which we drive by monkeypatching the registry.
"""
from actions.browser_form import fill_form_to_page, parse_fill_results
from core.form_fill import FieldResult


# -- parse_fill_results (pure) -------------------------------------------
def test_parse_reports_success_lines():
    results = parse_fill_results("Form filled:\n✓ #name\n✓ #amt", ["#name", "#amt"])
    assert results == [FieldResult("#name", True, "ok"), FieldResult("#amt", True, "ok")]


def test_parse_reports_failure_lines_with_detail():
    report = "Form filled:\n✓ #name\n✗ #amt: locator not found"
    results = parse_fill_results(report, ["#name", "#amt"])
    assert results[0].ok is True
    assert results[1] == FieldResult("#amt", False, "locator not found")


def test_parse_keeps_caller_selector_order():
    report = "Form filled:\n✓ #amt\n✓ #name"
    results = parse_fill_results(report, ["#name", "#amt"])
    assert [r.selector for r in results] == ["#name", "#amt"]


def test_parse_missing_selector_is_failed_not_dropped():
    results = parse_fill_results("Form filled:\n✓ #name", ["#name", "#amt"])
    assert results[1] == FieldResult("#amt", False, "not reported")


def test_parse_empty_report_marks_all_failed():
    results = parse_fill_results("", ["#a", "#b"])
    assert [r.ok for r in results] == [False, False]


def test_parse_tolerates_unmarked_lines():
    results = parse_fill_results("Form filled:\n#name\n✓ #amt", ["#name", "#amt"])
    assert results[0] == FieldResult("#name", False, "not reported")
    assert results[1].ok is True


# -- fill_form_to_page (I/O edge, no browser) ----------------------------
def test_fill_form_without_a_session_reports_every_field_failed(monkeypatch):
    from actions.browser_control import _registry

    monkeypatch.setattr(_registry, "has", lambda browser_name=None: False)
    results = fill_form_to_page("https://example.com", {"#name": "A"})
    assert results == [FieldResult("#name", False, "no browser session")]
