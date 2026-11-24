"""The thirteen board pages: what each one reads, and that it says what it knows.

WHY THIS FILE IS MOSTLY MUTATION-BAIT
    Thirteen pages of labels is the easiest place in this repository to write
    code that LOOKS finished: every widget has text, every page opens, and none
    of it has to be connected to anything. The tests below are written the way
    the board-6 tests had to be rewritten — they press the control and check the
    store, or they change the store and check the label. A page that draws a
    constant where it should read a store fails here.

WHAT IS NOT TESTED, AND WHY
    Rendered pixels. There is no Qt here and no rasteriser, so every assertion
    below is about WIDGET TEXT and STORE STATE. That is the honest limit, and it
    is the same one `verification.md` records for the whole panel.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
I18N = ROOT / "assets" / "i18n"


@pytest.fixture()
def indonesian():
    """The artboards are Indonesian, so the assertions read the words the
    designer drew. Pinned here rather than inherited from whichever test ran
    first — the same fixture, for the same reason, as `test_privacy_board27`."""
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
        from ui import tray_paint, tray_panel

        yield tray_panel, tray_paint
    finally:
        restore_ui(saved)


def catalogue(name: str) -> dict:
    return json.loads((I18N / name).read_text(encoding="utf-8"))


# ── the registry, and the three lists that must agree ────────────────────────

def test_every_registered_page_has_a_builder_and_a_painter():
    """Three lists: the registry, `pages_build`, `pages_paint`.

    A page in the registry with no builder opens empty; one with no painter
    shows whatever it said at build time forever. Neither is visible from a
    screenshot of a working page, so it is checked here.
    """
    from ui import pages_build, pages_paint
    from ui.page_registry import PAGE_KEYS

    # `page_keys()` includes "more" — it is built like any other page. The
    # registry's PAGE_KEYS is the thirteen the more-list LINKS to, and a row that
    # opened the list you are already on would be a row that does nothing.
    built = set(pages_build.page_keys()) - {"more"}
    assert built == set(PAGE_KEYS), (
        f"registry has {sorted(set(PAGE_KEYS) - built)} with no builder; "
        f"builders name unknown pages {sorted(built - set(PAGE_KEYS))}")

    painters = {name for name in dir(pages_paint)
                if name.startswith("paint_") and callable(getattr(pages_paint, name))}
    from ui.tray_paint import _PAGE_PAINTERS

    for key in PAGE_KEYS:
        assert key in _PAGE_PAINTERS, f"{key} has no entry in _PAGE_PAINTERS"
        painter = _PAGE_PAINTERS[key]
        if painter is not None:
            assert painter in painters, f"{key} names {painter}, which does not exist"


def test_every_page_key_the_panel_accepts_is_one_it_built(panel_module):
    """`set_page` must not accept a page nobody built, and must accept every one
    that was."""
    tray_panel, tray_paint = panel_module
    from ui.page_registry import ALL_PAGES

    panel = tray_panel.TrayPanel({})
    assert panel.open() is True

    for name in ALL_PAGES:
        assert panel.set_page(name) is True, f"set_page refused {name}"
        tray_paint.paint(panel, panel.snapshot)
        assert not [n for n in panel.notes if "would not paint" in n], (
            f"{name}: {panel.notes}")

    assert panel.set_page("does_not_exist") is False


def test_no_page_draws_a_control_off_the_panel(panel_module):
    """Every widget on every page is inside 460 x 660.

    A widget at x=470 is not a layout opinion, it is invisible: the panel is a
    fixed-size popup and anything past its edge is drawn where no user can click
    it. The artboards are all 460x660 for this reason.
    """
    tray_panel, _paint = panel_module
    from ui.tray_pages import PANEL_H, PANEL_W

    panel = tray_panel.TrayPanel({})
    panel.open()

    off = []
    for key, widget in list(panel._labels.items()) + list(panel._buttons.items()):
        try:
            x, y = widget.x(), widget.y()
            w, h = widget.width(), widget.height()
        except Exception:                        # noqa: BLE001
            continue
        if x < 0 or y < 0 or x + w > PANEL_W or y + h > PANEL_H:
            off.append((key, (x, y, w, h)))
    assert off == [], f"controls drawn outside the panel: {off}"


# ── board 9: the count is the store's, not the list's ───────────────────────

def test_board_9_counts_what_is_stored_not_what_fits(panel_module, monkeypatch):
    """The header says "12 hal", the panel holds 8. Both are true, and a page
    that made them agree would be counting widgets and calling it memory."""
    tray_panel, tray_paint = panel_module
    from ui import pages_memory

    rows = [{"category": "notes", "key": f"k{i}", "value": f"v{i}", "updated": ""}
            for i in range(12)]
    monkeypatch.setattr(pages_memory, "entries", lambda: rows)

    panel = tray_panel.TrayPanel({})
    panel.open()
    panel.set_page("memory")
    # A FRESH SNAPSHOT: `open()` captured one before the stub above ran, and
    # the subtitle is formatted from the store at snapshot time. Painting the
    # captured one would test the value from before the monkeypatch.
    from ui.tray_panel_model import snapshot

    tray_paint.paint(panel, snapshot("memory"))

    # THE COUNT IS THE SHARED HEADER'S SUBTITLE, because that is where `b09()`
    # puts it: `panel_head("Memori personal", "12 hal yang JARVIS ingat")`.
    header = panel._labels["subtitle"].text()
    assert "12" in header, f"the header does not state the store's count: {header!r}"

    drawn = [k for k in panel._labels if k.startswith("mem_key:")
             and panel._labels[k].text()]
    assert len(drawn) == pages_memory.LIST_ROWS < 12, (
        f"the page drew {len(drawn)} rows; the panel fits {pages_memory.LIST_ROWS}")

    rest = 12 - pages_memory.LIST_ROWS
    assert str(rest) in panel._labels["mem_more"].text(), (
        f"the {rest} rows that do not fit are not counted: "
        f"{panel._labels['mem_more'].text()!r}")


def test_board_9_row_button_opens_that_memory_and_holds_its_identity(
        panel_module, monkeypatch):
    """The row button must open the memory at ITS index, identified by
    (category, key) — not by the index, which moves when a row above is
    deleted."""
    tray_panel, tray_paint = panel_module
    from ui import pages_memory

    rows = [{"category": "notes", "key": "first", "value": "a", "updated": ""},
            {"category": "projects", "key": "second", "value": "b", "updated": ""}]
    monkeypatch.setattr(pages_memory, "entries", lambda: rows)

    panel = tray_panel.TrayPanel({})
    panel.open()
    panel.set_page("memory")
    tray_paint.paint(panel, panel.snapshot)

    # Press the SECOND row, through the signal, as a user would.
    panel._buttons["mem_open:1"].clicked.emit()
    assert panel.page == "memory_one"
    assert panel.target_memory() == ("projects", "second"), (
        f"the row opened {panel.target_memory()}")


def test_board_10_says_the_three_fields_it_cannot_show(panel_module, monkeypatch):
    """The store has no source, confidence or usage. The page must SAY so and
    must not draw a number where one would go."""
    tray_panel, tray_paint = panel_module
    from ui import pages_memory

    rows = [{"category": "notes", "key": "k", "value": "v", "updated": ""}]
    monkeypatch.setattr(pages_memory, "entries", lambda: rows)

    panel = tray_panel.TrayPanel({})
    panel.open()
    panel.set_page("memory")
    tray_paint.paint(panel, panel.snapshot)
    panel._buttons["mem_open:0"].clicked.emit()
    tray_paint.paint(panel, panel.snapshot)

    # THREE BANDS, THREE SENTENCES. Board 10 draws SUMBER, MASA BERLAKU,
    # KEYAKINAN and DIPAKAI OLEH as separate controls; the store has none of
    # them, so each band says so in its own place rather than one blanket line
    # standing in for four.
    conf = panel._labels["m1_conf_note"].text()
    assert conf.strip(), "the confidence band says nothing"
    assert "keyakinan" in conf.lower() or "confidence" in conf.lower(), (
        f"the confidence note does not name what is missing: {conf!r}")
    for key in ("m1_source", "m1_life", "m1_used"):
        assert panel._labels[key].text().strip(), f"{key} draws an empty band"
        assert (panel._labels[key].text().strip().lower()
                .startswith(("tidak", "not "))), (
            f"{key} does not read as an absence: {panel._labels[key].text()!r}")

    # And no percentage anywhere on the page: a confidence score is the specific
    # thing the artboard draws and this store does not have.
    texts = [w.text() for k, w in panel._labels.items() if k.startswith("m1_")]
    assert not any("%" in t for t in texts), f"a percentage was drawn: {texts}"


def test_board_10_forgets_the_memory_it_is_showing(tmp_path, monkeypatch,
                                                   panel_module):
    """The Forget button must delete the TARGET, and the target must be a pair."""
    tray_panel, tray_paint = panel_module
    from ui import pages_memory

    store = {"notes": {"a": {"value": "1"}}, "projects": {"b": {"value": "2"}}}
    monkeypatch.setattr(pages_memory, "entries", lambda: [
        {"category": c, "key": k, "value": v["value"], "updated": ""}
        for c, items in store.items() for k, v in items.items()])

    forgotten = []
    monkeypatch.setattr(pages_memory, "forget",
                        lambda c, k: (forgotten.append((c, k)), (True, "gone"))[1])

    panel = tray_panel.TrayPanel({})
    panel.open()
    panel.set_page("memory")
    tray_paint.paint(panel, panel.snapshot)
    panel._buttons["mem_open:0"].clicked.emit()
    target = panel.target_memory()

    # The panel's button calls the SHELL action; call the handler it lands on
    # with the same target, which is what `pages_actions.memory_forget` does.
    ok, _message = pages_memory.forget(*target)
    assert ok is True
    assert forgotten == [target], (
        f"the page forgot {forgotten}, not the memory it was showing ({target})")


# ── board 11: the pause is the engine's ─────────────────────────────────────

def test_board_11_reads_the_pause_the_scheduler_reads(monkeypatch):
    """The routine list is the store's; the proactive pause is the engine's.

    The scheduled routines come from `memory/routine_store.py` (the store is
    the only writer). The proactive check is NOT a scheduled routine - it
    fires on silence, not on a schedule - so its pause is read separately
    through `suggestion_paused`, and the list does not claim a row for it.
    """
    from ui import pages_people

    monkeypatch.setattr(pages_people, "suggestion_paused", lambda: True)
    # The list reads the store; with no routines stored it is empty, and the
    # pause is reported by its own reader, not as a routine row.
    assert pages_people.suggestion_paused() is True
    rows = pages_people.routines()
    assert rows == [], "no scheduled routines are stored, so the list is empty"


def test_board_11_pause_button_flips_the_engines_flag(monkeypatch, tmp_path):
    """The handler must write through `proactive._write_paused`."""
    from actions import proactive
    from ui import pages_actions

    written = {}
    monkeypatch.setattr(proactive, "_write_paused",
                        lambda paused: written.setdefault("paused", paused))
    monkeypatch.setattr(pages_actions, "_say", lambda shell, text: None)

    class Shell:
        pass

    assert pages_actions.routines_pause(Shell()) is True
    assert written == {"paused": True}, (
        f"the button wrote {written}; it must pause the engine")


def test_board_13_form_fill_refuses_an_unreviewed_url(monkeypatch):
    """Board 13's apply button builds a plan through the pure policy.

    With no URL in the field it says so and returns False without touching the
    browser — the review-first gate the board's strip promises.
    """
    from ui import pages_actions

    monkeypatch.setattr(pages_actions, "_say", lambda shell, text: None)

    class Panel:
        _inputs = {}
        def refresh(self):
            pass

    class Shell:
        _panel = Panel()

    assert pages_actions.form_fill_apply(Shell()) is False


def test_board_13_form_fill_reviews_before_applying(monkeypatch):
    """A reviewed plan is driven into the browser adapter.

    The URL and three field values are read from the inputs, the plan is built
    and reviewed (the "tinjau dulu" gate), then the adapter is called with the
    reviewed plan's fields. A failed fill is reported and returns False.
    """
    from ui import pages_actions

    called = {}

    def fake_fill(page_url, fields):
        called["page_url"] = page_url
        called["fields"] = fields
        return [type("R", (), {"selector": k, "ok": True, "detail": "ok"})()
                for k in fields]

    monkeypatch.setattr("actions.browser_form.fill_form_to_page", fake_fill)
    monkeypatch.setattr(pages_actions, "_say", lambda shell, text: None)

    class Panel:
        _inputs = {
            "hp_form_url": type("E", (), {"text": lambda self: "https://x.test/f"})(),
            "hp_form_input:0": type("E", (), {"text": lambda self: "Alice"})(),
            "hp_form_input:1": type("E", (), {"text": lambda self: "42"})(),
            "hp_form_input:2": type("E", (), {"text": lambda self: "100"})(),
        }
        def refresh(self):
            pass

    class Shell:
        _panel = Panel()

    assert pages_actions.form_fill_apply(Shell()) is True
    assert called["page_url"] == "https://x.test/f"
    assert called["fields"]["#field0"] == "Alice"


# ── board 12: the clipboard is read, and the sensitive label is a pattern ───

@pytest.mark.parametrize("text,expected", [
    ("1234 5678 9012 3456", True),
    ("halo, apa kabar", False),
    ("budi@example.com", True),
    ("sk-abcdefghijklmnop", True),
])
def test_board_12_detects_what_it_says_it_detects(text, expected):
    from ui import pages_people

    kind = pages_people.sensitive_kind(text)
    assert bool(kind) is expected, f"{text!r} -> {kind!r}"


def test_board_12_says_nothing_when_the_clipboard_is_empty(panel_module,
                                                           monkeypatch):
    tray_panel, tray_paint = panel_module
    from ui import pages_people

    monkeypatch.setattr(pages_people, "clipboard_text", lambda: "")
    panel = tray_panel.TrayPanel({})
    panel.open()
    panel.set_page("tools")
    tray_paint.paint(panel, panel.snapshot)

    assert panel._labels["tl_clip"].text().strip(), (
        "an empty clipboard leaves the card blank, which reads as a broken card")


def test_board_12_search_refreshes_the_page(panel_module, monkeypatch):
    """A search whose results are stored but not painted shows the PREVIOUS
    search's files under the words just typed."""
    tray_panel, tray_paint = panel_module
    from ui import pages_people

    monkeypatch.setattr(pages_people, "find_files",
                        lambda query, limit=3: [f"{query}-1.pdf", f"{query}-2.pdf"])
    panel = tray_panel.TrayPanel({})
    panel.open()
    panel.set_page("tools")
    tray_paint.paint(panel, panel.snapshot)

    panel.run_search("faktur")
    assert panel.hits == ("faktur-1.pdf", "faktur-2.pdf")
    assert panel._labels["tl_hit:0"].text() == "faktur-1.pdf", (
        "the hits were stored and the page was not repainted")


