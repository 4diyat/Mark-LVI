"""Obsidian integration: read the user's vault, append to it, never break it.

The stakes here are different from the rest of the suite. This module writes
into files that belong to another application and to the user's life — a
thesis, a journal, a work vault. So the tests are less about features and more
about the two promises that make the feature acceptable at all:

  1. Nothing is ever rewritten, reordered or deleted. Only appended to, and only
     new files are ever created.
  2. When the module cannot be sure — two vaults, two notes with one name —
     it asks. It never picks.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from core import obsidian as ob


@pytest.fixture()
def vault(tmp_path):
    """A vault with the shape a real one has: bookkeeping folders and all."""
    root = tmp_path / "Vault"
    (root / ".obsidian").mkdir(parents=True)
    (root / ".obsidian" / "workspace.json").write_text("{}", encoding="utf-8")
    (root / ".trash").mkdir()
    (root / ".trash" / "deleted.md").write_text("gone", encoding="utf-8")
    (root / "Daily").mkdir()
    (root / "Daily" / "2026-11-11.md").write_text(
        "# 2026-11-11\n\n- 09:00 standup\n- paid the deposit\n", encoding="utf-8")
    (root / "Housing contract.md").write_text("Deposit due.", encoding="utf-8")
    return root


@pytest.fixture()
def config(tmp_path, vault):
    """Obsidian's own record of the vault."""
    path = tmp_path / "obsidian.json"
    path.write_text(json.dumps({"vaults": {"a1b2": {"path": str(vault)}}}),
                    encoding="utf-8")
    return path


# ── discovery ───────────────────────────────────────────────────────────────

def test_a_vault_is_a_folder_with_obsidian_inside(vault, tmp_path):
    assert ob.is_vault(vault) is True
    assert ob.is_vault(tmp_path / "not-a-vault") is False
    (tmp_path / "empty").mkdir()
    assert ob.is_vault(tmp_path / "empty") is False


def test_the_vault_is_found_through_obsidians_own_config(config, vault):
    """No folder names are hardcoded: a vault is wherever Obsidian says it is."""
    assert vault in ob.known_vaults(config)


def test_a_broken_config_is_not_an_error(tmp_path):
    path = tmp_path / "obsidian.json"
    path.write_text("{ this is not json", encoding="utf-8")
    assert ob.known_vaults(path) == []
    assert ob.known_vaults(tmp_path / "missing.json") == []


def test_a_recorded_path_that_no_longer_exists_is_ignored(tmp_path):
    path = tmp_path / "obsidian.json"
    path.write_text(json.dumps({"vaults": {"x": {"path": str(tmp_path / "gone")}}}),
                    encoding="utf-8")
    assert ob.known_vaults(path) == []


def test_one_vault_is_the_default_and_several_are_not(config, vault):
    """Picking the first of several is how a note lands in the wrong vault."""
    assert ob.default_vault(config) == vault

    second = vault.parent / "Second"
    (second / ".obsidian").mkdir(parents=True)
    both = vault.parent / "both.json"
    both.write_text(json.dumps({"vaults": {
        "a": {"path": str(vault)}, "b": {"path": str(second)}}}), encoding="utf-8")
    assert ob.default_vault(both) is None
    with pytest.raises(ob.VaultError) as err:
        ob.resolve(config_path=both)
    assert "will not guess" in str(err.value)


def test_resolve_says_what_to_do_when_there_is_no_vault(tmp_path):
    with pytest.raises(ob.VaultError) as err:
        ob.resolve(config_path=tmp_path / "none.json")
    assert "cannot find an obsidian vault" in str(err.value).lower()
    assert "Obsidian" in str(err.value), "the message must name the fix"


def test_a_folder_that_is_not_a_vault_is_refused_with_the_reason(tmp_path):
    (tmp_path / "plain").mkdir()
    with pytest.raises(ob.VaultError) as err:
        ob.resolve(folder=tmp_path / "plain")
    assert ".obsidian" in str(err.value)


