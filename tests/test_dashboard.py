"""The dashboard layer: one board, entered on purpose, left with everything back.

WHAT THIS IS NOT
    "Floating widget" already exists here as a WINDOW (`core/floating.py`,
    `ui/floating_documents.py`). The macOS Dashboard is a PLACE: a single layer
    that shows the handful of things you glance at, and leaves with everything
    exactly where it was. The difference decides every rule below:

      * a window is always there, a layer exists only while you are in it;
      * a window can be behind another window; a layer is in front of
        everything this program owns;
      * a window may persist across launches, a layer must never;
      * a widget may be in the layer or in the workspace — never both.
"""
from __future__ import annotations

import ast
import importlib.util
import sys
import types
from pathlib import Path

from core import dashboard as db

ROOT = Path(__file__).resolve().parent.parent


# ── the catalogue is a decision, not a rule ───────────────────────────────

def test_the_catalogue_shows_things_you_glance_at():
    """A dashboard shows what you look at. Typing surfaces are refused, and the
    refusal is the interesting half of the feature."""
    assert "metrics" in db.DASHBOARD_WIDGETS
    assert "speech_caption" in db.DASHBOARD_WIDGETS
    for refused in ("conversation", "input_row", "drawer", "order_dialog",
                    "code_editor"):
        assert refused in db.NOT_ON_DASHBOARD, refused
        assert refused not in db.DASHBOARD_WIDGETS


def test_a_live_trade_confirmation_can_never_appear_on_the_board():
    """The single most important refusal: a dashboard must not be able to
    display, let alone accept, a LIVE acknowledgement."""
    decision = db.entry("order_dialog")
    assert decision.allowed is False
    assert "LIVE acknowledgement" in decision.reason


def test_an_unknown_widget_is_refused_with_a_sentence():
    """A plugin asking for a capability nobody reviewed must not get it by
    default."""
    decision = db.entry("some_plugin_window")
    assert decision.allowed is False
    assert "not a widget this program shows" in decision.reason


def test_every_refusal_explains_itself():
    """A greyed button with no reason is how a feature looks broken."""
    for name in db.NOT_ON_DASHBOARD:
        assert db.entry(name).reason, name
    assert db.entry("nonsense").reason


def test_the_catalogue_order_is_stable_across_launches():
    """A board that rearranges itself between launches is a board you have to
    re-find your things on."""
    assert db.catalogue() == db.catalogue()
    assert db.catalogue() == sorted(db.DASHBOARD_WIDGETS)


def test_every_catalogue_entry_has_a_tile_size():
    """Placing everything at one size is how a dashboard becomes a grid of
    clipped text; no size at all is a tile that cannot be placed."""
    for name in db.catalogue():
        assert name in db.TILE_SIZE, name
        columns, rows = db.TILE_SIZE[name]
        assert columns >= 1 and rows >= 1


# ── the layer: one home per widget ────────────────────────────────────────

def test_a_widget_cannot_be_in_both_places():
    """Two live surfaces for one thing is the bug this class exists to stop:
    two caption labels fed by one audio loop, two metric readers."""
    layer = db.Layer()
    layer.lift("metrics", slot=(10, 20, 100, 50))
    assert "metrics" in layer
    layer.dock("metrics")
    assert "metrics" not in layer


def test_lifting_twice_keeps_the_original_slot():
    """A second lift is a redraw, not a new home. Overwriting the slot is how a
    widget comes back in the wrong place."""
    layer = db.Layer()
    layer.lift("metrics", slot=(1, 2, 3, 4))
    layer.lift("metrics", slot=(9, 9, 9, 9))
    assert layer.slot_for("metrics") == (1, 2, 3, 4)


def test_docking_returns_the_slot_it_came_from():
    layer = db.Layer()
    layer.lift("speech_caption", slot=(5, 6, 7, 8))
    assert layer.dock("speech_caption") == (5, 6, 7, 8)


def test_docking_something_that_was_never_lifted_is_not_an_error():
    """Called from stop paths that can run more than once."""
    assert db.Layer().dock("metrics") is None


def test_a_refused_widget_is_never_recorded_as_lifted():
    layer = db.Layer()
    decision = layer.lift("conversation")
    assert decision.allowed is False
    assert len(layer) == 0, "a refused widget was recorded as being on the board"


def test_names_are_normalised():
    layer = db.Layer()
    layer.lift("  METRICS  ")
    assert layer.names() == ["metrics"]


# ── a partial request does not cancel the layer ───────────────────────────

def test_one_bad_name_does_not_lose_the_good_ones():
    """The user asked for three things and two can be shown. Refusing the whole
    request punishes them for a plugin they did not write."""
    shown, refused = db.plan(["metrics", "nonsense", "speech_caption"])
    assert [name for name, _ in shown] == ["metrics", "speech_caption"]
    assert len(refused) == 1