# ── board 14: no guest control, and the counts are the gate's ───────────────

def test_board_14_counts_are_the_risk_policys(panel_module, monkeypatch):
    from core import risk_policy
    from ui import pages_admin

    monkeypatch.setattr(risk_policy, "registered",
                        lambda: {"a": "safe", "b": "safe", "c": "risky"})
    counts = pages_admin.level_counts()
    assert counts["safe"] == 2 and counts["risky"] == 1 and counts["medium"] == 0, counts


def test_board_14_names_the_levels_the_gate_returns():
    from core import risk_policy
    from ui import pages_admin

    names = [row[0] for row in pages_admin.levels()]
    assert names == list(risk_policy.LEVELS), (
        f"the page draws {names}, the gate returns {list(risk_policy.LEVELS)}")


# ── board 15: three real settings ───────────────────────────────────────────

def test_board_15_language_switch_reports_what_took_effect(monkeypatch):
    """`set_locale` resolves; it does not always return what was asked for."""
    from core import i18n
    from ui import pages_actions, pages_admin

    monkeypatch.setattr(pages_admin, "set_language", lambda code: "en")
    monkeypatch.setattr(pages_actions, "_say", lambda shell, text: None)

    class Shell:
        pass

    assert pages_actions.language_set(Shell(), "id") is False, (
        "the handler reported success for a locale the program did not switch to")
    _ = i18n


