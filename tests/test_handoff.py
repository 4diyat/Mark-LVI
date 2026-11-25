"""Board 5.6's handoff context-transfer policy: build and validate a bundle.

These test the pure policy in `core.handoff` with no store and no network.
The point is that a handoff is a BOUNDED snapshot: only usable records go
in, the bundle is capped, and a received bundle that is not well-formed is
refused with a reason rather than resumed as if it were intact.
"""
from __future__ import annotations

from core.handoff import (BUNDLE_VERSION, MAX_HISTORY_TURNS,
                          MAX_MEMORY_ENTRIES, SCOPE_COMMAND, SCOPE_READ,
                          HandoffBundle, build_bundle, is_scope,
                          summary, validate_bundle)


def _memory():
    return [
        {"category": "preferences", "key": "nama", "value": "Budi",
         "updated": "2026-11-25T08:00:00"},
        {"category": "notes", "key": "proyek", "value": "Mark-LVI",
         "updated": "2026-11-25T08:01:00"},
        {"key": "", "value": "no key — dropped"},
        {"key": "no value", "value": ""},
        "not-a-dict",
    ]


def _history():
    return [
        {"role": "user", "text": "halo", "time": "2026-11-25T08:00:00"},
        {"role": "assistant", "text": "ya", "time": "2026-11-25T08:00:05"},
        {"role": "user", "text": "", "time": "2026-11-25T08:00:10"},
        "not-a-dict",
    ]


# ── scope ────────────────────────────────────────────────────────────────

def test_the_two_scopes_are_the_known_set():
    assert is_scope(SCOPE_COMMAND) and is_scope(SCOPE_READ)
    assert is_scope("nope") is False


def test_a_bundle_round_trips_through_to_dict():
    bundle = HandoffBundle(scope=SCOPE_READ, version=BUNDLE_VERSION,
                           memory=[{"key": "k", "value": "v"}])
    data = bundle.to_dict()
    assert data["scope"] == SCOPE_READ
    assert data["memory"] == [{"key": "k", "value": "v"}]
    ok, _ = validate_bundle(data)
    assert ok is True


# ── build_bundle ────────────────────────────────────────────────────────

def test_a_command_scope_bundle_carries_memory_and_history():
    bundle = build_bundle(SCOPE_COMMAND, _memory(), _history())
    assert bundle.scope == SCOPE_COMMAND
    assert bundle.version == BUNDLE_VERSION
    assert len(bundle.memory) == 2
    assert len(bundle.history) == 2


def test_a_read_scope_bundle_carries_memory_but_no_history():
    bundle = build_bundle(SCOPE_READ, _memory(), _history())
    assert bundle.scope == SCOPE_READ
    assert len(bundle.memory) == 2
    assert bundle.history == []


def test_unusable_records_are_dropped():
    bundle = build_bundle(SCOPE_COMMAND, _memory(), _history())
    keys = {m["key"] for m in bundle.memory}
    assert "nama" in keys and "proyek" in keys
    assert "no key — dropped" not in keys
    assert all(t["text"] for t in bundle.history)


def test_an_unknown_scope_falls_back_to_read():
    bundle = build_bundle("astral", _memory(), _history())
    assert bundle.scope == SCOPE_READ
    assert bundle.history == [], "an unknown scope must not leak the transcript"


def test_the_bundle_is_capped():
    memory = [{"key": f"k{i}", "value": f"v{i}"} for i in range(MAX_MEMORY_ENTRIES + 50)]
    history = [{"role": "user", "text": f"t{i}"} for i in range(MAX_HISTORY_TURNS + 50)]
    bundle = build_bundle(SCOPE_COMMAND, memory, history)
    assert len(bundle.memory) == MAX_MEMORY_ENTRIES
    assert len(bundle.history) == MAX_HISTORY_TURNS


def test_history_keeps_its_order():
    bundle = build_bundle(SCOPE_COMMAND, _memory(), _history())
    assert [t["text"] for t in bundle.history] == ["halo", "ya"]


# ── validate_bundle ─────────────────────────────────────────────────────

def test_a_built_bundle_validates():
    bundle = build_bundle(SCOPE_COMMAND, _memory(), _history())
    ok, reason = validate_bundle(bundle.to_dict())
    assert ok is True
    assert "diterima" in reason


def test_a_non_mapping_bundle_is_refused():
    ok, reason = validate_bundle("not a bundle")
    assert ok is False
    assert "bukan objek" in reason


def test_an_unknown_scope_bundle_is_refused():
    ok, reason = validate_bundle({"scope": "astral", "version": BUNDLE_VERSION,
                                  "memory": [], "history": []})
    assert ok is False
    assert "scope" in reason


def test_a_wrong_version_bundle_is_refused():
    ok, reason = validate_bundle({"scope": SCOPE_READ, "version": 99,
                                  "memory": [], "history": []})
    assert ok is False
    assert "versi" in reason


def test_a_bundle_with_bad_lists_is_refused():
    ok, reason = validate_bundle({"scope": SCOPE_READ, "version": BUNDLE_VERSION,
                                  "memory": "nope", "history": []})
    assert ok is False
    assert "memory" in reason


# ── summary ─────────────────────────────────────────────────────────────

def test_the_summary_names_what_the_bundle_carries():
    bundle = build_bundle(SCOPE_COMMAND, _memory(), _history())
    text = summary(bundle)
    assert "percakapan" in text
    assert "2 entri memori" in text
    assert "2 giliran" in text


def test_a_read_scope_summary_names_memory_only():
    bundle = build_bundle(SCOPE_READ, _memory(), _history())
    assert "memori" in summary(bundle)
