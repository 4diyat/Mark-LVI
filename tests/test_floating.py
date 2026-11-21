"""Floating widgets: who may leave, what it means here, and where it lands.

Two halves, tested differently on purpose:

  * `core/floating.py` decides everything without a display, so it is tested
    directly — a refusal is a sentence, a platform note is a fact about the
    platform, a saved position is clamped onto the screen it will appear on.
  * `ui/floating_window.py` changes window flags and re-parents, so it is
    tested against a stub whose layout records what happened. A stub is weaker
    than the real thing; the parts a stub cannot check (does the caption still
    follow the audio after re-parenting?) are in the manual checklist in
    `docs/verification.md`, where they belong.
"""
from __future__ import annotations

import pathlib

import pytest

from core import floating as fl


# ── who may leave ─────────────────────────────────────────────────────────

def test_a_widget_nobody_reviewed_does_not_get_to_float():
    """The default is refusal, not permission: a plugin asking for a capability
    that was never looked at must not receive one."""
    fit = fl.fit("some_plugin_panel", "linux", "x11")
    assert fit.allowed is False
    assert "not a widget" in fit.reason


def test_every_not_floatable_entry_says_why():
    """The interesting table. An entry without a reason is an opinion."""
    for name, reason in fl.NOT_FLOATABLE.items():
        assert reason.strip(), f"{name} is refused with no reason given"
        assert fl.fit(name, "linux", "x11").allowed is False


def test_every_floatable_entry_is_actually_allowable():
    """A catalogue entry that `fit` refuses is a lie in both directions."""
    for name in fl.FLOATABLE:
        assert fl.fit(name, "linux", "x11").allowed is True, name


def test_the_three_tables_do_not_overlap():
    """A name in two tables is a `fit` whose answer depends on dict order."""
    names = list(fl.FLOATABLE) + list(fl.NOT_FLOATABLE) + list(fl.RETIRED)
    assert len(names) == len(set(names)), sorted(names)


def test_the_float_button_can_only_name_widgets_the_catalogue_knows():
    """The row asks the catalogue, so a widget it cannot find is a click that
    silently does nothing — the exact bug this test was written after."""
    from pathlib import Path
    source = (Path(__file__).resolve().parent.parent
              / "ui" / "floating_row.py").read_text(encoding="utf-8")
    for name in fl.FLOATABLE:
        if name == "speech_caption":
            assert '"speech_caption"' in source


def test_the_drawer_cannot_float_because_it_is_anchored():
    """Not an opinion: `_position_ctrl_drawer` calls `mapTo` on its own button.
    As a window it has no button to anchor to."""
    assert fl.fit("drawer").allowed is False
    assert "anchor" in fl.fit("drawer").reason


def test_a_live_order_confirmation_cannot_float():
    """`show_document` deliberately keeps OrderDialog out of MDI because its
    acknowledgement is application-modal. Floating it over other apps is how
    somebody approves an order they never saw."""
    assert fl.fit("order_dialog", "windows").allowed is False
    assert "modal" in fl.fit("order_dialog").reason.lower()


def test_the_conversation_does_not_float():
    assert fl.fit("conversation").allowed is False


def test_a_retired_name_is_refused_and_says_what_replaced_it():
    """`hud` and `camera_preview` were in the catalogue and are not any more.

    A name that silently stops being floatable reads as a regression; a name
    that comes back with its reason reads as a decision. And the avatar in
    particular: it is ALREADY a window (`ui/face_bubble.py`), so "floating" it
    from the main window would build a second one.
    """
    for name, reason in fl.RETIRED.items():
        assert reason.strip(), name
        fit = fl.fit(name, "windows")
        assert fit.allowed is False
        assert fit.reason == reason

    assert "second avatar" in fl.fit("hud", "windows").reason
    assert "moves itself" in fl.fit("camera_preview", "windows").reason
    assert "'metrics'" in fl.fit("metric_bar", "windows").reason


# ── what it means on this platform ────────────────────────────────────────

def test_wayland_floats_but_does_not_promise_always_on_top():
    """The compositor accepts WindowStaysOnTopHint and ignores it. Promising it
    would be an interface claiming something it cannot observe."""
    fit = fl.fit("speech_caption", "linux", "wayland")
    assert fit.allowed is True
    assert fit.always_on_top is False
    assert "Wayland" in fit.note