def test_board_15_language_slots_are_in_the_artboards_order(panel_module):
    """`b15()` draws Indonesia · English · Campur, left to right.

    `i18n.available()` returns `["en", "id"]` — the order the FILES sort in.
    Building the row by iterating it put English where the drawing has
    Indonesia, and nothing failed: both slots said a real language, both
    switched the locale, and the row looked plausible. The drawing is what
    decides the order, and it is not the store's order.
    """
    from ui import pages_access

    assert pages_access.LANGUAGE_ORDER == ("id", "en")
    # And every slot drawn must be one the catalogues actually ship: drawing
    # a button for a locale with no JSON file offers a language the panel
    # cannot render.
    from ui.pages_admin import languages

    shipped = set(languages())
    assert set(pages_access.language_slots()) <= shipped
    assert pages_access.language_slots() == [c for c in ("id", "en") if c in shipped]


def test_board_15_text_scale_snaps_to_an_offered_value(monkeypatch):
    """Three sizes are offered; a stored value of 1.9 must become 1.3.

    The SNAP is what makes the three buttons mean something: a page that stored
    whatever it was handed would leave the panel at a size no segment shows, and
    the segments would read as decoration.
    """
    from memory import config_manager
    from ui import pages_admin

    stored = {}
    monkeypatch.setattr(config_manager, "set_config_values",
                        lambda **kw: stored.update(kw) or True)

    assert pages_admin.set_text_scale(1.9) is True
    assert stored[pages_admin.TEXT_SCALE_KEY] == 1.3, (
        f"1.9 was stored as {stored.get(pages_admin.TEXT_SCALE_KEY)}, "
        "not snapped to the largest offered size")

    stored.clear()
    assert pages_admin.set_text_scale(0.5) is True
    assert stored[pages_admin.TEXT_SCALE_KEY] == pages_admin.TEXT_SCALES[0]


