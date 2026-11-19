"""Model-supplied paths stay inside the folder they claim to be in.

The bug these cover: actions/dev_agent.py built `project_dir / file_path` from a
path inside a language model's JSON plan, called `.parent.mkdir(parents=True)`
and wrote the file. The plan's paths are not names, they are suggestions — and
one of them can be "../../.bashrc".

Nothing here needs an API key: the function is pure.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from actions.dev_agent import _safe_rel, _safe_target


@pytest.fixture()
def project(tmp_path):
    root = tmp_path / "JarvisProjects" / "demo"
    root.mkdir(parents=True)
    (root / "utils").mkdir()
    return root


ACCEPTED = [
    ("main.py", "main.py"),
    ("utils/helpers.py", "utils/helpers.py"),
    ("sub/dir/deep.py", "sub/dir/deep.py"),
    ("./main.py", "main.py"),
    ("main.py\x00", None),          # a NUL byte is not a path; must not raise
]


@pytest.mark.parametrize("given,expected", ACCEPTED)
def test_paths_inside_the_project(project, given, expected):
    got = _safe_rel(project, given)
    assert got == expected or (expected and got == os.path.normpath(expected))


REJECTED = [
    "../evil.py",
    "../../evil.py",
    "a/../../b.py",
    "utils/../../outside.py",
    "~/x.py",
    "",                       # empty
    ".git/hooks/pre-commit",  # protected directory
    "venv/lib/x.py",
]


@pytest.mark.parametrize("given", REJECTED)
def test_paths_outside_or_protected(project, given):
    assert _safe_rel(project, given) is None


@pytest.mark.parametrize("given", ["C:\\Users\\x\\Startup\\a.py", "D:relative.py"])
def test_windows_drive_paths_are_rejected(project, given):
    """On Windows this is an absolute path; the check must hold everywhere."""
    assert _safe_rel(project, given) is None


def test_safe_target_returns_a_resolvable_path(project):
    target = _safe_target(project, "utils/helpers.py")
    assert target is not None
    assert target.is_absolute()
    assert project.resolve() in target.parents


def test_safe_target_refuses_traversal(project):
    assert _safe_target(project, "../evil.py") is None


def test_safe_target_refuses_a_symlink_leaving_the_folder(project, tmp_path):
    """A symlinked subdirectory is the subtle version of the same escape."""
    if os.name == "nt":
        pytest.skip("creating symlinks on Windows needs privileges")
    outside = tmp_path / "outside"
    outside.mkdir()
    (project / "link").symlink_to(outside, target_is_directory=True)
    assert _safe_target(project, "link/evil.py") is None


# ── the guard must not refuse a legitimate folder ───────────────────────────
#
# `_safe_rel` used to compare a RESOLVED left side against an UNRESOLVED right
# side:
#     (folder / rel).resolve().relative_to(folder)
# so a relative root, or a root reached through a symlink, failed for EVERY
# path — the agent refused to write anything and the symptom looked like a
# model failure. These are the two shapes that produced it.

def test_a_relative_root_still_accepts_a_path(tmp_path, monkeypatch):
    (tmp_path / "demo" / "utils").mkdir(parents=True)
    monkeypatch.chdir(tmp_path)

    assert _safe_rel(Path("demo"), "utils/helpers.py") == "utils/helpers.py"


def test_a_root_reached_through_a_symlink_still_accepts_a_path(tmp_path):
    if os.name == "nt":
        pytest.skip("creating symlinks on Windows needs privileges")
    real = tmp_path / "real"
    (real / "utils").mkdir(parents=True)
    link = tmp_path / "link"
    link.symlink_to(real, target_is_directory=True)

    assert _safe_rel(link, "utils/helpers.py") == "utils/helpers.py"
    assert _safe_target(link, "utils/helpers.py") is not None


def test_the_relative_root_still_refuses_an_escape(tmp_path, monkeypatch):
    """Fixing the false rejection must not open the real one."""
    (tmp_path / "demo").mkdir()
    monkeypatch.chdir(tmp_path)

    assert _safe_rel(Path("demo"), "../outside.py") is None
