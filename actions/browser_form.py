"""Legacy form adapter retained for compatibility, with writes disabled.

The former session path did not verify the destination, bypassed the current
browser policy, and offered no real review. Parsing remains useful to callers;
no adapter call may write until a safe reviewed integration exists.
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
    """Fail closed: the legacy adapter cannot verify the active page or consent."""
    return [FieldResult(selector, False, "form filling is unavailable") for selector in fields]


__all__ = ["fill_form_to_page", "parse_fill_results"]
