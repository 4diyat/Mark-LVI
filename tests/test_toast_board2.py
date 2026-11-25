"""Board 2: the toast card, the eight-second rule, and the queue's honesty.

WHAT BOARD 2 DRAWS, AND WHAT THIS FILE HOLDS IT TO
    `n02()` stacks three cards and labels them in the margin: "maks. 3 tampil /
    sisanya antre", and the footnote above the desktop says "Hilang otomatis
    8 detik · tidak pernah meminta fokus · maksimal 3 saran per hari".

    Three of those were not true of the code when this file was written:

    1. AUTO-DISMISS WAS SIX SECONDS. `DEFAULT_TTL = 6.0` against the artboard's
       and the brief's 8. A toast that leaves while the user is still reading
       the first line is a toast that did not arrive.

    2. THE CARD HAD NO SHAPE. `ToastQueue` held one string per toast; the
       artboard draws a title at 13 px, a body at 11.5 px, a 3 px accent rule,
       and up to two action buttons. A one-line toast cannot say "Ruang Rapat 2
       · 5 peserta sudah masuk" and offer "Tunda 5 mnt" at the same time.

    3. THE OVERFLOW LABEL WAS NOT THE ARTBOARD'S. It said "2 lagi"; board 2 says
       "+2 lain dalam antrean".

    What is asserted here is the data model and the arithmetic — what a toast
    KNOWS. Where it is drawn is `tests/test_toast_stack.py`, and the two are
    separate on purpose: the queue is read from scheduler threads where a Qt
    widget cannot exist at all.

WHAT THE OWNER CHOSE ABOUT THE CAP
    The fourth toast REPLACES the oldest, and the count says how many were
    replaced. "Sisanya antre" in the artboard was not implemented as a growing
    backlog: a queue that grows without end on a desktop notification surface is
    a queue nobody drains, and the owner chose the smaller, honest version —
    drop the oldest, say the number, never silently.
"""
from __future__ import annotations

import threading
import time


from ui.toast_queue import (DEFAULT_TTL, KIND_INFO, KIND_RISKY, KIND_WARN,
                            VISIBLE_MAX, Toast, ToastQueue)


# ── 1. eight seconds, and it is the artboard's number ─────────────────────

def test_a_toast_lasts_eight_seconds_not_six():
    """`n02()`: "Hilang otomatis 8 detik". The brief says it, the artboard draws
    it, and the code said 6.0 — which is the kind of drift that never fails a
    test because the test was written from the code."""
    assert DEFAULT_TTL == 8.0


def test_the_eight_seconds_are_pinned_as_the_design_number():
    """Board 2's visual reference is `design/new-ui-proposal/02-command-bar.png`.

    The artboard sheet that used to be parsed here (`docs/mockups/build.py`)
    was retired on 2026-11-25: `design/new-ui-proposal/` is now the ONE visual
    source, and it is a PNG, so the design number is pinned here instead of
    parsed from a drawing.
    """
    assert DEFAULT_TTL == 8.0


def test_a_toast_expires_after_its_own_ttl_not_a_shared_clock():
    toast = Toast(text="x", created=0.0, ttl=8.0)
    assert toast.expired(now=7.9) is False
    assert toast.expired(now=8.0) is True


# ── 2. the card's content: title, body, actions ───────────────────────────

def test_a_toast_carries_a_title_a_body_and_actions():
    """Board 2's card is three pieces of text and up to two buttons."""
    toast = Toast(text="Rapat tim dimulai 10 menit lagi",
                  body="Ruang Rapat 2 · 5 peserta sudah masuk",
                  actions=("Buka tautan", "Tunda 5 mnt"))
    assert toast.text == "Rapat tim dimulai 10 menit lagi"
    assert toast.body == "Ruang Rapat 2 · 5 peserta sudah masuk"
    assert toast.actions == ("Buka tautan", "Tunda 5 mnt")


def test_a_toast_without_a_body_or_actions_is_still_a_toast():
    """The artboard's second and fourth cards have a body and no buttons; the
    minimal case must not be a different type."""
    toast = Toast(text="Selesai")
    assert toast.body == ""
    assert toast.actions == ()


def test_actions_are_a_tuple_so_a_caller_cannot_edit_them_later():
    """`Toast` is shared with the widget, which reads it on the UI thread while
    the producer may still hold a reference. A mutable list is a race with a
    friendly face."""
    toast = Toast(text="x", actions=["Buka", "Nanti"])
    assert isinstance(toast.actions, tuple)


def test_more_than_two_actions_are_refused_at_the_door():
    """Board 2 draws two buttons. A third is a card that no longer fits its 96
    px, so it is dropped when the toast is built rather than at paint time."""
    toast = Toast(text="x", actions=("a", "b", "c"))
    assert toast.actions == ("a", "b")


