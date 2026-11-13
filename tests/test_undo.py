"""One undo stack, and the promise it makes to the user.

WHY THIS FILE EXISTS
    `core/undo.py` is the reason the assistant does not ask "are you sure?"
    before everything — it acts, remembers how to reverse it, and lets the user
    say "undo" afterwards. That trade only works if the stack is right: an entry
    that cannot be reversed is worse than no entry, because the user is told
    there is something to undo and there is not.

    Everything here is checked against a real stack, reset between tests, so
    the depth limit and the ordering are exercised rather than assumed.
"""
from __future__ import annotations

import threading

import pytest

from core import undo


@pytest.fixture(autouse=True)
def empty_stack():
    undo.clear()
    yield
    undo.clear()


def test_pushing_makes_undo_available_and_says_what_it_would_do():
    undo.push_undo("volume → 30%", lambda: "volume back to 70%")

    assert undo.can_undo() is True
    assert undo.peek() == "volume → 30%"
    assert undo.history() == ["volume → 30%"]


def test_undo_runs_the_callable_and_reports_what_it_did():
    calls = []
    undo.push_undo("moved report.pdf", lambda: calls.append(1) or "put it back")

    message = undo.undo_last()

    assert calls == [1]
    assert "Undone: moved report.pdf" in message
    assert "put it back" in message


def test_undo_takes_the_entry_off_the_stack_even_when_it_succeeds():
    undo.push_undo("one", lambda: "")
    undo.undo_last()

    assert undo.can_undo() is False
    assert undo.peek() == ""


def test_undo_with_nothing_to_undo_explains_what_it_tracks():
    message = undo.undo_last()

    assert "nothing to undo" in message.lower()
    assert "files I moved" in message


def test_a_failing_undo_does_not_leave_the_entry_behind():
    """It is popped BEFORE it runs, on purpose.

    The world may have moved on — the file the user wants back may have been
    deleted by something else — and an entry that fails is an entry that will
    fail again on every press.
    """
    def broken():
        raise RuntimeError("the file is gone")

    undo.push_undo("restore notes.txt", broken)

    message = undo.undo_last()

    assert "Could not undo 'restore notes.txt'" in message
    assert "the file is gone" in message
    assert undo.can_undo() is False


def test_newest_first_is_the_order_the_user_expects():
    for label in ("first", "second", "third"):
        undo.push_undo(label, lambda: "")

    assert undo.history() == ["third", "second", "first"]
    assert undo.peek() == "third"


def test_the_stack_is_bounded_and_drops_the_oldest():
    """A closure holds a file's old contents; the stack cannot grow forever."""
    for i in range(undo.MAX_DEPTH + 5):
        undo.push_undo(f"step {i}", lambda: "")

    labels = undo.history()
    assert len(labels) == undo.MAX_DEPTH
    assert labels[0] == f"step {undo.MAX_DEPTH + 4}"      # newest kept
    assert "step 0" not in labels                          # oldest, correctly gone


def test_a_long_label_is_truncated_not_refused():
    undo.push_undo("x" * 500, lambda: "")

    assert len(undo.peek()) == 120


def test_a_non_callable_is_ignored_rather_than_crashing_later():
    """Better no entry than an entry whose undo raises TypeError on press."""
    undo.push_undo("typo", None)             # type: ignore[arg-type]
    undo.push_undo("also a typo", "not a function")  # type: ignore[arg-type]

    assert undo.can_undo() is False


def test_clear_forgets_everything():
    undo.push_undo("a", lambda: "")
    undo.push_undo("b", lambda: "")

    undo.clear()

    assert undo.can_undo() is False
    assert undo.history() == []


def test_pushing_from_many_threads_keeps_the_depth_limit():
    """Actions run on executor threads; the lock is the reason this is safe."""
    def push(n):
        undo.push_undo(f"t{n}", lambda: "")

    threads = [threading.Thread(target=push, args=(i,)) for i in range(50)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(undo.history()) == undo.MAX_DEPTH


def test_an_undo_that_returns_nothing_still_says_it_was_undone():
    """The reverse of a settings change has no sentence to add."""
    undo.push_undo("brightness → 10%", lambda: "")

    message = undo.undo_last()

    assert message == "Undone: brightness → 10%."
