"""The design tokens are the design, so they get the strictest test in the suite.

WHY THIS FILE IS SO LITERAL
    `docs/design/01-tokens.md` argues that the previous three rounds failed
    because the numbers had no rule behind them. A token module that anyone can
    silently edit is that same failure with a new address. So every value is
    pinned here with its provenance, and the derivations are RECOMPUTED rather
    than restated: a test that asserts `CARD_H_2LINE == 64` proves the constant
    has not changed, while `CARD_H_2LINE == S4 + CARD_TITLE + S1 + META + S4`
    proves the arithmetic still produces 64 from its parts.

    Both matter. The first catches "someone changed a token"; the second catches
    "someone changed a token and the doc still claims the old sum".

WHAT IS DELIBERATELY NOT TESTED
    Taste. Six text roles and eight spacing steps are a decision, and a test
    cannot say whether 16 px is the right card title. It can only say that the
    number is 16 everywhere and that no page invented a 17th.
"""
from __future__ import annotations

import re
import ast
from pathlib import Path

import pytest

from ui import tokens

ROOT = Path(__file__).resolve().parent.parent


# ── the scale itself ────────────────────────────────────────────────────────

def test_there_are_exactly_six_text_roles_in_five_sizes():
    """Fifteen sizes was the problem. This is the count that fixes it.

    SIX ROLES, FIVE SIZES, and the gap is deliberate: the wordmark is 13 px,
    which is also BODY. They are separate ROLES because they carry different
    weight and tracking — the brand line at 700/1.4, body copy at 400/0 — not
    because they need different sizes. A test that demanded six distinct
    numbers would have forced the wordmark to 12 or 14 for no reason, which is
    how the old 15-size scale happened in the first place.
    """
    sizes = {tokens.LABEL, tokens.META, tokens.BODY,
             tokens.CARD_TITLE, tokens.DISPLAY, tokens.WORDMARK}
    assert len(sizes) == 5, f"expected five distinct sizes, got {sorted(sizes)}"
    assert tokens.WORDMARK == tokens.BODY, "the shared size is the wordmark/BODY pair"


def test_every_text_role_is_ordered_as_its_name_says():
    """LABEL < META < BODY < CARD_TITLE < DISPLAY.

    A scale whose steps are out of order is how the old 15 sizes happened: each
    was chosen on its own. WORDMARK is the exception and is asserted separately,
    because it is the panel's brand at 13 px and not part of the reading scale.
    """
    assert tokens.LABEL < tokens.META < tokens.BODY < tokens.CARD_TITLE < tokens.DISPLAY
    assert tokens.WORDMARK == tokens.BODY, (
        "the wordmark is 13 px by the artboard's own drawing (panel_head); if "
        "that changes it is a decision, not an accident")


def test_nothing_readable_is_below_eleven():
    """Principle 4: 11 px is the floor, and only for the section marker.

    The artboard used 9.5 and 10 px for the same marker and for real sentences.
    At 1366x768 with Windows scaling at 125% that is ~7.5 effective pixels.
    """
    readable = {tokens.LABEL, tokens.META, tokens.BODY,
                tokens.CARD_TITLE, tokens.DISPLAY, tokens.WORDMARK}
    assert min(readable) >= 11


def test_spacing_is_a_four_pixel_scale_with_nothing_between():
    steps = [tokens.S1, tokens.S2, tokens.S3, tokens.S4,
             tokens.S5, tokens.S6, tokens.S7, tokens.S8]
    assert steps == sorted(steps) and len(set(steps)) == 8
    for step in steps:
        assert step % 4 == 0, f"{step} is not a multiple of 4"


# ── the derivations, recomputed ─────────────────────────────────────────────

def test_content_width_is_the_panel_minus_both_edges():
    assert tokens.CONTENT_W == tokens.PANEL_W - 2 * tokens.S5 == 412


