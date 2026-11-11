"""The log file: it opens, it rotates, it never takes the app down with it.

The bug this guards against is not in the logger, it is in the app: with no
console (`pythonw main.py`, which is what the desktop shortcut runs) every
diagnostic went to a null device, so a bug report could name a message nobody
could reproduce. A logger that raises would be a worse bug than that.
"""
from __future__ import annotations

import logging
import logging.handlers

import pytest

from core import logbook


@pytest.fixture()
def fresh_log(monkeypatch, tmp_path):
    """A log directory of its own, and a root logger put back afterwards."""
    monkeypatch.setattr(logbook, "log_dir", lambda: tmp_path)
    monkeypatch.setattr(logbook, "_configured", False)
    root = logging.getLogger()
    before = list(root.handlers)
    yield tmp_path
    for h in list(root.handlers):
        if h not in before:
            root.removeHandler(h)
            try:
                h.close()
            except Exception:
                pass


def test_setup_writes_a_file(fresh_log):
    path = logbook.setup()
    assert path is not None and path.exists()
    logbook.get("test").warning("something happened")
    for h in logging.getLogger().handlers:
        h.flush()
    assert "something happened" in path.read_text(encoding="utf-8")
    assert "WARNING" in path.read_text(encoding="utf-8")


def test_setup_is_idempotent(fresh_log):
    first = logbook.setup()
    second = logbook.setup()
    assert first == second
    handlers = [h for h in logging.getLogger().handlers
                if isinstance(h, logging.handlers.RotatingFileHandler)]
    assert len(handlers) == 1, "a second setup() added a second file handler"


def test_it_rotates_and_is_bounded(fresh_log, monkeypatch):
    monkeypatch.setattr(logbook, "_MAX_BYTES", 2000)
    path = logbook.setup()
    log = logbook.get("rotate")
    for i in range(400):
        log.warning("line %d %s", i, "x" * 60)
    for h in logging.getLogger().handlers:
        h.flush()
    size = path.stat().st_size
    assert size <= 2000, f"the active file grew past its cap: {size}"
    assert (fresh_log / "jarvis.log.1").exists(), "no rotation happened"


def test_unwritable_location_returns_none_instead_of_raising(monkeypatch):
    """A read-only install folder must not stop the app from starting."""
    def boom():
        raise OSError("read-only")
    monkeypatch.setattr(logbook, "log_dir", boom)
    monkeypatch.setattr(logbook, "_configured", False)
    assert logbook.setup() is None


def test_tail_returns_the_end(fresh_log):
    logbook.setup()
    log = logbook.get("tail")
    for i in range(5):
        log.warning("entry %d", i)
    for h in logging.getLogger().handlers:
        h.flush()
    out = logbook.tail(2)
    assert "entry 4" in out
    assert "entry 0" not in out
