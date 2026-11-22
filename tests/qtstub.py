"""The Qt stand-in the whole suite borrows, in the shape PyQt6 really reports.

WHY THIS IS A CONFTEST MODULE AND NOT A TEST FILE
    It was the first 500 lines of `tests/test_window_smoke.py`, which built the
    window and is now deleted with the window. The stub is the valuable half and
    it is not about the window: `test_orb_overlay`, `test_orb_paint`,
    `test_face_bubble`, `test_command_bar` and others import PyQt6 names through
    it, because PyQt6 cannot be installed in this sandbox (libGL and
    libxkbcommon are absent and apt is blocked).

    So it moved here, and the tests that need it ask for it by name. A conftest
    module rather than a `_fixtures/` package: pytest imports `conftest` modules
    the same way for every test file, and an import of this module from a test
    file is a plain `from tests.qtstub import install_qt`.

WHY IT IS DELIBERATELY NARROW
    It was written from PyQt6's own `.pyi` stubs, not from the code that uses
    it. An earlier fake invented `QAudioDevice.fromId` because it was written
    from the call site — which made the fake agree with the bug it was supposed
    to catch. Any name this has to invent is a name the code really uses, and
    that is the property worth keeping.
"""
from __future__ import annotations

import sys
import types
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


WINDOW = ROOT / "ui" / "window.py"


# ── a Qt stand-in, in the shape PyQt6 actually reports ─────────────────────

class _Signal:
    """A pyqtSignal that can be connected and emitted from Python."""

    def __init__(self, *_types):
        self.slots = []

    def connect(self, fn):
        self.slots.append(fn)

    def disconnect(self, fn=None):
        if fn is None:
            self.slots.clear()
        elif fn in self.slots:
            self.slots.remove(fn)

    def emit(self, *args):
        for fn in list(self.slots):
            fn(*args)


