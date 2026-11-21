"""Notes that belong to the user's Obsidian vault, not to this program.

WHY THIS IS NOT THE NOTEBOOK
    `plugins/_notes.py` writes `# Heading` and `- 2026-11-11 09:12 — text` into
    `config/notes/`. That format is this program's invention, and it was the
    right answer when there was nowhere else for a note to go.

    A vault is the other situation: the user already has a place where notes
    live, with their own structure, their own filenames, their own links, and an
    application that opens it. Writing this program's timestamped bullets into
    somebody's vault is how a vault becomes a mess the user has to clean up —
    and a note appended to `Daily/2026-11-11.md` is only useful if it respects
    how that file is organised.

WHAT A VAULT IS, READ FROM THE VAULT
    Nothing here assumes a layout. The vault is discovered from Obsidian's own
    config (`obsidian.json`), which is where the application records every vault
    it has ever opened; if that cannot be read, a folder is a vault when it
    contains `.obsidian`. There is no list of "supported" folder names, because
    a vault is the user's arrangement and a hardcoded `Daily/` would only ever
    fit the person who wrote it.

WRITES ARE APPENDS, AND THAT IS THE SAFETY ARGUMENT
    Every write here adds a line to an existing file or creates a NEW file. No
    function rewrites, reorders, reformats or deletes anything. A note-taking
    integration that can corrupt another application's notes is worse than no
    integration: Obsidian is where somebody's thesis lives. Creating a new file
    is refused if the name already exists, rather than overwriting the one that
    was there.

WHY THERE IS NO SYNC, INDEX OR CACHE
    Obsidian already has a search, an index and a sync. A second one here would
    be a stale copy of somebody else's database — the exact failure this project
    keeps designing against. Reading is a directory walk with a size cap, done
    when the question is asked.
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

# A vault is somebody's whole life; a "find my notes about X" query must not
# read all of it into memory. These two bounds are stated rather than tuned.
MAX_FILE_BYTES = 400_000        # one note; past this it is an attachment
MAX_SCAN_FILES = 800            # notes examined per search
MAX_RESULTS = 8

# What Obsidian will open as a note.
NOTE_SUFFIX = ".md"

# Nothing in this module writes outside a vault, but the SYMLINK case still
# matters: a note that resolves outside would be an append somewhere the user
# did not point at.
_MAX_NAME = 120


class VaultError(ValueError):
    """A vault that cannot be used, with a sentence saying why."""


# ── discovery ───────────────────────────────────────────────────────────────

def obsidian_config_path() -> Path:
    """Where Obsidian records its vaults, per OS.

    Windows keeps application data under `%APPDATA%`; macOS under
    `~/Library/Application Support`; Linux under `$XDG_CONFIG_HOME`.
    """
    home = Path.home()
    # `sys.platform`, not `os.name`: one source of truth, and one that a test
    # can change on any runner. `os.name == "nt"` short-circuited before the
    # macOS branch, so the macOS path was unreachable in a test on Windows.
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA") or home / "AppData" / "Roaming")
        return base / "obsidian" / "obsidian.json"
    if sys.platform == "darwin":
        return home / "Library" / "Application Support" / "obsidian" / "obsidian.json"
    base = Path(os.environ.get("XDG_CONFIG_HOME") or home / ".config")
    return base / "obsidian" / "obsidian.json"


def known_vaults(config_path: Path | None = None) -> list[Path]:
    """Every vault Obsidian has a record of, newest-looking first.

    A config that is missing, unreadable or a different shape is not an error:
    the caller falls back to looking for `.obsidian` folders, and a user who
    never opened Obsidian gets "I could not find a vault" rather than a
    traceback from a JSON parser.
    """
    path = config_path or obsidian_config_path()
    try:
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, ValueError):
        return []
    vaults = data.get("vaults") if isinstance(data, dict) else None
    if not isinstance(vaults, dict):
        return []
    found = []
    for entry in vaults.values():
        if not isinstance(entry, dict):
            continue
        raw = str(entry.get("path") or "").strip()
        if raw:
            candidate = Path(raw).expanduser()
            if candidate.is_dir():
                found.append(candidate)
    return found


def is_vault(path) -> bool:
    """True when `path` is a folder Obsidian would open as a vault."""
    try:
        return Path(path).is_dir() and (Path(path) / ".obsidian").is_dir()
    except OSError:
        return False


def default_vault(config_path: Path | None = None) -> Path | None:
    """The vault to use when the user has not chosen one.

    ONLY when there is exactly one candidate. Picking the first of several is
    how a note lands in the wrong vault: the user has three, this decides by
    directory order, and nothing says which one was used.
    """
    found = known_vaults(config_path)
    if len(found) == 1:
        return found[0]
    return None


def resolve(folder=None, config_path: Path | None = None) -> Path:
    """The vault to act on, or a `VaultError` explaining what to do instead."""
    if folder:
        path = Path(str(folder)).expanduser()
        if not path.is_dir():
            raise VaultError(f"there is no folder at {path}.")
        if not is_vault(path):
            raise VaultError(
                f"{path.name!r} is not an Obsidian vault — a vault has a "
                ".obsidian folder inside it.")
        return path

    found = known_vaults(config_path)
    if not found:
        raise VaultError(
            "I cannot find an Obsidian vault on this machine. Obsidian records "
            "them in its own config, and there is none there; open Obsidian "
            "once, or tell me the folder.")
    if len(found) == 1:
        return found[0]
    names = ", ".join(v.name for v in found[:4])
    raise VaultError(
        f"there are {len(found)} vaults ({names}) and I will not guess which "
        "one — say which vault to use.")


# ── reading ─────────────────────────────────────────────────────────────────

def _notes(vault: Path):
    """Every note in the vault, skipping Obsidian's own bookkeeping folders."""
    count = 0
    for root, dirs, files in os.walk(vault):
        # `.obsidian`, `.trash` and any other dotted folder is Obsidian's own
        # state, not the user's notes. Walking into them searches settings and
        # recently-deleted notes, which is the opposite of helpful.
        dirs[:] = sorted(d for d in dirs if not d.startswith("."))
        for name in sorted(files):
            if not name.lower().endswith(NOTE_SUFFIX) or name.startswith("."):
                continue
            path = Path(root) / name
            try:
                if path.stat().st_size > MAX_FILE_BYTES:
                    continue
            except OSError:
                continue
            count += 1
            if count > MAX_SCAN_FILES:
                return
            yield path


