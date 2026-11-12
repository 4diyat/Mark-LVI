"""Every module big enough to matter has a test, or a stated reason it cannot.

WHY NOT JUST A COVERAGE PERCENTAGE
    A `--fail-under` on the whole package measures the RUNNER, not the code:
    the same 254 tests read 36 % of core/ on a developer's machine with
    requirements.txt installed and 29 % on a CI runner that installs only the
    test tooling — and 1-2 points differently again on Windows than on Linux,
    because Qt, torch, a GPU and an audio device are unimportable there. A gate
    whose number moves with the operating system teaches people to add skips
    until it goes green.

    So the rule is structural instead, and it is the rule the percentage was
    only ever a proxy for: a module large enough to matter either has a test
    that names it, or is on the list below with a reason. Both halves are
    checked, so neither an untested module nor a stale exemption can pass by
    being forgotten.
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TESTS = ROOT / "tests"

# A module with fewer statements than this is a helper, not a component: the
# risk of it being wrong without a test is smaller than the cost of the test.
MIN_STATEMENTS = 120

# Modules a machine without a GPU, a display, a microphone or a network cannot
# execute, and what would be needed to test them. Anything NOT on this list has
# to be named by a test file.
CANNOT_RUN_HERE = {
    "core/avatar.py":          "needs a Qt paint device and a GPU-ish canvas",
    "core/avatar_mesh.py":     "numpy 3-D mesh maths used only by the avatar",
    "core/tts.py":             "needs an audio output device",
    "core/stt.py":             "needs a microphone",
    "core/wake_word.py":       "needs a microphone and the openwakeword model",
    "core/audio_devices.py":   "needs sounddevice and real hardware",
    "core/viseme.py":          "needs the avatar's mouth model",
    "core/installer.py":       "shells out to pip and Playwright installers",
    "core/_smoke_harness.py":  "a subprocess entry point, driven by code_checks",
    "core/code_checks.py":     "mostly subprocess and AST over OTHER projects",
    "core/gemini.py":          "imports google-genai and calls the Live API",
    "core/appidentity.py":     "reads the process table of a real desktop",
    "dashboard/server.py":     "needs fastapi + httpx; covered where they exist",
}

# Modules that ARE tested, mapped to the file that tests them. Named explicitly
# so a rename or a move shows up here instead of quietly reducing the list.
TESTED = {
    "core/action_loader.py":  "tests/test_loaders.py",
    "core/plugin_loader.py":  "tests/test_loaders.py",
    "core/outcome.py":        "tests/test_outcome.py",
    "core/undo.py":           "tests/test_undo.py",
    "core/confirm.py":        "tests/test_confirm.py",
    "core/echo.py":           "tests/test_echo.py",
    "core/hotkey.py":         "tests/test_hotkey.py",
    "core/i18n.py":           "tests/test_i18n.py",
    "core/secrets.py":        "tests/test_secrets.py",
    "core/lazyimport.py":     "tests/test_lazyimport.py",
    "core/logbook.py":        "tests/test_logbook.py",
    "core/platform_support.py": "tests/test_platform_support.py",
    "memory/config_manager.py": "tests/test_config.py",
    "memory/memory_manager.py": "tests/test_memory.py",
}


def statements(path: Path) -> int:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return sum(isinstance(node, ast.stmt) for node in ast.walk(tree))


def modules() -> dict[str, int]:
    out = {}
    for folder in ("core", "memory", "dashboard"):
        for path in sorted((ROOT / folder).glob("*.py")):
            if path.name == "__init__.py":
                continue
            out[path.relative_to(ROOT).as_posix()] = statements(path)
    return out


def test_every_component_is_either_tested_or_explained():
    missing = sorted(
        f"{name} ({count} statements)"
        for name, count in modules().items()
        if count >= MIN_STATEMENTS
        and name not in TESTED
        and name not in CANNOT_RUN_HERE
    )
    assert missing == [], (
        "these modules are big enough to matter and have neither a test nor a "
        "reason: " + ", ".join(missing))


def test_every_named_test_file_still_exists():
    """A stale mapping is worse than none: it claims coverage that is gone."""
    missing = [f"{module} -> {test}" for module, test in TESTED.items()
               if not (ROOT / test).is_file()]
    assert missing == []


def test_every_exemption_still_has_a_module_behind_it():
    """An exemption that outlives its module quietly shrinks the rule."""
    stale = [name for name in CANNOT_RUN_HERE if not (ROOT / name).is_file()]
    assert stale == []


def test_the_exemptions_are_not_where_the_bugs_were():
    """A weak rule, but the one that matters: the modules that decide what the
    assistant DOES to the machine must not be exempt from having a test."""
    dangerous = ["core/action_loader.py", "core/plugin_loader.py", "core/undo.py",
                 "core/confirm.py", "core/outcome.py", "core/echo.py"]
    for name in dangerous:
        assert name in TESTED, f"{name} decides real outcomes and has no test"


def test_a_named_test_actually_mentions_the_module():
    """`tests/x.py` existing is not the same as it testing anything."""
    for module, test in TESTED.items():
        stem = Path(module).stem
        text = (ROOT / test).read_text(encoding="utf-8")
        assert stem in text or module in text, (
            f"{test} does not mention {stem}; the mapping is a claim, make it true")