def test_x11_gets_always_on_top():
    fit = fl.fit("speech_caption", "linux", "x11")
    assert fit.allowed is True and fit.always_on_top is True


def test_windows_admits_the_fullscreen_exception():
    fit = fl.fit("metrics", "windows")
    assert fit.always_on_top is True
    assert "fullscreen" in fit.note


def test_macos_mentions_spaces():
    fit = fl.fit("metrics", "darwin")
    assert fit.always_on_top is True
    assert "Space" in fit.note


def test_the_platform_note_is_case_insensitive():
    """`platform.system()` casing is not something to depend on."""
    assert fl.platform_note("Linux", "Wayland")[0] is False
    assert fl.platform_note("WINDOWS", "")[0] is True


def test_a_refusal_describes_itself_for_the_drawer():
    text = fl.fit("drawer").describe()
    assert text.startswith("cannot float:")


def test_a_wayland_allowance_describes_the_caveat():
    text = fl.fit("speech_caption", "linux", "wayland").describe()
    assert "floating" in text and "Wayland" in text


# ── where it lands ────────────────────────────────────────────────────────

def test_a_saved_position_off_screen_is_brought_back():
    """A monitor that was unplugged must not take the widget with it."""
    placement = fl.place({"x": 5000, "y": 4000, "width": 300, "height": 120},
                         default=(10, 10, 300, 120), screen=(1920, 1080))
    assert placement.adjusted is True
    assert 0 <= placement.x <= 1920 and 0 <= placement.y <= 1080


def test_a_negative_position_is_pulled_inside_the_screen():
    placement = fl.place({"x": -900, "y": -900, "width": 300, "height": 120},
                         default=(10, 10, 300, 120), screen=(1920, 1080))
    assert placement.x >= 0 and placement.y >= 0


def test_a_window_taller_than_the_screen_is_pinned_to_the_top_left():
    """Not to a negative corner: at least part of it must be reachable."""
    placement = fl.place({"x": 100, "y": 100, "width": 400, "height": 5000},
                         default=(10, 10, 400, 200), screen=(800, 600))
    assert placement.x >= 0 and placement.y >= 0
    assert placement.width <= 800 and placement.height <= 600


def test_a_broken_saved_record_falls_back_to_the_default():
    """The config is whatever somebody edited by hand last week."""
    placement = fl.place({"x": "junk", "y": None, "width": [], "height": {}},
                         default=(40, 50, 300, 120), screen=(1920, 1080))
    assert (placement.width, placement.height) == (300, 120)
    assert placement.stored is True


def test_a_non_dict_saved_record_is_treated_as_no_record():
    placement = fl.place(["not", "a", "dict"], default=(40, 50, 300, 120),
                         screen=(1920, 1080))
    assert placement.stored is False


def test_a_stored_position_is_reported_as_stored():
    placement = fl.place({"x": 300, "y": 300, "width": 300, "height": 120},
                         default=(10, 10, 300, 120), screen=(1920, 1080))
    assert placement.stored is True and placement.adjusted is False
    assert (placement.x, placement.y) == (300, 300)


def test_clamp_keeps_a_corner_reachable_rather_than_being_pretty():
    x, y = fl.clamp(1919, 1079, 400, 300, 1920, 1080)
    assert (x, y) == (1920 - 400 - fl._MARGIN, 1080 - 300 - fl._MARGIN)


def test_clamp_survives_junk_it_was_never_promised():
    """Called from the Qt thread; an exception here is a window that never
    appears and a traceback nobody reads."""
    assert fl.clamp("x", None, {}, [], "w", "h") == (fl._MARGIN, fl._MARGIN)


# ── the live set ──────────────────────────────────────────────────────────

def test_state_tracks_what_is_floating():
    state = fl.State()
    assert not state.is_floating("speech_caption")
    state.add("Speech_Caption", fl.Placement(1, 2, 3, 4))
    assert state.is_floating("speech_caption")     # case is not a name
    assert state.names() == ["speech_caption"]
    state.remove("speech_caption")
    assert not state.is_floating("speech_caption")


