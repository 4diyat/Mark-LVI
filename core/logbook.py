"""core/logbook.py — the file that keeps what the console forgets.

WHY THE APP NEEDED ONE
    Every diagnostic in this project goes to stdout. That is fine while a
    terminal is open and useless the moment it is not:
    `pythonw main.py` (which the desktop shortcut runs) has no console at all —
    stdout is a null device — and a window opened from Explorer closes on exit
    with its scrollback. So the user reports "it said something about the
    microphone" and there is nothing to read.

    It also matters for `except Exception: pass`, of which this codebase has
    140. Some are deliberate (an optional overlay that failed to build must not
    stop the app). Several have hidden a real bug — the Linux firewall branch in
    dashboard/server.py was unreachable for a release because its NameError fell
    into one. The fix for that is not "remove the try/except", it is
    `except Exception as e: log.debug(...)`: a line nobody sees, that still
    exists when somebody asks.

WHERE IT WRITES
    <project>/logs/jarvis.log — the project folder first, because that is what
    a user copies when they report a problem, and `logs/` is already in
    .gitignore. If the install folder is read-only (a system-wide install, a
    packaged build in Program Files) it falls back to the per-user data folder.
    It never raises: a logger that can take the app down is worse than no log.

WHAT IT IS NOT
    Not a replacement for the activity log in the window. `player.write_log`
    is a conversation with the user; this is a record for whoever debugs it.
    Nothing here reaches the HUD.
"""
from __future__ import annotations

import logging
import logging.handlers
import os
import sys
from pathlib import Path

_MAX_BYTES = 2 * 1024 * 1024      # 2 MB per file
_BACKUPS = 3                      # jarvis.log + 3 rotations = 8 MB ceiling
_configured = False


def _base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent


def log_dir() -> Path:
    """Where the log lives, creating it on first use.

    Two candidates, in this order, for the reason in the module docstring: the
    folder the user can find, then the one the OS guarantees is writable.
    """
    for candidate in (_base_dir() / "logs",
                      Path(os.environ.get("LOCALAPPDATA")
                           or os.environ.get("XDG_STATE_HOME")
                           or Path.home() / ".local" / "state") / "MarkLVI" / "logs"):
        try:
            candidate.mkdir(parents=True, exist_ok=True)
            probe = candidate / ".write-test"
            probe.write_text("", encoding="utf-8")
            probe.unlink()
            return candidate
        except Exception:
            continue
    return Path(os.devnull).parent      # nothing writable; the file handler is skipped


def log_file() -> Path | None:
    """The active log file, or None when the disk would not take one."""
    path = log_dir() / "jarvis.log"
    return path if os.path.exists(path) or _configured else None


def setup(level: int = logging.INFO) -> Path | None:
    """Attach the rotating file handler to the root logger. Idempotent.

    Called once at the top of main.py. Everything already printing to the
    console keeps printing — this ADDS a file, it does not redirect anything,
    because a developer watching the terminal should not lose it.
    """
    global _configured
    root = logging.getLogger()
    if _configured:
        for h in root.handlers:
            if isinstance(h, logging.handlers.RotatingFileHandler):
                return Path(h.baseFilename)
    root.setLevel(level)
    try:
        path = log_dir() / "jarvis.log"
        handler = logging.handlers.RotatingFileHandler(
            path, maxBytes=_MAX_BYTES, backupCount=_BACKUPS, encoding="utf-8")
        handler.setFormatter(logging.Formatter(
            # Timestamp first: a log is read in order, and an ISO date sorts.
            "%(asctime)s %(levelname)-7s %(name)-22s %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"))
        root.addHandler(handler)
        _configured = True

        # The uncaught-exception case: a thread that dies, an asyncio task that
        # raises. Python's default hook writes to stderr, which is the null
        # device under pythonw. This keeps the traceback.
        previous = sys.excepthook

        def _hook(exc_type, exc, tb):
            logging.getLogger("uncaught").critical(
                "unhandled exception", exc_info=(exc_type, exc, tb))
            previous(exc_type, exc, tb)

        sys.excepthook = _hook
        logging.getLogger(__name__).info("log opened: %s", path)
        return path
    except Exception as e:                  # pragma: no cover — disk full, read-only
        # The reason is not re-derived from log_dir(): that is the call that
        # may be what failed. A logger that raises on its own error path is the
        # one thing worse than no logger.
        print(f"[Log] Could not open a log file: {e}")
        return None


def get(name: str) -> logging.Logger:
    """`logging.getLogger` with this project's prefix.

    A short alias so a line inside a hot function stays one line:
        from core.logbook import get as _log
        _log("browser").debug("click missed: %s", e)
    """
    return logging.getLogger(name)


def tail(lines: int = 200) -> str:
    """The last N lines of the log, for a future 'export diagnostics' button."""
    path = log_dir() / "jarvis.log"
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""
    return "\n".join(text.splitlines()[-lines:])
