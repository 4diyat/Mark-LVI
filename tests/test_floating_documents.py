"""Plugin documents that leave the workspace for the desktop.

Four things are worth testing here, and three of them are refusals:

  1. a manifest may ASK for a floating window and receives nothing;
  2. the order confirmation — the LIVE acknowledgement — never leaves;
  3. switching a plugin off takes its windows home through the document's own
     close veto, and stays ON when that veto refuses;
  4. recall puts the subwindow back into the MDI area in the state it left in,
     because a subwindow that is merely re-parented is a widget at 0,0.

Everything Qt is answered by a stub that records what happened; a stub is
weaker than the real thing, and the parts it cannot check (does the window
really appear above other apps) are in the manual checklist in
`docs/verification.md`.
"""
from __future__ import annotations

import importlib.util
import json
import sys
import types
from pathlib import Path

import pytest

from core import floating as fl
from core import plugin_manifest as pm

ROOT = Path(__file__).resolve().parent.parent


# ── 1. a manifest may ask; it never receives ──────────────────────────────

def _plugin(tmp_path, manifest: dict, source: str = "PLUGIN = {}\n"):
    py = tmp_path / "p.py"
    py.write_text(source, encoding="utf-8")
    payload = {"name": "p", "sha256": pm.sha256_of(py), **manifest}
    py.with_suffix(".json").write_text(json.dumps(payload), encoding="utf-8")
    return py


def test_a_manifest_may_say_it_would_rather_float(tmp_path):
    manifest = pm.verify(_plugin(tmp_path, {"window": "float"}), "p")
    assert manifest.ok
    assert manifest.window == "float"
    assert manifest.asks_to_float is True


def test_asking_to_float_is_not_a_problem_and_not_a_permission(tmp_path):
    """It must not fail the plugin — a description that can refuse a plugin is
    a permission with extra steps."""
    manifest = pm.verify(_plugin(tmp_path, {"window": "float"}), "p")
    assert manifest.problems == []
    assert "float" not in manifest.permissions
    assert not hasattr(manifest, "may_float") or not callable(
        getattr(manifest, "may_float", None))


def test_an_unknown_window_value_is_ignored_rather_than_refused(tmp_path):
    manifest = pm.verify(_plugin(tmp_path, {"window": "somewhere-or-other"}), "p")
    assert manifest.ok
    assert manifest.asks_to_float is False


def test_the_tooltip_the_log_gets_says_who_decides():
    hint = fl.plugin_hint("float")
    assert "only you can" in hint
    assert "CONTROLS" in hint


def test_a_manifest_that_asks_for_nothing_says_nothing():
    assert fl.plugin_hint("") == ""
    assert fl.plugin_hint("docked") != ""      # informative, still not an act


# ── 2. what may leave, and the one thing that never does ──────────────────

def test_the_order_confirmation_never_floats():
    fit = fl.fit_document("order_dialog", "windows")
    assert fit.allowed is False
    assert "LIVE acknowledgement" in fit.reason


def test_every_plugin_document_may_float():
    for kind in fl.PLUGIN_DOCUMENTS:
        assert fl.fit_document(kind, "linux", "x11").allowed is True, kind


def test_the_plugin_tables_do_not_overlap():
    names = list(fl.PLUGIN_DOCUMENTS) + list(fl.NOT_FLOATABLE_PLUGIN) + list(
        fl.PLUGIN_NEEDS_WORK)
    assert len(names) == len(set(names)), sorted(names)


def test_an_unknown_document_kind_is_allowed_and_says_so():
    """Refusing a plugin's window because a new `kind` string appeared would be
    a silent regression the day after this shipped."""
    fit = fl.fit_document("some_new_plugin", "linux", "x11")
    assert fit.allowed is True
    assert "not a document kind this build knows" in fit.note


def test_the_camera_window_is_not_a_document_and_says_why():
    fit = fl.fit_document("camera", "windows")
    assert fit.allowed is False
    assert "capture stream" in fit.reason


def test_wayland_says_it_cannot_promise_always_on_top_for_documents_too():
    fit = fl.fit_document("code_editor", "linux", "wayland")
    assert fit.allowed is True and fit.always_on_top is False
    assert "Wayland" in fit.note


# ── stubs ─────────────────────────────────────────────────────────────────

class _Signal:
    def connect(self, *_a, **_k):
        pass


class _Qt:
    class WindowType:
        FramelessWindowHint = 1
        WindowStaysOnTopHint = 2
        SubWindow = 4
        Widget = 8

    class WindowState:
        WindowNoState = 0