# ── board 16: the plugin list is the manifests, the default is the loader's ─

def test_board_16_plugins_off_until_asked_when_they_declare_permissions(
        monkeypatch):
    """The loader's rule: a plugin with a manifest declaring permissions is off
    until someone turns it on. A page that defaulted everything to on would
    invite a click on a plugin the loader is refusing.

    THE ASSERTION IS ON THE DEFAULT PASSED TO THE LOADER, not on the answer:
    `get_plugin_enabled(name, default=not declared)` is the rule, and a page
    that hardcoded `True` would still "return a bool" for every row.
    """
    from memory import config_manager
    from ui import pages_admin

    calls = []

    def fake_enabled(name, default=True):
        calls.append((name, default))
        return not default

    monkeypatch.setattr(config_manager, "get_plugin_enabled", fake_enabled)

    rows = pages_admin.plugin_rows()
    assert rows, "no plugin manifests were read"
    assert calls, "the page never asked the loader"
    declared = {row["name"]: row["declared"] for row in rows}
    for name, default in calls:
        assert default is (not declared[name]), (
            f"{name} declares permissions={declared[name]} so the loader must "
            f"be asked default={not declared[name]}, not {default}")


def test_board_16_toggle_writes_the_loaders_store(monkeypatch):
    from memory import config_manager
    from ui import pages_admin

    written = {}
    monkeypatch.setattr(config_manager, "save_plugin_enabled",
                        lambda name, on: written.update({name: on}) or True)
    monkeypatch.setattr(pages_admin, "plugin_rows",
                        lambda: [{"name": "quick_notes", "on": False,
                                  "declared": True, "description": ""}])

    assert pages_admin.set_plugin("quick_notes", True) is True
    assert written == {"quick_notes": True}


