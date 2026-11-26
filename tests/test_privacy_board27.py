"""Board 06a — Izin & Privasi, dan tiga hal yang diklaim tetapi tidak dilakukan.

WHY THESE TESTS EXIST
    The privacy page already drew four switches, three indicator words and two
    buttons before this file existed. What it could not do was keep the promises
    around them:

      1. "MODE TAMU — Sembunyikan memori & riwayat" was a SWITCH. Clicking it
         called `set_guest`, which printed "mode tamu belum ada" and returned
         False. Nothing was hidden, nothing was remembered, and the next paint
         put the switch back where it started. A control that invites a click
         and then does nothing is the failure this project keeps removing.
         The owner's ruling: if it cannot be done, DO NOT DRAW IT.

      2. "Hapus semua data lokal" deleted the AUDIT LOG and nothing else. The
         docstring was honest about that; the button was not. "Semua" is a
         claim about conversation history and keys, and the button never
         touched either. The owner's ruling: rename it to what it does.

      3. The page had no title of its own. Every page showed "JARVIS / Panel
         baki · mengikuti posisi taskbar", including this one, where the
         artboard writes "Izin & Privasi / Semua data diproses lokal secara
         default". `ui.panel.privacy.title` was in the catalogue, translated
         in both languages, and called by nothing.

HOW THIS FILE IS BUILT
    Tests lead. Every assertion here failed before the change it describes.
    Behaviour is driven through the real panel (built on `tests/qtstub.py`)
    and the real wiring; only the config file and the audit log are faked,
    because those are the two things a test must not leave behind.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
I18N = ROOT / "assets" / "i18n"


# ── fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture()
def indonesian():
    """The artboards are Indonesian, so the assertions read the same words the
    designer drew. Pinned rather than inherited from whichever test ran first."""
    from core import i18n

    i18n.reload()
    i18n.set_locale("id")
    yield
    i18n.set_locale("en")


@pytest.fixture()
def panel_module(indonesian):
    from tests.qtstub import fresh_ui, restore_ui

    saved = fresh_ui()
    try:
        from ui import tray_pages, tray_panel, tray_paint, tray_panel_model

        yield tray_panel, tray_pages, tray_paint, tray_panel_model
    finally:
        restore_ui(saved)


def catalogue(name: str) -> dict:
    return json.loads((I18N / name).read_text(encoding="utf-8"))


# ── 1. MODE TAMU is gone, not disabled, not pretending ──────────────────────

def test_the_panel_draws_no_guest_switch_because_nothing_happens_behind_it():
    """THE OWNER'S RULING, AS A TEST.

    A disabled switch would still be a promise: it says "this exists and you
    are not allowed yet". Guest mode needs every surface to stop reading memory
    and history, and nothing in this tree does that. So the section is not
    drawn at all.
    """
    from tests.qtstub import fresh_ui, restore_ui

    saved = fresh_ui()
    try:
        from ui import tray_pages, tray_panel

        panel = tray_panel.TrayPanel({})
        panel.open()
        assert tray_pages.PAGE_PRIVACY in panel._pages

        drawn = set(panel._labels) | set(panel._buttons)
        leftovers = sorted(k for k in drawn if "guest" in k.lower())
        assert leftovers == [], (
            f"the privacy page still builds {leftovers} — a switch for a mode "
            "that cannot be entered is a control that lies")

        # AND NO OTHER PAGE EITHER. Board 14 draws a MODE TAMU card, and when
        # its page was built it drew a heading and a sentence under that name —
        # no control, but a widget keyed `sec_guest`, which is how a disabled
        # switch comes back: one commit later somebody gives it a button.
        throughout = sorted(k for k in drawn if "guest" in k.lower())
        assert throughout == [], (
            f"a page builds {throughout}: the ruling is that guest mode is not "
            "drawn anywhere, not even as a label waiting for a switch")
    finally:
        restore_ui(saved)


def test_the_guest_strings_are_deleted_from_both_languages():
    """Dead keys are how a deleted feature comes back: the next person finds
    the words in the catalogue and rebuilds the switch around them."""
    for name in ("id.json", "en.json"):
        keys = catalogue(name)
        leftovers = sorted(k for k in keys
                           if k in ("ui.panel.section.guest",
                                    "ui.panel.guest.title",
                                    "ui.panel.guest.sub"))
        assert leftovers == [], f"{name} still has {leftovers}"


def test_the_wiring_no_longer_offers_a_guest_action():
    """The panel cannot draw what the map does not know, and a stale map is a
    function looking for a button. `set_guest` is deleted, not left as a no-op
    someone might re-wire."""
    from ui import tray_panel_wiring

    assert not hasattr(tray_panel_wiring, "set_guest"), (
        "set_guest still exists — an action with no control is dead code that "
        "invites the control back")

    from tests.qtstub import fresh_ui, restore_ui

    saved = fresh_ui()
    try:
        actions = tray_panel_wiring.actions_for(object())
        assert "guest" not in actions
    finally:
        restore_ui(saved)


# ── 2. the erase button says what it erases ─────────────────────────────────

def test_the_erase_button_does_not_claim_to_delete_everything():
    """It deletes the audit log. It does not touch conversation history files,
    it does not touch the API key, and it cannot reach what was already sent to
    the model. "Semua" was three claims too many."""
    for name, word in (("id.json", "semua"), ("en.json", "all ")):
        label = catalogue(name)["ui.panel.erase"].lower()
        assert word not in label, f"{name}: {label!r} still claims everything"


def test_the_erase_button_names_the_audit_log():
    """A rename is only honest if it names the thing. Otherwise the button says
    "delete some data" and the user still has to guess which."""
    for name in ("id.json", "en.json"):
        label = catalogue(name)["ui.panel.erase"].lower()
        assert "audit" in label, f"{name}: {label!r} does not name the audit log"


def test_the_erase_handler_really_erases_the_audit_log(monkeypatch):
    """Behaviour, not wording: the button calls `audit_log.erase()` and reports
    success only when it returns True."""
    import core.audit_log as audit_module
    from ui import tray_panel_wiring

    erased = []

    class FakeAudit:
        def erase(self):
            erased.append(True)
            return True

    monkeypatch.setattr(audit_module, "shared", lambda: FakeAudit())
    said = []
    monkeypatch.setattr(tray_panel_wiring, "_say",
                        lambda shell, text: said.append(text))

    assert tray_panel_wiring.erase_local(None) is True
    assert erased == [True]
    assert said, "an erase that says nothing leaves the user wondering"


def test_a_failed_erase_is_reported_as_failed(monkeypatch):
    import core.audit_log as audit_module
    from ui import tray_panel_wiring

    class FakeAudit:
        def erase(self):
            return False

    monkeypatch.setattr(audit_module, "shared", lambda: FakeAudit())
    said = []
    monkeypatch.setattr(tray_panel_wiring, "_say",
                        lambda shell, text: said.append(text))

    assert tray_panel_wiring.erase_local(None) is False
    assert said, "a refused erase must say so"


# ── 3. every page has its own title ─────────────────────────────────────────

def test_the_privacy_page_titles_itself(panel_module):
    """The artboard's first two lines are the page's identity. The panel drew
    "JARVIS / Panel baki" on all three pages instead, and the catalogue key for
    this page was never called by anything."""
    tray_panel, tray_pages, tray_paint, tray_panel_model = panel_module

    panel = tray_panel.TrayPanel({})
    panel.open()
    panel._page = tray_pages.PAGE_PRIVACY
    tray_paint.paint(panel, tray_panel_model.snapshot())

    assert panel._labels["title"].text() == "Izin & Privasi"
    assert panel._labels["subtitle"].text() == (
        "Tinjau akses dan aktivitas")


def test_the_main_page_keeps_the_assistant_name(panel_module):
    """The other direction: a title fix that renamed every page would put "Izin
    & Privasi" over the quick actions."""
    tray_panel, tray_pages, tray_paint, tray_panel_model = panel_module

    panel = tray_panel.TrayPanel({})
    panel.open()
    panel._page = tray_pages.PAGE_MAIN
    tray_paint.paint(panel, tray_panel_model.snapshot())

    assert panel._labels["title"].text() == "JARVIS"


