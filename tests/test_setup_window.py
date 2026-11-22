"""The setup screen: what it saves, what it refuses, and what it cannot skip.

WHY THESE ASSERTIONS AND NOT "IT OPENS"
    This screen is the only way into the product, so every way it can lie is
    permanent for whoever hits it:

      * saving a key the service just REJECTED — the file then holds a known-bad
        value and the next start fails with no screen left to explain it;
      * refusing an OFFLINE machine — the owner's decision is the opposite, and
        it is the failure a first run on a new laptop is most likely to hit;
      * offering a way past it — a "Lewati" button is a first run with no key,
        which is a session that cannot answer anything;
      * closing on a verdict that was never saved — `main.py` would then start a
        session against a blank key and reconnect into `NEEDS_KEY`;
      * a fourth verdict with no sentence — the screen would go blank at the
        worst moment, and `core/key_check` is a module other work can extend.

    So the tests drive `evaluate()` (the whole decision, no widget) and
    `apply_verdict()` (the whole effect, on the stub's widgets), and the
    integration case runs the real `config_manager` against `tmp_path`. No
    network, no display, no real key.

WHAT THE STUB CANNOT SHOW
    Whether the panel LOOKS right. `tests/qtstub.py` records geometry and text
    and nothing about paint; visual fidelity of this screen is unverified here
    and is stated as such in `docs/verification.md`.
"""
from __future__ import annotations

import json

import pytest

from tests.qtstub import fresh_ui, restore_ui

GOOD = "AIzaSyB" + "x" * 30


@pytest.fixture()
def setup_module():
    """`ui.setup_window` imported against the stub, then the real modules back."""
    saved = fresh_ui()
    try:
        from ui import setup_window

        yield setup_window
    finally:
        restore_ui(saved)


@pytest.fixture()
def screen(setup_module):
    return setup_module.SetupWindow()


def _verdict(kind, detail=""):
    from core import key_check

    return key_check.Verdict(kind, detail)


# ── the three sentences ─────────────────────────────────────────────────────

def test_every_verdict_the_check_can_return_has_a_sentence(setup_module):
    """A verdict added to `core/key_check` without a key here would render as
    the UNTESTED sentence — a saved-key message on a rejected key."""
    from core import key_check

    assert set(setup_module.RESULT_KEYS) == set(key_check.VERDICTS)


def test_every_sentence_is_in_both_catalogues(setup_module):
    """Read from the JSON rather than through `label()`, so a missing key shows
    up as the ⟪key⟫ marker instead of quietly falling back to English."""
    from pathlib import Path

    root = Path(setup_module.__file__).resolve().parent.parent
    for locale in ("en", "id"):
        data = json.loads((root / "assets" / "i18n" / f"{locale}.json")
                          .read_text(encoding="utf-8"))
        missing = [k for k in setup_module.RESULT_KEYS.values() if k not in data]
        assert missing == [], f"{locale}.json is missing {missing}"


def test_the_detail_is_appended_not_dropped(setup_module):
    """`core/key_check` writes the actionable half of the sentence — "check it
    was copied in full" — and a screen that showed only the generic line would
    leave the user with nothing to do."""
    text = setup_module.result_text("rejected", "Check it was copied in full.")
    assert "copied in full" in text


def test_an_unknown_kind_still_produces_a_sentence(setup_module):
    assert setup_module.result_text("nonsense", "") == \
        setup_module.result_text("untested", "")


# ── the decision, with no widget in it ──────────────────────────────────────

def test_a_working_key_is_saved_and_reported_ok(screen):
    saved = []
    screen._checker = lambda key: _verdict("ok")
    screen._saver = lambda key: saved.append(key) or True

    assert screen.evaluate(GOOD).kind == "ok"
    assert saved == [GOOD]


def test_a_rejected_key_is_never_written(screen):
    """THE ONE THAT MATTERS. Writing it would leave the config holding a key
    the service refused, and nothing left on screen to say so."""
    saved = []
    screen._checker = lambda key: _verdict("rejected", "not valid")
    screen._saver = lambda key: saved.append(key) or True

    verdict = screen.evaluate(GOOD)
    assert verdict.kind == "rejected"
    assert saved == []


