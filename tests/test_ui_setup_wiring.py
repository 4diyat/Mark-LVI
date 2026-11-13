"""The setup screen: what it saves, and that it always reports back.

WHY THIS IS A SOURCE CHECK AND NOT A WIDGET TEST
    The bug lives in the wiring between three Qt slots: the overlay must be
    STORED (`self._overlay`), its `done` signal must be CONNECTED to the save
    handler, and its disappearance must settle `_ready` — because main.py sits
    in `while not self._win._ready: await asyncio.sleep(1)` waiting for exactly
    that. Creating and showing the overlay without storing it looked correct,
    ran without an error, and left the session loop asleep forever.

    Proving that with a real widget needs a QApplication; this repository's CI
    runs headless, and a test that needs a display is a test that gets skipped.
    So the two halves are tested where each can actually run:

      * what gets SAVED  — tests/test_config.py::test_setup_merges_and_never_replaces
                           (real code, real file, no Qt at all)
      * the WIRING       — here, against the parsed source, which is precisely
                           the thing that was missing, and which no amount of
                           careful reading caught the first time.

    When ui/window.py is split further into ui/overlays/, SetupOverlay becomes
    constructible on its own and this becomes a normal widget test.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
UI = ROOT / "ui" / "window.py"


@pytest.fixture(scope="module")
def main_window():
    """The MainWindow class node from ui/window.py."""
    tree = ast.parse(UI.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "MainWindow":
            return node
    pytest.fail("MainWindow not found in ui/window.py")


def _method(cls, name: str) -> ast.FunctionDef:
    for node in cls.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    pytest.fail(f"MainWindow.{name} not found")


def _calls(fn: ast.FunctionDef):
    """(name, call node) for every call inside `fn` — methods and plain functions."""
    for node in ast.walk(fn):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute):
                yield node.func.attr, node
            elif isinstance(node.func, ast.Name):
                yield node.func.id, node


def _assigns_self_attr(fn: ast.FunctionDef, attr: str) -> bool:
    for node in ast.walk(fn):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if (isinstance(target, ast.Attribute)
                        and target.attr == attr
                        and isinstance(target.value, ast.Name)
                        and target.value.id == "self"):
                    return True
    return False


def test_show_setup_reuses_one_overlay(main_window):
    """The overlay must be stored, not just shown.

    The old version built it, connected `done`, showed it — and dropped the
    only reference. `_on_setup_done` could then never fire from a re-configure,
    so a rejected API key could be replaced correctly and the session still
    waited for a flag nothing would set.
    """
    fn = _method(main_window, "_show_setup")
    assert _assigns_self_attr(fn, "_overlay"), (
        "MainWindow._show_setup does not store the overlay in self._overlay — "
        "the re-configure path cannot report back")
    connected = {name for name, _ in _calls(fn)}
    assert "connect" in connected, "_show_setup connects nothing"


def test_show_setup_connects_done_and_close(main_window):
    """`done` carries the new key; `destroyed` is the dismiss-without-saving path."""
    src = ast.get_source_segment(UI.read_text(encoding="utf-8"),
                                 _method(main_window, "_show_setup")) or ""
    assert ".done.connect(" in src, "setup overlay's done signal is not connected"
    assert "destroyed.connect(" in src or "closeEvent" in src, (
        "a setup box closed without saving has no way to settle _ready — "
        "main.py would wait for it forever")


def test_saving_setup_goes_through_the_config_writer(main_window):
    """`_on_setup_done` must not write api_keys.json itself.

    It used to write {"gemini_api_key", "os_system"} over the whole file, which
    deleted the assistant's name, its voice, the device choices and every
    plugin credential on every re-configure.
    """
    fn = _method(main_window, "_on_setup_done")
    assert any(name == "save_setup" for name, _ in _calls(fn)), (
        "_on_setup_done does not use memory.config_manager.save_setup")
    # Inspect the AST, not the text: the docstring explains the old bug and
    # therefore mentions write_text() without calling it.
    writes = {name for name, call in _calls(fn)
              if name in {"write_text", "write", "dump", "dumps"}}
    assert not writes, (
        f"_on_setup_done writes the config file directly ({sorted(writes)}) — "
        "that is the bug that wiped people's settings on re-configure")


def test_dismissing_setup_settles_ready(main_window):
    """The no-key path must set _ready, or the session loop never resumes."""
    src = ast.get_source_segment(UI.read_text(encoding="utf-8"),
                                 _method(main_window, "_on_setup_closed")) or ""
    assert "_ready" in src and "True" in src
