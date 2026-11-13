"""Shared fixtures.

THE TWO RULES EVERY TEST HERE FOLLOWS
    1. Nothing touches the real `config/` or `memory/`. `api_keys.json` holds
       the developer's own API key and a linked WhatsApp session; a test that
       writes to it is a test that one day deletes it. `isolated_config` points
       memory.config_manager at tmp_path and restores the module globals after.
    2. Nothing touches the network. Every test runs offline, so the suite is
       fast enough to run on every push and cannot fail because an API was
       slow.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


@pytest.fixture()
def isolated_config(tmp_path, monkeypatch):
    """memory.config_manager writing to tmp_path instead of the repo.

    The module caches nothing on disk, but it does keep `_LAST_GOOD` in memory;
    resetting it between tests keeps a leftover value from making a "no config
    yet" test pass for the wrong reason.
    """
    from memory import config_manager as cm

    monkeypatch.setattr(cm, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(cm, "CONFIG_FILE", tmp_path / "api_keys.json")
    monkeypatch.setattr(cm, "_LAST_GOOD", {}, raising=False)
    return cm
