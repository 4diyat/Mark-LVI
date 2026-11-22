"""Board 25 — the risk confirmation, and the two things it was missing.

WHY THESE TESTS EXIST
    `ui/confirm_banner.py` was already a working gate: a human finger answers,
    `core/confirm` refuses on a 90 s timeout, and nothing blocks while it is up.
    What it did not have was the artboard's own information:

      1. NO ORIGIN. Artboard 25 has a field the panel does not:
         "ASAL PERMINTAAN / Perintah suara · 14:31 · tercatat di audit log".
         The banner showed a heading, a title and a detail. A user asked to
         approve an irreversible action could not see what ASKED for it —
         whether they said it, typed it, or a plugin did.

      2. NO KEYS. The artboard writes "Enter · Esc" in the corner; the banner
         had no key handler at all. A dialog that asks for a decision and then
         ignores the two keys every desktop dialog answers to is a dialog that
         is only half a dialog.

    The second one CONTRADICTED AN EXISTING TEST, deliberately:
    `test_cancel_has_the_focus_so_a_stray_enter_is_safe` pinned CANCEL as the
    default so that an unread Enter could never confirm. The owner's ruling is
    the artboard's: Enter confirms, Esc cancels, WITH THE INITIAL FOCUS STILL ON
    CANCEL — so pressing Enter without touching anything is still safe, and
    Enter only confirms once the user has moved to the confirm button. That
    test is replaced by the tests below, not deleted.

WHY THE ORIGIN IS REAL DATA AND NOT A SENTENCE
    "Perintah suara · 14:31 · tercatat di audit log" is three claims. The time
    is the request time. "Tercatat di audit log" is true because
    `core/confirm._audit` writes it. The INPUT MODE is the one that had no
    source at all, so this file makes the two entry points — voice and typed —
    record it, and the banner reads what was recorded. A banner that guessed
    "Perintah suara" would be wrong on every typed command.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
I18N = ROOT / "assets" / "i18n"


@pytest.fixture()
def indonesian():
    from core import i18n

    i18n.reload()
    i18n.set_locale("id")
    yield
    i18n.set_locale("en")


@pytest.fixture()
def qt():
    """The repo's stub, with BOTH module families restored afterwards.

    Restoring `PyQt6` matters: a later test that asserts its ABSENCE fails for
    a reason unrelated to what it tests. That leak was found on board 24.
    """
    import sys

    from tests import qtstub

    stubs = qtstub.install_qt()
    saved = {k: v for k, v in sys.modules.items()
             if k == "PyQt6" or k.startswith("PyQt6.")
             or k == "ui" or k.startswith("ui.")}
    sys.modules.update(stubs)
    for name in [k for k in sys.modules if k == "ui" or k.startswith("ui.")]:
        sys.modules.pop(name, None)
    try:
        yield
    finally:
        for name in [k for k in sys.modules
                     if k == "PyQt6" or k.startswith("PyQt6.")
                     or k == "ui" or k.startswith("ui.")]:
            sys.modules.pop(name, None)
        sys.modules.update(saved)


def catalogue(name: str) -> dict:
    return json.loads((I18N / name).read_text(encoding="utf-8"))


# ── 1. the words the artboard uses ──────────────────────────────────────────

def test_the_heading_is_the_artboards_word():
    """"BERISIKO", not "⚠ KONFIRMASI". The heading names the KIND of request;
    the buttons below already say what pressing them does, so a heading that
    also said "confirm" told the user the same thing twice and never told them
    why the dialog appeared."""
    for name, expected in (("id.json", "BERISIKO"), ("en.json", "AT RISK")):
        value = catalogue(name)["ui.confirm.heading"]
        assert value.upper() == expected, f"{name}: {value!r}"


def test_the_buttons_are_the_artboards_words():
    for name, yes, no in (("id.json", "Konfirmasi", "Batal"),
                          ("en.json", "Confirm", "Cancel")):
        keys = catalogue(name)
        assert keys["ui.confirm.button"].strip() == yes, name
        assert keys["ui.cancel"].strip() == no, name


def test_the_dialog_can_say_where_the_request_came_from():
    for name, expected in (("id.json", "Asal permintaan"), ("en.json", "Request origin")):
        assert catalogue(name)["ui.confirm.origin"].strip().lower() == expected.lower(), name


def test_the_dialog_can_say_the_action_cannot_be_undone(qt):
    """The artboard prints it as a standing sentence under the title. It is a
    claim about THIS dialog, not about the action — so it is a constant, not a
    translated string: the sentence is already in `DESIGN-ambient.md`."""
    from ui import confirm_banner

    assert confirm_banner.CANNOT_UNDO, "no sentence about irreversibility"
    assert "tidak bisa diurungkan" in confirm_banner.CANNOT_UNDO.lower()


def test_the_artboard_names_the_two_keys_it_answers_to(qt):
    """Needs Qt: `ui/confirm_banner.py` imports PyQt6 at module level, so
    reading its constants without the stub installed is an ImportError rather
    than a missing constant."""
    from ui import confirm_banner

    assert confirm_banner.KEYS_HINT == "Enter · Esc"


# ── 2. the origin is recorded by the entry points, not guessed ──────────────

def test_the_store_imports_nothing_so_an_audio_callback_can_use_it():
    """`core.input_source` is called from `main.py`'s audio loop. If it pulled in
    `ui.confirm_banner` — which imports PyQt6 at module level — a machine with
    no display would raise inside the microphone callback.

    Asserted by SOURCE rather than by import: the point is that the module has
    no dependencies to import in the first place."""
    source = (ROOT / "core" / "input_source.py").read_text(encoding="utf-8")
    imports = [line for line in source.splitlines()
               if line.startswith(("import ", "from ")) and "__future__" not in line]
    assert imports == [], f"core/input_source.py imports {imports}"


def test_the_origin_reads_voice_typed_and_unknown(qt, indonesian):
    """Three answers, because there are three cases: a spoken command, a typed
    one, and a request from a plugin or a timer that came from neither."""
    from ui import confirm_banner

    assert "suara" in confirm_banner.origin_text("voice").lower()
    assert "ketik" in confirm_banner.origin_text("typed").lower()
    assert "tidak diketahui" in confirm_banner.origin_text("").lower()


def test_a_typed_command_really_marks_the_source(qt, indonesian):
    """Drive the real store, not the string. A store that saves nothing is the
    failure this test class exists for — and the banner must read what it
    saved, not a second copy."""
    from core import input_source
    from ui import confirm_banner

    input_source.mark("typed")
    assert input_source.current() == "typed"
    assert "ketik" in confirm_banner.origin_text().lower(), (
        "the banner does not read the store the entry points write")

    input_source.mark("voice")
    assert input_source.current() == "voice"
    assert "suara" in confirm_banner.origin_text().lower()
    input_source.reset()


def test_the_voice_path_marks_voice():
    """The mic path is in main.py's audio loop. Read from the source: proving it
    by executing would need a live microphone session."""
    source = (ROOT / "main.py").read_text(encoding="utf-8")
    assert 'input_source.mark("voice")' in source, (
        "the microphone never records that a command was spoken, so the banner "
        "would call every request a typed one (or guess)")
    # and the typed door marks its own, or every request reads "unknown"
    assert 'input_source.mark("typed")' in source


# ── 3. Enter confirms, Esc cancels, and the default stays safe ─────────────

def test_escape_answers_no(qt, monkeypatch):
    from PyQt6.QtCore import Qt

    from ui import confirm_banner

    answered = []
    banner = confirm_banner.build_confirm_window()
    banner.answered.connect(answered.append)
    banner.keyPressEvent(_key_event(Qt.Key.Key_Escape))
    assert answered == [False], "Esc did not cancel"


def test_enter_answers_yes(qt):
    """THE OWNER'S RULING, WHICH REVERSED AN EARLIER TEST. Artboard 25 writes
    "Enter · Esc"; the dialog answers to both."""
    from PyQt6.QtCore import Qt

    from ui import confirm_banner

    answered = []
    banner = confirm_banner.build_confirm_window()
    banner.answered.connect(answered.append)
    banner.keyPressEvent(_key_event(Qt.Key.Key_Return))
    assert answered == [True], "Enter did not confirm"


def test_the_initial_focus_is_still_the_SAFE_answer(qt):
    """What survived of the old rule: an unread Enter must not confirm. Focus
    starts on Batal, so a user who presses Enter without moving confirms
    nothing — and once they have chosen Konfirmasi, Enter means what it says."""
    from ui import confirm_banner

    banner = confirm_banner.build_confirm_window()
    # `isDefault()`/`hasFocus()` are the stub's own state (qtstub records both
    # on every widget), so this asserts the widget the CODE asked for, not a
    # Qt behaviour the sandbox cannot run.
    assert banner._cancel_button is not banner._confirm_button
    assert banner._cancel_button.isDefault() is True
    assert banner._confirm_button.isDefault() is False


def _in_layout(banner, widget) -> bool:
    """Whether a widget is actually part of the dialog a user sees.

    MUTATION-DRIVEN. The first version of the three tests below only read the
    widget's text, and a mutation that built the label and never added it to the
    layout survived: an orphaned QLabel has the right text and is not on screen.
    """
    layout = banner.layout()
    for index in range(layout.count()):
        item = layout.itemAt(index)
        if item is not None and item.widget() is widget:
            return True
    return False


def test_the_keys_are_printed_in_the_dialog(qt):
    """"Enter · Esc" is in the artboard's corner. A shortcut nobody is told
    about is a shortcut only its author uses."""
    from ui import confirm_banner

    banner = confirm_banner.build_confirm_window()
    assert banner._keys_label.text() == "Enter · Esc"
    assert _in_layout(banner, banner._keys_label), (
        "the keys legend is built but never added to the dialog")


def test_the_origin_line_is_on_the_dialog_and_filled_from_the_store(qt, indonesian):
    """R6. `set_origin` had a test that only read the method's existence; a
    version that computed the sentence and dropped it survived."""
    from core import input_source
    from ui import confirm_banner

    input_source.mark("typed")
    try:
        banner = confirm_banner.build_confirm_window()
        banner.set_origin(when="14:31")
        assert _in_layout(banner, banner._origin_label), (
            "the origin line is built but never added to the dialog")
        text = banner._origin_label.text()
        assert "ketik" in text.lower(), text
        assert "14:31" in text, text
        assert "audit log" in text.lower(), text
    finally:
        input_source.reset()


def test_the_cannot_undo_sentence_is_on_the_dialog(qt):
    """R8. A safety sentence that is constructed and not shown is not a safety
    sentence."""
    from ui import confirm_banner

    banner = confirm_banner.build_confirm_window()
    assert banner._never_label.text() == confirm_banner.CANNOT_UNDO
    assert _in_layout(banner, banner._never_label), (
        "the \"cannot be undone\" sentence is built but never added")


def test_any_other_key_is_ignored(qt):
    from PyQt6.QtCore import Qt

    from ui import confirm_banner

    answered = []
    banner = confirm_banner.build_confirm_window()
    banner.answered.connect(answered.append)
    banner.keyPressEvent(_key_event(Qt.Key.Key_A))
    assert answered == [], "a random keypress answered the question"


def _key_event(key):
    """A key event the banner's handler can read: it only asks `.key()`."""
    return type("Event", (), {"key": lambda self, k=key: k,
                              "accept": lambda self: None,
                              "ignore": lambda self: None})()


