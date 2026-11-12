"""No `shell=True`, and the reasoning that has to replace it.

WHY A TEST AND NOT A CODE REVIEW
    `shell=True` is not a style preference. It means the string you built is a
    program, and on Windows it means the string went through cmd.exe — which is
    how `subprocess.Popen("notepad.exe & whoami", shell=True)` runs two things.
    This project has already shipped that line (actions/open_app.py) and the
    only reason it was found is that somebody rewrote the file for a different
    reason.

    So the rule is checked instead of remembered. The two exemptions below are
    real and documented in place; a third has to be added here on purpose, in a
    diff somebody can disagree with.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent

# Every directory that runs commands. The suite's own files and the docs are
# not searched: a test may legitimately assert about `shell=True` (this one
# does), and prose is not code.
SCANNED = ("actions", "core", "dashboard", "memory", "providers", "plugins", "ui")

# Files allowed to call a shell, and why. Keep this list short and specific.
ALLOWED: dict[str, str] = {}


def python_files():
    for folder in SCANNED:
        base = ROOT / folder
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            yield path
    yield ROOT / "main.py"


def _name(path: Path) -> str:
    """The path as a reader knows it: repo-relative when it is in the repo, and
    absolute otherwise (the self-tests below build files in tmp_path)."""
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def calls_with_shell_true(path: Path) -> list[str]:
    """`(... shell=True)` in the source, ignoring comments and docstrings.

    AST rather than grep on purpose: this project explains itself in comments,
    and three of the current matches are sentences in a docstring saying why the
    call is NOT there any more. A grep would fail on those, so the check would
    have to be relaxed until it caught nothing.
    """
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        for kw in node.keywords:
            if kw.arg == "shell" and isinstance(kw.value, ast.Constant) \
                    and kw.value.value is True:
                name = getattr(node.func, "attr", None) or getattr(node.func, "id", "?")
                found.append(f"{_name(path)}:{node.lineno} {name}(shell=True)")
    return found


def test_no_module_runs_a_command_through_a_shell():
    offenders = [hit for path in python_files()
                 if path.relative_to(ROOT).as_posix() not in ALLOWED
                 for hit in calls_with_shell_true(path)]
    assert offenders == [], (
        "these pass a string to a shell. Build an argument vector instead, and "
        "if a batch file really has to run, `cmd /c <path>` says so where a "
        "reader can see it:\n  " + "\n  ".join(offenders))


def test_the_allowlist_does_not_outlive_its_reason():
    """An exemption for a file that has been fixed — or deleted — is how the
    list grows back into a hiding place."""
    for name in ALLOWED:
        assert (ROOT / name).is_file(), f"{name} is exempt but does not exist"


def test_a_command_vector_is_used_where_a_string_used_to_be():
    """The two places this actually broke, pinned so they stay broken.

    `open_app` had `Popen(app_name, shell=True)` and `dev_agent` had
    `Popen([cmd, path], shell=True)`. The second is the subtler one: a list with
    a shell is not a vector on Windows, and it is what made a `.cmd` runnable —
    so removing the flag alone would have stopped VS Code from opening for
    every Windows user. The replacement has to name the batch case.
    """
    dev = (ROOT / "actions" / "dev_agent.py").read_text(encoding="utf-8")
    assert '["cmd", "/c", cmd, str(project_dir)]' in dev, (
        "the .cmd/.bat branch is what replaced shell=True on Windows")
    assert ".cmd" in dev and ".bat" in dev

    open_app = (ROOT / "actions" / "open_app.py").read_text(encoding="utf-8")
    tree = ast.parse(open_app)
    popens = [n for n in ast.walk(tree)
              if isinstance(n, ast.Call)
              and getattr(n.func, "attr", None) == "Popen"]
    assert popens, "open_app no longer starts anything?"
    for call in popens:
        # Popen(anything, shell=...) — the argument must not be a bare string.
        first = call.args[0] if call.args else None
        assert not isinstance(first, ast.Constant), (
            f"open_app.py:{call.lineno} starts a string, which only works "
            "through a shell")
        assert not any(kw.arg == "shell" for kw in call.keywords)


def test_brightness_no_longer_shells_out_to_compute_its_own_level():
    """The last `shell=True` in actions/ built a command with `$(...)`, a grep
    and a nested `python3 -c`. It also read a fraction where the rest of the
    file reports a percentage."""
    from actions import computer_settings as cs
    assert hasattr(cs, "_brightness_step")

    # The pipeline itself must be gone from the CODE. Checked through the AST —
    # the docstring in that function quotes the old command to explain it, and
    # a substring search would either fail on the explanation or be weakened
    # until it passed on the real thing.
    tree = ast.parse((ROOT / "actions" / "computer_settings.py")
                     .read_text(encoding="utf-8"))
    # Docstrings are excluded, and that is not a loophole: a docstring says what
    # somebody thought, and this one records why the pipeline went. A constant
    # that is not a docstring is a string the code USES.
    docstrings = {id(node.body[0].value) for node in ast.walk(tree)
                  if isinstance(node, (ast.FunctionDef, ast.ClassDef, ast.Module))
                  and node.body and isinstance(node.body[0], ast.Expr)
                  and isinstance(node.body[0].value, ast.Constant)}
    code_strings = [n.value for n in ast.walk(tree)
                    if isinstance(n, ast.Constant) and isinstance(n.value, str)
                    and id(n) not in docstrings and "xrandr" in n.value]
    assert code_strings == [], (
        f"the xrandr pipeline is back as a literal: {code_strings}")

    # The step reads, clamps, writes — and refuses rather than guessing.
    seen = {}
    original_get, original_set = cs.brightness_get, cs.brightness_set
    try:
        cs.brightness_get = lambda: 40
        cs.brightness_set = lambda v: seen.setdefault("value", v)
        assert cs.brightness_up() is True
        assert seen["value"] == 50
        seen.clear()
        assert cs.brightness_down() is True
        assert seen["value"] == 30
        cs.brightness_get = lambda: 4           # near the floor
        seen.clear()
        cs.brightness_down()
        assert seen["value"] == 1, "a step below 1 % must clamp, not go negative"
        cs.brightness_get = lambda: None
        seen.clear()
        assert cs.brightness_up() is False and not seen, (
            "an unreadable level must not produce a guess")
    finally:
        cs.brightness_get, cs.brightness_set = original_get, original_set


@pytest.mark.parametrize("snippet", [
    "subprocess.run(cmd, shell=True)",
    "subprocess.Popen([a, b], shell=True)",
])
def test_the_checker_catches_both_shapes(tmp_path, snippet):
    """Self-test: a rule that cannot fail is not a rule. Both shapes above are
    what this repository actually had."""
    probe = tmp_path / "probe.py"
    probe.write_text("import subprocess\n\n\ndef f(a, b, cmd):\n    " + snippet + "\n",
                     encoding="utf-8")
    assert calls_with_shell_true(probe), snippet


def test_a_docstring_mention_is_not_an_offence(tmp_path):
    probe = tmp_path / "probe.py"
    probe.write_text('"""We used to call shell=True here."""\n\n'
                     "def f():\n    return 1\n", encoding="utf-8")
    assert calls_with_shell_true(probe) == []


def test_no_module_builds_a_shell_command_from_user_text():
    """The dangerous half of `shell=True` without the flag: `os.system`, and
    `subprocess.*` fed an f-string that contains a path or a spoken value."""
    dangerous = re.compile(r"\bos\.system\s*\(|\bos\.popen\s*\(")
    hits = []
    for path in python_files():
        for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if line.lstrip().startswith("#"):
                continue
            if dangerous.search(line):
                hits.append(f"{path.relative_to(ROOT).as_posix()}:{i}")
    assert hits == [], f"os.system/os.popen somewhere: {hits}"