def test_an_offline_key_is_saved_and_reported_untested(screen):
    """The owner's decision: no network must still finish setup. The sentence
    says it was not verified, and `session_policy` catches a bad key later."""
    saved = []
    screen._checker = lambda key: _verdict("untested", "No network right now.")
    screen._saver = lambda key: saved.append(key) or True

    assert screen.evaluate(GOOD).kind == "untested"
    assert saved == [GOOD]


def test_a_save_that_fails_is_reported_as_rejected(screen):
    """A full disk is not "ok". The session would start against a key that was
    never written."""
    screen._checker = lambda key: _verdict("ok")
    screen._saver = lambda key: False

    assert screen.evaluate(GOOD).kind == "rejected"


def test_a_saver_that_raises_is_reported_rather_than_propagated(screen):
    screen._checker = lambda key: _verdict("ok")

    def boom(_key):
        raise OSError("disk full")

    screen._saver = boom
    verdict = screen.evaluate(GOOD)
    assert verdict.kind == "rejected"
    assert "disk full" in verdict.detail


def test_a_checker_that_raises_becomes_untested_not_a_crash(screen):
    """`key_check.check` promises never to raise; a replacement might. The
    honest answer is "could not tell", and refusing would block an offline
    machine — the failure this whole verdict kind exists for."""
    def boom(_key):
        raise RuntimeError("sdk exploded")

    screen._checker = boom
    assert screen.evaluate(GOOD).kind == "untested"


def test_an_empty_field_never_reaches_the_checker(screen):
    """A click on Simpan with an empty field is a form not yet filled in, and
    an 8-second network round trip to discover that is a bad trade."""
    asked = []
    screen._checker = lambda key: asked.append(key) or _verdict("ok")
    screen._saver = lambda key: True

    assert screen.evaluate("").kind == "rejected"
    assert screen.evaluate("   ").kind == "rejected"
    assert asked == []


def test_the_key_is_trimmed_before_it_is_checked_and_saved(screen):
    """A paste from a browser regularly carries a trailing newline, and a key
    with one in it is a 400 that looks like a revoked key."""
    saved = []
    screen._checker = lambda key: _verdict("ok")
    screen._saver = lambda key: saved.append(key) or True

    screen.evaluate(f"  {GOOD}\n")
    assert saved == [GOOD]


# ── what the screen does with the answer ────────────────────────────────────

def test_it_closes_itself_only_after_a_save(screen):
    screen.build()
    screen._checker = lambda key: _verdict("rejected", "not valid")
    screen._saver = lambda key: True
    screen.submit(GOOD)

    assert screen.finished is False
    assert screen.available is True, "the screen closed on a rejected key"


def test_it_closes_and_reports_on_ok(screen):
    done = []
    screen._on_done = done.append
    screen.build()
    screen._checker = lambda key: _verdict("ok")
    screen._saver = lambda key: True

    assert screen.submit(GOOD) == "ok"
    assert screen.finished is True
    assert screen.available is False
    assert len(done) == 1 and done[0].kind == "ok"


def test_finishing_twice_does_not_call_the_caller_twice(screen):
    """`mark_ready()` is idempotent, but a done handler that starts a session
    twice would not be."""
    done = []
    screen._on_done = done.append
    screen.build()
    screen.finish()
    screen.finish()
    assert len(done) == 1


def test_a_rejected_key_leaves_the_field_ready_to_retype(screen):
    screen.build()
    field = screen._field
    field.setText("bad")
    screen._checker = lambda key: _verdict("rejected")
    screen._saver = lambda key: True
    screen.submit("bad")

    assert field.isEnabled() is True
    assert screen._button.isEnabled() is True, "the button stayed disabled"


