"""quick_notes — keep what the user asked you to remember, in plain text.

WHAT THIS IS FOR
    "Catat: bayar kos tanggal 5" and "apa saja tugas saya?" are two of the most
    common things anybody says to an assistant, and both are worse when the
    model answers from its own recollection: a note the user decided to keep is
    not a summary of what they said. This writes the note down, reads it back
    verbatim, and moves a finished task to the archive without deleting it.

THE THREE NOTEBOOKS
    inbox    everything captured, in order — the default
    todo     tasks still open, one per line
    archive  tasks that are done, kept rather than removed

    Files, not a database: `config/notes/*.md` opens in Notepad, survives being
    copied to another machine, and cannot corrupt anything the app needs to
    boot. The format and the reasons are in `plugins/_notes.py`.

WHAT IT WILL NOT DO
    * It does not format or paraphrase a note. It echoes what was stored, so the
      user can see the difference between what they said and what was saved.
    * It does not guess which task is done. A phrase matching three open todos
      is a question back, not a coin flip.
    * It reads nothing but its own three files — no `memory/`, no other
      plugin's config.
"""
from __future__ import annotations

from plugins import _notes

PLUGIN = {
    "name": "quick_notes",
    "description": (
        "Save a note or a to-do in plain text and read it back later. Use for "
        "'catat …', 'remember that …', 'note this down', 'add a task' "
        "(action=add), for 'what are my notes/tasks' (action=list), and for "
        "'mark … as done' (action=done). The notes are files under "
        "config/notes/ that the user can open themselves. Do not use this to "
        "remember a preference about how to behave — that is session memory."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "add (default), list, or done.",
            },
            "text": {
                "type": "STRING",
                "description": ("The note itself when adding, or a word or phrase "
                                "from the task when marking one done. Keep the "
                                "user's own words; do not tidy them."),
            },
            "notebook": {
                "type": "STRING",
                "description": ("inbox for a note (default), todo for a task to be "
                                "done. 'archive' is written to by 'done', not by hand."),
            },
        },
        "required": ["action"],
    },
    # Writing a line to a file is instant; nothing here should make the
    # assistant stop talking.
    "behavior": "NON_BLOCKING",
    "scheduling": "WHEN_IDLE",
    "tier": "core",
}


def _notebook(parameters: dict, action: str) -> str:
    """Default notebook per action: adding a task that is not a task is the
    single most common mix-up, so 'add' + no notebook means inbox, and 'done'
    only ever looks at the todo list."""
    raw = str(parameters.get("notebook") or "").strip().lower()
    if raw in ("", "note", "notes", "catatan"):
        return "todo" if action == "done" else "inbox"
    return raw


def run(parameters: dict, player=None, session_memory=None) -> str:
    parameters = parameters or {}
    action = str(parameters.get("action") or "add").strip().lower()
    text = parameters.get("text", "")
    try:
        if action in ("add", "save", "write", "remember", "note"):
            notebook = _notebook(parameters, "add")
            if notebook == "archive":
                return ("Sir, the archive is written by marking a task done, not "
                        "by hand — say 'mark … as done' instead.")
            stored = _notes.append(notebook, text)
            return f"Saved to {notebook}: {stored}"

        if action in ("list", "read", "show"):
            notebook = _notebook(parameters, "list")
            return f"Sir, {_notes.digest(notebook, limit=8)}"

        if action in ("done", "complete", "finish", "archive"):
            what, left = _notes.complete(text)
            return f"Done: {what}. {left} task{'s' if left != 1 else ''} still open."

        return (f"Sir, I know add, list and done — not {action!r}. "
                "Which did you mean?")
    except LookupError as e:
        # "no match" and "too many matches" are the user's problem to resolve,
        # and both are sentences rather than tracebacks.
        return f"Sir, {e}"
    except ValueError as e:
        message = str(e)
        return f"Sir, {message[0].lower() + message[1:] if message else message}"