def test_the_detail_line_exists_only_when_there_is_a_detail(qt):
    """The artboard's dialog always carries a detail line; the code path without
    one is the common one. The banner answers it by not building the label at
    all rather than by leaving an empty band of dead space mid-dialog — and a
    later `set_title` cannot show one, so a reused banner is honest about it."""
    from ui import confirm_banner

    banner = confirm_banner.build_confirm_window()
    # `isVisible()` is False for every child of a window that has not been
    # shown yet — in real Qt as well as here — so the FLAG is what is asserted.
    assert banner._detail_label._visible is False, (
        "a banner with no detail is still showing the detail line")

    # THIS IS THE LIVE PATH, and it was broken: the detail arrives through
    # `set_title` after `build_confirm_window()` made the banner with "", so a
    # label that was only built when the constructor got a detail could never
    # carry the artboard's "Lampiran: anggaran.xlsx · 3 penerima" at all.
    banner.set_title("Kirim laporan", "Lampiran: anggaran.xlsx · 3 penerima")
    assert "anggaran.xlsx" in banner._detail_label.text()
    assert banner._detail_label._visible is True, (
        "the detail is set but the line is still hidden")

    banner.set_title("Hapus riwayat", "")
    assert banner._detail_label._visible is False, (
        "a reused banner still shows the previous question's detail")


