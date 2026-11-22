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


# The TEST FILES that load `ui/lifecycle.py` by path. Listed by file name
# because that is what pytest hands the fixture, and because the set has to stay
# small: a global stub of the `ui` package is exactly what broke five tests in
# `test_ui_split.py`, which imports the real one on purpose.
QT_FREE_UI_TESTS = frozenset({
    "test_presence_chain.py",
    "test_presence_wiring.py",
    "test_launch_options.py",
    "test_deeplink.py",
    "test_autostart.py",
})


@pytest.fixture(autouse=True)
def ui_package_stub_for_qt_free_modules(request, monkeypatch):
    """Make `from ui.ambient_shell import ...` work with no PyQt6 installed.

    THE PROBLEM
        Several tests load a module out of `ui/` by path, past `ui/__init__.py`,
        because that `__init__` imports the whole window and the window needs Qt
        — which CI deliberately does not install. That worked until
        `ui/lifecycle.py` gained `from ui.ambient_shell import ...`: any
        `from ui.x import y` imports the PARENT package first, which re-runs
        `ui/__init__.py`, and the test dies in `ui/theme.py` on a line it never
        asked for.

    WHY IT IS NARROW ON PURPOSE
        `tests/test_ui_split.py` imports the REAL `ui` package to assert what it
        re-exports, and a global stub quietly replaced it with an empty module —
        five of its tests failed on a missing `hud_canvas`. So the stub is
        installed only for the files that have declared themselves Qt-free.
    """
    import sys
    import types

    module_path = getattr(getattr(request, "module", None), "__file__", "") or ""
    if Path(module_path).name not in QT_FREE_UI_TESTS:
        yield
        return
    # REPLACED, not reused. An earlier test in the same session may have left
    # the REAL `ui` package in sys.modules (test_ui_split imports it on
    # purpose). Reusing it here would re-run `ui/__init__.py` and this fixture
    # would be a no-op that looks like it is working.
    stub = types.ModuleType("ui")
    stub.__path__ = [str(ROOT / "ui")]
    monkeypatch.setitem(sys.modules, "ui", stub)
    yield


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