class _Object:
    """Base for every stub widget: enough to be laid out and shown."""

    def __init__(self, *a, **k):
        # None means "never explicitly shown or hidden" — Qt's third state. A
        # child of a visible window is visible without having been shown itself,
        # and collapsing that to a boolean is how a visibility assertion ends up
        # testing the stub instead of the code.
        self._visible = None
        self._parent = a[0] if a and isinstance(a[0], _Object) else k.get("parent")
        self._layout = None
        self._text = ""
        # A positional string first argument is a widget's LABEL, as Qt reads
        # it (`QPushButton("Kirim", page)`, `QLabel("IZIN", page)`).
        if a and isinstance(a[0], str):
            self._text = a[0]
        self._style = ""
        self._enabled = True
        # Window flags are a bitmask in Qt and every floating surface ORs three
        # of them together. A stub that answered None made that OR a TypeError
        # which had nothing to do with the code under test.
        self._flags = 0
        # `QVBoxLayout(parent)` INSTALLS ITSELF, as Qt's does. The window relies
        # on that (`QVBoxLayout(self._content_panel)` with no setLayout), and a
        # stub that ignored it would make `panel.layout()` None — which is the
        # same shape as the bug this file exists to catch, for a different
        # reason.
        if a and isinstance(a[0], _Object):
            a[0].setLayout(self)

    # layout
    def setLayout(self, lay):
        self._layout = lay
        if isinstance(lay, _Layout):
            lay._set_owner(self)

    def layout(self):
        return self._layout

    def addWidget(self, w, *a, **k):
        # A widget container (QSplitter, QStackedWidget) reparents into itself.
        # ASSIGNING the parent is what makes the test meaningful: the audio bar
        # bug was a widget that was built and never added, and only a real
        # parenting chain can tell the difference between built and added.
        _reparent(w, self)

    def addLayout(self, *a, **k):
        pass

    def addStretch(self, *a, **k):
        pass

    def parentWidget(self):
        return self._parent

    def centralWidget(self):
        # `QMainWindow.centralWidget()` returns a widget whose parent IS the
        # window, which is what makes the parent walk in the test terminate.
        # Stored on the window, not built on every call: `setCentralWidget` has
        # to be able to replace it, and the window's layout is installed on it.
        if self.__dict__.get("_central") is None:
            self._central = _Object()
            _reparent(self._central, self)
        return self._central

    def setCentralWidget(self, w):
        self._central = w
        _reparent(w, self)

    def setWindowTitle(self, _t):
        pass

    # visibility — Qt's rule: a widget is visible only if it was shown AND every
    # ancestor was shown. Modelling it this way is what makes "shown inside a
    # hidden parent" detectable, which is the bug this file was written for.
    # window flags and placement
    def windowFlags(self):
        return self._flags

    def setWindowFlags(self, flags):
        # Qt's flags are an int already; the stub's `_Enum` OR returns itself,
        # and a `windowFlags()` that forgot to start at 0 gives None. Copying
        # the value without converting keeps both shapes working.
        self._flags = flags

    def parent(self):
        return self._parent

    def adjustSize(self):
        return None

    def move(self, *_a):
        return None

    def raise_(self):
        return None

    def activateWindow(self):
        return None

    def show(self):
        self._visible = True

    def hide(self):
        self._visible = False

    def setVisible(self, on):
        self._visible = bool(on)

    def isVisible(self):
        """Explicitly hidden anywhere in the chain wins; otherwise the topmost
        widget decides — which for the window means "was it shown"."""
        node, hops = self, 0
        while node is not None and hops < 40:
            parent = getattr(node, "_parent", None)
            state = getattr(node, "_visible", None)
            if state is False:
                return False
            if parent is None:
                return bool(state)
            node = parent
            hops += 1
        return True

    def isVisibleTo(self, _ancestor):
        return self.isVisible()

    # the rest, as no-ops that record what was asked
    def setText(self, t):
        self._text = t
        # `QPushButton("label", parent)` takes its text from the CONSTRUCTOR,
        # which Qt stores the same way `setText` does. The stub kept only the
        # argument-less case, so a panel built with `QPushButton(name, page)`
        # had every button reading back "". Real Qt does not behave that way
        # and a test that asserts button text must not pass on a stub quirk.
        if "text" in self.__dict__:
            self.__dict__.pop("text", None)

    def text(self):
        return self._text

    def setStyleSheet(self, s):
        self._style = s

    # The signals every widget really has. Set on the INSTANCE, because
    # `clicked` is looked up on the object in Python while `_Signal` on the class
    # would be shared by every button in the window.
    dataChanged = _Signal()
    destroyed = _Signal()
    finished = _Signal()
    activated_ = _Signal()
    clicked = _Signal()
    pressed = _Signal()
    toggled = _Signal()
    valueChanged = _Signal()
    currentIndexChanged = _Signal()
    textChanged = _Signal()
    returnPressed = _Signal()
    doubleClicked = _Signal()
    sliderReleased = _Signal()
    activated = _Signal()
    triggered = _Signal()
    timeout = _Signal()

    def style(self):
        return types.SimpleNamespace(standardIcon=lambda *_: _Object())

    def sizeHint(self):
        return self

    def width(self):
        return 980

    def height(self):
        return 700

    def document(self):
        # `QTextEdit.document()` returns a real object; the log viewer sets a
        # block limit on it.
        return _Object()

    # Checked / enabled are STATE, like visibility: a panel that draws a switch
    # reads both back, and a stub that always answered False made every toggle
    # look broken while the code was right. Same reason as `_visible`.
    def setCheckable(self, on):
        self._checkable = bool(on)

    def isChecked(self):
        return bool(self.__dict__.get("_checked", False))

    def setChecked(self, on):
        self._checked = bool(on)

    def setEnabled(self, on):
        self._enabled = bool(on)

    def isEnabled(self):
        return bool(self.__dict__.get("_enabled", True))

    def setPlaceholderText(self, text):
        self._placeholder_text = text

    def clear(self):
        self._text = ""

    def setFocus(self):
        self._focused = True

    def __getattr__(self, name):
        # A PRIVATE name is always real state, never a Qt convenience. Returning
        # a lambda for one turns a missing attribute into a silent wrong answer
        # — which is how this stub hid a bug of its own for a while.
        if name.startswith("_"):
            raise AttributeError(name)
        # A CAPITALISED name on a widget is a nested enum (`QFrame.Shape.NoFrame`,
        # `QGraphicsView.Shape.NoFrame`), not a method — Qt's own convention, and
        # the difference decides whether `QFrame.Shape.NoFrame` returns an enum
        # or a function.
        if name[:1].isupper():
            return _ENUMS
        return lambda *a, **k: None


