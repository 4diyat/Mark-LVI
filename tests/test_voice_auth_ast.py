"""Architectural promises of the voice gate, checked over the AST.

Three properties, each of the kind that fails silently if left to a reader:

  1. NO TOOL OR PLUGIN TOUCHES THE VOICEPRINT OR THE GATE. The voiceprint is
     biometric; a plugin that could read it (or flip the gate) would be a
     hole the size of the plugin system. The engine lives in `core/`, the
     store in `memory/`, and neither is reachable from `actions/` or
     `plugins/`.
  2. THE CORE ENGINE DOES NO I/O. `core/voice_auth.py` decides; it never
     writes files or reaches the network. Filesystem and network access are
     the store's job, and the store is the only writer.
  3. THE GATE IS NEVER ENABLED BY A PLUGIN. Enabling is a setting written
     by the owner-facing UI through `config_manager` — not a call any
     plugin can make.
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def _imports(tree: ast.Module) -> set[str]:
    """Every module name imported anywhere in the tree."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                names.add(a.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                names.add(node.module)
    return names


def _strings(tree: ast.Module) -> set[str]:
    """Every string literal in the tree (catches path mentions)."""
    vals: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            vals.add(node.value)
    return vals


def _tool_trees():
    """All loadable tool/plugin files: actions/*.py and plugins/*.py
    (leading-underscore helper modules are skipped by the loader, so they
    are not part of the surface being protected)."""
    files = []
    for folder in ("actions", "plugins"):
        for path in (ROOT / folder).glob("*.py"):
            if path.name.startswith("_"):
                continue
            files.append(path)
    return files


def test_no_tool_or_plugin_imports_the_voice_gate_or_store():
    forbidden = {"core.voice_auth", "memory.voiceprint_store",
                 "voiceprint_store", "voice_auth"}
    for path in _tool_trees():
        imports = _imports(_tree(path))
        offenders = sorted(imports & forbidden)
        assert not offenders, (
            f"{path.relative_to(ROOT)} imports {offenders} — tools and "
            "plugins cannot reach the voiceprint or the gate")


def test_no_tool_or_plugin_mentions_the_voiceprint_path():
    for path in _tool_trees():
        strings = _strings(_tree(path))
        offenders = {s for s in strings if "voiceprint" in s}
        assert not offenders, (
            f"{path.relative_to(ROOT)} mentions {offenders} — the voiceprint "
            "is not a tool's business")


def test_no_tool_or_plugin_can_flip_the_gate():
    for path in _tool_trees():
        tree = _tree(path)
        names = {n.id for n in ast.walk(tree) if isinstance(n, ast.Name)}
        attrs = {n.attr for n in ast.walk(tree)
                 if isinstance(n, ast.Attribute)}
        offenders = sorted(
            (names | attrs) &
            {"save_voice_auth_enabled", "get_voice_auth_enabled",
             "voice_auth_enabled"})
        assert not offenders, (
            f"{path.relative_to(ROOT)} can flip the voice gate via {offenders}")


def test_the_core_engine_does_no_filesystem_or_network_io():
    """The engine decides; the store owns the disk and nothing else touches
    the network. If `core/voice_auth.py` starts writing files or opening
    sockets, the boundary between policy and I/O is gone."""
    tree = _tree(ROOT / "core" / "voice_auth.py")
    banned_calls = {"write_text", "write_bytes", "unlink", "rmtree", "mkdir",
                    "rename", "replace", "open", "requests", "urlopen"}
    banned_imports = {"requests", "urllib.request", "socket", "http.client",
                      "ftplib", "smtplib"}
    imports = _imports(tree)
    offenders = sorted(imports & banned_imports)
    assert not offenders, offenders

    call_offenders = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in banned_calls:
                call_offenders.append(f"line {node.lineno}: {node.func.attr}()")
    assert not call_offenders, call_offenders


def test_the_store_is_the_only_module_that_writes_the_voiceprint_file():
    """The voiceprint file is written by exactly one module — the store. If
    another module learns to write it, the "one writer" promise is gone."""
    voiceprint_name = "voiceprint.json"
    writers: set[Path] = set()
    for path in list((ROOT / "core").glob("*.py")) + \
            list((ROOT / "memory").glob("*.py")) + \
            list((ROOT / "actions").glob("*.py")) + \
            list((ROOT / "plugins").glob("*.py")):
        tree = _tree(path)
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) \
                    and voiceprint_name in node.value:
                writers.add(path.relative_to(ROOT))
    # The store defines the path; nothing else may mention the filename.
    assert writers == {Path("memory/voiceprint_store.py")}, writers
