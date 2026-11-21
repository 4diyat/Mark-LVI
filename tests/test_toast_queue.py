"""The toast queue: bounded, ordered, and honest about what it dropped.

The cap is the interesting part. A stack that quietly discards the fourth toast
looks exactly like a stack that lost it, so the queue keeps a count and turns it
into a label the user can read.
"""
from __future__ import annotations

import importlib.util
import pathlib
import sys
import threading

# Loaded by PATH, not by `import ui.toast_queue`: `ui/__init__.py` re-exports
# the window and therefore needs PyQt6, which CI deliberately does not install.
# The queue itself is Qt-free — that is the whole point of it living here — so
# the test reaches it the way the repo already reaches `ui/metrics.py`.
_SPEC = importlib.util.spec_from_file_location(
    "toast_queue_under_test",
    pathlib.Path(__file__).resolve().parent.parent / "ui" / "toast_queue.py")
assert _SPEC and _SPEC.loader
toast_queue = importlib.util.module_from_spec(_SPEC)
# Registered before execution: a `@dataclass` looks its own module up in
# `sys.modules` while the class body runs, and finds None otherwise.
sys.modules[_SPEC.name] = toast_queue
_SPEC.loader.exec_module(toast_queue)

KIND_INFO = toast_queue.KIND_INFO
KIND_RISKY = toast_queue.KIND_RISKY
KIND_WARN = toast_queue.KIND_WARN
Toast = toast_queue.Toast
ToastQueue = toast_queue.ToastQueue
VISIBLE_MAX = toast_queue.VISIBLE_MAX


def test_one_push_one_toast():
    q = ToastQueue()
    assert q.push("Laporan siap") is not None
    assert len(q) == 1
    assert q.current()[0].text == "Laporan siap"


def test_empty_text_is_not_a_toast():
    q = ToastQueue()
    assert q.push("   ") is None
    assert q.push(None) is None
    assert len(q) == 0


def test_an_unknown_kind_becomes_info_rather_than_being_refused():
    q = ToastQueue()
    toast = q.push("something", "warning-ish")
    assert toast is not None
    assert toast.kind == KIND_INFO


def test_the_three_kinds_survive_the_round_trip():
    q = ToastQueue()
    for kind in (KIND_INFO, KIND_WARN, KIND_RISKY):
        q.push(kind, kind)
    assert [t.kind for t in q.current()] == [KIND_INFO, KIND_WARN, KIND_RISKY]


def test_order_is_oldest_first():
    q = ToastQueue()
    for i in range(3):
        q.push(f"t{i}")
    assert [t.text for t in q.current()] == ["t0", "t1", "t2"]


def test_the_cap_drops_the_oldest_and_counts_it():
    q = ToastQueue(visible_max=3)
    for i in range(5):
        q.push(f"t{i}")
    assert [t.text for t in q.current()] == ["t2", "t3", "t4"]
    assert q.dropped() == 2


def test_the_overflow_label_is_empty_until_something_is_lost():
    q = ToastQueue(visible_max=2)
    q.push("a")
    assert q.overflow_label() == ""
    q.push("b")
    assert q.overflow_label() == ""
    q.push("c")
    assert q.overflow_label() == "1 lagi"
    q.push("d")
    assert q.overflow_label() == "2 lagi"


def test_clearing_the_dropped_count_does_not_clear_the_stack():
    q = ToastQueue(visible_max=1)
    q.push("a")
    q.push("b")
    q.clear_dropped()
    assert q.dropped() == 0
    assert len(q) == 1


def test_clear_empties_everything():
    q = ToastQueue(visible_max=1)
    q.push("a")
    q.push("b")
    q.clear()
    assert len(q) == 0
    assert q.dropped() == 0


def test_dismiss_removes_one_by_identity():
    q = ToastQueue()
    first = q.push("a")
    q.push("b")
    assert q.dismiss(first) is True
    assert [t.text for t in q.current()] == ["b"]


def test_dismissing_twice_is_false_not_an_error():
    q = ToastQueue()
    first = q.push("a")
    q.dismiss(first)
    assert q.dismiss(first) is False


def test_dismiss_top_returns_the_oldest():
    q = ToastQueue()
    q.push("a")
    q.push("b")
    assert q.dismiss_top().text == "a"
    assert [t.text for t in q.current()] == ["b"]


def test_dismiss_top_on_an_empty_queue_is_none():
    assert ToastQueue().dismiss_top() is None


def test_a_toast_expires_on_its_own():
    toast = Toast(text="x", created=0.0, ttl=6.0)
    assert toast.expired(now=5.9) is False
    assert toast.expired(now=6.0) is True


def test_expired_toasts_are_removed_when_the_stack_is_read():
    q = ToastQueue()
    toast = q.push("x")
    toast.created -= 1000
    assert q.current() == []
    assert len(q) == 0


def test_a_zero_ttl_means_it_is_gone_before_it_is_shown():
    """A degenerate TTL must not make the queue permanent."""
    q = ToastQueue(ttl=0.0)
    q.push("x")
    assert q.current() == []


def test_a_capacity_of_zero_is_treated_as_one():
    """The alternative — an unlimited stack — is a worse failure than a cap of 1."""
    q = ToastQueue(visible_max=0)
    q.push("a")
    q.push("b")
    assert len(q) == 1
    assert q.dropped() == 1


def test_the_drawn_board_agrees_with_the_default_cap():
    """Board 2 draws three toasts in a 330 px stack; this keeps the two honest."""
    assert VISIBLE_MAX == 3


def test_concurrent_pushes_never_exceed_the_cap():
    q = ToastQueue(visible_max=3)
    threads = [threading.Thread(target=q.push, args=(f"t{i}",)) for i in range(60)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(q) <= 3
    assert q.dropped() >= 57