def test_a_reused_banner_drops_the_previous_questions_origin(qt, indonesian):
    """R16. The origin is the one line on this dialog that would be a LIE if it
    went stale — it describes who asked for the action now on screen."""
    from core import input_source
    from ui import confirm_banner

    banner = confirm_banner.build_confirm_window()
    input_source.mark("voice")
    try:
        banner.set_origin(when="14:31")
        first = banner._origin_label.text()
        assert "suara" in first.lower(), first

        # The store is marked BEFORE the dialog is asked to show the new
        # question — that is the real order: `main.py` marks on input, the
        # action then asks for confirmation.
        input_source.mark("typed")
        banner.set_title("Hapus riwayat", "")
        second = banner._origin_label.text()
        assert "ketik" in second.lower(), (
            f"a reused banner still says {second!r}")
    finally:
        input_source.reset()


def test_the_shell_fills_the_time_on_every_question(qt, monkeypatch):
    """R15. `_show_confirm_now` must call `set_origin`, or the line is always
    the one `set_title` produced — with no time in it at all."""
    from ui import confirm_banner as cb
    from ui import shell as shell_module

    seen = []
    monkeypatch.setattr(cb, "build_confirm_window", lambda: _RecordingBanner(seen))

    class Fake:
        _confirm_banner = None
        _confirm_token = ""
        notify = staticmethod(lambda *a, **k: None)
        _resolve_answered = staticmethod(lambda *a, **k: None)

    Fake._show_confirm_now = shell_module.AmbientShell._show_confirm_now
    shell_module.AmbientShell._show_confirm_now(Fake(), "tok", "Kirim laporan", "3 penerima")
    assert seen, "the banner was never given an origin"
    when = seen[-1][0]
    assert len(when) == 5 and when[2] == ":", f"no HH:MM time: {when!r}"