class _Sub:
    """A `QMdiSubWindow` that records everything done to it."""

    def __init__(self, mdi=None, width=800, height=600):
        self._mdi = mdi
        self._w, self._h = width, height
        self.flags = None
        self.state = None
        self.geometry_value = None
        self.shown = 0
        self.calls = []
        self._document = None
        self._max = False
        self._min = False

    # Qt's names
    def mdiArea(self):                                   # noqa: N802
        return self._mdi

    def setWindowFlags(self, flags):                     # noqa: N802
        self.flags = flags
        self.calls.append("setWindowFlags")

    def setWindowState(self, state):                     # noqa: N802
        self.state = state
        self.calls.append("setWindowState")

    def setGeometry(self, *a):                           # noqa: N802
        self.geometry_value = a if len(a) > 1 else a[0]
        self.calls.append("setGeometry")

    def geometry(self):
        return (10, 20, self._w, self._h)

    def width(self):
        return self._w

    def height(self):
        return self._h

    def show(self):
        self.shown += 1
        self.calls.append("show")

    def raise_(self):
        self.calls.append("raise_")

    def close(self):
        self.calls.append("close")

    def isMaximized(self):                               # noqa: N802
        return self._max

    def isMinimized(self):                               # noqa: N802
        return self._min

    def showMinimized(self):                             # noqa: N802
        self._min = True
        self.calls.append("showMinimized")

    def showMaximized(self):                             # noqa: N802
        self._max = True
        self.calls.append("showMaximized")

    def showNormal(self):                                # noqa: N802
        self.calls.append("showNormal")


class _Mdi:
    def __init__(self):
        self.removed = []
        self.added = []

    def removeSubWindow(self, sub):                      # noqa: N802
        self.removed.append(sub)

    def addSubWindow(self, sub):                         # noqa: N802
        self.added.append(sub)


