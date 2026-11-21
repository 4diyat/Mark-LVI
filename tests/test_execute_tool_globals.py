"""`_execute_tool` must not name a global that does not exist.

WHY THIS IS A STATIC CHECK
    `main.py` is not importable in this suite — it wants google-genai, a
    microphone and an open session. So `_execute_tool` is tested by pulling its
    single function out of the AST and exec'ing it with a hand-built namespace
    (see tests/test_pointing_vision.py). That works, but it means a NEW
    module-level global is invisible until someone happens to run the one test
    that supplies it.

    That is exactly what happened when the stateless tool branches moved to
    core/tool_dispatch: `_execute_tool` gained `_dispatch`, the vision test's
    namespace did not have it, and the failure surfaced as a mismatched capture
    count rather than "this name is undefined".

    On a real session it is worse than that. `_execute_tool` wraps the whole
    dispatch in `except Exception`, so a NameError is converted into the string
    "Tool 'x' failed: name '_dispatch' is not defined" and handed to the model,
    which will read it out loud. A typo would look like a broken tool.

    So the question is asked of the source, where the answer is cheap: every
    global this function loads must exist in main.py or be a builtin.
"""
from __future__ import annotations

import ast
import builtins
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAIN = ROOT / "main.py"


def _module_bindings(tree: ast.Module) -> set[str]:
    """Everything main.py defines or imports at module level."""
    names = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                names.update(n.id for n in ast.walk(target) if isinstance(n, ast.Name))
        elif isinstance(node, (ast.AnnAssign, ast.AugAssign)):
            names.update(n.id for n in ast.walk(node.target) if isinstance(n, ast.Name))
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                names.add(alias.asname or alias.name.split(".")[0])
        elif isinstance(node, ast.Try):
            for sub in ast.walk(node):
                if isinstance(sub, (ast.Import, ast.ImportFrom)):
                    for alias in sub.names:
                        names.add(alias.asname or alias.name.split(".")[0])
                if isinstance(sub, ast.Assign):
                    for target in sub.targets:
                        names.update(n.id for n in ast.walk(target)
                                     if isinstance(n, ast.Name))
    return names


def _function(tree: ast.Module, cls_name: str, fn_name: str):
    cls = next(node for node in tree.body
               if isinstance(node, ast.ClassDef) and node.name == cls_name)
    return next(node for node in cls.body
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                and node.name == fn_name)


def _unresolved(fn, available: set[str]) -> list[str]:
    """Globals the function loads that nothing in `available` provides."""
    local = {a.arg for a in ast.walk(fn) if isinstance(a, ast.arg)}
    for node in ast.walk(fn):
        # A nested def binds its NAME in the enclosing scope, and its own args
        # inside its own body. Both are locals here; neither is a module global.
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            local.add(node.name)
            local.update(a.arg for a in node.args.args + node.args.kwonlyargs)
        if isinstance(node, (ast.Lambda,)):
            local.update(a.arg for a in node.args.args + node.args.kwonlyargs)
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            local.add(node.id)
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                local.add(alias.asname or alias.name.split(".")[0])
        if isinstance(node, (ast.ExceptHandler, ast.comprehension)):
            if isinstance(node, ast.ExceptHandler) and node.name:
                local.add(node.name)
        if isinstance(node, (ast.With, ast.AsyncWith)):
            for item in node.items:
                if item.optional_vars is not None:
                    local.update(n.id for n in ast.walk(item.optional_vars)
                                 if isinstance(n, ast.Name))
    loaded = {n.id for n in ast.walk(fn) if isinstance(n, ast.Name)
              and isinstance(n.ctx, ast.Load)}
    builtin_names = set(dir(builtins))
    return sorted(loaded - local - available - builtin_names)


def test_execute_tool_reads_no_undefined_global():
    tree = ast.parse(MAIN.read_text(encoding="utf-8"))
    fn = _function(tree, "JarvisLive", "_execute_tool")
    missing = _unresolved(fn, _module_bindings(tree))
    assert missing == [], (
        "`_execute_tool` loads names main.py does not define. On a live session "
        "the surrounding `except Exception` turns this into a tool result the "
        "model reads out loud, so it must never reach a deploy:\n  "
        + "\n  ".join(missing))


def test_the_check_would_catch_a_typo():
    """Guard on the guard: it must actually fail on an undefined name."""
    fake = ast.parse(
        "import os\n"
        "def f(self, x):\n"
        "    return os.getcwd() + str(x) + missing_thing\n"
    )
    fn = next(n for n in ast.walk(fake) if isinstance(n, ast.FunctionDef))
    assert _unresolved(fn, _module_bindings(fake)) == ["missing_thing"]