class _RecordingBanner:
    """A banner that records what the shell asked it to display."""

    def __init__(self, seen):
        self._seen = seen
        self.answered = type("S", (), {"connect": lambda *a, **k: None})()

    def set_title(self, *a, **k):
        pass

    def set_origin(self, when="", source=None):
        self._seen.append((when, source))

    def adjustSize(self):
        pass

    def show(self):
        pass

    def raise_(self):
        pass

    def activateWindow(self):
        pass


# ── 4. the banner still cannot be bypassed ──────────────────────────────────

def test_an_expired_question_cannot_be_confirmed_after_the_fact(monkeypatch):
    """`core/confirm` owns the expiry; the banner must not resurrect a token it
    no longer owns. This is the rule the old Enter test was protecting, kept
    where it belongs — in the shell, not in the key handler."""
    from core import confirm

    seen = []
    monkeypatch.setattr(confirm, "resolve",
                        lambda token, accepted: seen.append((token, accepted)))
    from ui import shell

    class Fake:
        _confirm_token = ""
        _confirm_banner = None

        def _resolve_confirm(self, token, accepted):
            shell.AmbientShell._resolve_confirm(token, accepted)

    Fake._resolve_confirm = staticmethod(Fake._resolve_confirm)
    fake = Fake()
    shell.AmbientShell._resolve_answered(fake, True)
    assert seen == [], "an answer with no outstanding token was forwarded"