def test_the_history_page_titles_itself(panel_module):
    """Board 08a's page has its own name too, and the same bug hid it."""
    tray_panel, tray_pages, tray_paint, tray_panel_model = panel_module

    panel = tray_panel.TrayPanel({})
    panel.open()
    panel._page = tray_pages.PAGE_HISTORY
    tray_paint.paint(panel, tray_panel_model.snapshot())

    assert panel._labels["title"].text().lower() != "jarvis", (
        "the history page still wears the main page's title")


def test_switching_pages_repaints_the_title(panel_module):
    """A title set only on open is a title that goes stale the first time the
    user clicks Riwayat."""
    tray_panel, tray_pages, tray_paint, tray_panel_model = panel_module

    panel = tray_panel.TrayPanel({})
    panel.open()
    snap = tray_panel_model.snapshot()

    panel._page = tray_pages.PAGE_MAIN
    tray_paint.paint(panel, snap)
    main_title = panel._labels["title"].text()

    panel._page = tray_pages.PAGE_PRIVACY
    tray_paint.paint(panel, snap)
    privacy_title = panel._labels["title"].text()

    assert main_title != privacy_title, (
        "the title did not change with the page — it is baked in at build time")


# ── 4. the artboard's cards (BOARD 6, which replaced 06a) ───────────────────

