"""The voiceprint store: round-trips, atomicity, and corrupt-file safety.

The store is the only place the voiceprint touches the filesystem. These
tests use tmp_path (never the real `memory/` directory) and a synthetic
embedding, so no audio and no real biometric data are involved.
"""
from __future__ import annotations

import json

from memory.voiceprint_store import VoiceprintStore


def _vec(values=(0.1, 0.2, 0.3, 0.4)):
    return list(values)


def test_absent_file_loads_as_none(tmp_path):
    store = VoiceprintStore(tmp_path / "voiceprint.json")
    assert store.load() is None
    assert store.exists() is False


def test_save_then_load_round_trips(tmp_path):
    path = tmp_path / "voiceprint.json"
    store = VoiceprintStore(path)
    store.save(_vec(), embedder="band_energy", samples=4)
    assert path.exists()

    data = store.load()
    assert data is not None
    assert data["embedder"] == "band_energy"
    assert data["samples"] == 4
    assert data["embedding"] == _vec()


def test_delete_removes_the_file(tmp_path):
    path = tmp_path / "voiceprint.json"
    store = VoiceprintStore(path)
    store.save(_vec(), embedder="band_energy", samples=4)
    assert store.delete() is True
    assert not path.exists()
    # Deleting again is not an error — it is a no-op returning False.
    assert store.delete() is False


def test_corrupt_file_loads_as_none_not_raises(tmp_path):
    """A voiceprint that cannot be read must leave the gate OFF, not crash
    startup."""
    path = tmp_path / "voiceprint.json"
    path.write_text("{not json", encoding="utf-8")
    store = VoiceprintStore(path)
    assert store.load() is None


def test_missing_embedding_key_loads_as_none(tmp_path):
    path = tmp_path / "voiceprint.json"
    path.write_text(json.dumps({"embedder": "band_energy"}), encoding="utf-8")
    assert VoiceprintStore(path).load() is None


def test_save_rejects_an_empty_embedding(tmp_path):
    store = VoiceprintStore(tmp_path / "voiceprint.json")
    import pytest
    with pytest.raises(ValueError):
        store.save([], embedder="band_energy", samples=4)


def test_write_is_atomic_no_tmp_left_behind(tmp_path):
    """A temp file from a crashed write must not linger as a stray file."""
    path = tmp_path / "voiceprint.json"
    store = VoiceprintStore(path)
    store.save(_vec(), embedder="band_energy", samples=4)
    leftovers = [p.name for p in tmp_path.iterdir() if p.name != "voiceprint.json"]
    assert leftovers == []