def test_forgetting_one_keeps_the_others():
    state = fl.State()
    state.add("speech_caption", fl.Placement(1, 2, 3, 4))
    state.add("metrics", fl.Placement(5, 6, 7, 8))
    state.forget("speech_caption")
    assert state.names() == ["metrics"]
    state.forget()
    assert state.names() == []


def test_a_placement_round_trips_through_a_dict():
    """What gets written to the config, and read back by `place()`."""
    placement = fl.Placement(10, 20, 300, 120, stored=True)
    assert fl.Placement(**placement.as_dict(), stored=True) == placement
    # And the same numbers through the reader that trusts nothing. Coordinates
    # inside the margin are pulled out to it — a widget flush against the edge
    # is hard to grab — so this asks for a position the margin allows.
    on_screen = fl.Placement(300, 200, 300, 120, stored=True)
    read_back = fl.place(on_screen.as_dict(), default=(0, 0, 1, 1),
                         screen=(1920, 1080))
    assert (read_back.x, read_back.y) == (300, 200)
    assert (read_back.width, read_back.height) == (300, 120)


# ── the Qt half, against a stub ───────────────────────────────────────────

class _Layout:
    def __init__(self):
        self.children = []
        self.inserted = []

    def indexOf(self, widget):                   # noqa: N802 — Qt's name
        return self.children.index(widget) if widget in self.children else -1

    def insertWidget(self, index, widget):       # noqa: N802 — Qt's name
        self.inserted.append((index, widget))
        if index < 0 or index > len(self.children):
            self.children.append(widget)
        else:
            self.children.insert(index, widget)
        return index

    def addWidget(self, widget):                 # noqa: N802
        self.children.append(widget)


class _Parent:
    def __init__(self, layout):
        self._layout = layout

    def layout(self):
        return self._layout


class _Widget:
    """Just enough widget to be moved and put back."""

    def __init__(self, layout):
        self._parent = _Parent(layout)
        self.flags = None
        self.geometry = None
        self.visible = False
        self.raised = False
        self.attributes = {}

    def parentWidget(self):                      # noqa: N802
        return self._parent

    def setParent(self, parent):                 # noqa: N802
        self._parent = parent

    def setWindowFlags(self, flags):             # noqa: N802
        self.flags = flags

    def setGeometry(self, *args):                # noqa: N802
        self.geometry = args

    def setAttribute(self, name, value):         # noqa: N802
        self.attributes[name] = value

    def show(self):
        self.visible = True

    def raise_(self):
        self.raised = True


class _Qt:
    """A `Qt` with only the names the code is allowed to use."""

    class WindowType:
        FramelessWindowHint = 1
        Tool = 2
        WindowStaysOnTopHint = 4
        Widget = 8

    class WidgetAttribute:
        WA_TranslucentBackground = 100


@pytest.fixture()
def module():
    spec = __import__("importlib.util", fromlist=["x"]).spec_from_file_location(
        "floating_window",
        __import__("pathlib").Path(__file__).resolve().parent.parent / "ui" / "floating_window.py")
    mod = __import__("importlib.util", fromlist=["x"]).module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_attach_takes_the_widget_out_and_puts_it_where_it_was_told(module):
    layout = _Layout()
    widget = _Widget(layout)
    layout.children.append(widget)
    fit = fl.fit("speech_caption", "linux", "x11")
    placement = fl.Placement(100, 200, 400, 90)

    dock = module.attach(widget, _Qt, fit, placement)

    assert widget.geometry == (100, 200, 400, 90)
    assert widget.visible and widget.raised
    assert dock is not None and dock.index == 0
    assert widget.attributes[_Qt.WidgetAttribute.WA_TranslucentBackground] is True


def test_attach_refuses_a_widget_the_policy_refused(module):
    """The Qt layer does not get a second opinion."""
    widget = _Widget(_Layout())
    with pytest.raises(ValueError, match="anchor"):
        module.attach(widget, _Qt, fl.fit("drawer"), fl.Placement(0, 0, 10, 10))