def test_the_permission_cards_are_in_the_geometry_table(panel_module):
    """`rect(24, y, 412, 62)` behind each row, y = 106 + i*72 — `b06()`'s pitch.

    The page used to draw 06a's 56 px cards at a 66 px pitch. Board 6 draws
    62 px cards 72 px apart, so this is the number a reader can check against
    the sheet rather than against the widget code.
    """
    from ui import tray_pages

    g = tray_pages.GEOMETRY
    assert g["p6_card"] == (24, 62, 412)
    assert g["p6_row_y"] == 106
    assert g["p6_pitch"] == 72


def test_the_activity_log_is_board_6s_and_not_06as(tmp_path, monkeypatch):
    """Board 6 draws three timestamped lines from the audit log.

    The old page drew no log at all — the log lived on the history page under
    a different label. This asserts the log is ON the permissions page now,
    filled from the same store the gate writes to.
    """
    from core import audit_log

    log = audit_log.AuditLog(path=str(tmp_path / "audit.jsonl"))
    log.record("screen_processor", "safe", "done", "membaca layar")
    monkeypatch.setattr(audit_log, "shared", lambda: log)

    from ui import tray_pages
    from ui.tray_paint import _activity_lines

    lines = _activity_lines()
    assert lines, "the activity log came back empty with an entry in the store"
    when, what = lines[0]
    assert "screen_processor" in what
    # Newest first, as the artboard draws them.
    assert tray_pages.GEOMETRY["p6_log_row_y"] < tray_pages.GEOMETRY["p6_divider"][1]


def test_board_6s_buttons_act_on_the_log_they_sit_under(panel_module):
    """THE TRAP IN THIS PAGE, AND IT IS A REAL ONE.

    Board 6 draws "Ekspor log" and "Hapus riwayat" UNDER an activity log card.
    The same two labels are on the history page, where they mean the UNDO STACK
    — `clear_history`'s own docstring says it does not erase the audit log, and
    `export_history` writes `undo.history()`.

    Wiring board 6's buttons to those handlers would put a button under an
    activity log that clears a different store. This test pins the stores, not
    the labels.
    """
    tray_panel, _pages, _paint, _model = panel_module
    called = []

    def recorder(key):
        def handler(*_a, **_k):
            called.append(key)
            return True
        return handler

    actions = {key: recorder(key) for key in
               ("erase", "export_audit", "history_clear", "history_export")}
    panel = tray_panel.TrayPanel(actions)
    panel.open()

    # PRESS THE BUTTONS, THROUGH THE SIGNAL. The first version called
    # `panel._call()` with the two keys it EXPECTED, which asserted that
    # `_call` works and nothing else: wiring a button to the undo stack is a
    # mutation it could not see. The second version used `.click()`, which this
    # stub does not implement — `__getattr__` handed back a lambda, so it
    # pressed nothing and passed for the wrong reason. `clicked.emit()` is the
    # one path the stub really supports.
    panel._buttons["p6_clear"].clicked.emit()
    panel._buttons["p6_export"].clicked.emit()
    assert called == ["erase", "export_audit"], (
        f"board 6's buttons reached {called}, not the audit-log handlers")


