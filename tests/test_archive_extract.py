"""Extracting an archive must not write outside the folder you named.

The bug these cover: actions/file_processor.py did

    dest = Path(params.get("destination", ...))   # straight from the model
    dest.mkdir(parents=True, exist_ok=True)
    shutil.unpack_archive(path, dest)

with no check on `destination` and no look at the member names. On Python 3.11
`tarfile` has no default extraction filter, so a tar member called `../x` is
written OUTSIDE `dest`. That was reproduced in a sandbox, not assumed.

Nothing here needs the network or an API key: the guard and the member check are
pure, and the two extraction tests build their own archives.
"""
from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest

from actions.file_processor import (
    _MAX_EXTRACT_BYTES,
    _extract_archive,
    _is_safe_member_name,
)


# ── the member check, on its own ────────────────────────────────────────────

SAFE_NAMES = [
    "readme.txt",
    "dir/nested/file.py",
    "./leading-dot.txt",
    "spaces in name.txt",
    "ünïcode.txt",
]

UNSAFE_NAMES = [
    "../escape.txt",
    "../../escape.txt",
    "dir/../../escape.txt",
    "/absolute.txt",
    "C:\\Windows\\system32\\evil.dll",
    "c:/windows/evil.dll",
    "..\\escape.txt",          # backslashes normalised first
    "",
    "nul\x00byte.txt",
]


@pytest.mark.parametrize("name", SAFE_NAMES)
def test_a_plain_relative_name_is_allowed(name):
    assert _is_safe_member_name(name) is True


@pytest.mark.parametrize("name", UNSAFE_NAMES)
def test_a_name_that_leaves_the_folder_is_refused(name):
    assert _is_safe_member_name(name) is False


# ── the whole extraction path ───────────────────────────────────────────────

@pytest.fixture()
def workdir(tmp_path, monkeypatch):
    """A private 'home' so the destination check has a known boundary."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    archive_dir = home / "Downloads"
    archive_dir.mkdir()
    return archive_dir


def _zip_with(path: Path, members: dict[str, str]) -> Path:
    with zipfile.ZipFile(path, "w") as z:
        for name, body in members.items():
            z.writestr(name, body)
    return path


def test_a_clean_archive_extracts(workdir):
    archive = _zip_with(workdir / "clean.zip",
                        {"a.txt": "one", "sub/b.txt": "two"})
    out = _extract_archive(archive, "")

    assert "Extracted to:" in out
    assert (workdir / "clean" / "a.txt").read_text() == "one"
    assert (workdir / "clean" / "sub" / "b.txt").read_text() == "two"


def test_a_traversing_archive_is_refused_and_writes_nothing(workdir):
    archive = _zip_with(workdir / "evil.zip", {"../escaped.txt": "boom"})

    out = _extract_archive(archive, "")

    assert "Refused to extract" in out
    assert not (workdir / "escaped.txt").exists()
    assert not (workdir / "evil" / "escaped.txt").exists()


def test_a_tar_with_a_parent_member_is_refused(workdir):
    """The exact shape that escaped on Python 3.11: a tar, not a zip."""
    import tarfile

    archive = workdir / "evil.tar"
    with tarfile.open(archive, "w") as t:
        data = b"boom"
        info = tarfile.TarInfo("../escaped.txt")
        info.size = len(data)
        t.addfile(info, io.BytesIO(data))

    out = _extract_archive(archive, "")

    assert "Refused to extract" in out
    assert not (workdir / "escaped.txt").exists()


def test_a_tar_with_a_symlink_is_refused(workdir):
    import tarfile

    archive = workdir / "link.tar"
    with tarfile.open(archive, "w") as t:
        info = tarfile.TarInfo("link")
        info.type = tarfile.SYMTYPE
        info.linkname = "/etc/passwd"
        t.addfile(info)

    assert "Refused to extract" in _extract_archive(archive, "")


def test_a_destination_outside_home_and_the_archive_is_refused(workdir, tmp_path):
    archive = _zip_with(workdir / "a.zip", {"x.txt": "x"})
    outside = tmp_path / "elsewhere"

    out = _extract_archive(archive, str(outside))

    assert "Refused to extract into" in out
    assert not outside.exists()


def test_a_destination_inside_home_is_accepted(workdir):
    archive = _zip_with(workdir / "b.zip", {"x.txt": "x"})
    target = workdir / "chosen"

    assert "Extracted to:" in _extract_archive(archive, str(target))
    assert (target / "x.txt").read_text() == "x"


def test_a_zip_bomb_sized_archive_is_refused(workdir, monkeypatch):
    """Size is checked from the headers, before a byte is decompressed."""
    archive = _zip_with(workdir / "big.zip", {"zeros.txt": "x"})
    monkeypatch.setattr("actions.file_processor._MAX_EXTRACT_BYTES", 0)

    assert "exceeds the" in _extract_archive(archive, "")
    assert _MAX_EXTRACT_BYTES > 0     # the real ceiling is still a real number
