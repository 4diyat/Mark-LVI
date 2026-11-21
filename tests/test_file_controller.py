"""file_controller may not touch anything outside the user's folders.

WHY THIS FILE DID NOT EXIST
    actions/file_controller.py is 466 statements of delete, move, copy and write,
    and no test named it. `tests/test_coverage_map.py` only walked `core/`,
    `memory/` and `dashboard/`, so "every big module has a test or a reason"
    stopped exactly where the code starts deleting files.

WHAT IS GUARDED HERE
    The path guard (`_is_safe_path`, `_resolve_path`) and the refusal paths of
    delete/move that sit behind them. Nothing here trashes a real file: the
    "outside" cases are refused before they reach it, and the delete case that
    would run is redirected to a temp folder by monkeypatching the roots.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from actions import file_controller
from core import file_access


@pytest.fixture()
def home(tmp_path, monkeypatch):
    root = tmp_path / "home"
    for name in ("Desktop", "Documents", "Downloads", "Pictures", "Music", "Videos"):
        (root / name).mkdir(parents=True)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: root))
    # The boundary is a policy now; a test points it at the throw-away home.
    monkeypatch.setattr(file_controller, "_policy",
                        lambda: file_access.Policy(enabled=False, roots=(), home=root))
    return root


# ── the guard ───────────────────────────────────────────────────────────────

def test_a_file_in_the_home_folder_is_safe(home):
    assert file_controller._is_safe_path(home / "Desktop" / "notes.txt") is True


def test_a_path_outside_the_home_folder_is_not_safe(home, tmp_path):
    assert file_controller._is_safe_path(tmp_path / "outside.txt") is False


def test_a_traversal_out_of_home_is_not_safe(home):
    escape = home / "Desktop" / ".." / ".." / "secret.txt"
    assert file_controller._is_safe_path(escape) is False


def test_a_symlink_out_of_home_is_not_safe(home, tmp_path):
    import os
    if os.name == "nt":
        pytest.skip("creating symlinks on Windows needs privileges")
    outside = tmp_path / "outside"
    outside.mkdir()
    (home / "Desktop" / "link").symlink_to(outside, target_is_directory=True)
    assert file_controller._is_safe_path(home / "Desktop" / "link" / "x.txt") is False


# ── shortcut names ──────────────────────────────────────────────────────────

def test_a_shortcut_name_resolves_to_the_real_folder(home):
    assert file_controller._resolve_path("desktop") == home / "Desktop"


def test_a_quoted_shortcut_is_the_same_folder(home):
    assert file_controller._resolve_path('"desktop"') == home / "Desktop"


def test_a_shortcut_with_a_subpath_keeps_the_shortcut(home):
    resolved = file_controller._resolve_path("desktop/sub/file.txt")
    assert resolved == home / "Desktop" / "sub" / "file.txt"


def test_an_absolute_path_is_taken_literally(home):
    target = home / "Documents" / "a.txt"
    assert file_controller._resolve_path(str(target)) == target


# ── the operations refuse before they touch anything ────────────────────────

def test_delete_refuses_a_path_outside_home(home, tmp_path, monkeypatch):
    victim = tmp_path / "precious.txt"
    victim.write_text("keep me")
    monkeypatch.setattr(file_controller, "_safe_trash",
                        lambda p: pytest.fail("must not reach the trash"))

    out = file_controller.delete_file(str(victim))

    assert "Access denied" in out
    assert victim.read_text() == "keep me"


def test_delete_refuses_the_desktop_folder_itself(home, monkeypatch):
    monkeypatch.setattr(file_controller, "_safe_trash",
                        lambda p: pytest.fail("must not reach the trash"))
    assert "Protected directory" in file_controller.delete_file("desktop")


def test_delete_reports_a_missing_file(home):
    assert "Not found" in file_controller.delete_file("desktop", "nope.txt")


def test_delete_of_a_plain_file_goes_through_the_trash(home, monkeypatch):
    victim = home / "Desktop" / "old.txt"
    victim.write_text("bye")
    seen = []

    def fake_trash(path):
        seen.append(path)
        return f"Moved to Trash: {path.name}"

    monkeypatch.setattr(file_controller, "_safe_trash", fake_trash)
    out = file_controller.delete_file("desktop", "old.txt")

    assert seen and seen[0] == victim
    assert "Moved to Trash" in out


def test_move_refuses_a_source_outside_home(home, tmp_path):
    victim = tmp_path / "outside.txt"
    victim.write_text("x")

    out = file_controller.move_file(str(victim), destination="desktop")

    assert "Access denied" in out
    assert victim.exists()


def test_move_refuses_a_destination_outside_home(home, tmp_path):
    src = home / "Desktop" / "a.txt"
    src.write_text("x")

    out = file_controller.move_file("desktop", "a.txt",
                                    destination=str(tmp_path / "elsewhere"))

    assert "Access denied" in out
    assert src.exists()


def test_a_move_inside_home_actually_moves(home):
    src = home / "Desktop" / "a.txt"
    src.write_text("payload")

    out = file_controller.move_file("desktop", "a.txt", destination="documents")

    assert not src.exists()
    assert (home / "Documents" / "a.txt").read_text() == "payload"
    assert "a.txt" in out


# ── rename may not leave the folder, and may not be a path at all ───────────
#
# `rename_file` built `target.parent / new_name` and only ever asked
# `_is_safe_path` about the ORIGINAL file. `Path("/a/b") / "/etc/passwd"` is
# "/etc/passwd" — the left side is discarded without a word — so an absolute
# `new_name` moved the file wherever the model said.

@pytest.mark.parametrize("given", [
    "../escape.txt",          # climbs
    "../../escape.txt",
    "/etc/passwd",            # absolute: parent is discarded
    "sub/file.txt",           # a path, not a name
    "sub\\file.txt",
    "C:\\Windows\\evil.txt",
    "",                       # nothing
    ".",
    "..",
])
def test_a_rename_that_is_not_a_plain_name_is_refused(home, given):
    src = home / "Desktop" / "a.txt"
    src.write_text("payload")

    out = file_controller.rename_file("desktop", "a.txt", given)

    assert "not a file name" in out or "No new name" in out
    assert src.exists(), "the original must still be where it was"
    assert src.read_text() == "payload"


def test_a_plain_rename_still_works(home):
    src = home / "Desktop" / "a.txt"
    src.write_text("payload")

    out = file_controller.rename_file("desktop", "a.txt", "b.txt")

    assert not src.exists()
    assert (home / "Desktop" / "b.txt").read_text() == "payload"
    assert "Renamed" in out


def test_a_rename_onto_an_existing_name_is_refused(home):
    (home / "Desktop" / "a.txt").write_text("a")
    (home / "Desktop" / "b.txt").write_text("b")

    out = file_controller.rename_file("desktop", "a.txt", "b.txt")

    assert "already exists" in out
    assert (home / "Desktop" / "b.txt").read_text() == "b"


# ── move and copy must not overwrite ────────────────────────────────────────
#
# shutil.move and shutil.copy2 REPLACE an existing destination, and the
# replaced file is gone. That is the one outcome the undo stack cannot repair,
# so the operation has to decline instead.

def test_a_move_onto_an_existing_file_does_not_destroy_it(home):
    src = home / "Desktop" / "a.txt"
    src.write_text("NEW")
    victim = home / "Documents" / "a.txt"
    victim.write_text("ORIGINAL")

    out = file_controller.move_file("desktop", "a.txt", destination="documents")

    assert "already exists" in out
    assert victim.read_text() == "ORIGINAL", "the existing file must survive"
    assert src.read_text() == "NEW", "the source must not have gone anywhere"


def test_a_copy_onto_an_existing_file_does_not_destroy_it(home):
    src = home / "Desktop" / "a.txt"
    src.write_text("NEW")
    victim = home / "Documents" / "a.txt"
    victim.write_text("ORIGINAL")

    out = file_controller.copy_file("desktop", "a.txt", destination="documents")

    assert "already exists" in out
    assert victim.read_text() == "ORIGINAL"
    assert src.read_text() == "NEW"


def test_a_copy_into_a_free_name_still_works(home):
    (home / "Desktop" / "a.txt").write_text("payload")

    out = file_controller.copy_file("desktop", "a.txt", destination="documents")

    assert "Copied" in out
    assert (home / "Documents" / "a.txt").read_text() == "payload"
    assert (home / "Desktop" / "a.txt").exists()


def test_undoing_a_copy_trashes_it_rather_than_deleting_it(home, monkeypatch):
    """`rmtree` on undo is permanent; the user may have edited the copy."""
    (home / "Desktop" / "a.txt").write_text("payload")
    file_controller.copy_file("desktop", "a.txt", destination="documents")

    trashed = []
    monkeypatch.setattr(file_controller, "_safe_trash",
                        lambda p: trashed.append(p) or f"Moved to Trash: {p.name}")

    from core import undo
    undo.undo_last()

    assert trashed, "the copy should have gone to the Trash"
    assert trashed[0].name == "a.txt"
    assert home / "Documents" in trashed[0].parents
