"""The stateless tool branches, tested without a window or a Gemini socket.

These four lived inside `JarvisLive._execute_tool`, where reaching them meant
constructing a 2,400-line class that wants a Qt window, a microphone and an open
websocket. They are pure enough to move, so they moved to core/tool_dispatch.py
and are tested directly here.
"""
from __future__ import annotations

import asyncio

import pytest

from core import tool_dispatch


def run(coro):
    return asyncio.run(coro)


def test_it_claims_exactly_the_tools_it_can_answer():
    assert tool_dispatch.handles("recall_memory")
    assert tool_dispatch.handles("undo")
    assert tool_dispatch.handles("system_status")
    assert tool_dispatch.handles("manage_monitor")
    # The ones that need live session state must NOT be claimed, or main.py will
    # route them here and get a KeyError where a working tool used to be.
    for live in ("screen_process", "shutdown_jarvis", "save_memory", "close_camera"):
        assert not tool_dispatch.handles(live)


def test_a_tool_it_does_not_handle_raises_rather_than_returning_a_string():
    with pytest.raises(KeyError):
        run(tool_dispatch.dispatch("screen_process", {}))


def test_undo_list_says_so_when_there_is_nothing(monkeypatch):
    monkeypatch.setattr(tool_dispatch.undo_stack, "history", lambda: [])
    assert "have not changed anything" in run(
        tool_dispatch.dispatch("undo", {"action": "list"}))


def test_undo_list_numbers_most_recent_first(monkeypatch):
    monkeypatch.setattr(tool_dispatch.undo_stack, "history",
                        lambda: ["deleted notes.txt", "moved a.py"])
    out = run(tool_dispatch.dispatch("undo", {"action": "list"}))
    assert out.index("1. deleted notes.txt") < out.index("2. moved a.py")


def test_bare_undo_undoes_the_last_thing(monkeypatch):
    called = []
    monkeypatch.setattr(tool_dispatch.undo_stack, "undo_last",
                        lambda: called.append(True) or "Restored notes.txt")
    assert run(tool_dispatch.dispatch("undo", {})) == "Restored notes.txt"
    assert called == [True]


def test_manage_monitor_needs_a_topic_for_add_and_remove():
    msg = run(tool_dispatch.dispatch("manage_monitor", {"action": "add"}))
    assert "Specify action" in msg


def test_manage_monitor_lists_when_empty(monkeypatch):
    monkeypatch.setattr("actions.background_monitor.list_monitors", lambda: [])
    assert "No topics" in run(
        tool_dispatch.dispatch("manage_monitor", {"action": "list"}))


def test_manage_monitor_lists_what_is_there(monkeypatch):
    monkeypatch.setattr("actions.background_monitor.list_monitors",
                        lambda: ["rtx 5090 stock", "inbox"])
    out = run(tool_dispatch.dispatch("manage_monitor", {"action": "list"}))
    assert "rtx 5090 stock" in out and "inbox" in out


def test_recall_memory_passes_a_query_through(monkeypatch):
    seen = {}

    def fake_search(query, limit=8):
        seen["query"], seen["limit"] = query, limit
        return "found 1 thing"

    monkeypatch.setattr("memory.memory_manager.search_memory", fake_search)
    out = run(tool_dispatch.dispatch("recall_memory", {"query": "wifi password"}))
    assert out == "found 1 thing"
    assert seen == {"query": "wifi password", "limit": 8}
