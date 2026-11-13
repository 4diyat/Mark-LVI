"""The language setting: what it stores, what it refuses, and where it lands.

WHY THE SETTING HAS ITS OWN TEST
    i18n.label() can be perfect and the window still opens in English, because
    the choice is read from api_keys.json through the config module — the only
    place allowed to decide what a stored value means. Each test here is a bug
    that produces no error message:

      * a hand-edited config with "ui_language": "de" must fall back to 'auto',
        not select a catalogue that does not exist;
      * 'auto' must mean the OS locale, not English — a user who set LANG=id_ID
        has already told the machine once;
      * the value must land in the same file as every other setting, through
        the locked writer, so changing the language cannot delete the key the
        way the setup screen once did.
"""
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
WINDOW = ROOT / "ui" / "window.py"


def _method(tree, cls: str, name: str):
    """The FunctionDef for `cls.name` in a parsed module."""
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == cls:
            for sub in node.body:
                if isinstance(sub, ast.FunctionDef) and sub.name == name:
                    return sub
    raise AssertionError(f"{cls}.{name} not found — did it move or rename?")


@pytest.fixture()
def i18n():
    """The real catalogue, reset to English after each test."""
    for p in (str(ROOT), str(ROOT / "core")):
        if p not in sys.path:
            sys.path.insert(0, p)
    import i18n as mod
    mod.reload()
    mod.set_locale("en")
    yield mod
    mod.set_locale("en")


# ── what the config module decides ───────────────────────────────────────────

def test_default_is_auto_not_english(isolated_config):
    """A fresh install follows the OS. Defaulting to 'en' would make the 'auto'
    option unreachable for everyone who never opens the panel."""
    assert isolated_config.get_ui_language() == "auto"


def test_a_stored_locale_survives_a_round_trip(isolated_config):
    isolated_config.save_ui_language("id")
    assert isolated_config.get_ui_language() == "id"


def test_an_unknown_locale_collapses_to_auto(isolated_config):
    """Writing 'de' by hand (or by a newer version) must not select a language
    with no catalogue, and must not raise either."""
    isolated_config.set_config_values(ui_language="de")
    assert isolated_config.get_ui_language() == "auto"


def test_saving_an_unknown_locale_stores_auto(isolated_config):
    isolated_config.save_ui_language("klingon")
    stored = json.loads(isolated_config.CONFIG_FILE.read_text(encoding="utf-8"))
    assert stored["ui_language"] == "auto"


def test_the_language_does_not_disturb_the_api_key(isolated_config):
    """The setup screen once wrote its two fields over the whole file and took
    every other setting with it. The language must not repeat that."""
    isolated_config.save_api_keys("key-aaaaaaaaaaaaaaaa")
    isolated_config.save_assistant_config("JARVIS", "Fatih")
    isolated_config.save_ui_language("id")
    data = isolated_config.load_api_keys()
    assert data["gemini_api_key"] == "key-aaaaaaaaaaaaaaaa"
    assert data["user_name"] == "Fatih"
    assert data["ui_language"] == "id"


# ── what 'auto' resolves to ─────────────────────────────────────────────────

@pytest.mark.parametrize("env, expected", [
    ("id_ID.UTF-8", "id"),
    ("en_GB.UTF-8", "en"),
    ("de_DE.UTF-8", "en"),      # not shipped → the default, not a crash
])
def test_auto_follows_the_operating_system(i18n, monkeypatch, env, expected):
    for name in ("LANGUAGE", "LC_ALL", "LC_MESSAGES"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("LANG", env)
    i18n.set_locale(None)
    assert i18n.active_locale() == expected


def test_an_explicit_setting_beats_the_environment(i18n, monkeypatch):
    monkeypatch.setenv("LANG", "en_US.UTF-8")
    i18n.set_locale("id")
    assert i18n.active_locale() == "id"
    assert "KATA BANGUN" in i18n.label("ui.wake_word")


# ── what the window does with it ────────────────────────────────────────────

def test_the_window_sets_the_locale_before_its_first_label():
    """Ordering is the whole behaviour: set_locale() after the widgets are built
    paints the window in the OLD language until something else repaints it."""
    init = _method(ast.parse(WINDOW.read_text(encoding="utf-8")),
                   "MainWindow", "__init__")
    order = []
    for node in ast.walk(init):
        if isinstance(node, ast.Call):
            name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
            if name in ("set_locale", "label", "_t"):
                order.append((node.lineno, name))
    first_locale = min(ln for ln, name in order if name == "set_locale")
    first_label = min((ln for ln, name in order if name in ("label", "_t")),
                      default=10 ** 9)
    assert first_locale < first_label, (
        "the locale is chosen after a label is read, so the first paint is in "
        f"the wrong language: set_locale at {first_locale}, label at {first_label}")


def test_a_language_change_reaches_the_config_and_the_catalogue():
    """The two halves of applying the choice: the panel may preview, but only
    APPLY may write — and what it writes goes through the same locked
    primitive as every other setting."""
    window = ast.parse(WINDOW.read_text(encoding="utf-8"))
    apply_fn = _method(window, "MainWindow", "_apply_name_update")
    calls = {getattr(n.func, "attr", None) or getattr(n.func, "id", None)
             for n in ast.walk(apply_fn) if isinstance(n, ast.Call)}
    assert "save_ui_language" in calls, "APPLY does not persist the language"
    assert "set_locale" in calls, "APPLY does not switch the catalogue"
    assert "_retranslate_window" in calls, "APPLY does not repaint the window"


def test_cancelling_a_preview_puts_the_language_back():
    """The panel switches the catalogue live so the user can SEE the choice.
    Cancelling must undo that, or the window stays in a language its own config
    file does not agree with until the next start."""
    overlays = ast.parse((ROOT / "ui" / "overlays.py").read_text(encoding="utf-8"))
    cancel_fn = _method(overlays, "CustomizeOverlay", "_cancel")
    calls = {getattr(n.func, "id", None) or getattr(n.func, "attr", None)
             for n in ast.walk(cancel_fn) if isinstance(n, ast.Call)}
    assert "set_locale" in calls
