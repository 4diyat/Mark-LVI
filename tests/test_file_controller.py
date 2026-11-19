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


@pytest.fixture()
def home(tmp_path, monkeypatch):
    root = tmp_path / "home"
    for name in ("Desktop", "Documents", "Downloads", "Pictures", "Music", "Videos"):
        (root / name).mkdir(parents=True)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: root))
    monkeypatch.setattr(file_controller, "_SAFE_ROOTS", [root])
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