def test_an_inactive_plan_shows_nothing():
    assert db.plan(["metrics"], active=False) == ([], [])


def test_an_empty_request_shows_nothing_rather_than_everything():
    """Opening an empty board teaches the user the feature is broken, and
    substituting the whole catalogue is a surprise they did not ask for."""
    assert db.plan([]) == ([], [])


# ── leaving ───────────────────────────────────────────────────────────────

def test_every_way_out_has_a_sentence():
    """A dashboard you cannot leave is a modal trap. Each route is named so the
    log says which one happened instead of three silent code paths."""
    for key in ("escape", "toggle", "blur", "shutdown"):
        assert db.exit_reason(key) in db.EXITS.values()
    assert db.exit_reason("something else")


def test_a_layer_never_survives_a_restart():
    """A floating WINDOW may persist because it is a window. A layer is a MODE,
    and starting the app inside a mode the user did not choose this time is how
    a dashboard becomes something to escape from."""
    assert db.survives_restart() is False


# ── the Qt half, with Qt stubbed ──────────────────────────────────────────

class _Widget:
    """Enough of a QWidget to be re-parented, measured and dropped."""

    def __init__(self, geo=(1, 2, 30, 40)):
        self._geo = geo
        # Every move is recorded. Without this a test cannot tell "put back
        # where it was" from "never moved at all" — both leave the geometry at
        # the value it started with.
        self.moves = []
        self.shown = 0
        self.style = ""
        self.deleted = 0
        self._box = None

    def geometry(self):
        x, y, w, h = self._geo
        return types.SimpleNamespace(x=lambda: x, y=lambda: y,
                                     width=lambda: w, height=lambda: h)

    def setGeometry(self, *a):                        # noqa: N802
        self._geo = a
        self.moves.append(a)
    def setMinimumSize(self, *a): pass                # noqa: N802
    def setObjectName(self, *a): pass                 # noqa: N802
    def setStyleSheet(self, s): self.style = s        # noqa: N802
    def show(self): self.shown += 1                   # noqa: N802
    def hide(self): pass                              # noqa: N802
    def raise_(self): pass
    def deleteLater(self): self.deleted += 1          # noqa: N802
    def setWidgetResizable(self, *a): pass            # noqa: N802
    def setWidget(self, *a): pass                     # noqa: N802
    def setGeometry2(self, *a): pass


class _Layout:
    def __init__(self, *a, **k): self.items = []

    def setContentsMargins(self, *a): pass            # noqa: N802
    def setSpacing(self, *a): pass                    # noqa: N802
    def addWidget(self, *a): self.items.append(a)     # noqa: N802
    def count(self): return len(self.items)
    def takeAt(self, i):                              # noqa: N802
        return self.items.pop(i) if self.items else None