def _reparent(widget, parent):
    """Move `widget` to `parent`, taking it out of its old one — as Qt does.

    Qt REPARENTS; it does not copy. That is the whole bug this models: the HUD
    stack was added to a wrapper and then added to the splitter, which moved it
    out of the wrapper and left the wrapper holding only the audio bar — and
    the wrapper was never added anywhere.
    """
    old = getattr(widget, "_parent", None)
    if old is not None and old is not parent:
        kids = old.__dict__.get("_children")
        if kids and widget in kids:
            kids.remove(widget)
    # A slotted stub has no `_parent`; that is the case this tolerates, and it
    # is a fixture rather than app code, so there is nothing to report.
    try:
        widget._parent = parent
    except AttributeError:
        return
    if parent is not None:
        children = parent.__dict__.setdefault("_children", [])
        if widget not in children:
            children.append(widget)


class _Layout(_Object):
    """A layout. In Qt a layout is not a widget, and `addWidget` reparents the
    widget to the layout's OWNER — so the chain runs widget -> panel -> splitter
    -> window and never through a layout."""

    def __init__(self, *a, **k):
        # Before `super()`, because `_Object.__init__` installs a layout on its
        # parent immediately and that calls `_set_owner`.
        self._owner = None
        self._pending = []
        super().__init__(*a, **k)
        owner = a[0] if a and isinstance(a[0], _Object) else k.get("parent")
        if owner is not None:
            self._set_owner(owner)

    def _set_owner(self, owner):
        """Become part of `owner`, and take everything already added with us.

        This is the behaviour that matters: `body = QHBoxLayout()` has no owner
        while widgets are added to it, and Qt only reparents them when the
        layout is finally installed on a widget (`root.addLayout(body)`). A stub
        that ignored this would leave every widget in the window parentless —
        and the test would fail for a reason that is the stub's fault.
        """
        self._owner = owner
        for item in self._pending:
            if isinstance(item, _Layout):
                item._set_owner(owner)
            else:
                _reparent(item, owner)
        self._pending = []

    def addWidget(self, w, *a, **k):
        if self._owner is None:
            self._pending.append(w)
        else:
            _reparent(w, self._owner)

    def addLayout(self, lay, *a, **k):
        if self._owner is None:
            self._pending.append(lay)
        else:
            lay._set_owner(self._owner)

    def parentWidget(self):
        return self._owner


class _Enums:
    """Any nested enum, to any depth, as an object that compares like a value."""

    def __getattr__(self, name):
        return self

    def __or__(self, _other):
        return self

    def __ror__(self, _other):
        return self

    def __eq__(self, _other):
        return False

    def __hash__(self):
        return 0


_ENUMS = _Enums()


class _Meta(type):
    """Class-level `__getattr__`: how `QFrame.Shape.NoFrame` resolves.

    `type(C)` must BE this class for its `__getattr__` to be consulted, so the
    type is created with the metaclass directly — subclassing `type(_Object)`
    and passing `metaclass=` produces `_MetaType`, whose metaclass is plain
    `type`, and Python then never asks.
    """

    def __getattr__(cls, name):
        if name.startswith("__"):
            raise AttributeError(name)
        if name[:1].isupper():
            return _ENUMS
        return lambda *a, **k: None


def _stub_class(name, base=None):
    """A widget class whose metaclass is `_Meta`, so `QFrame.Shape` resolves."""
    return _Meta(name, (base or _Object,), {})


class QMediaPlayer(_Object):
    """The parts of QMediaPlayer the window uses, and nothing else."""

    class PlaybackState:
        StoppedState = 0
        PlayingState = 1
        PausedState = 2

    class MediaStatus:
        NoMedia = 0
        LoadingMedia = 1
        LoadedMedia = 2
        StalledMedia = 3
        BufferingMedia = 4
        BufferedMedia = 5
        EndOfMedia = 6
        InvalidMedia = 7

    class Error:
        NoError = 0
        ResourceError = 1
        FormatError = 2
        NetworkError = 3
        AccessDeniedError = 4

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.mediaStatusChanged = _Signal()
        self.positionChanged = _Signal()
        self.durationChanged = _Signal()
        self.seekableChanged = _Signal()
        self.playbackStateChanged = _Signal()
        self.errorOccurred = _Signal()
        self.sources = []
        self.state = self.PlaybackState.StoppedState
        self._position = 0
        self._error = ""

    def setSource(self, url):
        self.sources.append(url)

    def source(self):
        return self.sources[-1] if self.sources else None

    def play(self):
        self.state = self.PlaybackState.PlayingState

    def pause(self):
        self.state = self.PlaybackState.PausedState

    def stop(self):
        self.state = self.PlaybackState.StoppedState

    def playbackState(self):
        return self.state

    def position(self):
        return self._position

    def setPosition(self, p):
        self._position = int(p)

    def errorString(self):
        return self._error

    def setAudioOutput(self, out):
        self._audio_out = out

    def setVideoOutput(self, item):
        self._video_out = item


