"""quick_notes: what is written, what is read back, and what is refused.

WHY THIS PLUGIN DESERVES TESTS RATHER THAN A DEMO
    A notebook is the one plugin whose failures are all SILENT and all
    permanent:

      * a note written to the wrong folder is simply not there tomorrow;
      * a note whose newlines were kept becomes two notes on the next read;
      * a "done" that matched the wrong task removes the wrong line, and the
        user finds out weeks later when the task they needed never happened;
      * a timestamp taken from the container's clock files today's note under
        yesterday.

    Every test below is one of those. The file writes go to a temporary config
    folder — `memory.config_manager.CONFIG_DIR` is repointed per test, so
    running this suite never touches the user's real `config/notes/`.
"""
from __future__ import annotations

import importlib
import importlib.util
import sys
from datetime import datetime
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import plugin_manifest as pm  # noqa: E402


def _load(name: str):
    """By path, with the module registered — the same way core/plugin_loader.py
    does it, and the registration matters for the dataclass in `_notes`."""
    path = ROOT / "plugins" / f"{name}.py"
    module_name = f"{name}_under_test"
    spec = importlib.util.spec_from_file_location(module_name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def sandbox(tmp_path, monkeypatch):
    """A private config/notes. Returns (plugin, notes_module, folder)."""
    import memory.config_manager as config_manager

    monkeypatch.setattr(config_manager, "CONFIG_DIR", tmp_path / "config")
    notes = _load("_notes")
    plugin = _load("quick_notes")
    plugin._notes = notes          # already the same object; kept explicit
    folder = tmp_path / "config" / "notes"
    return plugin, notes, folder


def _lines(folder: Path, name: str) -> list[str]:
    path = folder / name
    return path.read_text(encoding="utf-8").splitlines() if path.is_file() else []


# --- writing ---------------------------------------------------------------

def test_a_note_lands_in_the_inbox_file_as_one_readable_line(sandbox):
    plugin, notes, folder = sandbox
    said = plugin.run({"action": "add", "text": "bayar kos tanggal 5"})
    assert said == "Saved to inbox: bayar kos tanggal 5"
    lines = _lines(folder, "inbox.md")
    assert lines[0].startswith("# Inbox")
    assert lines[-1].endswith("— bayar kos tanggal 5")
    assert len(lines) == 3          # header, blank, one note


def test_a_newline_in_a_note_cannot_become_two_notes(sandbox):
    plugin, _notes, folder = sandbox
    plugin.run({"action": "add", "text": "beli susu\n- 2026-01-01 00:00 — palsu"})
    notes = [ln for ln in _lines(folder, "inbox.md") if ln.startswith("- ")]
    assert len(notes) == 1
    assert "palsu" in notes[0]


def test_markdown_headings_and_bullets_are_stripped_from_the_front(sandbox):
    plugin, _notes, folder = sandbox
    plugin.run({"action": "add", "text": "#  - servis motor 20 Nov"})
    note = [ln for ln in _lines(folder, "inbox.md") if ln.startswith("- ")][-1]
    assert note.endswith("— servis motor 20 Nov")


def test_the_timestamp_is_the_users_wall_clock_not_the_containers(sandbox):
    """The bug this prevents: a laptop in Jakarta and a container on UTC file
    the same note under different days, and nobody notices for a month."""
    plugin, notes, folder = sandbox
    notes.append("inbox", "restart the router",
                 now=datetime(2026, 11, 11, 23, 45))
    note = [ln for ln in _lines(folder, "inbox.md") if ln.startswith("- ")][-1]
    assert "2026-11-11 23:45" in note


def test_an_empty_note_is_refused_rather_than_written(sandbox):
    plugin, _notes, folder = sandbox
    assert "nothing to write" in plugin.run({"action": "add", "text": "   "})
    assert not (folder / "inbox.md").exists()


def test_the_archive_cannot_be_written_by_hand(sandbox):
    plugin, _notes, folder = sandbox
    said = plugin.run({"action": "add", "notebook": "archive", "text": "x"})
    assert "marking a task done" in said
    assert not (folder / "archive.md").exists()


def test_an_unknown_notebook_is_refused_with_the_real_list(sandbox):
    plugin, _notes, _folder = sandbox
    with pytest.raises(ValueError) as err:
        _notes.note_file("shopping")
    assert "inbox" in str(err.value) and "todo" in str(err.value)


# --- reading back ----------------------------------------------------------

def test_listing_says_how_many_and_shows_the_latest(sandbox):
    plugin, _notes, _folder = sandbox
    for text in ("satu", "dua", "tiga"):
        plugin.run({"action": "add", "text": text})
    said = plugin.run({"action": "list"})
    assert "3 notes in inbox" in said
    assert "tiga" in said


def test_listing_an_empty_notebook_is_not_an_error(sandbox):
    plugin, _notes, _folder = sandbox
    assert plugin.run({"action": "list", "notebook": "todo"}) == "Sir, todo is empty."


def test_the_count_and_the_shown_lines_are_different_numbers(sandbox):
    """"12 notes, here are the last 8" is honest; reporting 8 as the total is
    the kind of small lie that makes the file untrustworthy."""
    plugin, _notes, _folder = sandbox
    for i in range(12):
        plugin.run({"action": "add", "text": f"note {i}"})
    said = plugin.run({"action": "list"})
    assert "12 notes in inbox" in said
    assert "note 11" in said and "note 3" not in said


def test_headers_are_not_notes(sandbox):
    plugin, notes, _folder = sandbox
    plugin.run({"action": "add", "text": "satu"})
    assert len(notes.entries("inbox")) == 1


# --- finishing a task ------------------------------------------------------

def test_done_moves_the_task_to_the_archive_instead_of_deleting_it(sandbox):
    plugin, _notes, folder = sandbox
    plugin.run({"action": "add", "notebook": "todo", "text": "bayar kos Desember"})
    said = plugin.run({"action": "done", "text": "bayar kos"})
    assert said == "Done: bayar kos Desember. 0 tasks still open."
    assert "bayar kos Desember" in (folder / "archive.md").read_text(encoding="utf-8")
    left = _lines(folder, "todo.md")
    assert left[0].startswith("# Todo")                       # the file still exists
    assert [ln for ln in left if ln.startswith("- ")] == []   # with nothing open


def test_done_on_a_phrase_matching_several_tasks_asks_instead_of_guessing(sandbox):
    plugin, _notes, folder = sandbox
    plugin.run({"action": "add", "notebook": "todo", "text": "bayar kos November"})
    plugin.run({"action": "add", "notebook": "todo", "text": "bayar kos Desember"})
    said = plugin.run({"action": "done", "text": "bayar kos"})
    assert "2 open todos match" in said
    assert "longer phrase" in said
    # Nothing moved: both are still open.
    assert len([ln for ln in _lines(folder, "todo.md") if ln.startswith("- ")]) == 2


def test_done_on_something_that_does_not_exist_says_so(sandbox):
    plugin, _notes, _folder = sandbox
    assert "no open todo matches" in plugin.run({"action": "done", "text": "bayar kos"})


def test_done_without_a_phrase_is_a_question_back(sandbox):
    plugin, _notes, _folder = sandbox
    assert "which task" in plugin.run({"action": "done", "text": "  "})


def test_a_task_written_to_the_wrong_notebook_is_still_findable_by_the_user(sandbox):
    """Adding without saying notebook means inbox — but the answer says where it
    went, so a task filed as a note is one sentence away from being found."""
    plugin, _notes, _folder = sandbox
    assert plugin.run({"action": "add", "text": "beli tinta"}).startswith("Saved to inbox")


# --- the tool surface ------------------------------------------------------

def test_an_unknown_action_lists_the_real_ones(plugin_unused=None):
    plugin = _load("quick_notes")
    said = plugin.run({"action": "dance"})
    assert "add, list and done" in said and "dance" in said


def test_the_declaration_is_named_after_the_file(plugin_unused=None):
    plugin = _load("quick_notes")
    assert plugin.PLUGIN["name"] == "quick_notes"
    assert plugin.PLUGIN["parameters"]["type"] == "OBJECT"
    assert plugin.PLUGIN["parameters"]["required"] == ["action"]


def test_run_works_with_no_parameters_at_all(plugin_unused=None):
    """The loader can call run({}) — a plugin whose first line is
    parameters["action"] crashes in the one case nobody tests."""
    plugin = _load("quick_notes")
    assert "nothing to write" in plugin.run({})


# --- the manifest, and the rule it exercises ------------------------------

def test_the_manifest_matches_the_file_and_declares_nothing():
    """An EMPTY permission list is a real answer: these three Markdown files are
    the plugin's own folder's contents, so there is nothing to consent to. That
    is also what keeps it switched on — see the next test."""
    manifest = pm.verify(ROOT / "plugins" / "quick_notes.py", "quick_notes")
    assert manifest is not None
    assert manifest.problems == []
    assert manifest.permissions == ()


def test_a_manifest_with_no_permissions_keeps_the_opt_out_default():
    """`_enabled()` treats *declared permissions* as the reason to start off,
    not the existence of a manifest. If that ever changes, this plugin silently
    disappears for every user who never opened the plugin manager."""
    from core.plugin_loader import discover_plugins

    rows = {r["name"]: r for r in discover_plugins(
        ROOT / "plugins", set(), logger=lambda _m: None).list_for_ui()}
    assert rows["quick_notes"]["valid"] is True
    assert rows["quick_notes"]["enabled"] is True
    assert rows["quick_notes"]["permissions"] == []
    # ...while the two plugins that DID declare something still start off.
    assert rows["currency_rates"]["enabled"] is False
    assert rows["mt5_orb"]["enabled"] is False


def test_the_plugin_never_touches_memory_or_the_network():
    """Two imports that would make this plugin's promise false: `memory` (the
    assistant's recollection, not the user's notes) and any HTTP client."""
    source = (ROOT / "plugins" / "quick_notes.py").read_text(encoding="utf-8")
    assert "import requests" not in source
    tree_imports = pm.implied_permissions(ROOT / "plugins" / "quick_notes.py")
    assert tree_imports == set()