# ── reading ─────────────────────────────────────────────────────────────────

def test_obsidians_own_folders_are_never_searched(vault):
    """`.trash` holds deleted notes and `.obsidian` holds settings. Searching
    them returns things the user removed, which is worse than a miss."""
    assert ob.search("gone", folder=vault) == []
    assert ob.search("workspace", folder=vault) == []


def test_search_reads_the_text_and_names_the_file(vault):
    hits = ob.search("deposit", folder=vault)
    titles = [h["title"] for h in hits]
    assert "Housing contract" in titles
    assert "Daily/2026-11-11" in titles
    # The matching line is quoted, not summarised: a summary is the model's
    # reading of the user's note, which is the thing that must not happen.
    daily = next(h for h in hits if h["title"].startswith("Daily"))
    assert daily["line"] == "- paid the deposit"


def test_a_name_match_outranks_a_body_match(vault):
    """A note called "Housing contract" is about the contract whatever its body
    says, so it comes first even when both files contain the word."""
    hits = ob.search("housing", folder=vault)
    assert hits[0]["title"] == "Housing contract"
    assert hits[0]["name_match"] is True


def test_an_empty_query_is_a_question_not_a_full_dump(vault):
    with pytest.raises(ob.VaultError) as err:
        ob.search("   ", folder=vault)
    assert "what should i look for" in str(err.value).lower()


def test_a_huge_note_is_not_a_search_candidate(vault, monkeypatch):
    monkeypatch.setattr(ob, "MAX_FILE_BYTES", 10)
    assert ob.search("deposit", folder=vault) == []


def test_a_note_can_be_read_by_name_with_or_without_the_extension(vault):
    for name in ("Housing contract", "Housing contract.md"):
        note = ob.read_note(name, folder=vault)
        assert note["text"] == "Deposit due."
        assert note["truncated"] is False


def test_a_missing_note_says_so_in_a_sentence(vault):
    with pytest.raises(ob.VaultError) as err:
        ob.read_note("Nothing like this", folder=vault)
    assert "no note called" in str(err.value)


def test_two_notes_with_one_name_are_a_question(vault):
    other = vault / "Archive"
    other.mkdir()
    (other / "Housing contract.md").write_text("old one", encoding="utf-8")
    (vault / "daily-notes").mkdir()
    with pytest.raises(ob.VaultError) as err:
        ob.read_note("Housing contract", folder=vault)
    assert "2 notes" in str(err.value)
    assert "Archive" in str(err.value), "the answer must name the candidates"


def test_a_long_note_is_truncated_and_says_that_it_was(vault):
    (vault / "Long.md").write_text("x" * 5000, encoding="utf-8")
    note = ob.read_note("Long", folder=vault, max_chars=100)
    assert len(note["text"]) == 100
    assert note["truncated"] is True


# ── writing: append only ────────────────────────────────────────────────────

def test_appending_adds_one_line_and_changes_nothing_else(vault):
    """Exactly one line more, and the original bytes are still the prefix."""
    before = (vault / "Housing contract.md").read_text(encoding="utf-8")
    ob.append_note("sent the signed copy", "Housing contract", folder=vault)
    after = (vault / "Housing contract.md").read_text(encoding="utf-8")
    assert after.startswith(before), "the existing text was not left alone"
    assert after == before + "\nsent the signed copy\n", (
        "the file had no final newline, so one had to be added first")
    # And only one line was added.
    assert after.count("sent the signed copy") == 1


def test_appending_keeps_the_files_own_line_endings(vault):
    """A note written on Windows ends its lines with CRLF; appending LF into it
    produces a file with two conventions, which Obsidian renders with stray
    characters."""
    path = vault / "Win.md"
    path.write_bytes(b"# Win\r\nfirst line\r\n")
    ob.append_note("second line", "Win", folder=vault)
    assert path.read_bytes() == b"# Win\r\nfirst line\r\nsecond line\r\n"


