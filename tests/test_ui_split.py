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
UI_PKG = ROOT / "ui"
WINDOW = UI_PKG / "window.py"

# Two ceilings, not targets. They exist so "just add it here" costs a
# conversation: both files may shrink freely and grow a little, but not back to
# the sizes that made them unreadable.
WINDOW_CEILING = 7_300
MODULES = [UI_PKG / "__init__.py", UI_PKG / "theme.py", UI_PKG / "metrics.py"]


def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def test_ui_is_a_package_not_a_file():
    """`ui.py` beside `ui/` is the trap that broke CI on the first attempt.

    Python resolves the DIRECTORY first, so `ui.py` is shadowed — without an
    error at import time of the package, and every `from ui.theme import ...`
    inside the shadowed file then fails with "ui is not a package". One of the
    two has to not exist.
    """
    assert not (ROOT / "ui.py").exists(), (
        "ui.py must not be recreated: it shadows the ui/ package"
    )
    assert (UI_PKG / "__init__.py").exists()


def test_the_window_does_not_grow_back():
    lines = len(WINDOW.read_text(encoding="utf-8").splitlines())
    assert lines <= WINDOW_CEILING, (
        f"ui/window.py is {lines} lines (ceiling {WINDOW_CEILING}). "
        "Put new widgets in a module of their own — see ui/theme.py for the shape."
    )


def test_every_ui_module_stays_readable():
    """A 7,000-line module is the thing this split exists to prevent.

    The ceiling is per-module and generous, so it does not dictate design — it
    only refuses the one outcome that has already happened once here.
    """
    big = {p.name: n for p in MODULES
           if (n := len(p.read_text(encoding="utf-8").splitlines())) > 1_000}
    assert big == {}, f"modules over 1,000 lines: {big}"


def test_only_the_theme_module_defines_the_palette():
    """`class C` is rebound at runtime by apply_ui_accent.

    Two definitions of it (or a second module assigning to `C`) is how a theme
    change ends up applying to half the window: the widgets that imported the
    other class keep the old colours and nothing raises.
    """
    definers = [
        p for p in sorted(UI_PKG.glob("*.py"))
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
    for node in ast.walk(_tree(UI_PKG / "__init__.py")):
        if isinstance(node, ast.ImportFrom) and node.module in {"ui.theme", "ui.window"}:
            imported |= {a.name for a in node.names}
    assert {"C", "qcol", "apply_ui_accent", "current_palette"} <= imported
    assert "*" in imported, "the whole window is re-exported, unchanged"


def test_the_moved_pieces_are_gone_from_ui_py():
    """Copies are worse than either half being in the wrong file.

    If `class _SysMetrics` reappears in ui.py, two sampler threads start and the
    numbers are read from whichever one registered a timer last.
    """
    tree = _tree(WINDOW)
    names = {n.name for n in tree.body if isinstance(n, (ast.ClassDef, ast.FunctionDef))}
    assert "_SysMetrics" not in names
    assert "apply_ui_accent" not in names
    assert "retheme_all_widgets" not in names


def test_no_ui_module_outside_the_theme_writes_to_the_palette():
    """Assigning `C.X = ...` outside ui/theme.py is a theme that half-applies."""
    offenders = []
    for path in sorted(UI_PKG.glob("*.py")):
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