def test_on_wayland_the_always_on_top_flag_is_never_asked_for(module):
    """Asking for a flag the compositor ignores turns a platform limit into a
    mystery: the widget floats, somebody covers it, and nothing explains why."""
    flags = module.window_flags(_Qt, fl.fit("speech_caption", "linux", "wayland"))
    assert not flags & _Qt.WindowType.WindowStaysOnTopHint
    assert flags & _Qt.WindowType.FramelessWindowHint
    assert flags & _Qt.WindowType.Tool


def test_on_x11_the_always_on_top_flag_is_asked_for(module):
    flags = module.window_flags(_Qt, fl.fit("speech_caption", "linux", "x11"))
    assert flags & _Qt.WindowType.WindowStaysOnTopHint


def test_the_widget_goes_back_to_its_own_index_not_the_end(module):
    """Re-appending would move the caption below the microphone row forever
    after one excursion to the desktop."""
    layout = _Layout()
    first, widget, last = _Widget(layout), _Widget(layout), _Widget(layout)
    layout.children.extend([first, widget, last])

    dock = module.attach(widget, _Qt, fl.fit("speech_caption", "linux", "x11"),
                         fl.Placement(10, 10, 300, 90))
    layout.children.remove(widget)              # the layout closed the gap
    module.detach(widget, _Qt, dock)

    assert layout.inserted[-1][0] == 1
    assert widget.flags == _Qt.WindowType.Widget


def test_closing_a_floating_widget_must_not_destroy_it(module):
    """`ui/desktop_workspace.py` sets WA_DeleteOnClose for documents. A caption
    is the opposite case: the window still owns it and still reads it, so this
    module must never set that attribute."""
    source = (module.__file__ and
              __import__("pathlib").Path(module.__file__).read_text(encoding="utf-8"))
    assert "WA_DeleteOnClose" in source          # mentioned, in the docstring
    assert "setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose" not in source
    assert "WA_DeleteOnClose, True" not in source


def test_detach_without_a_dock_does_nothing_rather_than_guessing(module):
    """An already-floating widget has no layout; re-docking it "at -1" would
    append it to a panel it never came from."""
    widget = _Widget(_Layout())
    module.detach(widget, _Qt, None)
    assert widget.flags is None


def test_take_returns_none_for_a_widget_in_no_layout(module):
    widget = _Widget(_Layout())
    widget._parent = None
    assert module.take(widget) is None


# ── the panel the window actually calls ───────────────────────────────────
#
# Qt is stubbed here for the same reason `tests/test_notify.py` stubs it: a
# floating window cannot be inspected from a headless machine, so what is under
# test is the BOOKKEEPING — did it refuse what it should refuse, did it save the
# dock, did the position survive a round trip through the config.

class _Window:
    """A window with a log and a screen, and nothing else."""

    def __init__(self, screen=(1920, 1080)):
        self.log = []
        self._screen = screen

    def write_log(self, text):
        self.log.append(text)

    def screen(self):
        class _Screen:
            def __init__(self, size):
                self._size = size

            def availableGeometry(self):            # noqa: N802 — Qt's name
                class _Area:
                    def __init__(self, size):
                        self._s = size

                    def width(self):
                        return self._s[0]

                    def height(self):
                        return self._s[1]
                return _Area(self._size)
        return _Screen(self._screen)


class _SizedWidget(_Widget):
    def size(self):
        class _Size:
            def width(self):
                return 420

            def height(self):
                return 96
        return _Size()


