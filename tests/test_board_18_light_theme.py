"""Board 18 — the light theme (izin): the tokens, checked for readability.

WHAT THIS VERIFIES
    Board 18 is the light palette. Its tokens have only been asserted by
    value so far — nobody has looked at the result. A light theme is only
    "seen" correctly when its text is READABLE against its surfaces and its
    accent is a real accent, not a dark-theme leftover. This test performs
    the part of the visual review that is deterministic: it computes the
    WCAG contrast ratio of every text/surface pair the light palette uses,
    and confirms the panel's stylesheet is built from the light tokens rather
    than a hardcoded dark set. The rendered pixels are a human step on a
    machine with a display; the contrast math is the substance that makes
    those pixels legible, and it belongs in the suite.

    Contrast is relative luminance per WCAG 2.1: L = 0.2126R + 0.7152G +
    0.0722B with sRGB linearisation, ratio = (L1+0.05)/(L2+0.05).
"""
from __future__ import annotations

import pytest

from ui.tray_pages import PALETTES


@pytest.fixture()
def indonesian():
    """The panel is drawn in Indonesian, pinned so assertions test the palette."""
    from core import i18n

    i18n.reload()
    i18n.set_locale("id")
    yield
    i18n.set_locale("en")


@pytest.fixture()
def panel_module(indonesian):
    """The panel against the Qt stub, with the real modules restored after."""
    from tests.qtstub import fresh_ui, restore_ui

    saved = fresh_ui()
    try:
        from ui import tray_panel, tray_pages, tray_panel_model

        yield tray_panel, tray_pages, tray_panel_model
    finally:
        restore_ui(saved)


# ── the light palette's readable pairs ──────────────────────────────────────

def _luminance(hex_colour: str) -> float:
    """Relative luminance of an #RRGGBB colour, per WCAG 2.1."""
    hex_colour = hex_colour.lstrip("#")
    rgb = [int(hex_colour[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]
    lin = []
    for c in rgb:
        lin.append(c / 12.92 if c <= 0.03928 else
                   ((c + 0.055) / 1.055) ** 2.4)
    return 0.2126 * lin[0] + 0.7152 * lin[1] + 0.0722 * lin[2]


def _contrast(fg: str, bg: str) -> float:
    """WCAG contrast ratio of fg text on bg surface."""
    l1, l2 = _luminance(fg), _luminance(bg)
    if l1 < l2:
        l1, l2 = l2, l1
    return (l1 + 0.05) / (l2 + 0.05)


# (text token, the surface it sits on, the WCAG minimum for normal text)
LIGHT_PAIRS = [
    ("text", "panel", 4.5),
    ("text", "card", 4.5),
    ("text", "base", 4.5),
    ("muted", "panel", 4.5),
    ("muted", "card", 4.5),
    ("on_accent", "accent", 4.5),
]


def test_the_light_palette_has_all_the_tokens_the_stylesheet_reads():
    """The stylesheet reads these keys; a missing one would KeyError at paint."""
    expected = {"base", "panel", "card", "line", "line_accent", "text",
                "muted", "accent", "amber", "on_accent"}
    assert set(PALETTES["light"]) == expected


def test_the_light_palette_is_actually_light():
    """A light theme's surfaces are light and its text is dark."""
    light = PALETTES["light"]
    # surfaces light (high luminance), text dark (low luminance)
    assert _luminance(light["panel"]) > 0.8
    assert _luminance(light["base"]) > 0.8
    assert _luminance(light["card"]) > 0.8
    assert _luminance(light["text"]) < 0.1


def test_light_text_meets_wcag_on_every_surface():
    """Every text/surface pair the light theme uses clears WCAG AA."""
    light = PALETTES["light"]
    for fg_key, bg_key, minimum in LIGHT_PAIRS:
        ratio = _contrast(light[fg_key], light[bg_key])
        assert ratio >= minimum, (
            f"{fg_key} on {bg_key} is {ratio:.2f}:1, WCAG wants {minimum}")


def test_the_light_accent_and_amber_are_distinct_from_the_dark_theme():
    """Board 17a is a real light accent, not a tinted dark one."""
    assert PALETTES["light"]["accent"] == "#0A7A93"
    assert PALETTES["dark"]["accent"] == "#4FD8F0"
    assert PALETTES["light"]["amber"] == "#9A5B00"
    # the accent must be readable on the card it highlights
    assert _contrast(PALETTES["light"]["accent"], PALETTES["light"]["card"]) >= 3.0


def test_light_surfaces_differ_from_dark_so_the_swap_is_visible():
    """The palette swap must change what is on screen — same widget, diff colour."""
    for key in ("panel", "card", "base", "text", "accent"):
        assert PALETTES["light"][key] != PALETTES["dark"][key], (
            f"{key} is identical in both themes; the swap would not be visible")


def test_the_light_stylesheet_is_built_from_the_light_tokens(panel_module):
    """`apply_style` writes the light tokens, not a hardcoded dark set."""
    tray_panel, _pages, _model = panel_module
    panel = tray_panel.TrayPanel({})
    panel.open()

    assert panel.set_theme("light") is True
    assert panel.theme == "light"
    window = panel._window
    assert "#FFFFFF" in window._style, "the light panel surface is missing"
    assert "#F6F9FB" not in window._style, (
        "the light base token leaked where the panel surface belongs")
    light = PALETTES["light"]
    assert light["accent"] in window._style, (
        "the light accent is not in the stylesheet")
    assert light["text"] in window._style, "the light text token is missing"


def test_the_light_high_contrast_pairs_also_clear_wcag():
    """The high-contrast palette, whatever theme it rides, stays legible."""
    high = PALETTES["high"]
    for fg_key, bg_key in (("text", "panel"), ("text", "card"),
                           ("text", "base"), ("muted", "panel")):
        ratio = _contrast(high[fg_key], high[bg_key])
        assert ratio >= 4.5, f"{fg_key} on {bg_key} is {ratio:.2f}:1"
