"""core/single_instance.py — one JARVIS, however many times it is started.

WHY THIS EXISTS (AND WHY IT DID NOT NEED TO UNTIL NOW)
    Starting the app twice used to be survivable: two windows, one of which
    the user closed. That stopped being true when the interface moved into the
    operating system. Every way the assistant can now be started is a way to
    start a SECOND copy of it:

      * the tray icon's "Show JARVIS" and the desktop shortcut both launch
        `main.py`;
      * auto-start (`core/autostart.py`) launches it at login — and the user,
        not seeing a window because the mode is ambient, launches it again;
      * the summon chord is global, so pressing it while the first copy is
        already answering does not push the user toward the running one.

    Two copies is not a cosmetic problem here, and it is worth being precise
    about why, because "just add a mutex" undersells it:

      * TWO ENVIRONMENTAL LISTENERS. `main.py` opens a Gemini Live session and
        a microphone. Two of them answer the same spoken question twice, in
        two voices, at slightly different times.
      * TWO SETS OF AUTOMATION. Both can drive the mouse and keyboard, and
        `core/appidentity.py` has a whole section about the assistant
        accidentally targeting itself.
      * TWO TRAY ICONS, identical, neither of which summons the other.
      * A CONFIG FILE WRITTEN BY BOTH. `memory/config_manager.py` merges on
        write, so this is not corruption — but the last writer wins, and which
        one is last is a race.
      * THE AUTO-START ENTRY POINTING AT A SECOND PROCESS while the first one
        holds the microphone.

WHAT IT DOES
    On start, a lock file in the per-user state folder. Held for the life of
    the process. If it is already held, this process is not a second JARVIS:
    it is a REQUEST to the one that exists — "come to the front" — and then it
    exits 0.

WHY A LOCK FILE AND NOT A QLocalServer
    Qt's `QLocalServer` would be the obvious answer and it is the wrong one
    here: it needs a QApplication, which means the second copy pays for
    constructing a window before it knows it is not wanted, and `core/` must
    stay importable on a machine with no Qt at all (`tests/` proves it).
    A lock file is `os.open(..., O_CREAT | O_EXCL)` — atomic on every
    filesystem this app supports, and it works in a headless test.

WHY NOT JUST "IS THE PID ALIVE"
    Because PIDs are reused. A stale lock file whose pid now belongs to the
    user's editor would make the assistant refuse to start for good. So the
    lock records pid, start time and the program path, and a stale lock is
    detected and taken over — see `_is_stale`.

WHAT THE SECOND COPY DOES
    It writes its request to `<lock>.want` and exits. The running copy watches
    that file on a timer (`ui/lifecycle.py` starts it) and summons itself when
    it appears. That is deliberately dumber than a socket and it is why this
    module has no platform-specific code at all: a file write and an mtime.

    If the running copy is wedged and does not answer, the second copy still
    exits 0 and says so on stdout — it does not sit there waiting to become a
    duplicate. The user can quit from the tray, which is the one action that
    always exists in ambient mode.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

LOCK_NAME = "instance.lock"
WANT_SUFFIX = ".want"


def state_dir() -> Path:
    """The per-user folder the lock lives in.

    Not the project folder: a project can be read-only (a packaged build in
    `Program Files`, or `C:\\Program Files\\Mark LVI`) and two checkouts of the
    app must still be one assistant per user, not one per directory.
    """
    env = os.environ.get("XDG_STATE_HOME") or os.environ.get("LOCALAPPDATA")
    base = Path(env) if env else Path.home() / ".local" / "state"
    path = base / "MarkLVI"
    try:
        path.mkdir(parents=True, exist_ok=True)
    except OSError:
        # Nowhere writable at all. Temp is the last resort and is still one
        # file for one user, which is what the lock actually needs.
        import tempfile
        path = Path(tempfile.gettempdir()) / "MarkLVI"
        path.mkdir(parents=True, exist_ok=True)
    return path


def lock_path() -> Path:
    return state_dir() / LOCK_NAME


def _as_path(lock) -> Path:
    """Accept a `Path`, a `str` or None.

    A path is a string in half the callers that would touch this (a config
    value, an argv entry), and `str.with_name` is an AttributeError three calls
    deep — found by running two real processes against each other, not by the
    suite, because every test here passed a `Path` already.
    """
    return Path(lock) if lock else lock_path()


def _want_path(lock: Path | None = None) -> Path:
    lock = _as_path(lock)
    return lock.with_name(lock.name + WANT_SUFFIX)


# ── reading and writing the lock ────────────────────────────────────────────

def _proc_start_time(pid: int) -> float | None:
    """When a pid started, as an absolute timestamp. `None` if it cannot be read.

    WHY THIS IS THE WHOLE OF THE PID-REUSE STORY
        PIDs are reused, and on a desktop that has been up for a week they are
        reused quickly. "Is pid 4242 alive" is therefore not the question —
        "is pid 4242 still THE PROCESS THAT WROTE THIS LOCK" is, and the answer
        is its start time.

    `psutil` answers it on all three platforms and is already a dependency of
    this app (the metric sampler reads it). `/proc/<pid>/stat` is the fallback
    for a machine where psutil is missing — field 22, in clock ticks since
    boot, converted with `btime`. On a system where neither works this returns
    None and `_is_stale` stops guessing: see the comment there.
    """
    try:
        import psutil
        return float(psutil.Process(pid).create_time())
    except Exception as e:                       # noqa: BLE001
        # psutil missing, or the process is gone between the two calls. Both
        # mean "ask /proc instead", and the reason is kept in the log rather
        # than swallowed — this module decides whether a second copy starts.
        from core.logbook import get as _log
        _log(__name__).debug("psutil create_time unavailable for %s: %s", pid, e)
    try:
        raw = Path(f"/proc/{pid}/stat").read_text()
        # The comm field is parenthesised and may contain spaces, so split
        # AFTER the closing parenthesis.
        fields = raw[raw.rindex(")") + 2:].split()
        ticks = float(fields[19])
        btime = None
        for line in Path("/proc/stat").read_text().splitlines():
            if line.startswith("btime "):
                btime = float(line.split()[1])
                break
        if btime is None:
            return None
        return btime + ticks / os.sysconf("SC_CLK_TCK")
    except (OSError, ValueError, IndexError, AttributeError):
        return None


def _pid_alive(pid: int) -> bool:
    """Whether a pid exists. `os.kill(pid, 0)` is the portable-enough answer.

    On Windows, signal 0 is not what it is on POSIX, so `ctypes` is asked
    instead — and its absence (a locked-down interpreter) is treated as "alive"
    so a failure here can never delete a live lock.
    """
    if pid <= 0:
        return False
    if sys.platform == "win32":
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            handle = kernel32.OpenProcess(0x1000, False, pid)  # QUERY_LIMITED
            if not handle:
                return False
            kernel32.CloseHandle(handle)
            return True
        except Exception:                        # noqa: BLE001
            return True
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True          # exists, owned by somebody else
    except OSError:
        return True


def read_lock(lock: Path | None = None) -> dict:
    """The lock's contents, or {} — a half-written lock is not an error."""
    lock = _as_path(lock)
    try:
        return json.loads(lock.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def _record(program: str) -> dict:
    return {
        "pid": os.getpid(),
        "program": program,
        "started": time.time(),
        "start_time": _proc_start_time(os.getpid()),
    }


def _is_stale(data: dict, lock: Path) -> bool:
    """Whether a lock can be taken over. Three independent reasons, in order.

    A lock that cannot be proven stale is LEFT ALONE. Refusing to start is the
    recoverable failure (the user deletes one file, and the message says so);
    trampling a live lock is not — it produces exactly the second copy this
    module exists to prevent.
    """
    pid = data.get("pid")
    if not isinstance(pid, int) or pid <= 0:
        return True                      # unreadable or half-written
    if not _pid_alive(pid):
        return True

    recorded = data.get("start_time")
    if recorded is not None:
        current = _proc_start_time(pid)
        if current is not None and abs(current - float(recorded)) > 0.5:
            return True                  # same pid, different process

    # Otherwise: the pid is alive and nothing says it is somebody else. HONOUR
    # THE LOCK.
    #
    #     An earlier draft also declared a lock stale when it was over a day old
    #     and recorded a different program path — and that rule was wrong in the
    #     direction that matters. `argv[0]` is not stable: a shortcut launches
    #     `main.py`, auto-start launches the same file from a different working
    #     directory, and a packaged build has an exe where the source has a
    #     path. Each of those is a legitimately different string for the SAME
    #     running program, and every one of them would have been a second copy.
    #
    #     So when the start time cannot be read, the doubt goes the other way.
    #     The cost of being wrong here is that the app refuses to start and
    #     says which file to delete; the cost of the other direction is two
    #     microphones.
    return False


# ── the public API ──────────────────────────────────────────────────────────

class AlreadyRunning(Exception):
    """Raised by `acquire()` when another copy holds the lock."""

    def __init__(self, holder: dict):
        self.holder = holder
        pid = holder.get("pid", "?")
        super().__init__(f"another copy is already running (pid {pid})")


class Instance:
    """The claim on the lock. Keep it alive; `release()` on quit.

    Deliberately a returned object rather than a module-level flag: the lock
    must be tied to the process's lifetime, and a global that a test can leave
    set is how a suite ends up unable to run itself twice.
    """

    def __init__(self, path: Path):
        self.path = path
        self._held = True

    def __enter__(self) -> Instance:
        return self

    def __exit__(self, *_exc) -> None:
        self.release()

    def release(self) -> None:
        if not self._held:
            return
        self._held = False
        # Only remove OUR lock: if a takeover already happened (a crash handler
        # wrote a new one), deleting it would free a lock somebody else holds.
        if read_lock(self.path).get("pid") == os.getpid():
            try:
                self.path.unlink()
            except OSError:
                pass

    @property
    def held(self) -> bool:
        return self._held


def acquire(program: str = "", lock: Path | None = None) -> Instance:
    """Take the lock, or raise `AlreadyRunning` with the holder's record.

    The write is `O_CREAT | O_EXCL`, so two processes starting in the same
    millisecond cannot both win — which is the entire reason this is not
    "read the file, then write it".
    """
    lock = _as_path(lock)
    record = _record(program or sys.argv[0])
    payload = json.dumps(record, indent=2).encode("utf-8")

    for _attempt in range(2):                # one retry after clearing a stale lock
        try:
            fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            data = read_lock(lock)
            if not _is_stale(data, lock):
                raise AlreadyRunning(data) from None
            # Stale. Remove it and try once more; if somebody else wins that
            # race, they become the instance and this one raises properly.
            try:
                lock.unlink()
            except OSError:
                pass
            continue
        except OSError:
            # Cannot write a lock at all (read-only temp, a hostile sandbox).
            # Starting without one is better than not starting: the failure it
            # protects against is a duplicate, not a single instance.
            return Instance(lock)
        try:
            os.write(fd, payload)
        finally:
            os.close(fd)
        return Instance(lock)

    data = read_lock(lock)
    raise AlreadyRunning(data)


# ── the second copy's request ───────────────────────────────────────────────

def request_foreground(lock: Path | None = None) -> bool:
    """Ask the running copy to come to the front. True if the request was written.

    A file, not a socket, and the cost of that choice is stated here: the
    running copy polls, so the window appears within one poll interval rather
    than immediately. The benefit is that this works identically on three
    operating systems, needs no Qt, and needs no server to be alive in the
    other process — which is the only thing that has to be true when the whole
    point is that the other process may be wedged.
    """
    want = _want_path(lock)
    try:
        want.parent.mkdir(parents=True, exist_ok=True)
        want.write_text(json.dumps({"pid": os.getpid(),
                                    "at": time.time()}), encoding="utf-8")
        return True
    except OSError:
        return False


def take_foreground_request(lock: Path | None = None) -> bool:
    """Whether somebody asked, consuming the request. Called by the running copy."""
    want = _want_path(lock)
    try:
        if not want.exists():
            return False
        want.unlink()
        return True
    except OSError:
        return False