def test_the_export_writes_the_audit_log_not_the_undo_stack(tmp_path, monkeypatch):
    """`export_audit` reads `core.audit_log`; `export_history` reads `undo`."""
    from core import audit_log

    log = audit_log.AuditLog(path=str(tmp_path / "audit.jsonl"))
    log.record("screen_processor", "safe", "done", "membaca layar")
    monkeypatch.setattr(audit_log, "shared", lambda: log)

    from ui import tray_panel_wiring as wiring

    said = []
    monkeypatch.setattr(wiring, "_say", lambda _shell, text: said.append(text))
    monkeypatch.setattr(wiring, "_desktop_path", lambda: tmp_path)
    assert wiring.export_audit(object()) is True
    written = (tmp_path / "jarvis-activity-log.txt").read_text(encoding="utf-8")
    assert "screen_processor" in written
    assert said and "jarvis-activity-log.txt" in said[-1]


def test_the_activity_log_is_written_by_the_paint(tmp_path, monkeypatch, panel_module):
    """The three log lines come from `paint_permissions`, on every refresh.

    A log filled once at build time is a screenshot of the moment the panel was
    constructed: an action that completes while the panel is open would never
    appear, and the card would look like the record while being stale.
    """
    from core import audit_log

    log = audit_log.AuditLog(path=str(tmp_path / "audit.jsonl"))
    monkeypatch.setattr(audit_log, "shared", lambda: log)

    tray_panel, _pages, tray_paint, _model = panel_module
    panel = tray_panel.TrayPanel({})
    panel.open()
    log.record("screen_processor", "safe", "done", "membaca layar")
    tray_paint.paint(panel, panel.snapshot)

    texts = [panel._labels[f"p6_log_text:{i}"].text() for i in range(3)]
    assert any("screen_processor" in t for t in texts), (
        f"the activity log was not refreshed by the paint: {texts}")
    times = [panel._labels[f"p6_log_time:{i}"].text() for i in range(3)]
    assert any(":" in t for t in times), f"no timestamped row: {times}"


def test_an_empty_audit_log_says_so_rather_than_reading_blank(tmp_path,
                                                              monkeypatch,
                                                              panel_module):
    """A fresh install's log is empty, and an empty card looks like a broken one.

    `_activity_lines()` returns `[]` for both "nothing has happened yet" and
    "the log could not be read". The page must say which one the user is
    looking at, so the first row carries the empty-state sentence instead of
    three blank lines under a LOG AKTIVITAS header.
    """
    from core import audit_log

    log = audit_log.AuditLog(path=str(tmp_path / "empty.jsonl"))
    monkeypatch.setattr(audit_log, "shared", lambda: log)

    tray_panel, _pages, tray_paint, _model = panel_module
    panel = tray_panel.TrayPanel({})
    panel.open()
    tray_paint.paint(panel, panel.snapshot)

    first = panel._labels["p6_log_text:0"].text()
    assert first.strip(), "the log is empty and the page says nothing about it"
    assert panel._labels["p6_log_text:1"].text() == ""
    assert panel._labels["p6_log_time:0"].text() == ""


def test_the_log_puts_the_newest_entry_on_top(tmp_path, monkeypatch,
                                             panel_module):
    """b06 draws its log newest-first, and the audit log stores oldest-first.

    Getting this backwards is invisible: the card still fills with plausible
    lines, and every row still has a time. It is only wrong to a user who
    watches an action happen and finds it on the bottom row.
    """
    from core import audit_log

    log = audit_log.AuditLog(path=str(tmp_path / "ordered.jsonl"))
    monkeypatch.setattr(audit_log, "shared", lambda: log)
    log.record("first_tool", "safe", "done", "satu")
    log.record("last_tool", "safe", "done", "tiga")

    tray_panel, _pages, tray_paint, _model = panel_module
    panel = tray_panel.TrayPanel({})
    panel.open()
    tray_paint.paint(panel, panel.snapshot)

    top = panel._labels["p6_log_text:0"].text()
    assert "last_tool" in top, (
        f"the newest entry is not the top row: {top!r}")


