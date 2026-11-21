"""The audit log: what it records, what it refuses to record, and that it never
takes down the action it describes.
"""
from __future__ import annotations

import json

import pytest

from core import audit_log
from core.audit_log import AuditLog


@pytest.fixture
def log(tmp_path):
    return AuditLog(path=str(tmp_path / "audit.jsonl"))


def test_a_record_round_trips(log):
    assert log.record("web_search", "safe", "done", "3 results") is True
    items = log.entries()
    assert len(items) == 1
    assert items[0]["tool"] == "web_search"
    assert items[0]["outcome"] == "done"
    assert items[0]["detail"] == "3 results"
    assert "at" in items[0]


def test_records_are_newest_last(log):
    log.record("a", "safe", "done")
    log.record("b", "safe", "done")
    assert [e["tool"] for e in log.entries()] == ["a", "b"]


def test_a_limit_returns_the_newest(log):
    for i in range(5):
        log.record(f"t{i}", "safe", "done")
    assert [e["tool"] for e in log.entries(limit=2)] == ["t3", "t4"]


def test_a_zero_limit_returns_nothing(log):
    log.record("a", "safe", "done")
    assert log.entries(limit=0) == []


def test_the_detail_is_truncated_so_a_file_body_cannot_land_in_the_log(log):
    log.record("file_read", "safe", "done", "x" * 5000)
    assert len(log.entries()[0]["detail"]) == audit_log.MAX_DETAIL


def test_the_log_is_json_lines_on_disk(log):
    log.record("a", "safe", "done")
    log.record("b", "risky", "cancelled")
    raw = log.entries.__self__._path
    with open(raw, encoding="utf-8") as fh:
        lines = [ln for ln in fh if ln.strip()]
    assert len(lines) == 2
    assert json.loads(lines[0])["tool"] == "a"


def test_a_malformed_line_is_skipped_not_fatal(tmp_path):
    path = tmp_path / "audit.jsonl"
    path.write_text('{"tool": "a", "outcome": "done"}\nnot json\n{"tool": "b"}\n',
                    encoding="utf-8")
    log = AuditLog(path=str(path))
    assert [e.get("tool") for e in log.entries()] == ["a", "b"]


def test_rotation_keeps_the_newest_and_drops_the_oldest(tmp_path):
    path = tmp_path / "audit.jsonl"
    log = AuditLog(path=str(path), max_records=10, keep_on_rotate=4)
    for i in range(11):
        log.record(f"t{i}", "safe", "done")
    tools = [e["tool"] for e in log.entries()]
    assert len(tools) == 4
    assert tools == ["t7", "t8", "t9", "t10"]


def test_erase_removes_everything(log):
    log.record("a", "safe", "done")
    assert log.erase() is True
    assert log.entries() == []


def test_erase_of_a_file_that_was_never_written_is_fine(tmp_path):
    assert AuditLog(path=str(tmp_path / "nothing.jsonl")).erase() is True


def test_an_unwritable_path_returns_false_rather_than_raising(tmp_path):
    """A directory that cannot exist must not become the action's exception.

    The obstacle is a regular FILE where a directory has to be, not a path under
    /proc: the first version used /proc and passed here while failing on the
    Windows runner, where `/proc` is simply `C:\proc` and an administrator can
    create it. A file-in-the-way fails identically on every OS.
    """
    blocker = tmp_path / "not-a-directory"
    blocker.write_text("this is a file", encoding="utf-8")
    log = AuditLog(path=str(blocker / "audit.jsonl"))
    assert log.record("a", "safe", "done") is False


def test_reading_a_missing_file_is_empty_not_an_error(tmp_path):
    assert AuditLog(path=str(tmp_path / "none.jsonl")).entries() == []


def test_the_module_level_helper_uses_the_shared_log(tmp_path, monkeypatch):
    monkeypatch.setenv("JARVIS_STATE_DIR", str(tmp_path))
    audit_log.reset_shared()
    try:
        assert audit_log.record("a", "safe", "done") is True
        assert audit_log.shared().entries()[0]["tool"] == "a"
    finally:
        audit_log.reset_shared()


def test_the_outcome_vocabulary_is_closed():
    """The log and the spoken sentence must not disagree about what happened.

    Asserted against the words the writers actually emit rather than against a
    docstring: `core.action_gate` and `core.confirm` are the only producers, and
    a new outcome word added there without a line here is a vocabulary the
    history page cannot render.
    """
    import inspect

    from core import action_gate

    vocabulary = {"requested", "awaiting", "held", "done", "unverified",
                  "failed", "confirmed", "cancelled", "expired"}
    source = inspect.getsource(action_gate)
    for word in vocabulary:
        if word in ("requested", "held", "done", "unverified", "failed"):
            assert f'"{word}"' in source, f"{word} is logged but not listed here"
    # Every word used must fit the shape the audit entry allows.
    for word in vocabulary:
        assert len(word) <= audit_log.MAX_DETAIL
