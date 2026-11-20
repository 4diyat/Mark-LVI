"""The gate in front of anything that cannot be undone.

WHY THIS FILE EXISTS
    `core/confirm.py` is the last thing between the assistant and a shutdown, a
    delete, a payment. Its whole value is that it REFUSES when it cannot ask —
    there is no display, the callback raised, the user took too long — and that
    refusal is a sentence the model reads out loud. So the interesting tests are
    the ones where nothing happens:

        * no interface bound        → refuse, do not do it
        * the banner cannot draw   → refuse, do not do it
        * the user said nothing     → expire, do not do it
        * the user said cancel      → do not do it

    A gate that fails open is worse than no gate, because the prompt tells the
    model it is there.

    `TIMEOUT_SECONDS` is not patched in most of these: a test that sleeps 90 s is
    a test nobody runs. The clock is moved instead, which is the same edit the
    production code would need to become testable — and it stays honest because
    the expiry the tests exercise is the real comparison.
"""
from __future__ import annotations

import threading
import time

import pytest

from core import confirm


@pytest.fixture(autouse=True)
def clean_gate(monkeypatch):
    """A fresh module for every test: the pending action is module state."""
    monkeypatch.setattr(confirm, "_pending", None)
    monkeypatch.setattr(confirm, "_show_cb", None)
    monkeypatch.setattr(confirm, "_hide_cb", None)
    monkeypatch.setattr(confirm, "_log_cb", None)
    yield
    confirm._pending = None


def bind(shown: list, hidden: list, log: list) -> None:
    confirm.bind(lambda token, title, detail: shown.append((token, title, detail)),
                 lambda token: hidden.append(token),
                 lambda message: log.append(message))


def wait_for(thread_holder: list) -> None:
    for t in thread_holder:
        t.join(timeout=5)


def run_in_threads() -> None:
    """`resolve()` starts a daemon thread; wait for the ones this test made."""
    for t in threading.enumerate():
        if t.name.startswith("confirm-"):
            t.join(timeout=5)


# ── the refusal that matters most ───────────────────────────────────────────

def test_with_no_interface_the_action_is_not_performed():
    done = []
    message = confirm.request("shutdown", "Shut down", "the machine now",
                              lambda: done.append(1) or "off")

    assert done == []
    assert "interface is not available" in message
    assert "not done it" in message


def test_the_model_is_told_to_ask_rather_than_to_act():
    shown, hidden, log = [], [], []
    bind(shown, hidden, log)

    message = confirm.request("delete", "Delete the folder", "and everything in it",
                              lambda: "deleted")

    assert "CONFIRMATION_PENDING" in message
    assert "before you do it" in message
    assert "Do not claim it is done" in message


def test_a_banner_that_cannot_be_drawn_cancels_the_request():
    """The gate must not stay armed if the user was never actually asked."""
    def broken_show(_token, _title, _detail):
        raise RuntimeError("no window")

    confirm.bind(broken_show, lambda: None, lambda _m: None)

    message = confirm.request("shutdown", "Shut down", "-", lambda: "off")

    assert "Nothing was done" in message
    assert confirm.pending_title() == ""


# ── the two answers ─────────────────────────────────────────────────────────

def test_confirm_runs_the_action_once_and_hides_the_banner():
    shown, hidden, log = [], [], []
    bind(shown, hidden, log)
    ran = []
    confirm.request("trash", "Empty the trash", "-",
                    lambda: ran.append(1) or "trash is empty")

    confirm.resolve(confirm._pending.token, True)
    run_in_threads()

    assert ran == [1]
    assert len(hidden) == 1 and hidden[0] == shown[0][0]
    assert any("Confirmed" in line for line in log)
    assert confirm.pending_title() == ""


def test_cancel_does_not_run_anything():
    shown, hidden, log = [], [], []
    bind(shown, hidden, log)
    ran = []
    confirm.request("trash", "Empty the trash", "-",
                    lambda: ran.append(1) or "done")

    confirm.resolve(confirm._pending.token, False)
    run_in_threads()

    assert ran == []
    assert any("Cancelled" in line for line in log)


def test_the_action_runs_off_the_qt_thread():
    """Shutting the machine down inside a button handler freezes the window."""
    shown, hidden, log = [], [], []
    bind(shown, hidden, log)
    where = {}
    confirm.request("shutdown", "Shut down", "-",
                    lambda: where.setdefault("thread", threading.current_thread().name)
                    or "off")

    caller = threading.current_thread().name
    confirm.resolve(confirm._pending.token, True)
    run_in_threads()

    assert where["thread"] != caller
    assert where["thread"].startswith("confirm-")


def test_a_failing_action_is_reported_not_raised():
    shown, hidden, log = [], [], []
    bind(shown, hidden, log)

    def boom():
        raise RuntimeError("the disk refused")

    confirm.request("wipe", "Wipe the disk", "-", boom)
    confirm.resolve(confirm._pending.token, True)         # must not raise
    run_in_threads()

    assert any("the disk refused" in line for line in log)