def test_an_empty_action_is_not_a_button():
    """`("Buka", "")` would draw an empty 22 px pill, which reads as a broken
    button. Empty strings are dropped."""
    assert Toast(text="x", actions=("Buka", "", None)).actions == ("Buka",)


# ── 3. the height the artboard draws ──────────────────────────────────────

def test_the_card_height_is_the_artboards_96_or_74():
    """`design/new-ui-proposal/01-ambient-main.png`: 96 with actions, 74 without."""
    assert Toast(text="x", actions=("a",)).height == 96
    assert Toast(text="x").height == 74


def test_the_height_is_pinned_as_the_design_number():
    """96 px with actions, 74 px without — the card the proposal draws.

    Same retirement as the TTL test: the number used to be read out of
    `build.py`'s `toast()` helper; the visual reference is now
    `design/new-ui-proposal/01-ambient-main.png` (the toast card) and the
    number is pinned here.
    """
    assert Toast(text="x", actions=("a",)).height == 96
    assert Toast(text="x").height == 74


# ── 4. the accent rule, and what "risky" looks like ───────────────────────

def test_the_accent_follows_the_kind():
    """Board 2's card has a 3 px rule down its left edge in the accent colour.
    Info and warn are cyan; risky is amber — the same rule board 14a uses for a
    confirmation, so a dangerous toast cannot look like a friendly one."""
    assert Toast(text="x", kind=KIND_INFO).accent == "#3486fe"
    assert Toast(text="x", kind=KIND_WARN).accent == "#3486fe"
    assert Toast(text="x", kind=KIND_RISKY).accent == "#ff9a40"


def test_an_unknown_kind_is_info_and_not_an_error():
    """The caller is usually an action that just succeeded. A typo in a label
    must not turn a completed action into a failed one."""
    toast = Toast(text="x", kind="nonsense")
    assert toast.kind == KIND_INFO
    assert toast.accent == "#3486fe"


# ── 5. the overflow label, in the artboard's words ────────────────────────

def test_the_overflow_label_is_the_artboards_phrase():
    """The design's phrase: `f"+{hidden} lain dalam antrean"`.

    It said "2 lagi" — shorter, and wrong in a way that matters: "lagi" reads as
    "two more will follow", which is exactly what does NOT happen when the cap
    replaced them.
    """
    q = ToastQueue(visible_max=2)
    for text in ("a", "b", "c"):
        q.push(text)
    assert q.overflow_label() == "+1 lain dalam antrean"


def test_the_label_speaks_indonesian_the_way_the_design_does():
    """The panel and the toasts are Indonesian; `i18n` has no key for this
    string because it is the design's own phrase, and inventing a key
    would mean a translated toast saying a different thing from the design.

    The phrase used to be parsed out of `build.py`; the visual reference is
    `design/new-ui-proposal/`, so the phrase is pinned here.
    """
    q = ToastQueue(visible_max=1)
    q.push("a")
    q.push("b")
    assert "lain dalam antrean" in q.overflow_label()


def test_the_label_is_empty_when_nothing_was_lost():
    q = ToastQueue(visible_max=3)
    q.push("a")
    assert q.overflow_label() == ""


# ── 6. what the queue still promises, now with the richer card ────────────

def test_push_keeps_the_card_intact():
    q = ToastQueue()
    q.push("Judul", kind=KIND_WARN, body="isi", actions=("Buka",))
    toast = q.current()[0]
    assert (toast.text, toast.body, toast.actions, toast.kind) == (
        "Judul", "isi", ("Buka",), KIND_WARN)


def test_the_drop_count_survives_a_reset_of_the_dropped_counter():
    q = ToastQueue(visible_max=1)
    q.push("a")
    q.push("b")
    q.clear_dropped()
    assert q.dropped() == 0
    assert [t.text for t in q.current()] == ["b"]


def test_an_expired_toast_is_not_counted_as_dropped():
    """Expiry is not a loss: the user saw it. Adding it to the overflow count
    would make the label accuse the queue of losing something it delivered."""
    q = ToastQueue(visible_max=3, ttl=0.01)
    q.push("gone")
    time.sleep(0.05)
    assert q.current() == []
    assert q.dropped() == 0
    assert q.overflow_label() == ""


def test_pushing_from_many_threads_never_exceeds_the_cap():
    """Unchanged behaviour, kept because the richer card made the lock easier to
    get wrong: `push` now builds a `Toast` with tuple actions OUTSIDE the lock,
    and only appends inside it."""
    q = ToastQueue(visible_max=3)

    def work(n):
        for i in range(40):
            q.push(f"t{n}-{i}")

    threads = [threading.Thread(target=work, args=(n,)) for n in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(q) <= 3


def test_the_cap_is_still_three_and_still_the_artboards():
    assert VISIBLE_MAX == 3