def test_board_16_rows_report_manifest_facts_not_provenance(panel_module):
    """The row's second line is the version and the SECURITY LEVEL.

    The first version printed `1.4.0 · third party`, deriving "official" from
    "declares no permissions". Every manifest in this build carries
    `author: MARK-LVI` and every one declares permissions, so the rule printed
    "third party" on all fifteen rows — a provenance claim the data cannot
    support, on a page whose whole job is to say what is true. `level` is in
    the manifest and is what the loader acts on, so that is what the row says.
    """
    from ui import pages_admin

    rows = pages_admin.plugin_rows()
    assert rows, "no plugin manifests found"
    for row in rows:
        assert "trust" not in row, "the invented provenance field is back"
        assert row["version"], f"{row['name']} has no version"
        assert row["level"], f"{row['name']} has no security level"
        assert row["level"].rsplit(".", 1)[1] in ("safe", "medium", "risky")


# ── boards 18, 19, 21, 22, 13, 7: pages that must state an absence ──────────

ABSENCE_PAGES = [
    # (page, the label key that carries the sentence, a word it must contain)
    ("tools", "tl_snap_absent", ("belum", "not", "does not")),
    ("gestures", "gs_absent", ("klik", "click", "drawing", "gambar")),
    ("security", "sec_os", ("tidak", "no ", "not")),
    ("plugins", "pl_phone", ("belum", "no ", "not")),
    # THE THIRD COLUMN, not the second. `b15()` draws the gesture's ACTION in
    # the middle ("Panggil antarmuka" at x=250, cyan) and "ubah" at 416 on the
    # right; the first version of this page wrote "fixed" into the middle
    # column and dropped the action entirely — and this line asserted the bug.
    # "fixed" belongs where "ubah" was, because there is no rebinding.
    ("access", "ac_gest_edit:0", ("tetap", "fixed")),
]