def test_appending_to_a_file_with_no_final_newline_does_not_join_the_lines(vault):
    path = vault / "Tight.md"
    path.write_text("no newline at the end", encoding="utf-8")
    ob.append_note("next", "Tight", folder=vault)
    assert path.read_text(encoding="utf-8") == "no newline at the end\nnext\n"


def test_appending_never_creates_a_note(vault):
    """"Add to my daily note" failing loudly beats silently inventing a file in
    a folder the user organises differently."""
    with pytest.raises(ob.VaultError):
        ob.append_note("hello", "No such note", folder=vault)
    assert not (vault / "No such note.md").exists()


def test_an_empty_line_is_not_written(vault):
    before = (vault / "Housing contract.md").read_text(encoding="utf-8")
    with pytest.raises(ob.VaultError):
        ob.append_note("   \n  ", "Housing contract", folder=vault)
    assert (vault / "Housing contract.md").read_text(encoding="utf-8") == before


def test_control_characters_never_reach_the_file(vault):
    ob.append_note("paid\x00it\x07", "Housing contract", folder=vault)
    text = (vault / "Housing contract.md").read_text(encoding="utf-8")
    assert "\x00" not in text and "\x07" not in text
    assert "paidit" in text


# ── creating ────────────────────────────────────────────────────────────────

def test_a_new_note_is_created_with_a_title(vault):
    made = ob.create_note("Groceries", "milk and eggs", folder=vault)
    text = Path(made["path"]).read_text(encoding="utf-8")
    assert text.startswith("# Groceries")
    assert "milk and eggs" in text


def test_creating_over_an_existing_note_is_refused(vault):
    """Obsidian is where somebody's thesis lives. Overwriting is the one
    mistake this module must be incapable of making."""
    before = (vault / "Housing contract.md").read_text(encoding="utf-8")
    with pytest.raises(ob.VaultError) as err:
        ob.create_note("Housing contract", "something else", folder=vault)
    assert "will not overwrite" in str(err.value)
    assert (vault / "Housing contract.md").read_text(encoding="utf-8") == before


def test_a_note_is_created_inside_a_subfolder_when_asked(vault):
    made = ob.create_note("2026-11-12", "today", folder_name="Daily", folder=vault)
    assert Path(made["path"]).parent == vault / "Daily"


def test_a_folder_that_escapes_the_vault_is_refused(vault):
    with pytest.raises(ob.VaultError) as err:
        ob.create_note("escape", "x", folder_name="../../outside", folder=vault)
    assert "outside the vault" in str(err.value)
    assert not (vault.parent / "outside").exists()


def test_a_name_with_a_path_separator_does_not_become_a_path(vault):
    """A note is a name, not a destination. `A/B` becomes `B`, inside the vault,
    rather than a file in a folder nobody asked for."""
    made = ob.create_note("../Deep", "x", folder=vault)
    assert Path(made["path"]).parent == vault
    assert not (vault.parent / "Deep.md").exists()


def test_a_name_a_filesystem_cannot_hold_is_refused(vault):
    for bad in ('a:b', 'a?b', 'a|b', 'a*b'):
        with pytest.raises(ob.VaultError):
            ob.create_note(bad, folder=vault)


def test_a_symlinked_note_pointing_outside_is_not_written(vault, tmp_path):
    """A note can be a link somewhere else entirely. Appending to it would write
    outside the folder the user pointed this at."""
    outside = tmp_path / "outside.md"
    outside.write_text("private", encoding="utf-8")
    link = vault / "Linked.md"
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("this filesystem cannot make symlinks")

    with pytest.raises(ob.VaultError):
        ob.append_note("nope", "Linked", folder=vault)
    assert outside.read_text(encoding="utf-8") == "private"


# ── the promise, stated as a test ───────────────────────────────────────────

