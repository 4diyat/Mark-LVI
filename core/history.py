"""The conversation, kept where a person can read it.

WHY THIS IS NOT THE LOG
    `logs/jarvis.log` already contains every turn, and that is exactly why it
    is the wrong place to look for them: it is a diagnostic file, it rotates
    at 2 MB, it records an exception in the middle of a sentence, and after a
    week the thing you said on Tuesday is gone. A conversation is not a
    diagnostic. Mixing the two means the answer to "what did we decide
    yesterday" depends on how many errors happened since.

WHY THIS IS NOT THE MEMORY EITHER
    `memory/memory_manager.py` keeps what the assistant was *told to remember*
    — curated, summarised, and trimmed to what fits in a prompt. History is the
    raw record: what was said, in order, including the parts nobody asked it to
    remember. One is for the model, the other is for the person.

WHAT A FILE IS
    One JSON object per line (JSONL): a transcript stays readable with a text
    editor, survives a half-written last line, and can be appended without
    rewriting the whole file — which matters because this is written while the
    user is talking and must never make them wait.

    Each line: {"at": ISO-8601 local, "role": "user"|"assistant", "text": ...,
                "session": "<id>"}

WHY A SESSION ID RATHER THAN ONE ENDLESS FILE
    A month of conversation in one file is a file nobody opens. Sessions are
    what a person actually remembers ("yesterday evening", "when we set up the
    printer"), and a session id also lets a crash-recovered process continue
    the transcript it was already writing instead of starting a second one.

FAILURE POLICY
    Never raises, never blocks the caller, and drops rather than grows without
    bound. A conversation that cannot be written is a conversation that still
    happened; losing the record of it must not also lose the session. The same
    rule `core/logbook.py` follows, for the same reason.
"""
from __future__ import annotations

import json
import re
import sys
import threading
from datetime import datetime, timedelta
from pathlib import Path

# One file per day keeps a folder scannable and caps what one corrupt write can
# damage. 2 MB/day of plain text is roughly a very talkative day, so the bound
# only ever trips on a loop.
MAX_BYTES_PER_FILE = 2_000_000

# What a single turn may add. A pasted document is a legitimate turn; a runaway
# loop is not, and both look the same from here.
MAX_TEXT = 4_000

# How many days of history are kept. Beyond this the files are deleted on the
# next write — a limit that is stated, rather than a folder that grows until
# the disk does something surprising.
KEEP_DAYS = 30

_lock = threading.RLock()
_session_id: str | None = None

_ROLES = ("user", "assistant")
_UNSAFE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def history_dir() -> Path:
    """Where transcripts live: `logs/history/`, created on first use.

    Under `logs/` because it is the one folder the user already knows how to
    find (the README sends them there for the log), and a second top-level
    folder is a second thing to explain.
    """
    path = _base_dir() / "logs" / "history"
    path.mkdir(parents=True, exist_ok=True)
    return path


def session_id() -> str:
    """This process's session id, created once and reused.

    Not a random uuid: a timestamp sorts, tells a person when the session was,
    and is still unique enough for one machine.
    """
    global _session_id
    with _lock:
        if _session_id is None:
            _session_id = datetime.now().strftime("%Y%m%d-%H%M%S")
        return _session_id


def reset_session(session: str | None = None) -> str:
    """Start a new session (a reconnect does not: the conversation continues)."""
    global _session_id
    with _lock:
        _session_id = session or datetime.now().strftime("%Y%m%d-%H%M%S")
        return _session_id


def clean(text: str) -> str:
    """One line, bounded, no control characters.

    A turn IS one line in a JSONL file. A newline inside the text would still
    encode correctly, but the file then stops being one-record-per-line for
    anybody reading it with `grep` or their eyes.
    """
    text = _UNSAFE.sub("", str(text or ""))
    text = " ".join(text.split())
    if len(text) > MAX_TEXT:
        text = text[:MAX_TEXT].rstrip() + "…"
    return text


def record(role: str, text: str) -> bool:
    """Append one turn. True when it was written.

    Called from the session loop, so it is deliberately: no exception, no
    return value the caller must check, and an append rather than a rewrite.
    """
    role = str(role or "").strip().lower()
    if role not in _ROLES:
        role = "user" if role.startswith("u") else "assistant"
    text = clean(text)
    if not text:
        return False

    line = json.dumps({
        "at": datetime.now().isoformat(timespec="seconds"),
        "role": role,
        "text": text,
        "session": session_id(),
    }, ensure_ascii=False)

    try:
        with _lock:
            path = _path_for_today()
            if path.exists() and path.stat().st_size + len(line) > MAX_BYTES_PER_FILE:
                # Still recorded, in the next file. Losing the turn entirely
                # would be worse than a day split across two files.
                path = path.with_name(path.stem + "-2" + path.suffix)
            with path.open("a", encoding="utf-8") as f:
                f.write(line + "\n")
            _prune()
        return True
    except Exception:                     # noqa: BLE001
        # Deliberately silent to the user: a missing transcript is a smaller
        # problem than an assistant that stops mid-sentence to report one.
        from core.logbook import get as _log
        _log(__name__).debug("could not append to the transcript", exc_info=True)
        return False