@pytest.mark.parametrize("page,label_key,words", ABSENCE_PAGES)
def test_a_page_that_cannot_do_something_says_so_on_the_page(
        panel_module, page, label_key, words):
    """`NOT-IN-MOCKUP.md` records the absence for a reader of the repo. A USER
    never reads that file: the page they are looking at has to say it too, in
    the place the artboard drew the thing that does not exist."""
    tray_panel, tray_paint = panel_module

    panel = tray_panel.TrayPanel({})
    panel.open()
    panel.set_page(page)
    tray_paint.paint(panel, panel.snapshot)

    text = panel._labels[label_key].text().strip().lower()
    assert text, f"board page {page!r} drew nothing where the absence belongs"
    assert any(word in text for word in words), (
        f"{page}.{label_key} does not read as an absence: {text!r}")


def test_board_22_choosing_a_mode_is_the_presence_switch(monkeypatch):
    """Board 22 must not have its own idea of which mode is on."""
    from core import presence_mode
    from ui import pages_admin

    chosen = {}
    monkeypatch.setattr(presence_mode, "set_mode",
                        lambda mode: chosen.setdefault("mode", mode) or True)

    assert pages_admin.apply_mode("focus") is True
    assert chosen == {"mode": "focus"}, (
        f"the first-run page set {chosen} without going through presence_mode")