def _title(path: Path, vault: Path) -> str:
    """A note's name as a person refers to it: no extension, vault-relative."""
    try:
        rel = path.relative_to(vault)
    except ValueError:
        rel = Path(path.name)
    # Always "/" — a title is a name the user and the model both quote, and it
    # must not change spelling because the note was read on Windows.
    return rel.with_suffix("").as_posix()


def search(query: str, folder=None, limit: int = MAX_RESULTS,
           config_path: Path | None = None) -> list[dict]:
    """Notes whose name or text contains `query`, best matches first.

    Scoring is deliberately simple and stated: a name match beats a text match,
    because a note called "Housing contract" is about the contract whatever its
    body says. Everything returned carries the path, so the answer can name the
    file rather than pretend to have read the user's mind.
    """
    vault = resolve(folder, config_path)
    needle = str(query or "").strip().lower()
    if not needle:
        raise VaultError("what should I look for? Give me a word from the note.")

    hits = []
    for path in _notes(vault):
        title = _title(path, vault)
        in_name = needle in title.lower()
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        in_text = needle in text.lower()
        if not (in_name or in_text):
            continue
        hits.append({
            "title": title,
            "path": str(path),
            "name_match": in_name,
            # The line that matched, so the answer can quote instead of
            # summarising. A summarised search result is the model's reading of
            # the user's note, which is the thing that must not happen here.
            "line": _matching_line(text, needle) if in_text else "",
        })
    hits.sort(key=lambda h: (not h["name_match"], h["title"].lower()))
    return hits[:max(1, min(int(limit), MAX_RESULTS * 2))]


def _matching_line(text: str, needle: str) -> str:
    for line in text.splitlines():
        if needle in line.lower():
            cleaned = " ".join(line.split())
            return cleaned[:200]
    return ""


def read_note(name: str, folder=None, config_path: Path | None = None,
              max_chars: int = 4000) -> dict:
    """One note, by the name a person would use.

    Accepts `Housing contract`, `Housing contract.md` and a path relative to the
    vault. Ambiguity is refused rather than resolved: two notes with the same
    name in different folders is a question, not a coin flip.
    """
    vault = resolve(folder, config_path)
    wanted = str(name or "").strip().replace("\\", "/")
    if not wanted:
        raise VaultError("which note?")
    if not wanted.lower().endswith(NOTE_SUFFIX):
        wanted += NOTE_SUFFIX

    # Strip the extension BEFORE lowering the string. Lowering is
    # length-preserving, so this was right by luck — but `[:-3]` on a string
    # that no longer ends in ".md" is exactly the kind of off-by-three that
    # turns a case-insensitive lookup into a silent miss.
    stem = wanted[:-len(NOTE_SUFFIX)] if wanted.lower().endswith(NOTE_SUFFIX) else wanted
    lowered = stem.lower()
    # A name identifies a note across the whole vault: "Housing contract" means
    # the one the user means, and if two folders have one, the note under
    # `Archive/` is not a different answer — it is a question to ask.
    exact = [p for p in _notes(vault)
             if _title(p, vault).replace("\\", "/").lower() == lowered
             or Path(_title(p, vault).replace("\\", "/")).name.lower() == lowered]
    if not exact:
        raise VaultError(f"there is no note called {name!r} in this vault.")
    if len(exact) > 1:
        # Group by the file that actually gets written, not by the name the
        # caller used: on a case-insensitive filesystem `House.md` and
        # `house.md` are one file, and "say which one" would be a question with
        # no wrong answer.
        real = {p.resolve() for p in exact}
        if len(real) > 1:
            where = "; ".join(str(p.relative_to(vault)) for p in exact[:3])
            raise VaultError(
                f"{len(exact)} notes are called {name!r} ({where}) — say which one.")

    path = exact[0]
    try:
        if not _inside(path.resolve(), vault.resolve()):
            # A symlinked note can point anywhere; appending to it would write
            # outside the folder the user pointed this at.
            raise VaultError("that note links outside the vault, so I will not touch it.")
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as e:
        raise VaultError(f"could not read that note: {e}") from e

    return {
        "title": _title(path, vault),
        "path": str(path),
        "vault": str(vault),
        "text": text[:max_chars],
        "truncated": len(text) > max_chars,
    }


