"""obsidian_notes — the user's own vault, read and appended to.

WHY THIS IS SEPARATE FROM quick_notes
    `quick_notes` writes `config/notes/*.md` in a format this program invented.
    A vault is the opposite situation: the notes already exist, with their own
    folders, names and links, and an application that opens them. Writing this
    program's timestamped bullets into somebody's vault turns it into a mess
    they have to clean up.

WHAT IT WILL NOT DO
    * It never rewrites, renames, reorders or deletes a note. Appending is the
      only modification, and creating a new note refuses to touch an existing
      one — `core/obsidian.py` explains why that is the safety argument.
    * It does not guess between vaults, nor between two notes with one name.
      Both are questions back to the user.
    * It does not summarise what it read. A search result is the matching line
      as written, because a summary is the model's reading of the user's note.

PERMISSIONS
    `files`: it reads and appends inside the vault the user pointed it at.
"""
from __future__ import annotations

from core import obsidian

PLUGIN = {
    "name": "obsidian_notes",
    "description": (
        "Work with the user's Obsidian vault: find a note, read one, append a "
        "line to an existing note, or create a new note. Use for 'cari catatan "
        "tentang …', 'baca catatan X', 'tambahkan ke catatan harian', "
        "'buat catatan baru'. The user's notes are files in their own vault; "
        "nothing here rewrites or deletes one. Do not use this for this "
        "assistant's own reminders — that is quick_notes."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": "search, read, append or create.",
            },
            "query": {
                "type": "STRING",
                "description": "What to look for (action=search).",
            },
            "note": {
                "type": "STRING",
                "description": (
                    "The note's name without the .md extension (read/append). "
                    "Quote the name exactly as a previous search returned it."
                ),
            },
            "text": {
                "type": "STRING",
                "description": (
                    "One line to add (append) — the user's own words, not a "
                    "rephrasing. The note body for create."
                ),
            },
            "title": {
                "type": "STRING",
                "description": "The name of the new note (action=create).",
            },
            "folder": {
                "type": "STRING",
                "description": (
                    "Optional subfolder inside the vault for create. Omit to "
                    "put the note at the vault root."
                ),
            },
        },
        "required": ["action"],
    },
    "behavior": "BLOCKING",
    "scheduling": "WHEN_ASKED",
    "tier": "core",
}


def run(parameters: dict, player=None, session_memory=None) -> str:
    parameters = parameters or {}
    action = str(parameters.get("action") or "search").strip().lower()
    try:
        if action == "search":
            hits = obsidian.search(parameters.get("query", ""))
            if not hits:
                return ("Sir, no note in your vault matches that. I did not "
                        "search Obsidian's own settings or trash folders.")
            lines = [f"{h['title']} — {h['line']}" if h["line"] else h["title"]
                     for h in hits]
            return "Notes that match:\n" + "\n".join(f"• {line}" for line in lines)

        if action in ("read", "open"):
            note = obsidian.read_note(parameters.get("note", ""))
            tail = "\n(truncated)" if note["truncated"] else ""
            return f"{note['title']}:\n{note['text']}{tail}"

        if action in ("append", "add"):
            result = obsidian.append_note(parameters.get("text", ""),
                                          parameters.get("note", ""))
            return f"Added to {result['title']} — one line, nothing else changed."

        if action in ("create", "new"):
            made = obsidian.create_note(
                parameters.get("title") or parameters.get("note", ""),
                parameters.get("text", ""),
                folder_name=parameters.get("folder", ""))
            return f"Created {made['title']}."

        return (f"Sir, I know search, read, append and create — not {action!r}. "
                "Which did you mean?")
    except obsidian.VaultError as e:
        # These are all sentences meant for the user: no vault, two vaults, two
        # notes with one name, a name that already exists. None is a traceback.
        return f"Sir, {e}"
    except Exception as e:                      # noqa: BLE001 — a plugin
        return f"Sir, the vault read failed: {e}"
