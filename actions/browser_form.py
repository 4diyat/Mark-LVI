"""Board 13 adapter — drive a reviewed form-fill plan into the browser session.

`core.form_fill.FormFillPlan` is the policy: it validates the page, builds the
field plan, and enforces "review before apply".  This module is the I/O edge
that turns an *approved* plan into real typing inside the existing
`actions.browser_control._BrowserSession`, which already owns Playwright and
the per-browser event loop.

WHY THE SPLIT.  The policy is pure and fully tested with a fake driver.  The
browser is the one thing that cannot be tested without a real page, so the
only logic worth unit-testing here is `parse_fill_results` — a pure function
that turns the session's textual report back into `FieldResult`s.  The I/O
function, `fill_form_to_page`, is deliberately thin: it asks the session to
fill, and hands the report to the parser.
"""
from __future__ import annotations

import re

from core.form_fill import FieldResult

# The session's `fill_form` reports one line per field:
#   "✓ #name"        when the write succeeded
#   "✗ #amt: <err>"  when it failed
# Leading markers are stable; the detail after a failure is whatever Playwright
# raised, so we parse tolerantly.
_OK_RE = re.compile(r"^\s*✓\s*(.+?)\s*$")
_FAIL_RE = re.compile(r"^\s*✗\s*(.+?)\s*:\s*(.*)$")


def parse_fill_results(report: str, selectors: list[str]) -> list[FieldResult]:
    """Turn a session's fill report into per-field results, in selector order.

    The report may list fields in any order, omit some, or add none; every
    selector the caller asked for gets exactly one result, so the plan's fields
    and the returned results stay aligned.  A field missing from the report is
    reported as failed with a clear detail rather than silently dropped.
    """
    by_selector: dict[str, FieldResult] = {}
    for line in report.splitlines():
        ok_match = _OK_RE.match(line)
        if ok_match:
            selector = ok_match.group(1).strip()
            by_selector[selector] = FieldResult(selector, True, "ok")
            continue
        fail_match = _FAIL_RE.match(line)
        if fail_match:
            selector = fail_match.group(1).strip()
            detail = fail_match.group(2).strip()
            by_selector[selector] = FieldResult(selector, False, detail or "failed")
    return [by_selector.get(s, FieldResult(s, False, "not reported")) for s in selectors]


def fill_form_to_page(page_url: str, fields: dict[str, str]) -> list[FieldResult]:
    """Fill `fields` into the active browser session for `page_url`.

    Returns one `FieldResult` per requested selector.  If no browser session
    exists, every field is reported as failed with a single clear reason — the
    board says "open a browser first" rather than pretending a fill happened.
    """
    from actions.browser_control import _registry

    selectors = list(fields)
    if not _registry.has():
        return [FieldResult(s, False, "no browser session") for s in selectors]
    session = _registry.get()
    try:
        report = session.run(session.fill_form(fields), timeout=60)
    except Exception as exc:                          # noqa: BLE001
        return [FieldResult(s, False, f"fill failed: {exc}") for s in selectors]
    return parse_fill_results(str(report), selectors)


__all__ = ["fill_form_to_page", "parse_fill_results"]
