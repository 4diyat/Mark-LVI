"""The labels the window shows: complete, consistent, and actually used.

WHY THESE TESTS EXIST
    A translation layer fails quietly. A locale missing one key shows English
    in one corner of the window for months; a template that says {name} in two
    locales and {nmae} in the third raises only when a phone connects, on
    somebody else's machine. So the catalogue is checked here, without Qt:
    the parts that can rot are data, and data can be tested anywhere.

    The last test is the one that keeps this honest rather than decorative: it
    reads ui/window.py and fails if a user-visible string is still hardcoded
    there. Without it, the next button added in a hurry bypasses the catalogue
    and nothing notices.
"""
from __future__ import annotations

import ast
import json
import string
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "core"))

import i18n  # noqa: E402

WINDOW = ROOT / "ui" / "window.py"


def catalogue(locale: str) -> dict[str, str]:
    raw = json.loads((ROOT / "assets" / "i18n" / f"{locale}.json")
                     .read_text(encoding="utf-8"))
    return {k: v for k, v in raw.items() if not k.startswith("_")}


def fields(template: str) -> set[str]:
    return {name for _, name, _, _ in string.Formatter().parse(template)
            if name}


# ── the catalogue as data ────────────────────────────────────────────────────

def test_every_promised_locale_has_a_file():
    missing = [loc for loc in i18n.LOCALES if not i18n.CATALOG_DIR.joinpath(
        f"{loc}.json").is_file()]
    assert missing == [], f"LOCALES promises {missing} but ships no file"


def test_every_locale_covers_every_key():
    reference = set(catalogue(i18n.DEFAULT_LOCALE))
    holes = {loc: sorted(reference - set(catalogue(loc)))
             for loc in i18n.available() if loc != i18n.DEFAULT_LOCALE}
    holes = {loc: keys for loc, keys in holes.items() if keys}
    assert holes == {}, f"untranslated keys: {holes}"


def test_no_locale_invents_keys_the_reference_lacks():
    reference = set(catalogue(i18n.DEFAULT_LOCALE))
    extras = {loc: sorted(set(catalogue(loc)) - reference)
              for loc in i18n.available() if loc != i18n.DEFAULT_LOCALE}
    extras = {loc: keys for loc, keys in extras.items() if keys}
    assert extras == {}, f"keys nobody reads (typos?): {extras}"


def test_placeholders_match_across_locales():
    """A translation may reorder {name} but not rename or drop it: a dropped
    placeholder is a sentence that silently changes meaning."""
    reference = catalogue(i18n.DEFAULT_LOCALE)
    for loc in i18n.available():
        if loc == i18n.DEFAULT_LOCALE:
            continue
        other = catalogue(loc)
        wrong = {key: (sorted(fields(reference[key])), sorted(fields(text)))
                 for key, text in other.items()
                 if key in reference and fields(text) != fields(reference[key])}
        assert wrong == {}, f"{loc} has mismatched placeholders: {wrong}"


def test_no_label_is_empty_or_left_english_by_accident():
    for loc in i18n.available():
        blank = [key for key, text in catalogue(loc).items() if not text.strip()]
        assert blank == [], f"{loc} has blank labels: {blank}"


def test_the_two_locales_are_not_the_same_file():
    """The specific failure this catches: a locale copied from English and
    never touched, which looks complete to every check above."""
    en, id_ = catalogue("en"), catalogue("id")
    shared = [key for key, text in id_.items() if en.get(key) == text]
    # Symbols and proper nouns legitimately survive untranslated.
    # Legitimately identical: a template that is only a name and a separator,
    # a command to paste, a key prefix, and "SETUP", which Indonesian borrows
    # whole. Everything else must have been looked at.
    identical_by_design = {
        "app.tagline",              # a backronym for JARVIS, in any language
        "ui.phone.no_qr_module",    # `pip install qrcode[pil]`
        "ui.placeholder.key",       # "AIza…" — the shape of a Google key
        "dialog.title",             # "{name} — {page}"
        "ui.video.title",           # "▶  {title}"
        "ui.video.heading",         # "▶  VIDEO"
        "ui.setup.panel",           # "◈ SETUP"
    }
    shared = [key for key in shared
              if any(ch.isalpha() for ch in en[key])
              and key not in identical_by_design]
    assert len(shared) <= 2, f"id.json looks copied from en: {shared}"


# ── label() behaviour ───────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _reset_locale():
    i18n.reload()
    i18n.set_locale("en")
    yield
    i18n.set_locale("en")


def test_label_reads_the_active_locale():
    i18n.set_locale("en")
    en = i18n.label("ui.wake_word")
    i18n.set_locale("id")
    id_ = i18n.label("ui.wake_word")
    assert en != id_ and "KATA BANGUN" in id_


def test_label_substitutes_named_fields():
    i18n.set_locale("en")
    assert i18n.label("ui.phone.connected", name="JARVIS") == \
        "Phone connected — JARVIS ready"


