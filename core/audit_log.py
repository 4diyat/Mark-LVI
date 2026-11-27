"""core/audit_log.py — what the assistant DID, kept apart from what it said.

WHY THIS IS A SECOND FILE AND NOT A LINE IN `logs/jarvis.log`
    `core/logbook.py` rotates at 2 MB with three backups, so it holds roughly a
    week and it holds EVERYTHING: exceptions mid-sentence, Qt warnings, debug
    lines from an overlay that failed to build. That is the right file for
    debugging and the wrong file for the two questions a privacy page has to
    answer honestly:

        "what did it do with my files and my clipboard?"
        "which confirmation did I actually give, and when?"

    A record that is interleaved with diagnostics cannot be exported without
    handing over the diagnostics too, cannot be filtered by tool, and disappears
    when the log rotates. The privacy page promises a readable activity log and
    a way to erase it; both need their own file with its own rotation.

WHAT A RECORD CONTAINS
    timestamp, tool, level, outcome, and a short detail — never the content of
    the file that was read, never the text that was typed. `detail` is the
    SENTENCE the tool already produced for the user, truncated. If a tool wants
    to record something a user would not want in a log, it should not put it in
    that sentence either, because the same sentence is shown on screen.

WHAT IT NEVER DOES
    It never raises into the caller. An audit write that can take down the
    action it was describing is worse than a missing line, and the action has
    already happened by the time this is called.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import threading

from typing import Any

# Rotate by count rather than size: an audit file is read line by line and a
# 2 MB ceiling would mean months disappear at once. 5,000 actions is roughly a
# year of ordinary use, and the oldest quarter is dropped on rotation.
MAX_RECORDS = 5000
KEEP_ON_ROTATE = 2500
MAX_DETAIL = 200


def default_path() -> str:
    base = os.environ.get("JARVIS_STATE_DIR")
    if base:
        return os.path.join(base, "audit.jsonl")
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(os.path.dirname(here), "config", "audit.jsonl")


class AuditLog:
    """Append-only JSON Lines. One object per process; tests make their own."""

    def __init__(self, path=None, max_records: int = MAX_RECORDS,
                 keep_on_rotate: int = KEEP_ON_ROTATE) -> None:
        self._path = path if path is not None else default_path()
        self._max = max(1, int(max_records))
        self._keep = max(0, min(int(keep_on_rotate), self._max))
        self._lock = threading.Lock()
        self._count = self._count_lines()

    # ── storage ──────────────────────────────────────────────────────────────

    def _count_lines(self) -> int:
        try:
            with open(self._path, "rb") as fh:
                return sum(1 for _ in fh)
        except OSError:
            return 0

    def _rotate_locked(self) -> None:
        """Keep the newest `_keep` lines. Caller holds the lock.

        Rewritten through a temp file so a crash cannot leave the audit log
        truncated — losing history is bad, but a half-file that parses as
        "nothing was ever done" is worse.
        """
        try:
            with open(self._path, encoding="utf-8") as fh:
                lines = fh.readlines()
        except OSError:
            self._count = 0
            return
        kept = lines[-self._keep:] if self._keep else []
        tmp = self._path + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as fh:
                fh.writelines(kept)
            os.replace(tmp, self._path)
            self._count = len(kept)
        except OSError as e:
            print(f"[Audit] rotation failed: {e}")

    # ── writing ──────────────────────────────────────────────────────────────

    def record(self, tool: str, level: str, outcome: str, detail: str = "") -> bool:
        """Append one action. Returns True if it reached the disk.

        `outcome` is one of the words `core.outcome` already uses — done,
        unverified, failed, cancelled — so the audit log and the sentence the
        user sees cannot disagree about what happened.
        """
        entry = {
            "at": _dt.datetime.now().isoformat(timespec="seconds"),
            "tool": str(tool or "")[:80],
            "level": str(level or "")[:16],
            "outcome": str(outcome or "")[:24],
            "detail": str(detail or "")[:MAX_DETAIL],
        }
        line = json.dumps(entry, ensure_ascii=False)
        with self._lock:
            try:
                directory = os.path.dirname(os.path.abspath(self._path)) or "."
                os.makedirs(directory, exist_ok=True)
                with open(self._path, "a", encoding="utf-8") as fh:
                    fh.write(line + "\n")
                self._count += 1
                if self._count > self._max:
                    self._rotate_locked()
                return True
            except OSError as e:
                print(f"[Audit] could not write: {e}")
                return False

    # ── reading, for the privacy page and for export ─────────────────────────

    def entries(self, limit: int | None = None, *, strict: bool = False) -> list[dict[str, Any]]:
        """Newest last. Strict reads distinguish a missing log from a damaged one."""
        out: list[dict[str, Any]] = []
        try:
            with self._lock, open(self._path, encoding="utf-8") as fh:
                for raw in fh:
                    raw = raw.strip()
                    if not raw:
                        continue
                    try:
                        item = json.loads(raw)
                    except ValueError:
                        if strict:
                            raise ValueError("Malformed audit record") from None
                        continue
                    if isinstance(item, dict):
                        out.append(item)
                    elif strict:
                        raise ValueError("Invalid audit record")
        except FileNotFoundError:
            return []
        except (OSError, UnicodeError):
            if strict:
                raise
            return []
        if limit is not None and limit >= 0:
            return out[-limit:] if limit else []
        return out

    def erase(self) -> bool:
        """Delete everything. The privacy page's "Hapus riwayat" button."""
        with self._lock:
            try:
                if os.path.exists(self._path):
                    os.remove(self._path)
                self._count = 0
                return True
            except OSError as e:
                print(f"[Audit] could not erase: {e}")
                return False


_shared: AuditLog | None = None
_shared_lock = threading.Lock()


def shared() -> AuditLog:
    global _shared
    with _shared_lock:
        if _shared is None:
            _shared = AuditLog()
        return _shared


def reset_shared() -> None:
    global _shared
    with _shared_lock:
        _shared = None


def record(tool: str, level: str, outcome: str, detail: str = "") -> bool:
    """Convenience: write to the process-wide log. Never raises."""
    return shared().record(tool, level, outcome, detail)