# ── writing, append-only ────────────────────────────────────────────────────

def _inside(candidate: Path, root: Path) -> bool:
    """True when `candidate` is `root` or below it."""
    try:
        candidate.relative_to(root)
        return True
    except ValueError:
        return False


def _clean_line(text: str) -> str:
    """One line, no control characters. The user's words, reshaped only."""
    text = " ".join(str(text or "").split())
    return re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text).strip()


def append_note(text: str, name: str, folder=None,
                config_path: Path | None = None) -> dict:
    """Add one line to an existing note. Never creates, never rewrites.

    Appending is the operation with no way to lose somebody's work: the file
    stays exactly as it was, with one line more. Creating is a separate call so
    that "add to my daily note" failing loudly beats silently inventing a file
    in a folder the user organises differently.
    """
    line = _clean_line(text)
    if not line:
        raise VaultError("there was nothing to add — tell me the line itself.")
    target = _existing_note(name, folder, config_path)
    path, vault = target["path"], target["vault"]
    try:
        _append_line(Path(path), line)
    except OSError as e:
        raise VaultError(f"could not write to that note: {e}") from e
    return {"title": _title(Path(path), vault), "path": path,
            "folder": target["folder"]}


def create_note(name: str, text: str = "", folder_name: str = "",
                folder=None, config_path: Path | None = None) -> dict:
    """A NEW note. Refuses when the name already exists — see the module docstring."""
    vault = resolve(folder, config_path)
    title = _clean_line(name)
    if not title:
        raise VaultError("what should the note be called?")

    # No path separators: a name is a name. A caller that wants a folder says
    # so through `folder_name`, and that is validated on its own.
    title = title.replace("\\", "/").split("/")[-1]
    if title.lower().endswith(NOTE_SUFFIX):
        title = title[: -len(NOTE_SUFFIX)]
    if len(title) > _MAX_NAME:
        raise VaultError("that name is too long for a filename.")
    if any(ch in title for ch in '<>:"|?*'):
        raise VaultError("that name has a character a filename cannot hold.")

    target_dir = vault
    if folder_name:
        clean_folder = _clean_line(folder_name).strip("/").replace("\\", "/")
        if ".." in clean_folder.split("/"):
            raise VaultError("that folder is outside the vault.")
        target_dir = vault / clean_folder
    try:
        target_dir.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise VaultError(f"could not create that folder: {e}") from e

    path = target_dir / f"{title}{NOTE_SUFFIX}"
    if path.exists():
        raise VaultError(
            f"a note called {title!r} already exists — I will not overwrite it. "
            "Say 'add to' to append instead.")

    body = _clean_line(text)
    content = f"# {title}\n\n{body}\n" if body else f"# {title}\n"
    try:
        # `open(..., "x")`: exclusive creation. The `exists()` check above is
        # the explanation the user gets; this is the guarantee. A file created
        # between the check and the write — by Obsidian itself, by sync — makes
        # this raise instead of being silently replaced.
        with path.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(content)
    except FileExistsError as e:
        raise VaultError(
            f"a note called {title!r} already exists — I will not overwrite it.") from e
    except OSError as e:
        raise VaultError(f"could not create that note: {e}") from e
    return {"title": _title(path, vault), "path": str(path)}


def _existing_note(name: str, folder, config_path) -> dict:
    found = read_note(name, folder=folder, config_path=config_path, max_chars=1)
    path = Path(found["path"])
    vault = Path(found["vault"])
    try:
        rel_folder = path.parent.relative_to(vault)
    except ValueError:
        rel_folder = Path(".")
    return {"path": path, "vault": vault, "folder": str(rel_folder)}


def _append_line(path: Path, line: str) -> None:
    """Append, keeping the file's own newline convention.

    A note created on Windows may end its lines with CRLF; appending `\\n` into
    it produces a file with two conventions in it, which Obsidian renders with
    stray characters. The existing convention is read from the file and matched.
    """
    needs_newline = False
    newline = "\n"
    try:
        with path.open("rb") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            if size:
                f.seek(max(0, size - 2))
                tail = f.read()
                if not tail.endswith(b"\n"):
                    needs_newline = True
                elif tail.endswith(b"\r\n"):
                    newline = "\r\n"
    except OSError:
        needs_newline = True

    with path.open("a", encoding="utf-8", newline="") as f:
        if needs_newline:
            f.write(newline)
        f.write(line + newline)


__all__ = [
    "MAX_FILE_BYTES", "MAX_SCAN_FILES", "MAX_RESULTS", "VaultError",
    "obsidian_config_path", "known_vaults", "is_vault", "default_vault",
    "resolve", "search", "read_note", "append_note", "create_note",
]