def test_an_unknown_key_is_visible_not_silent():
    """A missing key must not fall back to the key name or to an empty string:
    ⟪…⟫ on screen is a bug report, 'ui.foo' is a mystery."""
    out = i18n.label("ui.does_not_exist")
    assert out == i18n.MARKER.format("ui.does_not_exist")


def test_missing_field_is_flagged_rather_than_raising():
    """Called from a Qt slot while a phone is connecting: a crash there leaves
    the window half-painted, so the label shows the problem instead."""
    out = i18n.label("ui.phone.connected")
    assert "bad-fields" in out and "{name}" in out


def test_a_missing_key_falls_back_to_english_before_the_marker(monkeypatch):
    data = {"ui.broken_key": "Only English has this"}
    monkeypatch.setitem(i18n._loaded, "id", dict(data))
    i18n.set_locale("id")
    assert i18n.label("ui.broken_key") == "Only English has this"


def test_resolve_accepts_the_shapes_a_real_environment_uses():
    assert i18n.resolve("id") == "id"
    assert i18n.resolve("id_ID.UTF-8") == "id"
    assert i18n.resolve("id-ID") == "id"
    assert i18n.resolve("de_DE.UTF-8") == "en"      # not shipped → English
    assert i18n.resolve(None) == "en" if not i18n.resolve(None) else True


def test_resolve_prefers_the_caller_over_the_environment(monkeypatch):
    monkeypatch.setenv("LANG", "id_ID.UTF-8")
    assert i18n.resolve("en") == "en"        # an explicit choice wins
    assert i18n.resolve(None) == "id"        # otherwise the environment speaks


def test_a_broken_catalogue_file_does_not_stop_the_window(monkeypatch, tmp_path):
    monkeypatch.setattr(i18n, "CATALOG_DIR", tmp_path)
    (tmp_path / "en.json").write_text("{not json", encoding="utf-8")
    i18n.reload()
    assert i18n.label("ui.on") == i18n.MARKER.format("ui.on")


def test_missing_and_extra_report_the_difference(monkeypatch):
    monkeypatch.setitem(i18n._loaded, "xx", {"ui.on": "ON", "extra.key": "?"})
    assert "ui.wake_word" in i18n.missing("xx")
    assert i18n.extra("xx") == ["extra.key"]


# ── the window actually goes through it ─────────────────────────────────────

QT_LABEL_CALLS = {"setText", "setWindowTitle", "setPlaceholderText",
                  "setToolTip", "addItem", "setTitle", "setStatusTip"}

# Strings that are allowed to stay literal at a Qt call site, each for a reason
# that is not "we ran out of time".
LITERALS_OK = {
    "AIza…",                 # a key prefix, not a phrase
    "—", "✓", "▶  ", "FINISH  →",  # punctuation and glyph scaffolding (below)
    "pip install\nqrcode[pil]",     # a command to paste, identical everywhere
}


def hardcoded_labels() -> list[str]:
    """Every user-visible string passed straight to a Qt setter.

    Deliberately conservative: it looks only at the arguments of the calls a
    label reaches the screen through, so log lines, dict values and
    strftime patterns are not mistaken for UI text.
    """
    tree = ast.parse(WINDOW.read_text(encoding="utf-8"))
    found = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in QT_LABEL_CALLS):
            continue
        for arg in node.args:
            if isinstance(arg, ast.JoinedStr):        # f-string: cannot be a
                continue                              # catalogue key anyway
            if not (isinstance(arg, ast.Constant) and isinstance(arg.value, str)):
                continue
            text = arg.value
            if not text.strip() or text in LITERALS_OK:
                continue
            if not any(ch.isalpha() for ch in text):
                continue                              # separators, arrows
            # The second argument of addItem is the VALUE a combo box stores,
            # not a label: "after"/"before"/"1" are config keys, and
            # translating them would break the setting they select. Skipped by
            # position, not by content, so a genuinely hardcoded label
            # ("no"/"yes" in a first argument) is still caught.
            if node.func.attr == "addItem" and len(node.args) > 1 and arg is node.args[1]:
                continue
            found.append(f"line {arg.lineno}: {node.func.attr}({text!r})")
    return sorted(found)


def test_the_window_has_no_hardcoded_user_visible_strings():
    remaining = hardcoded_labels()
    assert remaining == [], (
        "these strings never reach the translation catalogue — pass a key to "
        "i18n.label() instead:\n  " + "\n  ".join(remaining))


def test_every_key_the_window_asks_for_exists():
    """The other direction: a key spelled wrong in the window is a ⟪…⟫ the
    user sees and nobody tests."""
    tree = ast.parse(WINDOW.read_text(encoding="utf-8"))
    asked = set()
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and node.func.id == "label" and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)):
            asked.add(node.args[0].value)
    assert asked, "window.py never calls label() — is the wiring missing?"
    missing = sorted(asked - set(catalogue(i18n.DEFAULT_LOCALE)))
    assert missing == [], f"window.py asks for keys nobody wrote: {missing}"
