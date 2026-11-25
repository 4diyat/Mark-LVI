"""actions/session_summary.py — the session summary & timeline adapter
(board 5.5, board 8 extended).

WHAT THIS DOES
    Reads the real transcript from `core.history` and hands it to the pure
    policy in `core.session_summary`, which searches it, filters it to a
    time window, and builds the structural summary. This module is the one
    place that touches the transcript files; it never decides what the
    transcript means.

WHY THE ADAPTERS SPLIT
    The policy in `core/session_summary.py` is pure — it takes a list of
    dicts and returns turns and a summary. That is so a test can drive every
    path with a fixture. This adapter reads the day files through the
    existing `core.history` readers and passes the rows through unchanged, so
    the policy never learns where the turns came from.

WHAT IT DOES NOT DO
    It does not write the summary back as memory and it does not call a
    model. The summary is structural and deterministic; the page shows it as
    a summary (the policy marks it `kind="summary"`) and can jump to the raw
    turns. The existing `memory_manager.save_session_summary` is a separate
    convenience for the assistant's own recap and is not used here.
"""
from __future__ import annotations

from typing import Optional


def read_day(day: Optional[str] = None) -> list[dict]:
    """Every turn recorded on a day, oldest first.

    A read that fails (a locked file, a missing dir) returns an empty list
    rather than raising: the summary page must render "no conversation" for
    an unreadable transcript, not crash. An empty transcript is a fact; a
    crash is a bug the user cannot act on.
    """
    try:
        from core.history import read_day as _read_day
        return _read_day(day)
    except Exception:                              # noqa: BLE001
        return []


def days(limit: int = 14) -> list[str]:
    """The days that have a transcript, newest first."""
    try:
        from core.history import days as _days
        return _days(limit)
    except Exception:                              # noqa: BLE001
        return []


def build(
    day: Optional[str] = None,
    *,
    query: str = "",
    since: str = "",
    until: str = "",
) -> "tuple[list, object]":
    """Build the timeline + summary for one day, through the policy.

    `day` defaults to today. The returned tuple is `(turns, summary)` where
    `turns` are the filtered `Turn` objects the page renders and `summary`
    is the `Summary` describing that same filtered set.
    """
    from core.session_summary import build as _build

    return _build(read_day(day), query=query, since=since, until=until)


__all__ = ["read_day", "days", "build"]
