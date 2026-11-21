"""The four widgets that left `ui/window.py` in the fifth split.

WHY THIS FILE EXISTS
    `ui/window.py` reached its line ceiling with one line to spare, and the rule
    this repository settled on is "extract, never raise the ceiling". Four things
    in it were self-contained QWidgets — a metric bar, the file drop zone, the
    camera preview, the first-run setup panel — so they moved, verbatim, to
    `ui/metric_bar.py`, `ui/drop_zone.py`, `ui/camera_preview.py` and
    `ui/setup_overlay.py`.

    A move like that fails in three ways, and all three are cheap to check:

      * the old name stops resolving (`ui.SetupOverlay`, `ui.MetricBar`) —
        the window still imports it, and `__all__` still lists it;
      * a copy is left behind, so there are two classes called MetricBar and
        the window silently builds whichever the import order picked;
      * the new module imports BACK into the window, which is how a small
        widget starts dragging the session, the sampler and the log along.

    Two of those are AST checks — they run on a machine with no display, like
    every structural test here. The third is a real build of the three panels
    that need nothing but Qt, against the same stub the smoke test uses.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
UI_PKG = ROOT / "ui"
WINDOW = UI_PKG / "window.py"

MOVED = {
    "MetricBar": "metric_bar.py",
    "FileDropZone": "drop_zone.py",
    "_DropCanvas": "drop_zone.py",
    "_CameraPreview": "camera_preview.py",
    "SetupOverlay": "setup_overlay.py",
}
# The private names the window itself kept reaching for after the move.
HELPERS = ("_file_category", "_count_files", "_fmt_size", "_FILE_ICONS",
           "_EXT_TO_CAT", "_SKIP_DIRS")


def _classes(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {n.name for n in tree.body if isinstance(n, ast.ClassDef)}


def _top_level(path: Path) -> set[str]:
    """Every name defined at module level — classes, functions AND the module's
    constants, because `_FILE_ICONS` and friends moved with the zone."""
    names = set()
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            names |= {t.id for t in node.targets if isinstance(t, ast.Name)}
    return names


def test_the_widgets_are_gone_from_the_window():
    """Moved, not copied. Two `SetupOverlay`s is the bug this prevents."""
    still_there = _classes(WINDOW) & set(MOVED)
    assert still_there == set(), (
        f"{sorted(still_there)} are still defined in ui/window.py")


@pytest.mark.parametrize("name,module", sorted(MOVED.items()))
def test_each_widget_lives_in_its_own_module(name, module):
    assert name in _classes(UI_PKG / module), f"{name} is not in ui/{module}"


def test_the_window_still_hands_the_helpers_back():
    """`_on_file_selected` draws a file card too, and imports these from here.

    Moving the zone without the three helpers beside it would have meant either
    a second copy of `_fmt_size` or the window importing a widget for a format
    function. Neither is a split; both are a mess left behind.
    """
    dropped = _top_level(UI_PKG / "drop_zone.py")
    missing = [name for name in HELPERS if name not in dropped]
    assert missing == [], f"ui/drop_zone.py lost: {missing}"

    imported = set()
    for node in ast.walk(ast.parse(WINDOW.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom) and node.module == "ui.drop_zone":
            imported |= {a.name for a in node.names}
    assert set(HELPERS) <= imported, (
        "window.py no longer imports the file helpers; its own file card "
        f"would NameError. missing: {sorted(set(HELPERS) - imported)}")


@pytest.mark.parametrize("module", ["metric_bar.py", "drop_zone.py",
                                    "camera_preview.py", "setup_overlay.py"])
def test_no_moved_module_imports_back_into_the_window(module):
    """The cycle that made `_assistant_display` move down to core/.

    A widget that imports ui/window.py to get one name pulls in the session,
    the metrics sampler and the log, and `ui/__init__.py` imports the window
    first — so the import either explodes or works by luck of ordering.
    """
    tree = ast.parse((UI_PKG / module).read_text(encoding="utf-8"))
    back = [node.module for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
            and (node.module or "").startswith("ui.window")]
    names = [alias.name for node in ast.walk(tree) if isinstance(node, ast.Import)
             for alias in node.names if alias.name.startswith("ui.window")]
    assert back == [] and names == [], (
        f"ui/{module} imports back into the window: {back + names}")


def test_the_window_imports_them_rather_than_redefining_them():
    """The names the window (and therefore the package) still offers."""
    imported = set()
    for node in ast.walk(ast.parse(WINDOW.read_text(encoding="utf-8"))):
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("ui."):
            imported |= {a.name for a in node.names}
    assert set(MOVED) <= imported, (
        f"ui/window.py no longer imports: {sorted(set(MOVED) - imported)}")


@pytest.fixture()
def qt(monkeypatch):
    """The window-smoke Qt stub, installed and torn down like that file does."""
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "smoke_for_split5", ROOT / "tests" / "test_window_smoke.py")
    smoke = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(smoke)
    saved = {k: v for k, v in sys.modules.items()
             if k == "ui" or k.startswith("ui.")}
    sys.modules.update(smoke._install_qt())
    for name in [k for k in sys.modules if k == "ui" or k.startswith("ui.")]:
        sys.modules.pop(name, None)
    try:
        import ui
        yield ui
    finally:
        for name in list(sys.modules):
            if name == "ui" or name.startswith("ui."):
                sys.modules.pop(name, None)
        for name in list(sys.modules):
            if name.startswith("PyQt6"):
                sys.modules.pop(name, None)
        sys.modules.update(saved)


def test_the_package_still_offers_the_moved_widgets(qt):
    """`ui.MetricBar` and `ui.SetupOverlay` are what the rest of the code says.

    The star-import in `ui/__init__.py` only carries names in `__all__`, so a
    widget that moved without being imported back stops existing under `ui.`
    while everything that uses it through the window keeps working — a split
    that breaks half its callers.
    """
    ui = qt
    assert ui.MetricBar is not None
    assert ui.FileDropZone is not None
    assert ui.SetupOverlay is not None
    assert ui.MetricBar.__module__ == "ui.metric_bar"
    assert ui.FileDropZone.__module__ == "ui.drop_zone"
    assert ui.SetupOverlay.__module__ == "ui.setup_overlay"


def test_the_setup_panel_builds_itself_and_reports_a_choice(qt):
    """The class is now constructible alone — which it never was before.

    It used to be 600 lines into a file that imports QtMultimedia, the session
    and the whole window; a test could only read its source. Here it is built,
    its auto-detected OS is one of the three the buttons offer, and `_submit`
    refuses an empty key without emitting — the one branch that decides whether
    main.py's `while not self._win._ready` loop ever ends.
    """
    ui = qt
    overlay = ui.SetupOverlay(None)
    assert overlay._sel_os in ("windows", "mac", "linux")
    assert set(overlay._os_btns) == {"windows", "mac", "linux"}

    emitted = []
    overlay.done.connect(lambda *a: emitted.append(a))
    # The Qt stub is not a QLineEdit: `text()` and `styleSheet()` are the two
    # things `_submit` reads, and the real widget returns "" for both on a
    # fresh line edit. Substituting them here is cheaper than teaching the
    # shared stub about a widget only this test builds.
    overlay._key_input.text = lambda: "   "
    overlay._key_input.styleSheet = lambda: ""
    overlay._submit()
    assert emitted == [], "an empty key must not be submitted"


def test_the_drop_zone_starts_empty_and_can_be_cleared(qt):
    ui = qt
    zone = ui.FileDropZone(None)
    assert zone.current_file() is None
    zone._set_file(str(ROOT / "readme.md"))
    assert zone.current_file() == str(ROOT / "readme.md")
    zone.clear_file()
    assert zone.current_file() is None


def test_the_metric_bar_skips_an_unchanged_repaint(qt):
    """`set_value` is called on a timer; a repaint per tick is a real cost.

    The early return is the whole optimisation, so it is asserted directly: the
    same number and the same text must not trigger `update()`.
    """
    ui = qt
    bar = ui.MetricBar("CPU")
    updates = []
    bar.update = lambda *a: updates.append(1)
    bar.set_value(40, "40%")
    bar.set_value(40, "40%")
    assert updates == [1], "an unchanged value repainted the widget"
    bar.set_value(90, "90%")
    assert updates == [1, 1]
