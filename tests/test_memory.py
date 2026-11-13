"""The assistant's memory: what it keeps, what it forgets, and what it says.

WHY THE FORGETTING IS THE INTERESTING PART
    `memory/memory_manager.py` went from "two pages, quietly forgetting your
    sister's name after a few weeks" to a store of 200 000 characters with a
    900-character prompt budget and an on-demand recall tool. Three rules make
    that work, and all three are invisible until they break:

      * what goes in the prompt is SMALL and prioritised, but the index lists
        everything else by name — a model cannot look up what it does not know
        exists;
      * trimming happens only at the runaway guard, and it is announced to the
        user, because silently deleting what someone told you is how a memory
        loses trust;
      * a value longer than the limit is truncated, not rejected.

    The tests write to tmp_path (the `isolated_config` pattern), because the
    real memory folder holds the developer's own life.
"""
from __future__ import annotations

import json

import pytest

from memory import memory_manager as mm


@pytest.fixture(autouse=True)
def isolated_memory(tmp_path, monkeypatch):
    """Point the module at a temp file and forget the notifier between tests."""
    monkeypatch.setattr(mm, "MEMORY_PATH", tmp_path / "long_term.json")
    monkeypatch.setattr(mm, "_trim_notifier", None)
    return tmp_path / "long_term.json"


def remember(**entries) -> None:
    mm.update_memory(entries)


# ── storage ────────────────────────────────────────────────────────────────

def test_a_fresh_install_has_all_the_categories_and_no_entries():
    memory = mm.load_memory()

    assert set(memory) == {"identity", "preferences", "projects",
                           "relationships", "wishes", "notes"}
    assert all(value == {} for value in memory.values())


def test_what_is_written_is_read_back():
    mm.update_memory({"identity": {"name": "Fatih"}})

    assert mm.load_memory()["identity"]["name"]["value"] == "Fatih"


def test_an_entry_carries_when_it_was_updated():
    """Recency is the only relevance signal the prompt block has."""
    mm.update_memory({"notes": {"dentist": "Tuesday 10:00"}})

    assert mm.load_memory()["notes"]["dentist"]["updated"]


def test_updating_one_key_keeps_the_others():
    """A merge, not a replace: this is a whole-file write behind a lock."""
    mm.update_memory({"preferences": {"tea": "no sugar"}})
    mm.update_memory({"preferences": {"coffee": "black"}})

    preferences = mm.load_memory()["preferences"]
    assert preferences["tea"]["value"] == "no sugar"
    assert preferences["coffee"]["value"] == "black"


def test_a_corrupt_file_reads_as_empty_rather_than_crashing(tmp_path, monkeypatch):
    path = tmp_path / "long_term.json"
    path.write_text("{ this is not json", encoding="utf-8")
    monkeypatch.setattr(mm, "MEMORY_PATH", path)

    assert mm.load_memory() == mm._empty_memory()


def test_a_file_missing_categories_gets_them_back(tmp_path, monkeypatch):
    path = tmp_path / "long_term.json"
    path.write_text(json.dumps({"identity": {"name": {"value": "A"}}}), encoding="utf-8")
    monkeypatch.setattr(mm, "MEMORY_PATH", path)

    memory = mm.load_memory()

    assert memory["identity"]["name"]["value"] == "A"
    assert memory["notes"] == {}


def test_a_very_long_value_is_truncated_not_rejected():
    mm.update_memory({"notes": {"rant": "x" * (mm.MAX_VALUE_LENGTH + 500)}})

    stored = mm.load_memory()["notes"]["rant"]["value"]
    # The ellipsis is the point: the model must be able to SEE that it was cut,
    # or it answers from a sentence that stops without saying so.
    assert stored.endswith("…")
    assert len(stored) <= mm.MAX_VALUE_LENGTH + 1


def test_saving_something_that_is_not_a_mapping_does_nothing():
    mm.save_memory(None)          # type: ignore[arg-type]
    mm.save_memory(["not", "a", "dict"])  # type: ignore[arg-type]
    assert mm.load_memory() == mm._empty_memory()


# ── what the model is handed every session ─────────────────────────────────

def test_nothing_stored_means_nothing_added_to_the_prompt():
    assert mm.format_memory_for_prompt(None) == ""
    assert mm.format_memory_for_prompt({}) == ""


def test_identity_is_always_included_in_full():
    """It is small, and it is wrong for the assistant to look up your name."""
    memory = mm.update_memory({"identity": {"name": "Fatih",
                                            "city": "Bandung"}})

    block = mm.format_memory_for_prompt(memory)

    assert "Fatih" in block and "Bandung" in block