class QAudioOutput(_Object):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self._muted = False
        self._volume = 1.0
        self._device = None

    def setMuted(self, m):
        self._muted = bool(m)

    def isMuted(self):
        return self._muted

    def setVolume(self, v):
        self._volume = float(v)

    def volume(self):
        return self._volume

    def setDevice(self, d):
        self._device = d

    def device(self):
        return self._device


class QAudioDevice:
    """NO `fromId`. PyQt6 has no such method, and the window must not call one.

    Adding it here to make an AttributeError go away is how the bug survived a
    green suite the first time. If the code needs a device, it asks
    `QMediaDevices.audioOutputs()`.
    """

    def __init__(self, desc="", null=False):
        self._desc = desc
        self._null = null

    def description(self):
        return self._desc

    def isNull(self):
        return self._null

    def id(self):
        return b"stub:" + self._desc.encode()


class QMediaDevices:
    outputs = [QAudioDevice("Speakers (Realtek)"),
               QAudioDevice("Xiaomi Bluetooth Headphones")]

    @staticmethod
    def audioOutputs():
        return list(QMediaDevices.outputs)


class QUrl:
    """Faithful where it matters, and ONLY where it matters.

    `QUrl("C:\\\\x.mp4")` really does report scheme "c" in Qt, and that fact is
    the bug. A stub that "fixed" the string would have hidden it again.
    """

    def __init__(self, url=""):
        self._url = str(url)

    @staticmethod
    def fromLocalFile(path):
        u = QUrl(path)
        u._local = True
        return u

    def toString(self):
        return self._url

    def isLocalFile(self):
        return getattr(self, "_local", False)

    def scheme(self):
        if getattr(self, "_local", False):
            return "file"                        # what fromLocalFile always gives
        if self._url.lower().startswith(("http://", "https://", "file://")):
            return self._url.split(":", 1)[0].lower()
        if len(self._url) > 2 and self._url[1] == ":":
            return self._url[0].lower()          # "C:" -> "c", as Qt does
        return ""

    def isEmpty(self):
        return not self._url


