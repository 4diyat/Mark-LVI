"""Imports that are only paid if they are used — and stay findable when they are.

WHY THE PROXY IS THE POINT
    `actions/computer_control.py` calls `pyautogui.` eighty-six times. Replacing
    those with accessor functions is eighty-six chances to miss one, and the one
    that is missed is a `NameError` at the moment somebody is talking to the
    assistant, not a slow launch. So the NAME stays a module global and what it
    holds changes.

    That decision fails in one specific way, and the module's own docstring
    describes watching it happen: PEP 562's module `__getattr__` does NOT fire
    for a bare name inside the module, so a proxy written that way passes a test
    that reads `module.pyautogui` from outside and raises NameError on every
    real call. The test below calls a name from *inside* a module for exactly
    that reason.
"""
from __future__ import annotations

import sys
import types

import pytest

from core.lazyimport import LazyModule, installed


# ── is it installed, without importing it ──────────────────────────────────

def test_a_package_that_is_installed_answers_yes():
    assert installed("json") is True


def test_a_package_that_is_not_installed_answers_no():
    assert installed("a_package_nobody_has_installed_anywhere") is False


def test_a_half_installed_package_answers_no_instead_of_raising(monkeypatch):
    """`find_spec` raises ValueError for a module left in a broken state.

    A crashed install should read as "not available", which every caller already
    handles, rather than take the launch down at import time.
    """
    import importlib.util as util

    def broken(_name):
        raise ValueError("module is partially initialised")

    monkeypatch.setattr(util, "find_spec", broken)

    assert installed("anything") is False


# ── the proxy ──────────────────────────────────────────────────────────────

@pytest.fixture()
def fake_module(monkeypatch):
    """A real module in sys.modules, so importlib.import_module finds it."""
    module = types.ModuleType("lazy_test_pkg")
    module.CALLS = []
    module.PAUSE = 0.0

    def press(key):
        module.CALLS.append(key)
        return f"pressed {key}"

    module.press = press
    monkeypatch.setitem(sys.modules, "lazy_test_pkg", module)
    return module


def test_nothing_is_imported_until_an_attribute_is_asked_for(fake_module):
    proxy = LazyModule("lazy_test_pkg")
    assert "not yet imported" in repr(proxy)
    assert proxy._module is None


def test_the_first_attribute_access_fetches_the_module(fake_module):
    proxy = LazyModule("lazy_test_pkg")

    assert proxy.press("a") == "pressed a"
    assert "loaded" in repr(proxy)
    assert fake_module.CALLS == ["a"]


def test_the_module_is_fetched_once_not_once_per_call(fake_module):
    proxy = LazyModule("lazy_test_pkg")
    proxy.press("a")
    first = proxy._module
    proxy.press("b")

    assert proxy._module is first


def test_writing_an_attribute_reaches_the_real_module(fake_module):
    """`pyautogui.PAUSE = 0.05` has to set the real module's PAUSE."""
    proxy = LazyModule("lazy_test_pkg")

    proxy.PAUSE = 0.05

    assert fake_module.PAUSE == 0.05


def test_the_configure_hook_runs_on_every_access(fake_module):
    """The three files that share pyautogui disagree about PAUSE on purpose.

    Eagerly imported, the winner was whichever file was imported LAST, and
    discovery order made that one file every time — stable and wrong for the
    other two. Re-running the hook per access gives each caller what it asked
    for, immediately before its own call.
    """
    seen = []

    def configure(module):
        seen.append(module.PAUSE)

    proxy = LazyModule("lazy_test_pkg", configure)
    proxy.PAUSE = 0.05          # also an access: the hook runs before the write
    proxy.press("a")
    proxy.PAUSE = 0.06
    proxy.press("b")

    # What matters is the value the hook saw on the access that did the work:
    # the CALLS, not the writes. The last configure before each press must have
    # seen the value the caller had just set.
    assert seen[:4] == [0.0, 0.05, 0.05, 0.06], seen
    assert seen[-1] == fake_module.PAUSE == 0.06


def test_dir_lists_the_real_module(fake_module):
    assert "press" in dir(LazyModule("lazy_test_pkg"))


def test_a_missing_package_raises_only_when_used(monkeypatch):
    """A launch must not fail over an optional library nobody asked for."""
    proxy = LazyModule("a_package_nobody_has_installed_anywhere")
    assert proxy is not None            # constructing it is free

    with pytest.raises(ModuleNotFoundError):
        proxy.press("a")


def test_the_proxy_works_for_a_name_used_inside_a_module(fake_module, tmp_path):
    """THE FAILURE MODE THE DOCSTRING DESCRIBES.

    A bare `pyautogui.press(...)` inside a module is a global lookup: locals,
    then the module's globals, then builtins. It never reaches a module-level
    `__getattr__`. So the test executes a module whose global is the proxy and
    calls it from inside, which is the only arrangement that proves the fix.
    """
    source = (
        "pyautogui = PROXY\n\n"
        "def run():\n"
        "    return pyautogui.press('a')\n"
    )
    namespace: dict = {"PROXY": LazyModule("lazy_test_pkg")}
    exec(compile(source, "fake_action.py", "exec"), namespace)

    assert namespace["run"]() == "pressed a"


def test_a_configure_hook_that_raises_is_not_swallowed():
    """A hook is setup code; a broken one must be visible, not silently skipped."""
    module = types.ModuleType("lazy_bad_pkg")
    sys.modules["lazy_bad_pkg"] = module

    def broken(_module):
        raise RuntimeError("cannot configure")

    try:
        with pytest.raises(RuntimeError):
            LazyModule("lazy_bad_pkg", broken).anything
    finally:
        sys.modules.pop("lazy_bad_pkg", None)