def test_card_content_starts_where_the_artboard_starts_its_text():
    """44 = 24 edge + 20 padding. MEASURED: 50 call sites at x=44."""
    assert tokens.S5 + tokens.CARD_PAD == 44


def test_the_two_card_heights_are_sums_of_their_parts():
    """The artboard drew ten card heights; these two sums collapse them."""
    assert tokens.CARD_H_2LINE == (
        tokens.S4 + tokens.CARD_TITLE + tokens.S1 + tokens.META + tokens.S4) == 64
    assert tokens.CARD_H_3LINE == (
        tokens.S4 + tokens.CARD_TITLE + tokens.S1 + tokens.META
        + tokens.S1 + tokens.BODY + tokens.S4) == 81


def test_the_list_pitch_is_the_card_plus_the_gap():
    assert tokens.LIST_PITCH == tokens.CARD_H_2LINE + tokens.S3 == 76


def test_the_content_area_is_the_panel_minus_head_and_actions():
    assert tokens.CONTENT_H == tokens.PANEL_H - tokens.HEAD_H - tokens.ACTION_H == 500


def test_the_visible_row_count_follows_from_the_area_and_the_pitch():
    """Six, not eight, and that is a stated cost — see 01-tokens.md.

    This test is the arithmetic. The DOCUMENT is where the consequence is
    argued; if someone changes S3 to fit more rows, this fails and points at
    the doc that has to change with it.
    """
    assert tokens.ROWS_VISIBLE == tokens.CONTENT_H // tokens.LIST_PITCH == 6


def test_the_head_is_tall_enough_for_its_own_two_lines():
    """DERIVED: subtitle line box ends at 69; first label needs ~80; head is 88."""
    line = round(tokens.LINE_FACTOR * 10.5)
    subtitle_bottom = tokens.HEAD_SUBTITLE_BASELINE + line
    assert subtitle_bottom == 69
    assert tokens.HEAD_H > subtitle_bottom, "the head ends before its own subtitle"


def test_a_toggle_is_the_size_the_artboard_draws():
    assert (tokens.TOGGLE_W, tokens.TOGGLE_H) == (40, 22)
    assert tokens.TOGGLE_KNOB_INSET < tokens.TOGGLE_H / 2


# ── the palette did not change ──────────────────────────────────────────────

PALETTE_CASES = [
    ("TEXT", "#E6F4F8", "#081520", 4.5),
    ("MUTED", "#8FA9B5", "#081520", 4.5),
    ("CYAN", "#4FD8F0", "#081520", 4.5),
    ("AMBER", "#F5A524", "#081520", 4.5),
    ("LTEXT", "#0B1A24", "#FFFFFF", 4.5),
    ("LMUTED", "#5B7480", "#FFFFFF", 4.5),
    ("LACC", "#0A7A93", "#FFFFFF", 4.5),
]


def _luminance(hex_colour: str) -> float:
    r, g, b = (int(hex_colour.lstrip("#")[i:i + 2], 16) / 255 for i in (0, 2, 4))
    def channel(c: float) -> float:
        return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
    return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)


def _contrast(a: str, b: str) -> float:
    la, lb = _luminance(a), _luminance(b)
    hi, lo = max(la, lb), min(la, lb)
    return (hi + 0.05) / (lo + 0.05)


@pytest.mark.parametrize("name,ink,bg,floor", PALETTE_CASES)
def test_every_text_colour_clears_four_point_five_to_one(name, ink, bg, floor):
    """`01-tokens.md` measured these; this is the measurement, not a quote of it.

    The reason the light palette's cards are always pure white: LMUTED on white
    is 4.94 and on the light BASE (#F6F9FB) it would fall under 4.5. A test is
    the only thing that stops a later "nicer" grey from breaking that.
    """
    assert _contrast(ink, bg) >= floor, f"{name} on {bg} is too faint"