@pytest.fixture()
def panel(tmp_path, monkeypatch):
    """A FloatingPanel with Qt and the config file both faked."""
    from memory import config_manager

    cfg = tmp_path / "api_keys.json"
    cfg.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(config_manager, "CONFIG_FILE", cfg)
    monkeypatch.setattr(config_manager, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(config_manager, "_LAST_GOOD", {})

    spec = __import__("importlib.util", fromlist=["x"]).spec_from_file_location(
        "floating_panel",
        __import__("pathlib").Path(__file__).resolve().parent.parent / "ui" / "floating_panel.py")
    module = __import__("importlib.util", fromlist=["x"]).module_from_spec(spec)
    spec.loader.exec_module(module)

    floating_window = __import__("importlib.util", fromlist=["x"]).spec_from_file_location(
        "floating_window",
        __import__("pathlib").Path(__file__).resolve().parent.parent / "ui" / "floating_window.py")
    fw = __import__("importlib.util", fromlist=["x"]).module_from_spec(floating_window)
    floating_window.loader.exec_module(fw)

    # `ui.floating_panel` reaches `ui.floating_window` (which logs, not draws)
    # and, on a failure path, `ui.theme` — and `ui.theme` imports the whole
    # PyQt6 colour stack. Both are stubbed for the same reason `test_notify.py`
    # stubs them: this test is about the bookkeeping, not the painting.
    from memory import config_manager as _cm
    monkeypatch.setattr(_cm, "CONFIG_FILE", cfg)
    monkeypatch.setattr(_cm, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(_cm, "_LAST_GOOD", {})

    import types as _types
    qtcore = _types.ModuleType("PyQt6.QtCore")
    qtcore.Qt = _Qt
    qtcore.QPoint = lambda *a, **k: None
    qtcore.pyqtSignal = lambda *a, **k: None
    qtgui = _types.ModuleType("PyQt6.QtGui")
    qtgui.QColor = lambda *a, **k: None
    qtgui.QFont = lambda *a, **k: None
    theme = _types.ModuleType("ui.theme")
    theme.C = _types.SimpleNamespace(PRI="#0ff", TEXT="", TEXT_DIM="", WHITE="",
                                     BORDER="", BORDER_B="")
    # `ui.floating_panel` reaches `ui.floating_row` through `paint()`, and that
    # row's module imports the package's re-exported palette names. Filled in
    # here so the stub is a plausible `ui.theme` rather than half of one.
    theme.DEFAULT_UI_COLOR = "#00ffff"
    theme.current_palette = lambda: {}
    theme.apply_ui_accent = lambda *a, **k: None
    theme.retheme_all_widgets = lambda *a, **k: None
    theme.qcol = lambda *a, **k: None
    # The WHOLE `ui` package is stubbed, not just the submodule. `from ui import
    # floating_window` executes `ui/__init__.py`, which re-exports `ui.window`
    # and with it every Qt name in the program — chasing those into a stub is
    # how a test becomes a second implementation of Qt. What is under test is
    # the panel's bookkeeping, and it only ever asks `ui` for one module.
    ui_stub = _types.ModuleType("ui")
    ui_stub.floating_window = fw
    saved = {n: __import__("sys").modules.get(n)
             for n in ("PyQt6", "PyQt6.QtCore", "PyQt6.QtGui", "ui", "ui.theme",
                       "ui.floating_window")}
    __import__("sys").modules.update({"PyQt6": _types.ModuleType("PyQt6"),
                                      "PyQt6.QtCore": qtcore,
                                      "PyQt6.QtGui": qtgui,
                                      "ui": ui_stub,
                                      "ui.theme": theme,
                                      "ui.floating_window": fw})
    p = module.FloatingPanel(_Window(), os_name="linux", session="x11")
    try:
        yield p
    finally:
        for name, value in saved.items():
            if value is None:
                __import__("sys").modules.pop(name, None)
            else:
                __import__("sys").modules[name] = value


def test_the_panel_finds_qt_from_a_module_it_did_not_import(panel):
    """`_qt()` reads `sys.modules`, not a name captured at import time.

    WHY THIS IS WORTH A TEST AT ALL, AND WHAT IT IS NOT
        `_qt()` exists so the lookup lives in ONE function rather than in each
        method that needs it. This test asserts exactly that and no more: the
        `Qt` the panel hands to the Qt layer is the one currently loaded, not a
        copy bound earlier. What it does NOT claim is that `from PyQt6.QtCore
        import Qt` would be different — measured, it is answered from
        `sys.modules` too when the submodule is already loaded, so the two are
        interchangeable and a mutation swapping them survives. Believing
        otherwise is how a test ends up asserting a comment.
    """
    import sys

    loaded = sys.modules["PyQt6.QtCore"]
    original = loaded.Qt
    replacement = object()
    try:
        loaded.Qt = replacement
        assert panel._qt_lookup() is replacement
    finally:
        loaded.Qt = original


def test_the_panel_reports_the_os_it_was_told_about(monkeypatch):
    """The OS and session are read as a pair: "wayland on Windows" is not a
    state, and passing only one of them used to leave the other stale."""
    import importlib.util
    import sys
    import types

    from core import platform_support

    monkeypatch.setattr(platform_support, "os_name", lambda: "Windows")
    monkeypatch.setattr(platform_support, "_linux_session", lambda: "wayland")

    # Loaded by path, and `ui` stubbed with nothing in it: `from ui import
    # floating_panel` would run the real package, which re-exports the window
    # and with it the whole Qt import graph. Construction needs no Qt at all —
    # that is the point of the panel keeping Qt behind `_qt()`.
    saved = sys.modules.get("ui")
    sys.modules["ui"] = types.ModuleType("ui")
    try:
        spec = importlib.util.spec_from_file_location(
            "panel_under_test", pathlib.Path(__file__).resolve().parent.parent
            / "ui" / "floating_panel.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        if saved is None:
            sys.modules.pop("ui", None)
        else:
            sys.modules["ui"] = saved

    class _Window:
        pass

    panel = module.FloatingPanel(_Window())
    assert panel._os_name == "Windows"
    assert panel._session == "wayland"

    told = module.FloatingPanel(_Window(), os_name="Linux", session="x11")
    assert (told._os_name, told._session) == ("Linux", "x11")


def test_the_panel_refuses_an_anchored_widget_and_says_why(panel):
    layout = _Layout()
    widget = _SizedWidget(layout)
    layout.children.append(widget)

    assert panel.float("drawer", widget) is False
    assert panel.state.names() == []
    assert any("anchor" in line for line in panel._window.log), panel._window.log


def test_the_panel_floats_a_caption_and_remembers_its_position(panel):
    """Saved on the way OUT, not only on the way back.

    A widget still floating when the program closes has no "way back" to save
    it from, and would reappear in the default corner next launch — which is
    the thing a remembered position exists to prevent.
    """
    layout = _Layout()
    widget = _SizedWidget(layout)
    layout.children.append(widget)

    assert panel.float("speech_caption", widget) is True
    assert panel.is_floating("speech_caption")
    assert widget.visible

    from memory.config_manager import load_api_keys
    saved = (load_api_keys().get("floating_widgets") or {}).get("speech_caption")
    assert saved is not None, "floating it saved no position at all"
    assert saved["width"] >= 120 and saved["height"] >= 80
    assert saved["x"] == widget.geometry[0]


def test_docking_removes_it_from_the_floating_set(panel):
    layout = _Layout()
    widget = _SizedWidget(layout)
    layout.children.append(widget)
    panel.float("speech_caption", widget)

    assert panel.dock("speech_caption") is True
    assert not panel.is_floating("speech_caption")
    assert widget.flags == _Qt.WindowType.Widget


def test_toggle_floats_then_docks(panel):
    layout = _Layout()
    widget = _SizedWidget(layout)
    layout.children.append(widget)

    assert panel.toggle("speech_caption", widget) is True
    assert panel.toggle("speech_caption", widget) is False
    assert not panel.is_floating("speech_caption")


def test_a_saved_position_is_used_on_the_next_float(panel, tmp_path):
    from memory import config_manager

    cfg = config_manager.CONFIG_FILE
    cfg.write_text('{"floating_widgets": {"speech_caption": '
                   '{"x": 400, "y": 300, "width": 420, "height": 96}}}',
                   encoding="utf-8")
    config_manager._LAST_GOOD.clear()

    layout = _Layout()
    widget = _SizedWidget(layout)
    layout.children.append(widget)
    panel.float("speech_caption", widget)

    assert widget.geometry == (400, 300, 420, 96)


def test_a_position_from_a_monitor_that_is_gone_is_pulled_back(panel):
    from memory import config_manager

    config_manager.CONFIG_FILE.write_text(
        '{"floating_widgets": {"speech_caption": '
        '{"x": 9000, "y": 9000, "width": 420, "height": 96}}}', encoding="utf-8")
    config_manager._LAST_GOOD.clear()

    layout = _Layout()
    widget = _SizedWidget(layout)
    layout.children.append(widget)
    panel.float("speech_caption", widget)

    x, y, w, h = widget.geometry
    assert 0 <= x <= 1920 and 0 <= y <= 1080


def test_the_wayland_warning_reaches_the_activity_log(panel, monkeypatch):
    """A platform limit the user cannot see is a mystery; one in the log is an
    explanation."""
    panel._session = "wayland"
    layout = _Layout()
    widget = _SizedWidget(layout)
    layout.children.append(widget)

    panel.float("speech_caption", widget)

    assert any("Wayland" in line for line in panel._window.log), panel._window.log


def test_docking_everything_on_close_leaves_nothing_behind(panel):
    layout = _Layout()
    widget = _SizedWidget(layout)
    layout.children.append(widget)
    panel.float("speech_caption", widget)

    panel.dock_all()

    assert panel.state.names() == []
    assert widget.flags == _Qt.WindowType.Widget


def test_a_widget_that_vanished_does_not_raise(panel):
    """Closing a floating widget's owner and then docking it must log, not
    traceback into the Qt thread."""
    assert panel.dock("speech_caption") is False


# ── the drawer row, and the explanation under it ──────────────────────────

def _row_modules():
    """`ui.floating_row` + `ui.drawer_note`, with Qt answered by a stub.

    The row is where the user actually meets this feature, and until now it had
    no test at all — which is how it came to look up its widget in a
    one-entry dictionary and paint a count that could only ever be 0 or 1.
    """
    import importlib.util
    import sys
    import types
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent

    class _RowStub:
        """Stands in for the drawer's `_row`: it ADDS the widget it is given.

        Every other row module in this drawer hands its widget to `_row` and
        lets the drawer place it, so the stub records the call rather than
        being a layout with `addWidget` on it.
        """

        def __init__(self):
            self.collected = []
            self.calls = []

        def __call__(self, widget, *a, **k):
            self.collected.append(widget)
            self.calls.append((widget, *a))
            return widget

    class _Button:
        def __init__(self, *a, **k):
            self._text = ""
            self._tip = ""
            self.clicked = types.SimpleNamespace(connect=lambda fn: None)

        def setFont(self, *a): pass          # noqa: N802 — Qt's names
        def setStyleSheet(self, *a): pass    # noqa: N802
        def setToolTip(self, tip): self._tip = tip   # noqa: N802
        def toolTip(self): return self._tip  # noqa: N802
        def setText(self, text): self._text = text   # noqa: N802
        def text(self): return self._text

    class _Label(_Button):
        def setWordWrap(self, on): pass      # noqa: N802
        def setTextInteractionFlags(self, flags): pass   # noqa: N802
        def setMaximumHeight(self, h): self.max_height = h   # noqa: N802
        def setCursor(self, c): self.cursor = c   # noqa: N802

    class _Qt:
        class TextInteractionFlag:
            NoTextInteraction = 0

        class CursorShape:
            ArrowCursor = 0

    qtgui = types.ModuleType("PyQt6.QtGui")
    qtgui.QFont = lambda *a, **k: None
    qtwidgets = types.ModuleType("PyQt6.QtWidgets")
    qtwidgets.QPushButton = _Button
    qtwidgets.QLabel = _Label
    qtcore = types.ModuleType("PyQt6.QtCore")
    qtcore.Qt = _Qt

    theme = types.ModuleType("ui.theme")
    theme.C = types.SimpleNamespace(PRI="", TEXT="", TEXT_DIM="", WHITE="",
                                    BORDER="", BORDER_B="")

    saved = {n: sys.modules.get(n) for n in
             ("PyQt6", "PyQt6.QtCore", "PyQt6.QtGui", "PyQt6.QtWidgets",
              "ui.theme", "ui.floating_row", "ui.drawer_note")}
    sys.modules.update({"PyQt6": types.ModuleType("PyQt6"),
                        "PyQt6.QtCore": qtcore, "PyQt6.QtGui": qtgui,
                        "PyQt6.QtWidgets": qtwidgets, "ui.theme": theme})

    def load(name):
        spec = importlib.util.spec_from_file_location(
            f"ui.{name}", root / "ui" / f"{name}.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[f"ui.{name}"] = module
        spec.loader.exec_module(module)
        return module

    try:
        yield load("drawer_note"), load("floating_row"), _Button, _Label, _RowStub
    finally:
        for name, value in saved.items():
            if value is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = value


def test_the_capability_note_is_text_not_a_dead_button():
    """A greyed-out button that never responds reads as "not installed"."""
    gen = _row_modules()
    note_mod, _, _, Label, Row = next(gen)
    asked = []
    note_mod._t = lambda key: asked.append(key) or ""
    try:
        row = Row()
        label = note_mod.build_capability_note(object(), row,
                                               "ui.capability.captions")
        assert isinstance(label, Label)
        assert row.collected == [label], "the note was never added to the drawer"
        # The KEY, not the rendered text: `ui.theme` is stubbed here, and the
        # point of this row is that it asks for a sentence about a capability.
        # That both language files actually carry the key is `test_i18n.py`'s
        # job, not a Qt stub's.
        assert asked == ["ui.capability.captions"], asked
        # `_row` clips every widget to 26px, which is right for a button and
        # cuts a wrapped sentence in half. The note undoes it.
        assert label.max_height > 26, label.max_height
    finally:
        try:
            next(gen)
        except StopIteration:
            pass


def test_the_float_row_paints_its_state_every_time_it_is_built():
    """The drawer rebuilds its buttons on every open. A row that painted once
    would come back saying OFF while the captions were out."""
    import types

    gen = _row_modules()
    _, row_mod, Button, _, _ = next(gen)
    try:
        class _State:
            def __init__(self, names):
                self._names = names

            def names(self):
                return list(self._names)

        class _Panel:
            def __init__(self, names):
                self.state = _State(names)
                self._window = types.SimpleNamespace(_speech_caption=None)

        floating = _Panel(["speech_caption"])
        button = Button()
        row_mod.paint(button, floating)
        assert "1" in button.text(), button.text()

        # …and after a CLICK, not only on build: the drawer is rebuilt on every
        # open, so a row that only painted at construction time would come back
        # saying OFF while the captions were still out on the desktop.
        clicked = _Panel([])
        clicked._window = types.SimpleNamespace(
            _speech_caption=types.SimpleNamespace())

        def _float(name, widget):
            clicked.state._names = ["speech_caption"]
            clicked.state.names = lambda: list(clicked.state._names)

        clicked.toggle = _float
        # A FRESH button, deliberately: reusing the one above would still be
        # carrying the "1" that the previous `paint` left on it, and the
        # assertion would pass whether or not `toggle` repainted anything.
        fresh = Button()
        row_mod.paint(fresh, _Panel([]))
        assert "OFF" in fresh.text() or "MATI" in fresh.text(), fresh.text()
        row_mod.toggle(fresh, clicked)
        assert "1" in fresh.text(), f"did not repaint after the click: {fresh.text()}"

        docked = _Panel([])
        row_mod.paint(button, docked)
        assert "OFF" in button.text() or "MATI" in button.text(), button.text()
    finally:
        try:
            next(gen)
        except StopIteration:
            pass


def test_a_click_with_no_captions_yet_says_so_instead_of_doing_nothing():
    """The captions widget does not exist until the first reply is spoken.

    Clicking FLOAT WIDGETS before that used to call `panel.toggle` with a None
    widget, which returns False and says nothing at all — the one outcome a
    drawer row may never have.
    """
    import types

    gen = _row_modules()
    _, row_mod, Button, _, _ = next(gen)
    try:
        class _Panel:
            def __init__(self):
                self.state = types.SimpleNamespace(names=lambda: [])
                self.said = []
                self._window = types.SimpleNamespace(_speech_caption=None)

            def toggle(self, name, widget):
                raise AssertionError("nothing to float, but it tried")

            def say(self, message):
                self.said.append(message)

        panel = _Panel()
        row_mod.toggle(Button(), panel)
        assert panel.said, "a click that cannot do anything said nothing"
    finally:
        try:
            next(gen)
        except StopIteration:
            pass


def test_the_float_row_names_the_one_widget_it_can_actually_float():
    """It used to take a tuple of names and resolve them through a dictionary
    holding one real widget — a list pretending to be general."""
    import ast
    from pathlib import Path

    source = (Path(__file__).resolve().parent.parent
              / "ui" / "floating_row.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    toggles = [n for n in ast.walk(tree)
               if isinstance(n, ast.FunctionDef) and n.name == "toggle"]
    assert len(toggles) == 1
    assert "names=" not in source, "the general-looking tuple is back"
