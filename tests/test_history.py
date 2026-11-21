"""The transcript: appended while the user talks, readable afterwards.

Two properties matter and they pull in opposite directions. It is written from
the session loop, so it must be fast, silent and unable to raise. It is read by
a person later, so a crash at the wrong moment must not destroy what came
before. Every test here is one of those two.
"""
from __future__ import annotations

import json
from pathlib import Path
from datetime import datetime, timedelta

import pytest

from core import history


@pytest.fixture()
def store(tmp_path, monkeypatch):
    """A history folder of its own, and a session id that does not leak."""
    monkeypatch.setattr(history, "_base_dir", lambda: tmp_path)
    monkeypatch.setattr(history, "_session_id", "20260101-000000")
    return tmp_path / "logs" / "history"


def today():
    return datetime.now().strftime("%Y-%m-%d")


# ── writing ─────────────────────────────────────────────────────────────────

def test_a_turn_becomes_one_readable_line(store):
    assert history.record("user", "turn on the lights") is True
    files = list(store.glob("*.jsonl"))
    assert len(files) == 1
    with files[0].open(encoding="utf-8") as f:
        lines = [ln for ln in f.read().splitlines() if ln]
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["role"] == "user"
    assert entry["text"] == "turn on the lights"
    assert entry["at"].startswith(today())
    assert entry["session"]


def test_a_turn_containing_newlines_stays_one_line(store):
    """A pasted stack trace is a legitimate turn. Two lines would break the
    one-record-per-line promise the file makes to `grep` and to a reader."""
    history.record("assistant", "line one\nline two\r\nline three")
    raw = next(store.glob("*.jsonl")).read_text(encoding="utf-8")
    assert len([ln for ln in raw.splitlines() if ln]) == 1
    assert json.loads(raw.strip())["text"] == "line one line two line three"


def test_control_characters_never_reach_the_file(store):
    history.record("user", "hi\x00there\x07")
    raw = next(store.glob("*.jsonl")).read_text(encoding="utf-8")
    assert "\x00" not in raw and "\x07" not in raw
    assert json.loads(raw.strip())["text"] == "hithere"


def test_an_endless_turn_is_cut_not_stored_whole(store):
    assert len(history.clean("x" * 10_000)) <= history.MAX_TEXT + 1
    history.record("user", "y" * 10_000)
    assert next(store.glob("*.jsonl")).stat().st_size < history.MAX_TEXT + 500


def test_empty_text_is_not_a_turn(store):
    assert history.record("user", "   ") is False
    assert history.record("user", "") is False
    assert not list(store.glob("*.jsonl"))


def test_an_unknown_role_is_coerced_rather_than_refused(store):
    """The caller is the session loop; a typo there must not lose the turn."""
    history.record("User ", "hello")
    history.record("jarvis", "hi")
    roles = [e["role"] for e in history.read_day()]
    assert roles == ["user", "assistant"]


def test_a_turn_is_recorded_even_when_the_day_file_is_full(store, monkeypatch):
    """The cap splits the day, it does not drop the turn: losing the sentence
    the user just spoke is worse than a day stored in two files."""
    monkeypatch.setattr(history, "MAX_BYTES_PER_FILE", 60)
    for i in range(5):
        assert history.record("user", f"message number {i} with some length") is True
    files = sorted(p.name for p in store.glob("*.jsonl"))
    assert len(files) == 2
    assert len(history.read_day()) == 5


def test_the_writer_never_raises_and_never_blocks_the_session(store, monkeypatch):
    """A transcript that cannot be written must not take the conversation with
    it — the turn still happened, and the session is still live."""
    def boom(*a, **k):
        raise OSError("disk full")

    monkeypatch.setattr(history, "_path_for_today", boom)
    assert history.record("user", "still talking") is False


# ── reading ─────────────────────────────────────────────────────────────────

def test_turns_come_back_in_the_order_they_were_spoken(store):
    for text in ("one", "two", "three"):
        history.record("user", text)
    assert [e["text"] for e in history.read_day()] == ["one", "two", "three"]


def test_a_half_written_last_line_is_skipped_not_fatal(store):
    """This is what a crash looks like: the record before it is still true."""
    history.record("user", "good turn")
    path = next(store.glob("*.jsonl"))
    with path.open("a", encoding="utf-8") as f:
        f.write('{"at": "2026-01-01T00:00:00", "role": "user", "tex')
    assert [e["text"] for e in history.read_day()] == ["good turn"]


def test_junk_lines_are_ignored(store):
    history.record("user", "real")
    path = next(store.glob("*.jsonl"))
    with path.open("a", encoding="utf-8") as f:
        f.write("not json at all\n[1,2,3]\n{\"text\": \"\"}\n")
    assert [e["text"] for e in history.read_day()] == ["real"]


def test_tail_reaches_back_to_yesterday_when_today_is_short(store):
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    store.mkdir(parents=True, exist_ok=True)
    (store / f"{yesterday}.jsonl").write_text(json.dumps(
        {"at": yesterday + "T20:00:00", "role": "user", "text": "last night",
         "session": "s"}) + "\n", encoding="utf-8")
    history.record("user", "this morning")
    texts = [e["text"] for e in history.tail(5)]
    assert texts == ["last night", "this morning"]


def test_the_readable_form_names_who_spoke(store):
    history.record("user", "what time is it")
    history.record("assistant", "half past nine")
    assert history.as_text() == "You: what time is it\nJARVIS: half past nine"


