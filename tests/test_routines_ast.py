"""Architectural promises of the routine scheduler, checked over the AST.

The routine list is user-created local data with a background thread firing
it, so the same boundary the voiceprint obeys applies here: the store in
`memory/` is the ONLY writer of the file, and no tool or plugin may reach
either the store, the scheduler, or the routine policy. A plugin that could
add or fire a routine would be a hole the size of the plugin system — a
scheduled command that runs without the owner ever asking for it.
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def _imports(tree: ast.Module) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                names.add(a.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names.add(node.module)
    return names


def _tool_trees():
    files = []
    for folder in ("actions", "plugins"):
        for path in (ROOT / folder).glob("*.py"):
            if path.name.startswith("_"):
                continue
            files.append(path)
    return files


def test_no_tool_or_plugin_imports_the_routine_store_or_scheduler():
    forbidden = {"memory.routine_store", "core.routine_scheduler",
                 "core.routines", "routine_store", "routine_scheduler",
                 "routines"}
    for path in _tool_trees():
        offenders = sorted(_imports(_tree(path)) & forbidden)
        assert not offenders, (
            f"{path.relative_to(ROOT)} imports {offenders} — tools and "
            "plugins cannot create, fire or remove a routine")


def test_no_tool_or_plugin_mentions_the_routines_path():
    for path in _tool_trees():
        strings = {n.value for n in ast.walk(_tree(path))
                   if isinstance(n, ast.Constant) and isinstance(n.value, str)}
        offenders = {s for s in strings if "routines.json" in s}
        assert not offenders, (
            f"{path.relative_to(ROOT)} mentions {offenders} — the routine "
            "list is not a tool's business")


def test_the_store_is_the_only_module_that_writes_the_routines_file():
    name = "routines.json"
    writers: set[Path] = set()
    for folder in ("core", "memory", "actions", "plugins"):
        for path in (ROOT / folder).glob("*.py"):
            tree = _tree(path)
            for node in ast.walk(tree):
                if isinstance(node, ast.Constant) and isinstance(node.value, str) \
                        and name in node.value:
                    writers.add(path.relative_to(ROOT))
    assert writers == {Path("memory/routine_store.py")}, writers


def test_the_scheduler_does_no_filesystem_or_network_io():
    """The scheduler owns the thread; the store owns the disk. If
    `core/routine_scheduler.py` starts writing files or opening sockets, the
    boundary between timing and I/O is gone."""
    tree = _tree(ROOT / "core" / "routine_scheduler.py")
    banned_calls = {"write_text", "write_bytes", "unlink", "rmtree", "mkdir",
                    "rename", "replace", "open", "requests", "urlopen"}
    banned_imports = {"requests", "urllib.request", "socket", "http.client",
                      "ftplib", "smtplib"}
    offenders = sorted(_imports(tree) & banned_imports)
    assert not offenders, offenders
    call_offenders = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in banned_calls:
                call_offenders.append(f"line {node.lineno}: {node.func.attr}()")
    assert not call_offenders, call_offenders
