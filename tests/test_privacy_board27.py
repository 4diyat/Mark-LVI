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
        "Semua data diproses lokal secara default")


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


# ── 4. the artboard's cards ─────────────────────────────────────────────────

def test_the_permission_and_indicator_cards_are_in_the_geometry_table(panel_module):
    """`rect(24, y, 412, 56)` behind each permission row (y = 208 + i*66) and
    `rect(x, 102, 132, 62)` behind each indicator (x = 24 + i*140).

    Without the cards the four rows read as one paragraph rather than four
    separate permissions, and the three indicators are loose words.
    """
    from ui import tray_pages

    g = tray_pages.GEOMETRY
    assert g["permx_card"] == (24, 208, 412, 56)
    assert g["permx_pitch"] == 66
    assert g["indicator_card"] == (24, 102, 132, 62)
    assert g["indicator_pitch"] == 140


def test_the_cards_are_actually_widgets(panel_module):
    """Geometry in a table is not a card on screen. Assert the widgets exist at
    the table's coordinates."""
    tray_panel, tray_pages, _paint, _model = panel_module

    panel = tray_panel.TrayPanel({})
    panel.open()
    g = tray_pages.GEOMETRY

    for index, key in enumerate(("screen", "microphone", "files")):
        card = panel._labels.get(f"indicator_card:{key}")
        assert card is not None, f"no card behind the {key} indicator"
        expected = (g["indicator_card"][0] + index * g["indicator_pitch"],
                    g["indicator_card"][1],
                    g["indicator_card"][2], g["indicator_card"][3])
        assert (card.x(), card.y(), card.width(), card.height()) == expected

    for index, key in enumerate(("screen", "microphone", "files", "apps")):
        card = panel._labels.get(f"permx_card:{key}")
        assert card is not None, f"no card behind the {key} permission row"
        expected_y = g["permx_card"][1] + index * g["permx_pitch"]
        assert (card.x(), card.y(), card.width(), card.height()) == (
            g["permx_card"][0], expected_y, g["permx_card"][2], g["permx_card"][3])


# ── 5. the four switches still work, and still refuse what they cannot do ────

def test_the_two_real_switches_write_plugin_enablement(monkeypatch):
    from memory import config_manager
    from ui import tray_panel_wiring

    written = []
    monkeypatch.setattr(config_manager, "save_plugin_enabled",
                        lambda name, on: written.append((name, on)) or True)
    monkeypatch.setattr(tray_panel_wiring, "_say", lambda shell, text: None)

    assert tray_panel_wiring.set_permission(None, "files", True) is True
    assert tray_panel_wiring.set_permission(None, "apps", False) is True
    assert written == [("file_controller", True), ("computer_control", False)]


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