def _day_of(path: Path) -> str:
    """`2026-11-19` from `2026-11-19.jsonl` — the whole prefix, not its first
    field. Splitting on the first dash yields "2026", which sorts as the
    oldest day in existence and would have made the prune delete everything."""
    stamp = path.name[:10]
    return stamp if len(stamp) == 10 and stamp[4] == "-" and stamp[7] == "-" else ""


def _path_for_today() -> Path:
    return history_dir() / f"{datetime.now().strftime('%Y-%m-%d')}.jsonl"


def _prune() -> None:
    """Delete day files older than KEEP_DAYS. Best effort, never raises."""
    cutoff = (datetime.now() - timedelta(days=KEEP_DAYS)).strftime("%Y-%m-%d")
    for path in history_dir().glob("*.jsonl"):
        stem = _day_of(path)
        if stem and stem < cutoff:
            try:
                path.unlink()
            except OSError:
                pass


def keep_turn(role: str, text: str) -> None:
    """Record one turn, named for the call site rather than the mechanism.

    `main.py` calls this from inside the session loop, where the class already
    has a line ceiling and every added line costs readability. The wrapper also
    makes the intent explicit at the call site: this is "keep what was said",
    not "write a file".
    """
    record(role, text)


def read_day(day: str | None = None) -> list[dict]:
    """Every turn recorded on `day` (`YYYY-MM-DD`), oldest first.

    A corrupt line is SKIPPED, not fatal: a half-written last line is what a
    crash looks like, and the turns before it are still the user's.
    """
    day = day or datetime.now().strftime("%Y-%m-%d")
    out: list[dict] = []
    for path in sorted(history_dir().glob(f"{day}*.jsonl")):
        try:
            with path.open("r", encoding="utf-8") as f:
                for raw in f:
                    raw = raw.strip()
                    if not raw:
                        continue
                    try:
                        entry = json.loads(raw)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(entry, dict) and entry.get("text"):
                        out.append(entry)
        except OSError:
            continue
    return out


def days(limit: int = KEEP_DAYS) -> list[str]:
    """The days that have a transcript, newest first."""
    found = set()
    for path in history_dir().glob("*.jsonl"):
        stem = _day_of(path)
        if stem:
            found.add(stem)
    return sorted(found, reverse=True)[:limit]


def tail(turns: int = 20) -> list[dict]:
    """The last `turns` turns across today and, if needed, yesterday.

    This is what the assistant reads when the user asks "what did we just
    talk about" — the raw recent past, not the curated memory.
    """
    out: list[dict] = []
    today = datetime.now()
    for back in (0, 1, 2):
        day = (today - timedelta(days=back)).strftime("%Y-%m-%d")
        out = read_day(day) + out
        if len(out) >= turns:
            break
    return out[-turns:]


def as_text(turns: int = 20) -> str:
    """A readable transcript, for a prompt or for the activity log."""
    lines = []
    for entry in tail(turns):
        who = "You" if entry.get("role") == "user" else "JARVIS"
        lines.append(f"{who}: {entry.get('text', '')}")
    return "\n".join(lines)


def clear(day: str | None = None) -> bool:
    """Delete one day's transcript. True when the files are gone.

    The user asked for a record of themselves; they are entitled to take it
    back, and there is no undo stack for that because deleting is the point.
    """
    day = day or datetime.now().strftime("%Y-%m-%d")
    ok = True
    for path in history_dir().glob(f"{day}*.jsonl"):
        try:
            path.unlink()
        except OSError:
            ok = False
    return ok


def total_bytes() -> int:
    """How much disk the transcripts use — shown in SETUP, not guessed."""
    total = 0
    for path in history_dir().glob("*.jsonl"):
        try:
            total += path.stat().st_size
        except OSError:
            pass
    return total


__all__ = [
    "MAX_BYTES_PER_FILE", "MAX_TEXT", "KEEP_DAYS",
    "history_dir", "session_id", "reset_session", "clean", "record",
    "keep_turn", "read_day", "days", "tail", "as_text", "clear", "total_bytes",
]