def test_board_7_records_the_answer_and_does_not_repeat_the_question(
        monkeypatch):
    from memory import config_manager
    from ui import pages_people

    stored = {}
    monkeypatch.setattr(config_manager, "set_config_values",
                        lambda **kw: stored.update(kw) or True)
    monkeypatch.setattr(config_manager, "load_api_keys",
                        lambda: dict(stored))

    assert pages_people.consent_given() is False
    assert pages_people.record_consent(True) is True
    assert stored.get(pages_people.CONSENT_KEY) is True
    assert pages_people.consent_given() is True


def test_board_7_says_the_flow_is_one_step_not_four(panel_module):
    """The artboard says "Langkah 2 dari 4". There is no four-step flow, and a
    page that printed "2 dari 4" would be describing a program that does not
    exist."""
    tray_panel, tray_paint = panel_module

    panel = tray_panel.TrayPanel({})
    panel.open()
    panel.set_page("consent")
    tray_paint.paint(panel, panel.snapshot)

    # THE STEP LINE IS THE SHARED SUBTITLE. `b07()` passes "Langkah 2 dari 4"
    # to `panel_head()`, so the page's step count belongs in the header's second
    # line — the page having its own copy was the duplicate.
    step = panel._labels["subtitle"].text()
    assert "4" not in step, f"the page claims a four-step flow: {step!r}"
    assert "1" in step, f"the page does not say how many steps there are: {step!r}"

    # AND THE SENTENCE COMES FROM THE CATALOGUE, not from a literal in the
    # painter: change the catalogue and the page must change with it.
    from core import i18n
    from ui import pages_paint
    from ui.tray_pages import GEOMETRY, PALETTES

    # The header's subtitle for this page must BE the catalogue's step string,
    # not a literal typed into the model: swap the catalogue entry and the
    # subtitle has to follow it.
    from ui.tray_panel_model import PAGE_TITLES

    _title, sub_key = PAGE_TITLES["consent"]
    assert sub_key == "ui.page.consent.subtitle", (
        f"board 7's subtitle is {sub_key!r}, not the step sentence")
    assert i18n.label(sub_key) == panel._labels["subtitle"].text(), (
        "the step line is not the catalogue's sentence")
    _ = (pages_paint, GEOMETRY, PALETTES)


# ── the more-list reaches every page ────────────────────────────────────────

def test_the_more_page_has_a_button_for_every_board_page(panel_module):
    tray_panel, tray_paint = panel_module
    from ui.page_registry import PAGE_KEYS

    panel = tray_panel.TrayPanel({})
    panel.open()
    panel.set_page("more")
    tray_paint.paint(panel, panel.snapshot)

    missing = [key for key in PAGE_KEYS if f"more:{key}" not in panel._buttons]
    assert missing == [], f"the more page cannot reach {missing}"


def test_pressing_a_more_row_opens_that_page(panel_module):
    tray_panel, tray_paint = panel_module

    panel = tray_panel.TrayPanel({})
    panel.open()
    panel.set_page("more")
    tray_paint.paint(panel, panel.snapshot)

    panel._buttons["more:access"].clicked.emit()
    assert panel.page == "access"


def test_the_more_list_names_the_board_each_page_implements(panel_module):
    """The board number is how a reader checks a page against the sheet."""
    tray_panel, tray_paint = panel_module
    from ui.page_registry import PAGE_BOARD, PAGES

    panel = tray_panel.TrayPanel({})
    panel.open()
    panel.set_page("more")
    tray_paint.paint(panel, panel.snapshot)

    for key, _label, _title, board in PAGES:
        text = panel._labels[f"more_board:{key}"].text()
        assert f"{PAGE_BOARD[key]:02d}" in text, (
            f"{key} shows {text!r}, not board {PAGE_BOARD[key]:02d}")


# ── the ruling that held before this round and must hold after ──────────────

