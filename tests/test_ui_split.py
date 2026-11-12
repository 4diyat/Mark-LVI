"""The window's structure: one owner per job, and no file that nobody can hold.

WHY THIS IS A TEST AND NOT A NOTE IN A DOCUMENT
    `ui.py` reached 7,504 lines with 36 top-level classes, and the cost was not
    theoretical: the palette was read in one file by everyone, the accent code
    that REBINDS it lived 100 lines away from the class that defines it, and
    nothing could be checked without a display. The split is only worth doing if
    it stays done — so the ownership rules are asserted here, cheaply, from the
    source, on machines with no Qt at all (which includes every CI runner).

    These are structural assertions on purpose. Importing `ui` needs a working
    Qt, which a headless machine does not have; AST does not.
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UI_PY = ROOT / "ui.py"
UI_PKG = ROOT / "ui"

# A ceiling, not a target. It exists so "just add it to ui.py" costs a
# conversation: the file is allowed to shrink freely and to grow a little, but
# not back to the size that made it unreadable.
UI_PY_CEILING = 7_300


def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def test_ui_py_does_not_grow_back():
    lines = len(UI_PY.read_text(encoding="utf-8").splitlines())
    assert lines <= UI_PY_CEILING, (
        f"ui.py is {lines} lines (ceiling {UI_PY_CEILING}). "
        "Put new widgets in ui/ and import them — see ui/theme.py for the shape."
    )


def test_only_the_theme_module_defines_the_palette():
    """`class C` is rebound at runtime by apply_ui_accent.

    Two definitions of it (or a second module assigning to `C`) is how a theme
    change ends up applying to half the window: the widgets that imported the
    other class keep the old colours and nothing raises.
    """
    definers = [
        p for p in [UI_PY, *UI_PKG.glob("*.py")]
        if any(isinstance(n, ast.ClassDef) and n.name == "C" for n in _tree(p).body)
    ]
    assert definers == [UI_PKG / "theme.py"]


def test_ui_py_re_exports_what_it_moved():
    """A split that breaks its callers is a rename, not a refactor.

    Plugins and main.py say `ui.C`, `ui.qcol`, `ui._metrics`. Those names have
    to keep resolving through `ui.py` — the assertion is on the import list,
    not on runtime, so it holds without Qt.
    """
    imported = set()
    for node in ast.walk(_tree(UI_PY)):
        if isinstance(node, ast.ImportFrom) and node.module in {"ui.theme", "ui.metrics"}:
            imported |= {a.name for a in node.names}
    assert {"C", "qcol", "apply_ui_accent", "current_palette"} <= imported
    assert {"_metrics", "_SysMetrics"} <= imported


def test_the_moved_pieces_are_gone_from_ui_py():
    """Copies are worse than either half being in the wrong file.

    If `class _SysMetrics` reappears in ui.py, two sampler threads start and the
    numbers are read from whichever one registered a timer last.
    """
    tree = _tree(UI_PY)
    names = {n.name for n in tree.body if isinstance(n, (ast.ClassDef, ast.FunctionDef))}
    assert "_SysMetrics" not in names
    assert "apply_ui_accent" not in names
    assert "retheme_all_widgets" not in names


def test_no_ui_module_outside_the_theme_writes_to_the_palette():
    """Assigning `C.X = ...` outside ui/theme.py is a theme that half-applies."""
    offenders = []
    for path in [UI_PY, *UI_PKG.glob("*.py")]:
        if path == UI_PKG / "theme.py":
            continue
        for node in ast.walk(_tree(path)):
            # C.PRI = "..."  and  setattr(C, "PRI", "...")
            if (isinstance(node, ast.Assign)
                    and isinstance(node.targets[0], ast.Attribute)
                    and isinstance(node.targets[0].value, ast.Name)
                    and node.targets[0].value.id == "C"):
                offenders.append(f"{path.name}:{node.lineno}")
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                    and node.func.id == "setattr" and len(node.args) > 1
                    and isinstance(node.args[0], ast.Name) and node.args[0].id == "C"):
                offenders.append(f"{path.name}:{node.lineno}")
    assert offenders == []