def _load(monkeypatch):
    """`ui.dashboard_layer` with Qt, the window and the theme stubbed."""
    qtcore = types.ModuleType("PyQt6.QtCore")
    qtwidgets = types.ModuleType("PyQt6.QtWidgets")
    class _Sized(_Widget):
        """The board and its scroll area are sized from the window."""

        def width(self):
            return 0

        def height(self):
            return 0

    for name in ("QScrollArea", "QWidget"):
        setattr(qtwidgets, name, _Sized)
    qtwidgets.QGridLayout = _Layout
    qtwidgets.QVBoxLayout = _Layout
    monkeypatch.setitem(sys.modules, "PyQt6.QtCore", qtcore)
    monkeypatch.setitem(sys.modules, "PyQt6.QtWidgets", qtwidgets)
    stub = types.ModuleType("ui")
    stub.__path__ = [str(ROOT / "ui")]
    monkeypatch.setitem(sys.modules, "ui", stub)
    spec = importlib.util.spec_from_file_location(
        "dashboard_layer_under_test", ROOT / "ui" / "dashboard_layer.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class _Window:
    """A window with a caption and a metrics reader, and a log."""

    def __init__(self):
        self._speech_caption = _Widget((100, 200, 300, 40))
        self._metrics = _Widget((10, 10, 80, 200))
        self.log = []
        self._w, self._h = 1280, 800

    def width(self): return self._w
    def height(self): return self._h

    def write_log(self, text): self.log.append(text)


def test_opening_the_board_borrows_the_real_widgets(monkeypatch):
    module = _load(monkeypatch)
    window = _Window()
    layer = module.attach(window)
    layer.show(["speech_caption", "metrics"])
    assert layer.open is True
    assert set(layer.tiles) == {"speech_caption", "metrics"}
    assert "Dashboard open" in " ".join(window.log)


def test_the_widgets_return_to_the_place_they_left(monkeypatch):
    """THE ONE THING A LAYER MUST GET RIGHT. A `QWidget` has one parent; the
    layout closes the gap while it is away, so the only record of where it was
    is the one taken before it moved."""
    module = _load(monkeypatch)
    window = _Window()
    layer = module.attach(window)
    layer.show(["speech_caption"])
    layer.hide("escape")
    assert layer.open is False
    # It must have been MOVED back, not merely left where it was: the board
    # took it out of its layout, and a widget that is never re-placed is one the
    # user has lost.
    assert window._speech_caption.moves == [(100, 200, 300, 40)]
    assert layer.tiles == {}


def test_escaping_a_closed_board_does_not_consume_the_key(monkeypatch):
    """An Escape swallowed in an ordinary window is an Escape the user presses
    again, harder."""
    module = _load(monkeypatch)
    layer = module.attach(_Window())
    assert layer.hide("escape") is False


def test_toggling_twice_leaves_the_board_closed(monkeypatch):
    module = _load(monkeypatch)
    layer = module.attach(_Window())
    layer.toggle(["metrics"])
    assert layer.open is True
    layer.toggle()
    assert layer.open is False


def test_a_board_with_nothing_to_show_does_not_open(monkeypatch):
    """An empty board teaches the user the feature is broken. Say so and stay
    closed."""
    module = _load(monkeypatch)
    window = _Window()
    layer = module.attach(window)
    refused = layer.show(["conversation"])
    assert layer.open is False
    assert refused, "the refusal was not reported"
    assert "Nothing on this machine" in " ".join(window.log)


def test_every_way_out_returns_the_widgets(monkeypatch):
    """Esc, the button and shutdown take the same path, because a layer that
    only tidies up on the polite exit eats the caption the first time the user
    alt-tabs."""
    module = _load(monkeypatch)
    for reason in ("escape", "toggle", "blur", "shutdown"):
        window = _Window()
        layer = module.attach(window)
        layer.show(["speech_caption"])
        layer.hide(reason)
        assert window._speech_caption.moves == [(100, 200, 300, 40)], reason


def test_closing_the_window_closes_the_layer(monkeypatch):
    """A layer is a mode: it must not outlive the window it covers."""
    module = _load(monkeypatch)
    window = _Window()
    layer = module.attach(window)
    layer.show(["metrics"])
    module.close(window)
    assert layer.open is False
    assert window._metrics.moves == [(10, 10, 80, 200)]


def test_closing_a_window_with_no_layer_is_not_an_error(monkeypatch):
    module = _load(monkeypatch)
    module.close(_Window())


def test_a_widget_that_is_not_there_is_reported_not_crashed(monkeypatch):
    """`camera_preview` has no plain widget: it is a self-positioning overlay.
    Lifting it would fight the code that moves it."""
    module = _load(monkeypatch)
    window = _Window()
    layer = module.attach(window)
    layer.show(["camera_preview", "metrics"])
    assert "camera_preview" not in layer.tiles
    assert "metrics" in layer.tiles
    assert "not available" in " ".join(window.log)


# ── the wiring ────────────────────────────────────────────────────────────

def test_the_window_keeps_its_ceiling():
    """The rule this whole repository runs on: a new widget gets a new module."""
    lines = (ROOT / "ui" / "window.py").read_text(encoding="utf-8").count("\n")
    assert lines <= 3800, f"ui/window.py is {lines} lines"


def test_the_window_only_wires_three_things():
    """build a row, route Esc, close on shutdown — and nothing else. Every
    decision is in the two modules this test also covers."""
    source = (ROOT / "ui" / "window.py").read_text(encoding="utf-8")
    assert "_dash_row.build(self, lay, _row)" in source
    assert "dashboard_row.escape(self)" in source
    assert "_dl.close(self)" in source
    # No layout, geometry or catalogue arithmetic in the window.
    tree = ast.parse(source)
    window_class = next(n for n in tree.body
                        if isinstance(n, ast.ClassDef) and n.name == "MainWindow")
    code = ast.unparse(ast.Module(body=window_class.body, type_ignores=[]))
    assert "BOARD_COLUMNS" not in code
    assert "DASHBOARD_WIDGETS" not in code


def test_the_layer_module_imports_only_the_rules_and_logging():
    """It needs Qt, but it must not reach into the window's own state — the
    widgets are borrowed through `getattr`, named in the catalogue."""
    source = (ROOT / "ui" / "dashboard_layer.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert imported <= {"__future__", "core", "PyQt6"}, imported


def test_the_rules_module_needs_no_display():
    source = (ROOT / "core" / "dashboard.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert imported <= {"__future__", "dataclasses"}, imported