def test_no_function_deletes_or_rewrites(vault):
    """The module may only append and create. This checks the source rather than
    trusting the docstring: an `unlink`, `rmtree` or `rename` added later would
    be the end of somebody's vault."""
    import ast
    src = Path(ob.__file__).read_text(encoding="utf-8")
    tree = ast.parse(src)
    forbidden = {"unlink", "rmdir", "rmtree", "rename", "truncate", "remove",
                 "removedirs", "move", "write_text", "write_bytes",
                 "os.remove", "os.replace"}
    # CALLS, not attributes: `"a".replace(x, y)` is string handling, and a
    # name-only check flagged it on the very first run.
    calls = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            calls.add(node.func.attr)
    assert not (forbidden & calls), f"destructive call in obsidian.py: {forbidden & calls}"


def test_writes_stay_inside_the_vault(vault):
    """Every returned path resolves under the vault it was given."""
    made = ob.create_note("Inside", "x", folder=vault)
    note = ob.read_note("Inside", folder=vault)
    for returned in (made["path"], note["path"]):
        assert Path(returned).resolve().is_relative_to(vault.resolve())


def test_the_config_path_is_per_os(monkeypatch, tmp_path):
    """The one platform where a wrong path silently finds nothing."""
    monkeypatch.setattr(ob.sys, "platform", "darwin")
    monkeypatch.setattr(ob.Path, "home", classmethod(lambda cls: tmp_path))
    assert "Application Support" in str(ob.obsidian_config_path())
    assert ob.obsidian_config_path().name == "obsidian.json"


# ── the plugin the model actually calls ─────────────────────────────────────

@pytest.fixture()
def plugin_vault(monkeypatch, vault):
    """The plugin, pointed at the fixture vault instead of the real machine."""
    from plugins import obsidian_notes as pn
    monkeypatch.setattr(ob, "known_vaults", lambda *a, **k: [vault])
    return pn


def test_the_plugin_finds_a_note_and_quotes_the_line(plugin_vault):
    out = plugin_vault.run({"action": "search", "query": "deposit"})
    assert "Housing contract" in out
    assert "- paid the deposit" in out, "the matching line is quoted, not summarised"


def test_the_plugin_reads_a_note_verbatim(plugin_vault):
    out = plugin_vault.run({"action": "read", "note": "Housing contract"})
    assert "Deposit due." in out


def test_the_plugin_appends_one_line_and_says_so(plugin_vault, vault):
    out = plugin_vault.run({"action": "append", "note": "Housing contract",
                            "text": "signed it"})
    assert "one line" in out
    assert (vault / "Housing contract.md").read_text(encoding="utf-8").endswith("signed it\n")


def test_the_plugin_creates_and_then_refuses_to_overwrite(plugin_vault):
    assert "Created" in plugin_vault.run({"action": "create", "title": "New one"})
    out = plugin_vault.run({"action": "create", "title": "New one"})
    assert "will not overwrite" in out


def test_a_vault_problem_becomes_a_sentence_not_a_traceback(plugin_vault, monkeypatch):
    monkeypatch.setattr(ob, "known_vaults", lambda *a, **k: [])
    out = plugin_vault.run({"action": "search", "query": "anything"})
    assert out.startswith("Sir,")
    assert "vault" in out.lower()


def test_an_unknown_action_asks_rather_than_guessing(plugin_vault):
    out = plugin_vault.run({"action": "frobnicate"})
    assert "Which did you mean" in out


def test_the_plugin_declares_files_and_the_manifest_matches_its_code():
    """The manifest's hash is checked in CI against the .py beside it, and its
    permission list has to say what the code really does."""
    from pathlib import Path
    from core import plugin_manifest as pm
    py = Path(ob.__file__).resolve().parent.parent / "plugins" / "obsidian_notes.py"
    manifest = pm.read(py, "obsidian_notes")
    assert manifest.problems == [], manifest.problems
    assert "files" in manifest.permissions