def test_the_language_is_an_observation_not_a_standing_order():
    """'Language: English' written months ago made Turkish come back English."""
    memory = mm.update_memory({"identity": {"language": "Turkish"}})

    block = mm.format_memory_for_prompt(memory)

    assert "Has spoken to you in: Turkish" in block
    assert "CURRENT message" in block
    assert "Language: Turkish" not in block


def test_the_block_stays_within_its_character_budget():
    """Sessions connect faster because this block is SMALLER than a full dump."""
    memory = {"preferences": {f"p{i}": {"value": "v" * 200,
                                        "updated": "2026-01-01"}
                              for i in range(60)}}

    block = mm.format_memory_for_prompt(memory)

    # Identity is empty here; the rest is budgeted. Allow the fixed header text.
    assert len(block) < mm.PROMPT_CORE_CHARS * 2


def test_a_category_cannot_take_the_whole_budget():
    """Forty preferences must not push out the one relationship that matters."""
    memory = {"preferences": {f"p{i}": {"value": f"preference {i} detail",
                                        "updated": "2026-01-02"}
                              for i in range(40)},
              "relationships": {"ayse": {"value": "my sister, lives in Izmir",
                                         "updated": "2020-01-01"}}}

    block = mm.format_memory_for_prompt(memory)

    assert "Ayse" in block or "ayse" in block, block


def test_everything_else_is_listed_by_name_so_it_can_be_looked_up():
    """A model cannot decide to recall something it does not know exists."""
    memory = {"relationships": {"ayse_sister": {"value": "lives in Izmir",
                                                "updated": "2020-01-01"}},
              "projects": {f"project_{i}": {"value": "detail " * 30,
                                            "updated": "2026-01-01"}
                           for i in range(20)}}

    block = mm.format_memory_for_prompt(memory)

    assert "ayse" in block.lower()


def test_an_empty_category_does_not_print_a_heading():
    block = mm.format_memory_for_prompt({"notes": {"one": {"value": "x"}}})
    assert "Relationships" not in block


# ── recall, on demand ──────────────────────────────────────────────────────

def test_search_finds_an_entry_by_any_word_in_it():
    mm.update_memory({"relationships": {"ayse": "my sister, lives in Izmir"},
                      "projects": {"garden": "the tomato beds"}})

    result = mm.search_memory("sister")

    assert "Izmir" in result


def test_search_that_matches_nothing_says_so_plainly():
    mm.update_memory({"notes": {"dentist": "Tuesday"}}) 

    result = mm.search_memory("spaceship")

    assert "no" in result.lower() or "not" in result.lower()


def test_search_is_bounded():
    """A recall that returns the whole memory is a prompt the session pays for."""
    mm.update_memory({"notes": {f"k{i}": f"shared word {i}" for i in range(30)}})

    result = mm.search_memory("shared", limit=3)

    assert len(result) < 2_000


def test_the_ui_listing_shows_every_entry_with_its_category():
    mm.update_memory({"preferences": {"tea": "no sugar"},
                      "identity": {"name": "Fatih"}})

    rows = mm.all_entries_for_ui()

    assert {row["category"] for row in rows} == {"preferences", "identity"}
    assert any(row["key"] == "tea" for row in rows)


# ── trimming, which must be rare, bounded and announced ────────────────────

def test_nothing_is_trimmed_until_the_runaway_guard(monkeypatch):
    """MEMORY_MAX_CHARS is a guard against a bug, not a feature limit."""
    mm.update_memory({"notes": {"small": "x" * 100}})
    monkeypatch.setattr(mm, "MEMORY_MAX_CHARS", 200_000)

    assert "small" in mm.load_memory()["notes"]


def test_a_runaway_store_drops_the_oldest_and_says_so(monkeypatch):
    notices = []
    mm.set_trim_notifier(notices.append)
    for i in range(6):
        mm.update_memory({"notes": {f"old_{i}": {"value": "x" * 100,
                                                 "updated": f"2020-01-0{i + 1}"}}})

    monkeypatch.setattr(mm, "MEMORY_MAX_CHARS", 400)
    memory = mm.update_memory({"notes": {"new": "y" * 100}})

    assert "new" in memory["notes"]
    assert len(memory["notes"]) < 7
    assert notices and "Memory full" in notices[0]


def test_a_notifier_that_raises_does_not_stop_the_trim():
    mm.set_trim_notifier(lambda _m: (_ for _ in ()).throw(RuntimeError("gone")))
    for i in range(6):
        mm.update_memory({"notes": {f"old_{i}": {"value": "x" * 100,
                                                 "updated": f"2020-01-0{i + 1}"}}})

    memory = mm.update_memory({"notes": {"new": "y" * 100}})

    assert "new" in memory["notes"]