def _install_qt() -> dict[str, types.ModuleType]:
    core = types.ModuleType("PyQt6.QtCore")
    core.QUrl = QUrl
    # Qt's enums are namespaces of integers, and the window uses dozens of them
    # (`Qt.AlignmentFlag.AlignRight`, `Qt.Orientation.Vertical`, ...). Spelling
    # each one out is a list that goes stale with the next widget, so anything
    # asked for is an integer — and every stub that receives one ignores it.
    class _Enum:
        """Nested namespaces of integers, to any depth.

        `Qt.AlignmentFlag.AlignRight` and `Qt.AlignmentFlag.AlignLeft | Qt...`
        both work: attribute access nests, and the result of `|` is another one.
        """

        def __getattr__(self, name):
            if name.startswith("__"):
                raise AttributeError(name)
            return _Enum()

        def __or__(self, _other):
            return self

        def __ror__(self, _other):
            return self

        # Flag tests AND the value: `flags & WindowType.X`. Without these the
        # stub turns a correct check into a TypeError, which reads as a bug in
        # the code under test.
        def __and__(self, _other):
            return self

        def __rand__(self, _other):
            return self

        def __bool__(self):
            return True

        # A KEY is an identity, not a flag: `event.key() == Qt.Key.Key_Escape`
        # is the only comparison in the app that must be TRUE, and the one
        # below this (`== False`) made every key press look like "not Esc" —
        # which silently skipped each branch in `_on_key`. Key names answer
        # with themselves so a handler can be driven at all.
        def __eq__(self, _other):
            body = self.__dict__.get("_path", ())
            other = getattr(_other, "_path", None)
            return bool(body) and bool(other) and body == other

        def __hash__(self):
            return 0

    class _PathEnum(_Enum):
        """`Qt.Key.Key_Escape` — an enum whose attributes remember their path."""

        def __init__(self, path=()):
            self._path = path

        def __getattr__(self, name):
            if name.startswith("__"):
                raise AttributeError(name)
            return _PathEnum(self._path + (name,))

    _KEY_ROOTS = ("Key", "KeyboardModifier")
    core.Qt = _Enum()
    for _root in _KEY_ROOTS:
        setattr(core.Qt, _root, _PathEnum((_root,)))
    core.QDir = type("QDir", (), {"Filter": _Enum()})
    core.QTimer = type("QTimer", (_Object,), {"start": lambda s, *a: None,
                                             "stop": lambda s, *a: None,
                                             "setInterval": lambda s, *a: None,
                                             "setSingleShot": lambda s, *a: None,
                                             "timeout": _Signal(),
                                             "singleShot": staticmethod(lambda *a: None)})
    core.pyqtSignal = _Signal
    for geom in ("QLineF", "QPointF", "QPoint", "QRectF", "QSizeF", "QRect", "QSize"):
        setattr(core, geom, type(geom, (_Object,), {}))

    gui = types.ModuleType("PyQt6.QtGui")
    for name in ("QBrush", "QColor", "QCursor", "QFont", "QKeySequence",
                 "QPainter", "QPen", "QPixmap", "QIcon", "QLinearGradient", "QRadialGradient", "QShortcut"):
        setattr(gui, name, type(name, (_Object,), {}))
    # Qt 6 exposes QFileSystemModel from QtGui, not QtWidgets.
    gui.QFileSystemModel = type("QFileSystemModel", (_Object,), {})
    gui.QColor.Weight = None
    gui.QFont.Weight = _Enum()
    gui.QPainter.RenderHint = _Enum()
    gui.QDragEnterEvent = gui.QDropEvent = type("_Event", (_Object,), {})

    widgets = types.ModuleType("PyQt6.QtWidgets")
    layouts = {"QHBoxLayout", "QVBoxLayout", "QGridLayout", "QFormLayout",
               "QBoxLayout"}
    for name in ("QApplication", "QComboBox", "QFileDialog", "QFrame",
                 "QHBoxLayout", "QLabel", "QLineEdit", "QMenu", "QMainWindow",
                 "QPushButton", "QScrollArea", "QSplitter", "QGraphicsScene",
                 "QGraphicsView", "QStackedWidget", "QTextEdit", "QVBoxLayout",
                 "QWidget", "QProgressBar", "QSlider", "QSizePolicy",
                 "QGraphicsItem"):
        # `type.__getattr__` is not a thing, so a nested enum on a CLASS has to
        # be a metaclass. Without this, `QFrame.Shape.NoFrame` is an
        # AttributeError and the window cannot even be constructed.
        base = _Layout if name in layouts else None
        setattr(widgets, name, _stub_class(name, base))
    class _Menu(_Object):
        aboutToShow = _Signal()
        def addAction(self, text):
            action = _Object()
            action.setText(text)
            action.triggered = _Signal()
            return action
    widgets.QMenu = _Menu
    class _ScrollArea(_Object):
        def setWidget(self, widget):
            self._widget = widget
            _reparent(widget, self)
        def widget(self):
            return self._widget
    widgets.QScrollArea = _ScrollArea
    widgets.QToolButton = _stub_class("QToolButton")
    widgets.QMainWindow = _stub_class("QMainWindow")
    class _MdiArea(_Object):
        ViewMode = _Enum()
        subWindowActivated = _Signal()
        def viewport(self):
            return self
        def addSubWindow(self, sub):
            _reparent(sub, self)
    class _MdiSubWindow(_Object):
        def setWidget(self, widget):
            _reparent(widget, self)
    widgets.QMdiArea = _MdiArea
    widgets.QMdiSubWindow = _MdiSubWindow
    widgets.QSizePolicy.Policy = _Enum()
    widgets.QStyle = _stub_class("QStyle")
    widgets.QHeaderView = _stub_class("QHeaderView")
    widgets.QHeaderView.ResizeMode = _Enum()

    class _TreeView(_Object):
        def header(self):
            return _Object()

    widgets.QTreeView = _TreeView

    class _Geometry(_Object):
        # A QRect answers x() and y() as well as width() and height(), and a
        # panel anchored to a corner needs all four: without x()/y() the stub
        # made `panel_position` raise, so a test that only ever asked for the
        # size would have "proved" the panel could not be placed at all.
        def x(self):
            return 0

        def y(self):
            return 0

        def width(self):
            return 1920

        def height(self):
            return 1080

    class _Screen(_Object):
        def availableGeometry(self):
            return _Geometry()

    class _App(_Object):
        aboutToQuit = _Signal()
        focusChanged = _Signal()
        # Class-level, because the window calls QApplication.primaryScreen()
        # without having constructed one — a static in Qt, an instance here.
        primaryScreen = staticmethod(lambda: _Screen())

        @staticmethod
        def instance():
            return _App()

        @staticmethod
        def setAttribute(*a, **k):
            pass

        @staticmethod
        def clipboard():
            return _Object()          # has dataChanged, setText, text()

    widgets.QApplication = _App

    mm = types.ModuleType("PyQt6.QtMultimedia")
    mm.QMediaPlayer = QMediaPlayer
    mm.QAudioOutput = QAudioOutput
    mm.QAudioDevice = QAudioDevice
    mm.QMediaDevices = QMediaDevices

    mmw = types.ModuleType("PyQt6.QtMultimediaWidgets")

    class QGraphicsVideoItem(_Object):
        nativeSizeChanged = _Signal()

        def nativeSize(self):
            class _Size:
                def isEmpty(self):
                    return False

                def width(self):
                    return 640

                def height(self):
                    return 360
            return _Size()

    mmw.QGraphicsVideoItem = QGraphicsVideoItem

    # EVERYTHING ELSE, ON DEMAND.
    #
    # The window and its overlays import thirty-odd names, and listing them by
    # hand means the next import fails the test for a reason that has nothing to
    # do with playback. A module-level `__getattr__` (PEP 562) hands back a stub
    # for any name not defined above — while the classes whose BEHAVIOUR is the
    # subject (QUrl, the players, the devices) stay explicit. Named imports work
    # through `__getattr__`, which is how `from PyQt6.QtGui import QPen` asks.
    def _anything(module_globals):
        cache = {}

        def __getattr__(name):
            if name.startswith("__") or (module_globals.get("__name__") == "PyQt6.QtWidgets"
                                          and name == "QFileSystemModel"):
                raise AttributeError(name)
            if name not in cache:
                cache[name] = type(name, (_Object,), {})
            return cache[name]
        module_globals["__getattr__"] = __getattr__
        return module_globals

    _anything(vars(core))
    _anything(vars(gui))
    _anything(vars(widgets))
    _anything(vars(mm))
    _anything(vars(mmw))

    pkg = types.ModuleType("PyQt6")
    pkg.__path__ = [str(ROOT / "ui")]          # not a real package; shapes only
    _anything(vars(pkg))
    return {"PyQt6.QtCore": core, "PyQt6.QtGui": gui, "PyQt6.QtWidgets": widgets,
            "PyQt6.QtMultimedia": mm, "PyQt6.QtMultimediaWidgets": mmw,
            "PyQt6": pkg}


