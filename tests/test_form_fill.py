"""Tests for the board 13 form-filling policy (no browser or network).

`core/form_fill.FormFillPlan` is a pure policy module: it validates a target
page, builds a selector→value plan with value sanitisation, enforces the
"review before apply" gate, and refuses to apply an unreviewed plan.  These
tests drive it with a fake `apply_to_page` driver so no browser is needed.
"""
import pytest

from core.form_fill import (
    FieldEntry,
    FieldResult,
    FormFillError,
    FormFillPlan,
    apply_plan,
)


def _driver(results_per_field=2):
    """A fake driver: records the call, returns one ok result per field."""
    calls = []

    def _apply(page_url, fields):
        calls.append((page_url, dict(fields)))
        return [FieldResult(sel, True, "ok") for sel in fields] if results_per_field else []

    return _apply, calls


# -- construction & validation --------------------------------------------
def test_build_makes_a_plan_from_a_good_page_and_fields():
    plan = FormFillPlan.build("https://example.com/pay", {"#name": "Alice", "#amt": "100"})
    assert len(plan.entries) == 2
    assert plan.entries[0] == FieldEntry("#name", "Alice")
    assert plan.reviewed is False


def test_build_rejects_a_non_http_page():
    with pytest.raises(FormFillError):
        FormFillPlan.build("javascript:alert(1)", {"#x": "1"})


def test_build_rejects_a_file_url():
    with pytest.raises(FormFillError):
        FormFillPlan.build("file:///etc/passwd", {"#x": "1"})


def test_build_rejects_a_bad_selector():
    with pytest.raises(FormFillError):
        FormFillPlan.build("https://example.com", {"script>": "x"})


def test_build_rejects_empty_fields():
    with pytest.raises(FormFillError):
        FormFillPlan.build("https://example.com", {})


def test_build_sanitises_long_values_to_a_bound():
    plan = FormFillPlan.build("https://example.com", {"#x": "x" * 900})
    assert len(plan.entries[0].value) == 512


def test_build_treats_none_value_as_empty_text():
    plan = FormFillPlan.build("https://example.com", {"#x": None})
    assert plan.entries[0].value == ""


# -- review gate ----------------------------------------------------------
def test_unreviewed_plan_refuses_to_apply():
    plan = FormFillPlan.build("https://example.com", {"#x": "1"})
    driver, _ = _driver()
    with pytest.raises(FormFillError):
        apply_plan(plan, driver)


def test_reviewed_plan_applies_through_the_driver():
    plan = FormFillPlan.build("https://example.com/pay", {"#name": "Alice"})
    plan.review()
    driver, calls = _driver()
    results = apply_plan(plan, driver)
    assert results[0].ok is True
    assert calls[0][0] == "https://example.com/pay"
    assert calls[0][1] == {"#name": "Alice"}


def test_review_returns_the_plan_for_chaining():
    plan = FormFillPlan.build("https://example.com", {"#x": "1"})
    assert plan.review() is plan
    assert plan.reviewed is True


def test_applied_is_false_until_the_driver_runs():
    plan = FormFillPlan.build("https://example.com", {"#x": "1"})
    plan.review()
    assert plan.applied is False
    apply_plan(plan, _driver()[0])
    assert plan.applied is True


# -- summaries ------------------------------------------------------------
def test_summary_lines_list_url_and_each_field():
    plan = FormFillPlan.build("https://example.com/pay", {"#name": "Alice", "#amt": "100"})
    lines = plan.summary_lines()
    assert lines[0] == "→ https://example.com/pay"
    assert "#name = Alice" in lines
    assert "#amt = 100" in lines
    assert "belum ditinjau" in lines[-1]


def test_markup_values_are_flagged_in_the_review():
    plan = FormFillPlan.build("https://example.com", {"#x": "<b>x</b>"})
    lines = plan.summary_lines()
    assert "#x = <b>x</b> ⚠" in lines
    assert plan.entries[0].looks_markup is True


def test_plain_values_are_not_flagged():
    plan = FormFillPlan.build("https://example.com", {"#x": "plain text"})
    assert plan.entries[0].looks_markup is False


def test_reviewed_summary_drops_the_unreviewed_note():
    plan = FormFillPlan.build("https://example.com", {"#x": "1"})
    plan.review()
    assert not any("belum ditinjau" in line for line in plan.summary_lines())


# -- driver result handling ---------------------------------------------
def test_driver_failure_still_marks_applied_when_it_returns_results():
    plan = FormFillPlan.build("https://example.com", {"#x": "1"})
    plan.review()
    results = apply_plan(plan, lambda u, f: [FieldResult("#x", False, "not found")])
    assert results[0].ok is False
    assert plan.applied is True


def test_driver_returning_nothing_does_not_mark_applied():
    plan = FormFillPlan.build("https://example.com", {"#x": "1"})
    plan.review()
    apply_plan(plan, lambda u, f: [])
    assert plan.applied is False