# ── expiry ─────────────────────────────────────────────────────────────────

def test_an_old_banner_expires_instead_of_firing_hours_later():
    """A live shutdown button left on the HUD for the rest of the day."""
    shown, hidden, log = [], [], []
    bind(shown, hidden, log)
    ran = []
    confirm.request("shutdown", "Shut down", "-",
                    lambda: ran.append(1) or "off")

    # The clock, not the sleep: the module compares with time.monotonic().
    real = time.monotonic
    try:
        confirm.time.monotonic = lambda: real() + confirm.TIMEOUT_SECONDS + 1
        confirm.resolve(confirm._pending.token, True)
        run_in_threads()
    finally:
        confirm.time.monotonic = real

    assert ran == []
    assert any("expired" in line for line in log)


def test_an_expired_banner_is_no_longer_shown_as_pending():
    shown, hidden, log = [], [], []
    bind(shown, hidden, log)
    confirm.request("shutdown", "Shut down", "-", lambda: "off")

    real = time.monotonic
    try:
        confirm.time.monotonic = lambda: real() + confirm.TIMEOUT_SECONDS + 1
        assert confirm.pending_title() == ""
    finally:
        confirm.time.monotonic = real


def test_a_fresh_banner_is_pending_and_says_what_it_is():
    shown, hidden, log = [], [], []
    bind(shown, hidden, log)

    confirm.request("shutdown", "Shut down the machine", "-", lambda: "off")

    assert confirm.pending_title() == "Shut down the machine"
    assert [(title, detail) for _, title, detail in shown] == [("Shut down the machine", "-")]


def test_resolving_when_nothing_is_pending_is_harmless():
    """The UI can call this after a timeout; it must not raise or run anything."""
    shown, hidden, log = [], [], []
    bind(shown, hidden, log)

    confirm.resolve("no-such-request", True)

    assert hidden == []


def test_a_hide_callback_that_raises_does_not_stop_the_confirmed_action():
    shown, log = [], []
    confirm.bind(lambda token, t, d: shown.append(t),
                 lambda token: (_ for _ in ()).throw(RuntimeError("gone")),
                 log.append)
    ran = []
    confirm.request("trash", "Empty", "-", lambda: ran.append(1) or "done")

    confirm.resolve(confirm._pending.token, True)
    run_in_threads()

    assert ran == [1]


def test_second_request_is_refused_and_old_token_cannot_resolve_new():
    shown, hidden, log, ran = [], [], [], []
    bind(shown, hidden, log)
    confirm.request("a", "First", "-", lambda: ran.append("a"))
    first = shown[-1][0]
    result = confirm.request("b", "Second", "-", lambda: ran.append("b"))
    assert "already awaiting" in result and len(shown) == 1
    confirm.resolve(first, False)
    confirm.request("b", "Second", "-", lambda: ran.append("b"))
    second = shown[-1][0]
    assert first != second and not confirm.is_pending(first) and confirm.is_pending(second)
    confirm.resolve(first, True)
    assert confirm.is_pending(second) and hidden == [first]
    confirm.resolve(second, True)
    confirm.resolve(second, True)
    run_in_threads()
    assert ran == ["b"] and hidden == [first, second]


def test_concurrent_requests_only_one_can_be_armed():
    shown, hidden, log = [], [], []
    bind(shown, hidden, log)
    barrier = threading.Barrier(12)
    results = []
    def run(i):
        barrier.wait(timeout=5)
        results.append(confirm.request(str(i), str(i), "-", lambda: "done"))
    threads = [threading.Thread(target=run, args=(i,)) for i in range(12)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)
        assert not thread.is_alive()
    assert len(shown) == 1
    assert sum("CONFIRMATION_PENDING" in result for result in results) == 1
    assert sum("already awaiting" in result for result in results) == 11


def test_late_failed_show_cannot_clear_a_new_request(monkeypatch):
    started, release = threading.Event(), threading.Event()
    shown = []
    def show(token, title, detail):
        if title == "First":
            started.set()
            assert release.wait(5)
            raise RuntimeError("old callback failed")
        shown.append(token)
    confirm.bind(show, lambda token: None)
    t = threading.Thread(target=lambda: confirm.request("a", "First", "-", lambda: "a"))
    t.start()
    assert started.wait(5)
    now = time.monotonic()
    monkeypatch.setattr(confirm.time, "monotonic", lambda: now + confirm.TIMEOUT_SECONDS + 1)
    confirm.request("b", "Second", "-", lambda: "b")
    release.set()
    t.join(timeout=5)
    assert not t.is_alive() and confirm.is_pending(shown[0])


def test_overlong_details_are_rejected_instead_of_silently_truncated():
    shown, hidden, log = [], [], []
    bind(shown, hidden, log)
    for title, detail in (("x" * 121, "detail"), ("title", "x" * 301)):
        message = confirm.request("unsafe", title, detail, lambda: pytest.fail("must not run"))
        assert "complete action details" in message
    assert shown == [] and confirm.pending_title() == ""
