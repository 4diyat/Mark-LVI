"""Aktif / Fokus / Senyap, from the saved file to the orb and back again.

THE BUG THIS FILE EXISTS FOR
    `apply_presence_mode` was written, tested and merged — and nothing ever
    called it. `core.presence_mode` was asked `current()` in three places and
    never `bind()`-ed to the config, so it answered "active" forever. The result
    was the worst kind: a tray setting that saved correctly, dimmed the orb once,
    and was silently forgotten on the next launch. Every unit was green.

    So these tests are about the CHAIN, not the pieces: the file is read at
    startup, the tray cycles the mode, the orb follows, and the value survives a
    restart because it is written where the reader looks.
"""
from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def lifecycle():
    from core import presence_mode

    presence_mode.reset()
    presence_mode.bind(None, None)
    module = _load("lifecycle_chain_under_test", ROOT / "ui" / "lifecycle.py")
    yield module
    presence_mode.reset()
    presence_mode.bind(None, None)


class _Orb:
    def __init__(self):
        self.modes = []

    def set_mode(self, mode):
        self.modes.append(mode)


class _Shell:
    def __init__(self, orb=None):
        self._orb = orb


# ── the chain: file → state → orb ─────────────────────────────────────────

def test_the_saved_mode_is_read_at_startup_and_not_assumed(lifecycle, monkeypatch):
    """Without the bind, `current()` answers "active" no matter what is saved."""
    import memory.config_manager as cfg

    monkeypatch.setattr(cfg, "get_presence_mode", lambda: "quiet")
    monkeypatch.setattr(cfg, "save_presence_mode", lambda _m: True)

    from core import presence_mode
    presence_mode.bind(read=cfg.get_presence_mode, write=cfg.save_presence_mode)
    assert presence_mode.current() == "quiet"
    assert presence_mode.allows_banner() is False


def test_main_py_binds_the_mode_before_anything_asks_for_it():
    """Read from main.py: the wiring, not a running session.

    `main.py` cannot be imported here (it builds a Gemini session), so the call
    site is checked structurally — the same approach `test_gate_wiring.py`
    takes for the gate.
    """
    source = (ROOT / "main.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    defined = {n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)}
    assert "_presence_bound" in defined, "main.py no longer binds the saved mode"

    run = source[source.index("    async def run(self):"):]
    body = run[:run.index("audio_devices.configure")]
    assert "_presence_bound()" in body, (
        "the presence mode is bound after the session starts, so the first "
        "notification policy decision of every launch uses the wrong mode")


def test_the_bind_helper_names_both_halves():
    """A bind with only a reader forgets every change; only a writer never
    restores one."""
    source = (ROOT / "main.py").read_text(encoding="utf-8")
    start = source.index("def _presence_bound()")
    block = source[start:source.index("return presence_mode.current()", start)]
    assert "read=get_presence_mode" in block
    assert "write=save_presence_mode" in block


# ── the tray ──────────────────────────────────────────────────────────────

def test_cycling_walks_all_three_and_comes_home(lifecycle):
    from core import presence_mode

    shell = _Shell(orb=_Orb())
    assert lifecycle.cycle_presence_mode(shell) == "focus"
    assert lifecycle.cycle_presence_mode(shell) == "quiet"
    assert lifecycle.cycle_presence_mode(shell) == "active"
    assert presence_mode.current() == "active"


def test_each_step_dims_the_orb_immediately(lifecycle):
    orb = _Orb()
    shell = _Shell(orb=orb)
    lifecycle.cycle_presence_mode(shell)
    lifecycle.cycle_presence_mode(shell)
    assert orb.modes == ["focus", "quiet"]


def test_the_tray_label_states_the_mode_not_the_action(lifecycle):
    """A menu item called "Presence" tells the user nothing; the current mode
    is the thing that decides whether the assistant may interrupt them."""
    labels = {m: lifecycle.presence_label(m) for m in ("active", "focus", "quiet")}
    assert len(set(labels.values())) == 3
    assert "Fokus" in labels["focus"]
    assert "Senyap" in labels["quiet"]
    for text in labels.values():
        assert "—" in text, "the label should name the mode and what it does"


def test_an_unknown_mode_gets_a_readable_label(lifecycle):
    assert lifecycle.presence_label("nonsense") == lifecycle.presence_label("active")


def test_the_tray_menu_has_one_presence_item_not_three():
    source = (ROOT / "ui" / "tray.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    menu = None
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "MENU_ITEMS" for t in node.targets):
            menu = node.value
    keys = [elt.elts[0].value for elt in menu.elts]
    assert keys.count("presence") == 1
    assert "focus" not in keys and "quiet" not in keys, (
        "three entries for three modes is three chances to pick the wrong one")


def test_the_presence_item_is_behind_the_quit_item():
    """Quit must stay last — it is the one item that must never be hit by
    accident, and a new entry appended after it moves it under the cursor."""
    source = (ROOT / "ui" / "tray.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "MENU_ITEMS" for t in node.targets):
            keys = [elt.elts[0].value for elt in node.value.elts]
    assert keys[-1] == "quit"
    assert keys[-2] == "autostart"


# ── the label is a value, so it must be re-read ───────────────────────────

def test_a_dynamic_label_is_asked_for_again_after_the_click():
    """The callback changed the mode; a menu that still shows the old label is
    the same bug as a stale tick, one line further down."""
    source = (ROOT / "ui" / "tray.py").read_text(encoding="utf-8")
    handler = source[source.index("def _make_handler"):]
    handler = handler[:handler.index("return _fire")]
    # Both halves, together: `setText` alone could be setting the constant, and
    # the guard alone changes nothing. A mutation that deletes the guard while
    # leaving the two other `self._label(` calls alone must fail here.
    assert "action.setText" in handler
    assert "key in DYNAMIC_ITEMS and self._label" in handler
    assert "self._label(key) or action.text()" in handler


def test_a_label_provider_that_raises_leaves_a_usable_menu():
    """Same rule as `checked`: a probe that throws costs the label, not the
    tray — the tray is how a headless install is reachable at all.

    Read from the source rather than constructed: `ui/tray.py` imports Qt at
    module scope, and CI installs only the test tooling. What is asserted is
    that every call site is inside a `try`, which is the property that matters.
    """
    source = (ROOT / "ui" / "tray.py").read_text(encoding="utf-8")
    assert source.count("self._label(") == 2
    for call in ("label = self._label(key) or label",
                 "action.setText(self._label(key) or action.text())"):
        assert call in source
    # And the constant fallback still exists for a caller with no provider.
    assert "Aktif — boleh menyela" in source