def test_the_log_fills_all_three_rows_when_there_is_that_much(tmp_path,
                                                              monkeypatch,
                                                              panel_module):
    """Three entries in, three rows out. Reading two of them leaves the third
    row blank under a header that promised a table."""
    from core import audit_log

    log = audit_log.AuditLog(path=str(tmp_path / "full.jsonl"))
    monkeypatch.setattr(audit_log, "shared", lambda: log)
    for n in range(4):
        log.record(f"tool_{n}", "safe", "done", f"langkah {n}")

    tray_panel, _pages, tray_paint, _model = panel_module
    panel = tray_panel.TrayPanel({})
    panel.open()
    tray_paint.paint(panel, panel.snapshot)

    filled = [panel._labels[f"p6_log_text:{i}"].text() for i in range(3)]
    assert all(t.strip() for t in filled), f"a log row came up blank: {filled}"
    assert "tool_3" in filled[0] and "tool_1" in filled[2], (
        f"the three newest entries are not on the card: {filled}")


def test_the_log_card_has_exactly_three_rows(panel_module):
    """Three, because that is what fits in the 118 px card at a 32 px pitch.

    A fourth row would be drawn underneath the divider and the buttons.
    """
    tray_panel, tray_pages, _paint, _model = panel_module

    panel = tray_panel.TrayPanel({})
    panel.open()

    rows = [k for k in panel._labels if k.startswith("p6_log_text:")]
    assert len(rows) == 3, f"board 6 draws {len(rows)} log rows, not 3"

    g = tray_pages.GEOMETRY
    last_y = g["p6_log_row_y"] + 2 * g["p6_log_pitch"] + 16
    assert last_y < g["p6_divider"][1], (
        "the third log row runs into the divider")


def test_the_cards_are_actually_widgets(panel_module):
    """Geometry in a table is not a card on screen. Assert the widgets exist at
    the table's coordinates."""
    tray_panel, tray_pages, _paint, _model = panel_module

    panel = tray_panel.TrayPanel({})
    panel.open()
    g = tray_pages.GEOMETRY

    for index, key in enumerate(("screen", "microphone", "files", "apps")):
        card = panel._labels.get(f"p6_card:{key}")
        assert card is not None, f"no card behind the {key} permission row"
        expected_y = g["p6_row_y"] + index * g["p6_pitch"]
        assert (card.x(), card.y(), card.width(), card.height()) == (
            g["p6_card"][0], expected_y, g["p6_card"][2], g["p6_card"][1])

    # The activity log's card too. It is the widest surface on the page, and a
    # page that drew the IZIN AKSES cards and forgot this one would still pass
    # every row assertion above.
    log_card = panel._labels.get("p6_log_card")
    assert log_card is not None, "no card behind the activity log"
    assert (log_card.x(), log_card.y(),
            log_card.width(), log_card.height()) == g["p6_log_card"]
    header = panel._labels.get("p6_log_header")
    assert header is not None and header.y() < log_card.y(), (
        "the LOG AKTIVITAS header is not above the log it names")


# ── 5. the four switches still work, and still refuse what they cannot do ────

def test_builtin_actions_do_not_claim_plugin_settings_control_them(monkeypatch):
    from memory import config_manager
    from ui import tray_panel_wiring

    written = []
    monkeypatch.setattr(config_manager, "save_plugin_enabled",
                        lambda name, on: written.append((name, on)) or True)
    monkeypatch.setattr(tray_panel_wiring, "_say", lambda shell, text: None)
    assert tray_panel_wiring.set_permission(None, "files", True) is False
    assert tray_panel_wiring.set_permission(None, "apps", False) is False
    assert written == []


def test_a_switch_with_nothing_behind_it_is_refused_by_name(monkeypatch):
    """`screen` and `microphone` are facts about the machine. The panel disables
    them; the wiring must refuse them too, because a disabled widget is a UI
    convention and not an invariant."""
    from ui import tray_panel_wiring

    said = []
    monkeypatch.setattr(tray_panel_wiring, "_say",
                        lambda shell, text: said.append(text))

    assert tray_panel_wiring.set_permission(None, "screen", False) is False
    assert tray_panel_wiring.set_permission(None, "microphone", True) is False
    assert len(said) == 2
