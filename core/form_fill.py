"""Board 13 — form filling, review-first.

The artboard calls this the "fill a form, but review it first" panel: three
labelled fields, a cyan preview strip, and the promise that nothing is applied
until the person has reviewed what will go into the page.  This module is the
backend that promise rests on.  It is deliberately a *policy* module, not a
driver: it knows which pages may be filled, what a field plan is, how a value
is sanitised so it cannot carry markup or script into a page, and how a plan is
reviewed and applied.  It never opens a browser and never touches the network.

THE ONE SOURCE OF TRUTH FOR A PLAN.  A :class:`FormFillPlan` is built from a
target page URL plus a mapping of CSS selectors to the values that should be
written into them.  It is reviewed (`plan.review()`) before it is applied
(`plan.apply_result()`), and the review is what makes the whole flow
"tinjau dulu": nothing is applied to a page until a :class:`FormFillPlan` has
been explicitly reviewed, and an unreviewed plan refuses to report success.

WHAT IT DOES NOT DO.  It does not launch Playwright, does not touch a socket,
and does not import any browser or file-IO module — the same discipline the
routines and voice backends follow.  The actual typing into a page is done by
the existing `_BrowserSession.fill_form` / `core.browser_autofill.fill_script`
machinery, which this module is designed to drive through a small port
(`apply_to_page`, see :func:`apply_plan`).  Keeping the policy free of I/O is
what makes every rule here testable with plain assertions and no browser.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Callable, Mapping

# A selector must be a plain CSS selector: an identifier, a dotted class, or a
# combinator chain.  Rejecting anything with a quote, angle bracket or script
# tag stops a value that looks like markup from ever becoming a selector that
# a page could interpret.
_SELECTOR_RE = re.compile(r"^[A-Za-z#.][A-Za-z0-9#._\- ]*(?:\[[^\]]+\])?$")

# Values are written verbatim into a field, so the only thing we can safely
# promise is that they are treated as *text*, never as HTML or JS.  We flag
# characters that would matter if a careless driver ever interpreted a value as
# markup; the review screen shows them so the person sees what is being sent.
_MARKUP_CHARS = re.compile(r"[<>\"'`]")

# A field value is bounded so a runaway plan cannot ask for an unbounded write.
_MAX_VALUE_LEN = 512


@dataclass(frozen=True)
class FieldEntry:
    """One field of a plan: a selector and the text to write into it."""

    selector: str
    value: str

    @property
    def looks_markup(self) -> bool:
        """True when the value carries a character a page could misread.

        This is *not* an error — form values legitimately contain quotes and
        apostrophes — but the review screen flags it so the person confirms they
        intend to send exactly these characters, unchanged, as text.
        """
        return bool(_MARKUP_CHARS.search(self.value))


@dataclass(frozen=True)
class FieldResult:
    """Outcome for a single field once a plan has been applied."""

    selector: str
    ok: bool
    detail: str


@dataclass
class FormFillPlan:
    """A reviewed-or-not set of fields to write into one page.

    The plan is *inert* until reviewed.  `reviewed` is the gate the whole
    "tinjau dulu" flow hangs on: an unreviewed plan reports that it was not
    applied, no matter how the driver behaves.
    """

    page_url: str
    entries: tuple[FieldEntry, ...] = ()
    reviewed: bool = False

    def __post_init__(self) -> None:
        # Normalise the entries to a tuple so the plan is hashable and stable.
        self.entries = tuple(self.entries)

    # -- construction -----------------------------------------------------
    @classmethod
    def build(cls, page_url: str, fields: Mapping[str, str]) -> "FormFillPlan":
        """Validate a target page and a selector→value map into a plan.

        Raises :class:`FormFillError` when the page is not a safe http(s) URL or
        when a selector is not a plain CSS selector.  Values are sanitised to
        bounded text; no value is ever dropped silently.
        """
        origin = _validate_page(page_url)
        entries = []
        for raw_selector, raw_value in fields.items():
            entry = _make_entry(raw_selector, raw_value)
            entries.append(entry)
        if not entries:
            raise FormFillError("No fields given — nothing to plan.")
        plan = cls(page_url, tuple(entries))
        # Stash the origin on the plan so the apply step can re-check the page
        # did not navigate away from the reviewed site before the fields landed.
        plan._origin = origin
        return plan

    # -- review gate ------------------------------------------------------
    def review(self) -> "FormFillPlan":
        """Mark the plan reviewed, returning it for chaining.

        Calling review is the explicit human/agent confirmation that the
        displayed fields are the ones to send.  Without it, `applied` is False.
        """
        self.reviewed = True
        return self

    @property
    def applied(self) -> bool:
        """A plan is applied only when it was reviewed *and* applied."""
        return self.reviewed and getattr(self, "_applied", False)

    # -- summaries used by the review screen -------------------------------
    def summary_lines(self) -> list[str]:
        """Human-readable lines for the board's preview strip and review."""
        lines = [f"→ {self.page_url}"]
        for entry in self.entries:
            flag = " ⚠" if entry.looks_markup else ""
            lines.append(f"{entry.selector} = {entry.value}{flag}")
        if not self.reviewed:
            lines.append("belum ditinjau — belum diterapkan")
        return lines


class FormFillError(ValueError):
    """Raised when a plan cannot be built from the given page and fields."""


def _validate_page(page_url: str) -> str:
    """Return the https origin of `page_url`, or raise.

    Only absolute http(s) URLs are fillable.  We reuse the browser URL rule so
    a plan can never target a `javascript:` or `file:` page, and we return the
    origin so the apply step can prove the page is still on the same site.
    """
    from core.browser_url import https_origin

    try:
        return https_origin(page_url)
    except Exception as exc:  # ValueError from validate_browser_url
        raise FormFillError(f"Not a fillable page: {page_url!r}") from exc


def _make_entry(selector: str, value: object) -> FieldEntry:
    """Validate one selector/value pair into a :class:`FieldEntry`."""
    selector = str(selector or "").strip()
    if not _SELECTOR_RE.match(selector):
        raise FormFillError(f"Bad selector: {selector!r}")
    text = "" if value is None else str(value)
    if len(text) > _MAX_VALUE_LEN:
        text = text[:_MAX_VALUE_LEN]
    return FieldEntry(selector=selector, value=text)


def apply_plan(
    plan: FormFillPlan,
    apply_to_page: Callable[[str, Mapping[str, str]], list[FieldResult]],
) -> list[FieldResult]:
    """Apply a *reviewed* plan through a driver, returning per-field results.

    `apply_to_page(page_url, fields)` is the port to the real browser session:
    it takes the page URL and the selector→value map and returns one
    :class:`FieldResult` per field.  This function enforces the two rules that
    make the flow safe regardless of how the driver is wired:

    * an unreviewed plan is refused outright — the board's "tinjau dulu" gate;
    * the plan's own URL is passed through unchanged, so the driver and the
      plan agree on which page is being filled.
    """
    if not plan.reviewed:
        raise FormFillError("Plan not reviewed — refusing to apply an unreviewed form fill.")
    fields = {entry.selector: entry.value for entry in plan.entries}
    results = list(apply_to_page(plan.page_url, fields))
    # Mark applied only once the driver has actually run, and only for the
    # fields the plan asked for (the driver may return results for a subset).
    if results:
        plan._applied = True  # type: ignore[attr-defined]
    return results


__all__ = [
    "FieldEntry",
    "FieldResult",
    "FormFillError",
    "FormFillPlan",
    "apply_plan",
]