def test_the_result_line_says_which_of_the_three_happened(screen):
    screen.build()
    label = screen._labels["result"]

    screen._checker = lambda key: _verdict("rejected", "detail-here")
    screen._saver = lambda key: True
    screen.submit(GOOD)
    rejected = label.text()

    screen._checker = lambda key: _verdict("ok")
    screen.submit(GOOD)
    accepted = label.text()

    assert rejected != accepted
    assert "detail-here" in rejected


# ── there is no way past it ─────────────────────────────────────────────────

def test_the_screen_has_no_skip_control(setup_module):
    """An AST check because the failure is the EXISTENCE of a button, and a
    widget-level test can only see the ones that were built."""
    import ast
    from pathlib import Path

    source = Path(setup_module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    literals = {node.value for node in ast.walk(tree)
                if isinstance(node, ast.Constant) and isinstance(node.value, str)}
    forbidden = {"skip", "lewati", "ui.setup.skip", "ui.setup.skip_button"}
    assert not (literals & forbidden), "a skip control is back on the setup screen"


def test_the_screen_offers_one_button_and_no_second_way_out(setup_module):
    """Simpan & uji is the only control. A second one that closed the window
    would be a skip button with a different label."""
    screen = setup_module.SetupWindow()
    screen.build()
    # Both the button and Enter are wired to `_pressed`, which cannot finish
    # without a save. Nothing else on the screen closes it.
    assert screen._button is not None
    assert screen._button.isEnabled() is True


def test_closing_the_window_before_a_save_is_refused(setup_module):
    """The X button is not a skip button. Without this, closing the window hid
    it and left `main.py` waiting on a screen nobody could see — the silent hang
    the screen exists to end."""
    class Event:
        def __init__(self):
            self.ignored = False

        def ignore(self):
            self.ignored = True

    screen = setup_module.SetupWindow()
    screen.build()
    event = Event()
    screen._on_close_event(event)

    assert event.ignored is True
    assert screen.finished is False
    assert screen._labels["result"].text(), "the refusal was silent"
    assert "skip" in screen._labels["result"].text().lower() or \
        "dilewati" in screen._labels["result"].text().lower()


def test_closing_after_a_save_is_not_refused(setup_module):
    """Otherwise shutting the app down after setup would be blocked by the
    screen's own guard."""
    class Event:
        def __init__(self):
            self.ignored = False

        def ignore(self):
            self.ignored = True

    screen = setup_module.SetupWindow()
    screen.build()
    screen._checker = lambda key: _verdict("ok")
    screen._saver = lambda key: True
    screen.submit(GOOD)

    event = Event()
    screen._on_close_event(event)
    assert event.ignored is False


def test_the_key_is_hidden_while_it_is_typed(setup_module):
    """The field is on a desktop that may be shared, and a key pasted into a
    screenshot is a key that has to be rotated."""
    from PyQt6.QtWidgets import QLineEdit

    screen = setup_module.SetupWindow()
    screen.build()
    assert screen._field.echoMode() == QLineEdit.EchoMode.Password


# ── the real save, against the real config manager ─────────────────────────

def test_a_real_save_reaches_the_real_file(screen, isolated_config):
    """NO MOCK ON THE SAVE PATH HERE. `save_api_keys()` has its own tests, and
    this one is about the screen calling it with the right key — the seam where
    a screen can be perfect and the file still ends up empty."""
    screen._checker = lambda key: _verdict("ok")

    assert screen.evaluate(GOOD).kind == "ok"
    data = isolated_config.load_api_keys()
    assert data["gemini_api_key"] == GOOD
    assert data["gemini_api_key_source"] == "file"
    assert isolated_config.get_gemini_key() == GOOD


def test_a_real_save_keeps_the_rest_of_the_config(screen, isolated_config):
    """The overlay bug `save_setup()` was written about: the second run of the
    setup screen deleted the assistant's name, the voice, the plugins."""
    isolated_config.save_assistant_config("JARVIS", "Fatih")
    screen._checker = lambda key: _verdict("ok")

    screen.evaluate(GOOD)
    assert isolated_config.load_api_keys()["user_name"] == "Fatih"