def test_the_light_palette_has_almost_no_headroom_and_that_is_the_point():
    """LMUTED is 4.94 on white and 4.67 on the light BASE — both pass, barely.

    THE FIRST VERSION OF THIS TEST CLAIMED OTHERWISE. It asserted that LMUTED
    on the light BASE fell under 4.5, which would have justified the rule "light
    cards are always pure white". Measured, it is 4.67: it passes. So the rule
    in `01-tokens.md` was rewritten to say what is actually true — the light
    palette has about 0.4 of headroom, so nothing in it may be lightened — and
    this test now pins the real numbers instead of a convenient story.

    A test that encodes a false premise is worse than no test: it makes the
    premise look verified.
    """
    on_white = _contrast("#5B7480", "#FFFFFF")
    on_base = _contrast("#5B7480", "#F6F9FB")
    assert on_white >= 4.5 and on_base >= 4.5, "the light palette regressed"
    assert on_base < 5.0, (
        "LMUTED on the light base now clears 5.0 — the 'no headroom' warning in "
        "01-tokens.md is stale and can be relaxed")
    assert on_base < on_white, "a card lighter than white? impossible"


# ── the pages cannot invent numbers ────────────────────────────────────────

# Calls whose first argument is a pixel size for TEXT. `setGeometry` is not here
# yet: the migrated page uses it for layout, and removing it entirely is
# `03-adopt.md` step 5, not this one.
TEXT_SIZE_CALLS = ("setPixelSize", "setPointSize")


def _page_modules() -> list[Path]:
    return sorted(ROOT.glob("ui/pages_*.py"))


def test_there_are_page_modules_to_check():
    """A test that walks an empty list passes for the wrong reason."""
    assert len(_page_modules()) >= 5


@pytest.mark.parametrize("call", TEXT_SIZE_CALLS)
def test_no_page_sets_a_text_size_from_a_literal(call):
    """The rule with teeth: `setPixelSize(13)` in a page is a bug.

    This is what makes the token module more than documentation. A page may
    compute a size from `tokens.*` — that is the point — but a literal is how
    the 15-size problem grew back last time.
    """
    offenders = []
    for path in _page_modules():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = getattr(node.func, "attr", None) or getattr(node.func, "id", None)
            if name != call or not node.args:
                continue
            arg = node.args[0]
            if isinstance(arg, ast.Constant) and isinstance(arg.value, (int, float)):
                offenders.append(f"{path.name}:{node.lineno} {call}({arg.value})")
    assert offenders == [], (
        "a page chose its own text size; use ui.tokens instead: "
        + "; ".join(offenders))


def test_the_token_module_itself_has_no_float_sizes_masquerading_as_roles():
    """Sizes are integers. A 12.5 in here would be the old habit returning."""
    for name in ("LABEL", "META", "BODY", "CARD_TITLE", "DISPLAY", "WORDMARK"):
        value = getattr(tokens, name)
        assert isinstance(value, int), f"{name} is {value!r}, not an int"


# ── the docs and the code agree ────────────────────────────────────────────

def test_the_tokens_doc_lists_the_same_numbers_as_the_module():
    """A doc that drifts from the code is worse than no doc.

    Reads the six role sizes out of `01-tokens.md`'s table and compares. It is a
    narrow parse on purpose: it checks the numbers, not the prose, because the
    prose is for people and the numbers are what pages consume.
    """
    text = (ROOT / "docs" / "design" / "01-tokens.md").read_text(encoding="utf-8")
    documented = {int(m) for m in re.findall(r"\|\s*`(?:LABEL|META|BODY|CARD_TITLE|DISPLAY|WORDMARK)`\s*\|[^|]*\*\*(\d+) px\*\*", text)}
    implemented = {tokens.LABEL, tokens.META, tokens.BODY,
                   tokens.CARD_TITLE, tokens.DISPLAY, tokens.WORDMARK}
    assert documented == implemented, (
        f"doc says {sorted(documented)}, code says {sorted(implemented)}")