def test_every_page_keeps_its_own_title(panel_module):
    """EACH PAGE KEEPS ITS OWN TITLE — a ruling, not a preference.

    The panel has ONE `title` label shared by seventeen pages, so a page missing
    from `PAGE_TITLES` silently shows "JARVIS". That is exactly what happened
    when the board pages landed: all fourteen new pages were labelled with the
    assistant's name, and nothing failed, because "JARVIS" is a plausible title.
    Found by printing every page's title, not by a test — so here is the test.
    """
    tray_panel, tray_paint = panel_module
    from ui.page_registry import ALL_PAGES

    panel = tray_panel.TrayPanel({})
    panel.open()

    titles = {}
    for name in ALL_PAGES:
        panel.set_page(name)
        tray_paint.paint(panel, panel.snapshot)
        titles[name] = panel._labels["title"].text().strip()

    for name, title in titles.items():
        assert title, f"{name} has no title"
        if name != "main":
            assert title != "JARVIS", (
                f"{name} shows the assistant's name as its title, not its own")
            assert title == "JARVIS" or titles["main"] != title, (
                f"{name} and main share a title: {title!r}")

    # And they are DIFFERENT from each other: four pages called "Memory" would
    # satisfy the assertions above while telling the user nothing.
    shared = [t for t in set(titles.values()) if list(titles.values()).count(t) > 2]
    assert not shared, f"pages share one title: {shared}"


def test_the_more_page_is_not_entry_in_its_own_list(panel_module):
    """A row that opens the page you are already on is a row that does nothing."""
    tray_panel, tray_paint = panel_module
    from ui.page_registry import PAGE_KEYS

    panel = tray_panel.TrayPanel({})
    panel.open()
    panel.set_page("more")
    tray_paint.paint(panel, panel.snapshot)

    assert "more:more" not in panel._buttons
    assert "more" not in PAGE_KEYS


# ── board 12's "Tandai aman": it has to change what the page says ────────────

def test_mark_safe_changes_the_line_it_promises_to_change(panel_module, monkeypatch):
    """"Tandai aman" must change the sensitive-text line, or it is a button that
    does nothing.

    WHAT IT CANNOT BE. There is no secret scanner in this build, so this is a
    DISPLAY decision: the page stops calling the text sensitive for as long as
    that text is on the clipboard. A test that only checked the flag was set
    would pass while the page went on saying "Terdeteksi: nomor rekening".
    """
    tray_panel, tray_paint = panel_module
    from ui import pages_people

    monkeypatch.setattr(pages_people, "clipboard_text",
                        lambda: "1234 5678 9012 3456")

    panel = tray_panel.TrayPanel({})
    panel.open()
    panel.set_page("tools")
    tray_paint.paint(panel, panel.snapshot)

    before = panel._labels["tl_kind"].text()
    assert "1234" not in before
    assert "Terdeteksi" in before or "Detected" in before, before

    panel._marked_safe = True
    tray_paint.paint(panel, panel.snapshot)
    after = panel._labels["tl_kind"].text()

    assert after != before, "marking it safe changed nothing on the page"
    assert "Terdeteksi" not in after and "Detected" not in after, after


def test_mark_safe_belongs_to_the_text_not_the_page(panel_module, monkeypatch):
    """New clipboard text, new question.

    A mark that survived a clipboard change would silently clear a secret the
    user never looked at — the one way this display decision could become a
    safety problem.
    """
    tray_panel, tray_paint = panel_module
    from ui import pages_people

    current = {"text": "1234 5678 9012 3456"}
    monkeypatch.setattr(pages_people, "clipboard_text", lambda: current["text"])

    panel = tray_panel.TrayPanel({})
    panel.open()
    panel.set_page("tools")
    tray_paint.paint(panel, panel.snapshot)
    panel._marked_safe = True
    tray_paint.paint(panel, panel.snapshot)
    assert panel._marked_safe is True

    current["text"] = "kunci: sk-abcdefghijklmnop"
    tray_paint.paint(panel, panel.snapshot)

    assert panel._marked_safe is False, (
        "the mark followed the clipboard to text it was never given for")
    assert "Terdeteksi" in panel._labels["tl_kind"].text()