def install_qt() -> dict[str, types.ModuleType]:
    """Alias with a public name, for callers that are not this module."""
    return _install_qt()


def fresh_ui(stubs: dict[str, types.ModuleType] | None = None):
    """Install the stub, drop every cached `ui.*`, then import the package.

    THE PURGE IS THE POINT. A hand-written list of `ui` modules drifted once —
    it named seven while `ui/` had twenty-nine — so whichever modules it did not
    name stayed cached from a REAL import and were reused against the stub. The
    symptom was fifty setup errors deep inside a widget constructor. Deriving
    the list from `sys.modules` means the next module added to `ui/` is purged
    automatically.
    """
    stubs = install_qt() if stubs is None else stubs
    saved = {k: v for k, v in sys.modules.items()
             if k == "PyQt6" or k.startswith("PyQt6.") or k == "ui" or k.startswith("ui.")}
    sys.modules.update(stubs)
    for name in [k for k in sys.modules if k == "ui" or k.startswith("ui.")]:
        sys.modules.pop(name, None)
    return saved


def restore_ui(saved: dict[str, types.ModuleType]) -> None:
    """Undo `fresh_ui`: drop the stubbed modules and put the real ones back."""
    for name in [k for k in sys.modules if k == "ui" or k.startswith("ui.")]:
        sys.modules.pop(name, None)
    for name in [k for k in list(sys.modules) if k.startswith("PyQt6")]:
        if name not in saved:
            sys.modules.pop(name, None)
    sys.modules.update(saved)