def _load(name: str):
    """Load one `ui.*` module by path, with `ui` stubbed to nothing.

    `from ui import X` would run the real package, which re-exports the window
    and with it every Qt name in the program. The modules under test reach Qt
    through `sys.modules`, so the stub below is enough.
    """
    saved = sys.modules.get("ui")
    sys.modules["ui"] = types.ModuleType("ui")
    try:
        spec = importlib.util.spec_from_file_location(
            f"fl_{name}", ROOT / "ui" / f"{name}.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        if saved is None:
            sys.modules.pop("ui", None)
        else:
            sys.modules["ui"] = saved


@pytest.fixture()
def qt(monkeypatch):
    """`Qt` where `ui.floating_documents._qt()` looks for it."""
    core = sys.modules.get("PyQt6.QtCore")
    stubbed = core is None
    if stubbed:
        core = types.ModuleType("PyQt6.QtCore")
    original = getattr(core, "Qt", None)
    core.Qt = _Qt
    monkeypatch.setitem(sys.modules, "PyQt6.QtCore", core)
    yield _Qt
    if stubbed:
        sys.modules.pop("PyQt6.QtCore", None)
    else:
        core.Qt = original


# ── 3. detach and recall, against a recording subwindow ───────────────────

def test_floating_a_document_takes_it_out_of_the_mdi_area(qt):
    module = _load("floating_document")
    mdi = _Mdi()
    sub = _Sub(mdi)

    dock = module.detach(sub, _Qt, fl.fit_document("code_editor", "linux", "x11"),
                         fl.Placement(100, 120, 700, 500))

    assert mdi.removed == [sub], "the MDI area would still be managing it"
    assert sub.flags & _Qt.WindowType.FramelessWindowHint
    assert sub.flags & _Qt.WindowType.WindowStaysOnTopHint, "x11 honours it"
    assert sub.shown >= 1
    assert dock.mdi is mdi


def test_the_always_on_top_hint_is_only_asked_for_where_it_works(qt):
    module = _load("floating_document")
    sub = _Sub(_Mdi())
    module.detach(sub, _Qt, fl.fit_document("code_editor", "linux", "wayland"),
                  fl.Placement(0, 0, 400, 300))
    assert not sub.flags & _Qt.WindowType.WindowStaysOnTopHint


def test_a_maximised_subwindow_is_not_dragged_out_full_screen(qt):
    """The MDI area maximises its subwindows; on the desktop that is a window
    with no title bar and no obvious way back."""
    module = _load("floating_document")
    sub = _Sub(_Mdi())
    module.detach(sub, _Qt, fl.fit_document("code_editor", "linux", "x11"),
                  fl.Placement(0, 0, 400, 300))
    assert sub.state == _Qt.WindowState.WindowNoState


def test_recalling_re_adds_it_to_the_mdi_area(qt):
    """A subwindow that is merely re-parented is a child widget at 0,0 with no
    title bar — `addSubWindow` is what makes it a window again."""
    module = _load("floating_document")
    mdi = _Mdi()
    sub = _Sub(mdi)
    dock = module.detach(sub, _Qt, fl.fit_document("code_editor", "linux", "x11"),
                         fl.Placement(0, 0, 400, 300))

    module.recall(sub, _Qt, dock)

    assert mdi.added == [sub]
    assert sub.flags == _Qt.WindowType.SubWindow
    assert sub.geometry_value == (10, 20, 800, 600), "geometry was not restored"


def test_recall_gives_back_the_maximised_state_it_found(qt):
    module = _load("floating_document")
    sub = _Sub(_Mdi())
    sub._max = True
    dock = module.detach(sub, _Qt, fl.fit_document("code_editor", "linux", "x11"),
                         fl.Placement(0, 0, 400, 300))
    sub._max = False

    module.recall(sub, _Qt, dock)

    assert "showMaximized" in sub.calls


def test_recall_is_safe_with_nothing_to_recall():
    """Called from close paths that may run twice."""
    module = _load("floating_document")
    module.recall(_Sub(None), _Qt, None)


def test_detach_refuses_what_the_policy_refused():
    module = _load("floating_document")
    with pytest.raises(ValueError):
        module.detach(_Sub(_Mdi()), _Qt, fl.fit_document("order_dialog"), None)


# ── the panel: bookkeeping, saving, and the revoke path ───────────────────

class _Window:
    def __init__(self):
        self.log = []

    def write_log(self, line):
        self.log.append(line)


@pytest.fixture()
def docs(qt, monkeypatch, tmp_path):
    from memory import config_manager as cm
    cfg = tmp_path / "api_keys.json"
    cfg.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(cm, "CONFIG_FILE", cfg)
    monkeypatch.setattr(cm, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(cm, "_LAST_GOOD", {})

    # Both modules, loaded with `ui` stubbed, and the stub KEPT for the whole
    # test: the panel does `from ui import floating_document` at CALL time, so a
    # stub removed after loading makes every float fail with whatever the real
    # `PyQt6` does — in a container without `libxkbcommon`, an ImportError.
    stub = types.ModuleType("ui")
    saved = sys.modules.get("ui")
    sys.modules["ui"] = stub
    try:
        documents = _load("floating_documents")
        stub.floating_document = _load("floating_document")
        stub.floating_documents = documents
    finally:
        if saved is None:
            sys.modules.pop("ui", None)
        else:
            sys.modules["ui"] = saved
    monkeypatch.setitem(sys.modules, "ui", stub)
    return documents.FloatingDocuments(_Window(), os_name="linux", session="x11"), documents, cfg


def test_floating_a_document_remembers_where_it_went(docs):
    panel, _, cfg = docs
    sub = _Sub(_Mdi())

    assert panel.float("doc-1", sub, "code_editor") is True
    assert panel.count() == 1

    saved = json.loads(cfg.read_text(encoding="utf-8"))
    assert "doc-1" in saved["floating_documents"]


def test_the_order_dialog_is_refused_and_the_user_is_told(docs):
    panel, module, _ = docs
    sub = _Sub(_Mdi())

    assert panel.float("doc-1", sub, "order_dialog") is False
    assert panel.count() == 0
    assert any("LIVE acknowledgement" in line for line in panel._window.log)


def test_floating_the_same_document_twice_is_not_an_error(docs):
    panel, _, _ = docs
    sub = _Sub(_Mdi())
    panel.float("doc-1", sub, "code_editor")
    assert panel.float("doc-1", sub, "code_editor") is True
    assert panel.count() == 1


def test_toggle_floats_and_then_brings_back(docs):
    panel, _, _ = docs
    sub = _Sub(_Mdi())
    assert panel.toggle("doc-1", sub, "code_editor") is True
    assert panel.count() == 1
    assert panel.toggle("doc-1", sub, "code_editor") is False
    assert panel.count() == 0


# ── the revoke path ───────────────────────────────────────────────────────

class _Document:
    def __init__(self, may_close=True):
        self.may_close = may_close
        self.closed = 0

    def close(self):
        self.closed += 1
        return self.may_close


def test_switching_a_plugin_off_takes_its_windows_home(docs):
    panel, _, _ = docs
    sub = _Sub(_Mdi())
    sub._document = _Document()
    panel.float("doc-1", sub, "code_editor", plugin="weather")

    assert panel.forget_plugin("weather") is True

    assert panel.count() == 0
    assert sub._document.closed == 1, "the veto was bypassed"


def test_unsaved_work_stops_the_plugin_being_switched_off(docs):
    """Removing a plugin whose window is still up leaves a panel the user can
    see and cannot account for; destroying the work to avoid that is worse."""
    panel, _, _ = docs
    sub = _Sub(_Mdi())
    sub._document = _Document(may_close=False)
    panel.float("doc-1", sub, "code_editor", plugin="weather")

    assert panel.forget_plugin("weather") is False
    assert panel.count() == 1
    assert any("unsaved work" in line for line in panel._window.log)


def test_one_plugins_windows_do_not_touch_another_plugins(docs):
    panel, _, _ = docs
    mine, theirs = _Sub(_Mdi()), _Sub(_Mdi())
    mine._document, theirs._document = _Document(), _Document()
    panel.float("doc-1", mine, "code_editor", plugin="weather")
    panel.float("doc-2", theirs, "trading", plugin="stocks")

    panel.forget_plugin("weather")

    assert panel.names() == ["doc-2"]


def test_the_window_hook_is_a_real_method():
    """Bound with `_recall_floating_plugin = toggle_hook()` inside the class,
    the returned function receives `self`. A version written without `self`
    would raise TypeError on the first click, and only on a machine where a
    plugin actually had a floating window."""
    module = _load("floating_documents")
    hook = module.toggle_hook()
    assert hook.__code__.co_varnames[:2] == ("self", "name")


def test_the_hook_returns_true_when_the_window_has_no_floating_panel():
    """The plugin manager overlay is also built by `tools/`, where there is no
    window to ask. Nothing to bring home is success, not failure."""
    module = _load("floating_documents")

    class _Bare:
        pass

    assert module.return_before_disabling(_Bare(), "weather") is True


# ── the drawer row ────────────────────────────────────────────────────────

def _isolate_config(monkeypatch, tmp_path):
    """Point the config at a temp file. Every test that FLOATS anything needs
    this: `_remember` writes the position through `config_manager`, and one of
    these tests once wrote `floating_documents` into the repository's real
    `config/api_keys.json` — caught by `git status`, not by a test."""
    from memory import config_manager as cm
    cfg = tmp_path / "api_keys.json"
    cfg.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(cm, "CONFIG_FILE", cfg)
    monkeypatch.setattr(cm, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(cm, "_LAST_GOOD", {})
    return cfg


def _row_modules():
    """`ui.floating_documents_row`, with Qt and the theme answered by stubs."""
    qtgui = types.ModuleType("PyQt6.QtGui")
    qtgui.QFont = lambda *a, **k: None
    qtwidgets = types.ModuleType("PyQt6.QtWidgets")

    class _Button:
        def __init__(self, *a, **k):
            self._text = ""
            self._tip = ""
            self._enabled = True
            self.clicked = types.SimpleNamespace(connect=lambda fn: None)

        def setFont(self, *a): pass           # noqa: N802
        def setStyleSheet(self, *a): pass     # noqa: N802
        def setEnabled(self, on): self._enabled = on   # noqa: N802
        def setToolTip(self, tip): self._tip = tip     # noqa: N802
        def setText(self, text): self._text = text     # noqa: N802
        def text(self): return self._text

    qtwidgets.QPushButton = _Button
    theme = types.ModuleType("ui.theme")
    theme.C = types.SimpleNamespace(PRI="", TEXT="", TEXT_DIM="", WHITE="",
                                    BORDER="", BORDER_B="")
    qtcore = types.ModuleType("PyQt6.QtCore")
    qtcore.Qt = _Qt                          # the panel reads it at call time
    stub = types.ModuleType("ui")
    stub.__path__ = [str(ROOT / "ui")]      # a package, so `ui.x` resolves
    saved = {n: sys.modules.get(n) for n in
             ("PyQt6", "PyQt6.QtCore", "PyQt6.QtGui", "PyQt6.QtWidgets",
              "ui", "ui.theme", "ui.floating_documents",
              "ui.floating_document")}
    sys.modules.update({"PyQt6": types.ModuleType("PyQt6"),
                        "PyQt6.QtCore": qtcore,
                        "PyQt6.QtGui": qtgui, "PyQt6.QtWidgets": qtwidgets,
                        "ui": stub, "ui.theme": theme})
    try:
        documents = _load("floating_documents")
        stub.floating_documents = documents
        stub.floating_document = _load("floating_document")
        sys.modules["ui.floating_documents"] = documents
        sys.modules["ui.floating_document"] = stub.floating_document
        spec = importlib.util.spec_from_file_location(
            "fl_row", ROOT / "ui" / "floating_documents_row.py")
        row = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(row)
        yield row, documents, _Button
    finally:
        for name, value in saved.items():
            if value is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = value


class _Host:
    def __init__(self, documents):
        self._workspace_documents = documents
        self.log = []

    def write_log(self, line):
        self.log.append(line)


def _sub(kind):
    return _Sub(_Mdi())


def test_the_row_only_offers_documents_that_may_float():
    gen = _row_modules()
    row, _, _ = next(gen)
    try:
        host = _Host({
            "doc-1": ("code_editor", _sub("code_editor")),
            "doc-2": ("order_dialog", _sub("order_dialog")),
            "doc-3": ("camera", _sub("camera")),
        })
        kinds = sorted(item[2] for item in row.candidates(host))
        assert kinds == ["camera", "code_editor", "order_dialog"], \
            "candidates() lists what is OPEN; the floatable filter is separate"

        floatable = [item[2] for item in row._floatable(host)]
        assert floatable == ["code_editor"], \
            "an order confirmation and a camera window were offered"
    finally:
        try:
            next(gen)
        except StopIteration:
            pass


def test_a_disabled_row_is_honest_about_having_nothing_to_do():
    gen = _row_modules()
    row, _, Button = next(gen)
    try:
        host = _Host({})
        button = Button()
        row.paint(button, host)
        assert button._enabled is False, "a live button whose only outcome is a log line"
    finally:
        try:
            next(gen)
        except StopIteration:
            pass


def test_the_row_counts_what_is_out_and_what_could_be():
    gen = _row_modules()
    row, documents, Button = next(gen)
    try:
        host = _Host({"doc-1": ("code_editor", _sub("code_editor"))})
        button = Button()
        row.paint(button, host)
        assert "1" in button.text(), button.text()
        assert button._enabled is True
        _ = documents
    finally:
        try:
            next(gen)
        except StopIteration:
            pass


def test_toggling_twice_returns_the_documents_home(monkeypatch, tmp_path):
    _isolate_config(monkeypatch, tmp_path)
    gen = _row_modules()
    row, _, Button = next(gen)
    try:
        sub = _sub("code_editor")
        host = _Host({"doc-1": ("code_editor", sub)})
        button = Button()

        assert row.toggle(button, host) == 1
        assert row.toggle(button, host) == 0
        assert sub.calls.count("show") >= 1
    finally:
        try:
            next(gen)
        except StopIteration:
            pass


def test_pressing_it_with_nothing_open_says_so():
    gen = _row_modules()
    row, _, Button = next(gen)
    try:
        host = _Host({})
        row.toggle(Button(), host)
        assert any("No tool window is open" in line or line for line in host.log), \
            "a press that cannot do anything said nothing"
    finally:
        try:
            next(gen)
        except StopIteration:
            pass


# ── the plugin manager's side ─────────────────────────────────────────────

def test_the_plugin_manager_asks_the_window_before_switching_off():
    """Read as an AST rather than as text: the call has to be in `_toggle`,
    before the save, or a plugin is switched off and then asked."""
    import ast

    tree = ast.parse((ROOT / "ui" / "overlays.py").read_text(encoding="utf-8"))
    toggle = [n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name == "_toggle"]
    assert len(toggle) == 1, "more than one _toggle: which one runs?"
    body = ast.dump(toggle[0])
    assert "_recall_floating" in body, \
        "a plugin can be switched off while its window is still on the desktop"

    # `save_plugin_enabled` is a plain name (imported inside the function), not
    # an attribute, so the order is read from the SOURCE lines of the two calls.
    lines = (ROOT / "ui" / "overlays.py").read_text(encoding="utf-8").splitlines()
    recall = next(i for i, line in enumerate(lines) if "_recall_floating(name)" in line)
    save = next(i for i, line in enumerate(lines) if "save_plugin_enabled(name, new_val)" in line)
    assert recall < save, "the recall happens after the plugin is already switched off"


def test_a_plugin_with_no_floating_windows_is_switched_off_normally():
    module = _load("floating_documents")

    class _Window:
        pass

    assert module.return_before_disabling(_Window(), "weather") is True