def test_days_lists_whole_dates_newest_first(store):
    store.mkdir(parents=True, exist_ok=True)
    for day in ("2026-03-04", "2026-03-05", "2025-12-31"):
        (store / f"{day}.jsonl").write_text("", encoding="utf-8")
    assert history.days() == ["2026-03-05", "2026-03-04", "2025-12-31"]


# ── pruning and clearing ────────────────────────────────────────────────────

def test_old_days_are_deleted_and_recent_ones_are_not(store, monkeypatch):
    """The date prefix has to be read WHOLE. Taking the first dash-separated
    field yields "2026", which is older than every cutoff — a prune that
    deletes today's conversation."""
    store.mkdir(parents=True, exist_ok=True)
    old = (datetime.now() - timedelta(days=history.KEEP_DAYS + 2)).strftime("%Y-%m-%d")
    (store / f"{old}.jsonl").write_text("{}\n", encoding="utf-8")
    (store / f"{today()}.jsonl").write_text("{}\n", encoding="utf-8")

    history.record("user", "today's turn")

    assert not (store / f"{old}.jsonl").exists()
    assert (store / f"{today()}.jsonl").exists()
    assert history._day_of(store / "2026-11-19.jsonl") == "2026-11-19"
    assert history._day_of(store / "2026-11-19-2.jsonl") == "2026-11-19"


def test_clearing_a_day_removes_every_part_of_it(store, monkeypatch):
    monkeypatch.setattr(history, "MAX_BYTES_PER_FILE", 60)
    for i in range(4):
        history.record("user", f"message number {i} with some length")
    assert len(list(store.glob("*.jsonl"))) > 1
    assert history.clear() is True
    assert not list(store.glob("*.jsonl"))
    assert history.read_day() == []


def test_total_bytes_is_measured_not_guessed(store):
    history.record("user", "abc")
    assert history.total_bytes() == next(store.glob("*.jsonl")).stat().st_size


# ── the session boundary ────────────────────────────────────────────────────

def test_a_session_id_is_stable_until_reset(store):
    first = history.session_id()
    assert first == "20260101-000000"
    history.record("user", "a")
    assert history.session_id() == first
    second = history.reset_session()
    assert second != first
    history.record("user", "b")
    # Both turns are on disk; the second one carries the new session.
    assert [e["session"] for e in history.read_day()] == [first, second]


def test_a_reconnect_continues_the_same_transcript(store):
    """A dropped Live session is the same conversation. A new session id per
    reconnect would shatter one evening into nine files."""
    history.record("user", "before the drop")
    history.reset_session(history.session_id())
    history.record("assistant", "after the reconnect")
    assert {e["session"] for e in history.read_day()} == {"20260101-000000"}


def test_the_transcript_is_not_the_log_file(store):
    """History and the diagnostic log are separate files for a reason: the log
    rotates at 2 MB, so a conversation kept there disappears by Thursday."""
    from core import logbook
    history.record("user", "hello")
    assert history.history_dir() != logbook.log_dir()


# ── it is reachable: the tool, and the call site ────────────────────────────

def test_the_model_can_read_the_transcript_back(store):
    """'What did we talk about' has to be answerable from what was SAID, not
    from the curated memory — those are different files with different rules."""
    import asyncio
    from core import tool_dispatch

    history.record("user", "book me a table for six")
    history.record("assistant", "Booked for six at eight.")
    assert tool_dispatch.handles("recall_history")
    out = asyncio.run(tool_dispatch.dispatch("recall_history", {}))
    assert "book me a table for six" in out
    assert "JARVIS: Booked for six at eight." in out


def test_the_tool_says_so_instead_of_inventing_a_conversation(store):
    import asyncio
    from core import tool_dispatch

    out = asyncio.run(tool_dispatch.dispatch("recall_history", {}))
    assert "no recorded conversation" in out.lower()


def test_the_tool_refuses_to_walk_the_whole_history(store):
    """`days` is clamped to the retention window: a model asking for 10,000
    days must not turn one tool call into a directory scan."""
    import asyncio
    from core import tool_dispatch

    history.record("user", "only today")
    out = asyncio.run(tool_dispatch.dispatch(
        "recall_history", {"days": 10_000, "turns": 10_000}))
    assert "only today" in out


def test_hitting_the_cap_does_not_make_the_tool_fail(store):
    import asyncio
    from core import tool_dispatch

    out = asyncio.run(tool_dispatch.dispatch("recall_history", {"days": "x"}))
    assert isinstance(out, str)


def test_the_session_writes_the_transcript_at_the_turn_it_was_spoken():
    """The call site matters: a transcript written from a summary would record
    what the assistant remembered, not what the user said. Both halves of a
    turn are recorded where the log line is written."""
    import re
    src = (history.__file__).replace("history.py", "")          # core/
    main = open(Path(src).parent / "main.py", encoding="utf-8").read()

    assert main.count('keep_turn("user"') == 1
    assert main.count('keep_turn("assistant"') == 1
    # And next to the UI log line, which is the definition of "a turn happened".
    for role in ("user", "assistant"):
        block = re.search(r'keep_turn\("%s", \w+\)' % role, main)
        assert block, role
        before = main[:block.start()]
        assert "self.ui.write_log(" in before[-400:], role


def test_the_transcript_import_does_not_pull_in_the_world():
    """`main.py` imports it at startup, so it must stay a leaf module."""
    import subprocess
    import sys
    code = ("import sys; import core.history;"
            "bad=[m for m in ('PyQt6','numpy','psutil','requests','google') "
            "if m in sys.modules]; print(bad)")
    out = subprocess.run([sys.executable, "-c", code], capture_output=True,
                         text=True, cwd=Path(history.__file__).resolve().parents[1])
    assert out.stdout.strip() == "[]", out.stdout + out.stderr
