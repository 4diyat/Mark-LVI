"""memory/voiceprint_store.py — the local voiceprint file.

WHY A STORE OF ITS OWN
    The voiceprint is biometric data: it is written once at enrollment and
    read on every boot. It gets its own module so the policy in
    `core/voice_auth.py` never touches the filesystem directly — the engine
    asks a store, and a store can be swapped (or pointed at a tmp_path in
    tests) without the engine knowing.

WHAT IT IS NOT
    It is not encryption. The voiceprint is stored as a plain JSON vector on
    disk, same as the memory store. Verification is a local gate against
    exposure, not a guarantee that the file cannot be read by someone with
    access to the machine — the spec's "batasan" says so, and the UI does.

The file is gitignored (`memory/voiceprint.json`) and tested by
`tests/test_gitignore.py`, which runs `git check-ignore` per rule.
"""
from __future__ import annotations

import json
import threading
from pathlib import Path

from memory.memory_manager import get_base_dir

# Sitting beside the memory store, in the same gitignored directory.
VOICEPRINT_PATH = get_base_dir() / "memory" / "voiceprint.json"

_lock = threading.RLock()


def _atomic_write(path: Path, data: dict) -> None:
    """Write via a temp file + rename, so a crash mid-write cannot leave a
    half-written voiceprint that would then be read as valid on the next
    boot. Mirrors memory_manager's write discipline."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data), encoding="utf-8")
    tmp.replace(path)


class VoiceprintStore:
    """Load / save / delete the enrolled voiceprint."""

    def __init__(self, path: Path | str | None = None) -> None:
        self._path = Path(path) if path is not None else VOICEPRINT_PATH
        self._lock = threading.RLock()

    @property
    def path(self) -> Path:
        return self._path

    def exists(self) -> bool:
        return self._path.exists()

    def load(self) -> dict | None:
        """Return the stored voiceprint dict, or None if absent/corrupt.

        A corrupt file is treated as "not enrolled" rather than raising: a
        voiceprint that cannot be read should leave the gate off, not crash
        startup.
        """
        try:
            with self._lock:
                if not self._path.exists():
                    return None
                data = json.loads(self._path.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or "embedding" not in data:
                return None
            return data
        except Exception:
            return None

    def save(self, embedding, *, embedder: str, samples: int) -> None:
        """Persist the voiceprint. `embedding` is a sequence of floats."""
        vec = [float(x) for x in embedding]
        if not vec:
            raise ValueError("empty voiceprint embedding")
        data = {
            "embedder": str(embedder or ""),
            "samples": int(samples),
            "embedding": vec,
        }
        with self._lock:
            _atomic_write(self._path, data)

    def delete(self) -> bool:
        """Remove the voiceprint. True if a file was removed."""
        with self._lock:
            if self._path.exists():
                try:
                    self._path.unlink()
                    return True
                except Exception:
                    return False
            return False


# A module-level default store, so callers that just want "the" voiceprint
# file do not have to construct one.
default_store = VoiceprintStore()
