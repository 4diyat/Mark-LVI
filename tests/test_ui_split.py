"""One owner per job, and no module that nobody can hold.

WHY THIS IS A TEST AND NOT A NOTE IN A DOCUMENT
    The old `ui.py` reached 7,504 lines with 36 top-level classes, and the cost
    was not theoretical: the palette was read in one file by everyone, the code
    that REBINDED it lived a hundred lines from the class that defined it, and
    nothing could be checked without a display.

    The design cut took that further in the other direction — from 64 modules to
    13 — so the rules below are the ones that keep a small package small. Every
    one is a structural assertion on purpose: importing `ui` needs a working Qt
    and a display, which a headless runner does not have; AST does not.

WHAT IS ASSERTED
    * the package is a package, not a file, and it has one public name;
    * every module stays under its ceiling, and the ceiling is real (a module
      that grows past it fails here, not in a code review);
    * a drawing module never imports the shell, and the shell never imports a
      surface — the dependency arrow points one way, so a surface cannot make
      the shell depend on Qt at import time;
    * the modules that were deleted stay deleted: no `ui/window.py`, no desktop
      workspace, nothing that needs a main window to be worth importing.
"""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UI_PKG = ROOT / "ui"

# Sixteen modules, and the ceiling is per module rather than per file: the old
# 3,800-line `window.py` ceiling was a ratchet, and a ratchet with one big
# bucket always ends up with one big file.
MODULE_CEILING = 600


def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _modules() -> list[Path]:
    return sorted(UI_PKG.glob("*.py"))


def test_ui_is_a_package_not_a_file():
    assert UI_PKG.is_dir(), "ui.py is back: the whole split was reverted"
    assert not (ROOT / "ui.py").exists()


def test_the_package_has_exactly_the_mockup_modules():
    """Sixty-four modules went; sixteen stayed. The list is the design."""
    expected = {
        "__init__.py", "ambient_shell.py", "command_bar.py", "confirm_banner.py",
        "face_bubble.py", "face_canvas.py", "lifecycle.py", "orb_overlay.py",
        "orb_paint.py", "shell.py", "theme.py", "toast_queue.py", "tray.py",
    }
    present = {p.name for p in _modules()}
    assert present == expected, (
        f"unexpected in ui/: {sorted(present - expected)}; "
        f"missing: {sorted(expected - present)}")


def test_every_module_stays_under_the_ceiling():
    """`MODULE_CEILING` exists so "just add it here" costs a conversation."""
    over = [(p.name, len(p.read_text(encoding="utf-8").splitlines()))
            for p in _modules()
            if len(p.read_text(encoding="utf-8").splitlines()) > MODULE_CEILING]
    assert over == [], f"past {MODULE_CEILING} lines: {over}"


def test_the_ceiling_can_actually_fail():
    """A ceiling nobody has approached is a number, not a rule.

    This asserts the measurement works — the previous version of this file
    compared a constant against itself and passed for a year.
    """
    assert len((UI_PKG / "lifecycle.py").read_text(encoding="utf-8").splitlines()) > 300


# ── the dependency arrow ──────────────────────────────────────────────────

# Modules that draw. They may import `ui.orb_paint`, `ui.theme` and Qt; they
# may not import the shell, because the shell is what DECIDES what to draw.
DRAWERS = ("orb_paint.py", "orb_overlay.py", "face_canvas.py", "command_bar.py",
           "confirm_banner.py", "toast_queue.py", "face_bubble.py", "tray.py")


def _imported(path: Path) -> set[str]:
    out = set()
    for node in ast.walk(_tree(path)):
        if isinstance(node, ast.ImportFrom) and node.module:
            out.add(node.module)
        elif isinstance(node, ast.Import):
            out.update(alias.name for alias in node.names)
    return out


def test_no_drawing_module_imports_the_shell():
    """THE RULE THAT KEEPS THE PACKAGE SMALL.

    `ui/shell.py` is the coordinator: it owns the surfaces and decides what
    each one is told. A drawer that imported it would close the cycle, and the
    first symptom is an `ImportError` on a machine with no display — which is
    every CI runner.
    """
    for name in DRAWERS:
        path = UI_PKG / name
        assert path.exists(), f"ui/{name} is gone"
        imported = _imported(path)
        bad = {m for m in imported if m in ("ui.shell", "ui.lifecycle")}
        assert not bad, f"ui/{name} imports {sorted(bad)}: the arrow points the wrong way"


def test_the_shell_does_not_import_a_surface_at_module_scope():
    """Surfaces are built lazily, inside the method that needs one.

    `ui/lifecycle.py` is the only module allowed to import them at the top,
    because it is the one that builds them — and it is imported only when the
    app starts, never by `import ui`.
    """
    tree = _tree(UI_PKG / "shell.py")
    top_level = set()
    for node in tree.body:
        if isinstance(node, ast.ImportFrom) and node.module:
            top_level.add(node.module)
        elif isinstance(node, ast.Import):
            top_level.update(alias.name for alias in node.names)
    surfaces = {"ui.orb_overlay", "ui.face_bubble", "ui.command_bar", "ui.tray",
                "ui.confirm_banner", "ui.toast_queue"}
    assert not (top_level & surfaces), (
        f"ui/shell.py imports {sorted(top_level & surfaces)} at module scope")


def test_the_package_init_does_not_import_the_surfaces():
    """`import ui` must work on a machine with no display.

    `ui/shell.py` is allowed and is the ONLY internal import: it holds
    `AmbientShell`, the name the rest of the program is written against, and it
    imports no widget — every surface is built lazily inside a method.
    """
    imported = _imported(UI_PKG / "__init__.py")
    allowed = {"ui.theme", "ui.shell"}
    assert not {m for m in imported if m.startswith("ui.") and m not in allowed}, (
        "ui/__init__.py pulls a surface in, so `import ui` needs a display")


# ── what was deleted stays deleted ────────────────────────────────────────

# Named individually rather than as a glob, because a glob answers "nothing
# matched" — the same result as a typo in the pattern.
DELETED = (
    "window.py", "desktop_workspace.py", "chat_log.py", "overlays.py",
    "providers_overlay.py", "hud_canvas.py", "hand_gesture.py", "image_editor.py",
    "code_editor.py", "ssh_manager.py", "trading_terminal.py", "workspace_browser.py",
    "floating_document.py", "dashboard_layer.py", "creative.py", "audio.py",
    "setup_overlay.py", "metrics.py", "icons.py", "camera_preview.py",
    "narrative_content.py", "visual_content.py", "localization.py",
)


def test_the_modules_that_needed_a_window_are_gone():
    """Not "unused" — absent. `docs/mockups/NOT-IN-MOCKUP.md` says how to get
    any of them back, and why each one went."""
    survivors = [name for name in DELETED if (UI_PKG / name).exists()]
    assert survivors == [], f"back from the dead: {survivors}"


def test_nothing_in_the_package_mentions_a_deleted_module():
    """A comment is fine; an IMPORT is not, because the import is what runs."""
    imports = set()
    for path in _modules():
        imports |= _imported(path)
    stale = sorted(m for m in imports if m.startswith("ui.")
                   and not (UI_PKG / (m.split(".")[-1] + ".py")).exists())
    assert stale == [], f"imports of deleted modules: {stale}"
