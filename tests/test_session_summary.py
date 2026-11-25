"""Board 5.5's session summary & timeline policy: search, filter, summarize.

These test the pure policy in `core.session_summary` with no file and no
Qt. The point is the honesty rule: the summary is always marked as a summary
(never a transcript), it describes exactly the set the timeline shows, and a
blank search shows everything rather than nothing.
"""
from __future__ import annotations

from core.session_summary import (ASSISTANT, USER, Summary, Turn, build,
                                  filter_by_time, normalise, search,
                                  summarize)


def _day():
    """A small transcript: a few user turns and assistant replies."""
    return [
        {"role": USER, "text": "Cek harga emas hari ini", "time": "2026-11-25T08:00:00"},
        {"role": ASSISTANT, "text": "Harga emas saat ini Rp 900 ribu.", "time": "2026-11-25T08:00:30"},
        {"role": USER, "text": "Batas anggaran saya 1 juta", "time": "2026-11-25T08:01:00"},
        {"role": ASSISTANT, "text": "Beres, saya catat batasnya.", "time": "2026-11-25T08:01:20"},
        {"role": USER, "text": "Cek gmail saya", "time": "2026-11-25T09:00:00"},
    ]


# ── normalise ──────────────────────────────────────────────────────────────

def test_normalise_drops_empty_turns():
    turns = normalise([
        {"role": USER, "text": "ok", "time": "t1"},
        {"role": USER, "text": "", "time": "t2"},
        {"role": USER, "text": "  ", "time": "t3"},
        {"not-a-dict": True},
    ])
    assert len(turns) == 1
    assert turns[0].text == "ok"


def test_normalise_keeps_role_and_time():
    turns = normalise([{"role": "user", "text": "hi", "time": "2026-11-25T08:00:00"}])
    assert turns[0].role == "user"
    assert turns[0].time == "2026-11-25T08:00:00"


def test_turn_from_entry_accepts_ts_alias():
    turn = Turn.from_entry({"role": "user", "text": "hi", "ts": "2026-11-25T08:00:00"})
    assert turn.time == "2026-11-25T08:00:00"


# ── search ─────────────────────────────────────────────────────────────────

def test_search_is_case_insensitive_and_ordered():
    turns = normalise(_day())
    found = search(turns, "cek")
    assert [t.text for t in found] == ["Cek harga emas hari ini", "Cek gmail saya"]


def test_a_blank_query_returns_everything():
    turns = normalise(_day())
    assert len(search(turns, "")) == len(turns)
    assert len(search(turns, "   ")) == len(turns)


def test_a_query_with_no_match_returns_empty():
    turns = normalise(_day())
    assert search(turns, "zzz-not-present") == []


# ── filter_by_time ─────────────────────────────────────────────────────────

def test_a_since_bound_drops_earlier_turns():
    turns = normalise(_day())
    kept = filter_by_time(turns, since="2026-11-25T08:01:00")
    assert all(t.time >= "2026-11-25T08:01:00" for t in kept)
    assert len(kept) == 3


def test_an_until_bound_drops_later_turns():
    turns = normalise(_day())
    kept = filter_by_time(turns, until="2026-11-25T08:01:00")
    assert all(t.time <= "2026-11-25T08:01:00" for t in kept)


def test_no_bounds_keeps_everything():
    turns = normalise(_day())
    assert len(filter_by_time(turns)) == len(turns)


def test_a_bounded_query_drops_undated_turns():
    """A turn with no time cannot be placed in a window — drop it, don't guess."""
    turns = normalise([
        {"role": USER, "text": "undated", "time": ""},
        {"role": USER, "text": "dated", "time": "2026-11-25T08:00:00"},
    ])
    kept = filter_by_time(turns, since="2026-11-25T00:00:00")
    assert [t.text for t in kept] == ["dated"]


# ── summarize ─────────────────────────────────────────────────────────────

def test_the_summary_is_marked_as_a_summary():
    report = summarize(normalise(_day()))
    assert report.kind == "summary"
    assert isinstance(report, Summary)


def test_the_summary_reports_the_turn_count():
    report = summarize(normalise(_day()))
    assert report.turn_count == 5
    assert "5 giliran" in report.text


def test_the_summary_names_the_topics_the_user_raised():
    report = summarize(normalise(_day()))
    assert "Cek" in report.topics
    assert "Batas" in report.topics


def test_the_summary_states_the_last_thing_said():
    report = summarize(normalise(_day()))
    assert "Cek gmail saya" in report.text


def test_an_empty_transcript_yields_an_honest_summary():
    report = summarize([])
    assert report.kind == "summary"
    assert report.turn_count == 0
    assert "tidak ada percakapan" in report.text.lower()


def test_topics_are_capped():
    turns = normalise([
        {"role": USER, "text": f"topic{i} something", "time": f"t{i}"}
        for i in range(20)
    ])
    report = summarize(turns)
    assert len(report.topics) <= 5


# ── build ─────────────────────────────────────────────────────────────────

def test_build_returns_the_filtered_turns_and_a_matching_summary():
    turns, report = build(_day(), query="cek")
    assert len(turns) == 2
    assert report.turn_count == 2
    assert report.kind == "summary"


def test_build_search_narrows_the_summary_too():
    _, full = build(_day())
    _, narrow = build(_day(), query="gmail")
    assert full.turn_count > narrow.turn_count


def test_build_filters_by_time_and_summarizes_the_window():
    turns, report = build(_day(), since="2026-11-25T08:01:00")
    assert report.turn_count == 3
    assert all(t.time >= "2026-11-25T08:01:00" for t in turns)
