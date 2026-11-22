"""The fake in `tests/qtstub.py`, held to the promises it makes in its comments.

WHY THIS FILE EXISTS
    Every Qt test in this repository runs against a stub, and a stub that
    answers plausibly is worse than no stub: it lets a test pass on behaviour
    real Qt does not have. The stub's own source says so, twice — once about
    `move`, which has to REMEMBER a position or the drag tests save nothing, and
    once about the signals, which are declared "on the INSTANCE, because
    `clicked` … on the class would be shared by every button in the window".

    That second comment was false. `clicked = _Signal()` was a class attribute,
    so every button in the process shared one signal object, and board 6's test
    went looking for the audit-log handlers and found the history page's too.
    The comment described the intent; nothing tested it. This file tests it.

WHAT IS AND IS NOT COVERED
    Signal identity, and the one behaviour that depends on it. The rest of the
    stub is checked where it is used (`tests/test_tray_panel.py` and the board
    tests assert positions, text and visibility), because a stub property tested
    only here would be a property no page relies on.
"""


def test_each_stub_widget_gets_its_own_signals():
    """`clicked` on one button must not fire another button's handlers.

    THE DEFECT THIS PINS
        `clicked = _Signal()` lived on the class. A test that pressed board 6's
        "Hapus riwayat" also pressed the history page's, and a wiring test that
        expected `["erase"]` saw `["history_export", "history_clear", …]`. Worse:
        when those extra calls happened to be the same two keys in a different
        order, the test PASSED — a shared signal makes a wiring test unable to
        tell one button from another, which is the whole thing a wiring test is
        for.
    """
    from tests.qtstub import fresh_ui, restore_ui

    saved = fresh_ui()
    try:
        from PyQt6.QtWidgets import QPushButton

        first, second = QPushButton("a", None), QPushButton("b", None)
        assert first.clicked is not second.clicked, (
            "two buttons share one `clicked`; every press fires both")

        hits = []
        first.clicked.connect(lambda: hits.append("first"))
        second.clicked.connect(lambda: hits.append("second"))
        first.clicked.emit()
        assert hits == ["first"], f"one button's click fired {hits}"

        # And the reverse direction, so a stub that always fires the FIRST
        # widget's slots cannot pass the assertion above.
        hits.clear()
        second.clicked.emit()
        assert hits == ["second"], f"the second button's click fired {hits}"
    finally:
        restore_ui(saved)


def test_the_stub_click_is_not_silently_swallowed():
    """A press must be expressible. `QPushButton.click()` does not exist in the
    stub, and `__getattr__` used to answer with a no-op, so a test could write
    `button.click()` and press nothing while reading as a press.

    This pins the shape the tests use — `clicked.emit()` — so the next person
    writing a press is told how, by a test that fails if it stops working,
    rather than by a test that passes while doing nothing.
    """
    from tests.qtstub import fresh_ui, restore_ui

    saved = fresh_ui()
    try:
        from PyQt6.QtWidgets import QPushButton

        button = QPushButton("Kirim", None)
        fired = []
        button.clicked.connect(lambda: fired.append(True))
        button.clicked.emit()
        assert fired == [True]
    finally:
        restore_ui(saved)
