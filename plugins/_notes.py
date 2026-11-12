"""The note store and the text around it — everything a plugin needs, nothing more.

WHY A PLUGIN AND NOT AN ACTION
    "Catat: servis motor tanggal 20" is a thing people say to an assistant, and
    a note is the one kind of memory that must NOT be left to the model: a note
    is a fact the user decided to keep, and a summary of it is not the same
    thing. It also has no business in `memory/long_term.json`, which is the
    assistant's own recollection and is rewritten by the summariser.

WHERE THE NOTES LIVE
    `config/notes/` — the folder that already holds the app's state and is
    already what a user backs up or moves to another machine. Three files, one
    per kind, so a note can be read with Notepad and nothing here can corrupt
    anything the app needs to boot:

        config/notes/inbox.md      everything captured, newest at the bottom
        config/notes/todo.md       open tasks, one per line
        config/notes/archive.md    tasks that are done

WHY MARKDOWN AND NOT JSON
    A JSON file is this program's format; a Markdown file is the user's. When a
    note is written every day, the difference between "you can open it" and
    "you can open it with the right app" decides whether it gets used.

WHY THE CLOCK IS A PARAMETER
    Every date in here is the USER's date, and this app runs on laptops in
    Jakarta, Berlin and Seattle. `now` is injected, the local timezone is used
    by default, and the tests pass a fixed instant — a note filed under
    yesterday because the container is on UTC is a bug nobody would notice for
    weeks.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

# How much of a note is echoed back. Long enough to recognise, short enough to
# read aloud without a paragraph of somebody's meeting minutes.
ECHO_CHARS = 80

NOTEBOOKS = {
    "inbox": "inbox.md",
    "todo": "todo.md",
    "archive": "archive.md",
}


def notes_dir() -> Path:
    """`config/notes` beside the running app, created on first use.

    Imported lazily (memory.config_manager builds its paths at import time and
    a plugin can be loaded before the app is ready) and never fatal: a plugin
    that cannot find the config folder still has to say something useful rather
    than crash the loader.
    """
    try:
        from memory.config_manager import CONFIG_DIR
        root = Path(CONFIG_DIR)
    except Exception:
        root = Path(__file__).resolve().parent.parent / "config"
    folder = root / "notes"
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def note_file(notebook: str) -> Path:
    name = NOTEBOOKS.get(notebook)
    if name is None:
        raise ValueError(
            f"I keep three notebooks — {', '.join(NOTEBOOKS)} — not {notebook!r}.")
    return notes_dir() / name


def _clean(text: str) -> str:
    """One line, no markdown headings, no leading bullets.

    A newline inside a note would turn one entry into two on the next read, and
    a leading '#' would be read back as a heading. The text is the user's; only
    its shape is ours.
    """
    collapsed = " ".join(str(text or "").split())
    while collapsed[:1] in ("#", "-", "*", "•"):
        collapsed = collapsed[1:].lstrip()
    return collapsed.strip()


def append(notebook: str, text: str, *, now: datetime | None = None) -> str:
    """Add one line to a notebook. Returns the text as it was stored."""
    line_text = _clean(text)
    if not line_text:
        raise ValueError("there was nothing to write — tell me the note itself.")
    stamp = (now or datetime.now()).strftime("%Y-%m-%d %H:%M")
    path = note_file(notebook)
    existing = path.read_text(encoding="utf-8") if path.is_file() else ""
    prefix = "" if existing else f"# {notebook.capitalize()} — written by MARK LVI\n\n"
    with path.open("a", encoding="utf-8") as handle:
        handle.write(f"{prefix}- {stamp} — {line_text}\n")
    return line_text


def entries(notebook: str) -> list[str]:
    """The note lines, oldest first. Headers and blank lines are not notes."""
    path = note_file(notebook)
    if not path.is_file():
        return []
    return [line.rstrip("\n") for line in path.read_text(encoding="utf-8").splitlines()
            if line.startswith("- ")]


def complete(index_text: str, *, now: datetime | None = None) -> tuple[str, int]:
    """Move the matching todo(s) to the archive.

    Matching is a case-insensitive substring on the note text — the part after
    the date — because that is what the model can quote back from what was just
    read out. Ambiguity is not resolved by picking one: if a phrase matches
    three notes, the answer says so and nothing moves. Silently archiving the
    wrong task is the failure that makes a task list untrustworthy.
    """
    needle = _clean(index_text).lower()
    if not needle:
        raise ValueError("which task is done? I need a word from it.")
    open_lines = entries("todo")
    hits = [line for line in open_lines if needle in _body(line).lower()]
    if not hits:
        raise LookupError(f"no open todo matches {index_text!r}.")
    if len(hits) > 1:
        raise LookupError(
            f"{len(hits)} open todos match {index_text!r} — say a longer phrase: "
            + "; ".join(_body(line)[:40] for line in hits[:3]))
    hit = hits[0]
    remaining = [line for line in open_lines if line != hit]
    note_file("todo").write_text(_render("todo", remaining), encoding="utf-8")
    stamp = (now or datetime.now()).strftime("%Y-%m-%d %H:%M")
    archive = note_file("archive")
    # The archive gets the same header as every other notebook the first time a
    # task lands in it; appending to a file that does not exist yet left it
    # looking like a fragment instead of a file a person wrote.
    fresh = not archive.is_file() or not archive.stat().st_size
    with archive.open("a", encoding="utf-8") as handle:
        if fresh:
            handle.write("# Archive — written by MARK LVI\n\n")
        handle.write(f"{hit}  (done {stamp})\n")
    return _body(hit), len(remaining)


def _body(line: str) -> str:
    """A stored line without its bullet and date: `- 2026-11-11 09:12 — call Budi`."""
    text = line[2:] if line.startswith("- ") else line
    return text.split("—", 1)[1].strip() if "—" in text else text.strip()


def _render(notebook: str, lines: list[str]) -> str:
    # Always a header: a todo file with no header would be read back as empty
    # by `entries()` and then rewritten without one, losing the only clue that
    # a human wrote in it too.
    head = f"# {notebook.capitalize()} — written by MARK LVI\n\n"
    return head + ("\n".join(lines) + "\n" if lines else "")


def digest(notebook: str, limit: int = 5) -> str:
    """The last few notes as one sentence, for the answer that confirms a write.

    `total` and `shown` are separate on purpose: "saved 12, here are the last 5"
    is honest, and "you have 5 notes" when there are 12 is not.
    """
    rows = entries(notebook)
    shown = rows[-limit:] if limit else []
    parts = [f"{_body(row)}" for row in shown]
    # The count is right either way, but "2 notes in todo" reads like a bug to
    # the person who just asked about their tasks.
    noun = {"todo": "task", "archive": "finished task"}.get(notebook, "note")
    head = (f"{len(rows)} {noun}{'s' if len(rows) != 1 else ''} in {notebook}"
            if rows else f"{notebook} is empty")
    if not parts:
        return head + "."
    return head + "; last: " + " | ".join(parts) + "."
