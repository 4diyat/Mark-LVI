"""The window, IMPORTED and CONSTRUCTED — the test that would have caught "still errors".

WHY THIS FILE EXISTS
    Three bugs shipped in the playback work, and every one of them was invisible
    to the tests that existed:

      * `QAudioDevice.fromId(...)` does not exist in PyQt6. The call raised
        AttributeError inside a `try/except Exception: pass`, so the speaker the
        user had chosen in AUDIO DEVICES was silently ignored. `test_audio_bar.py`
        could not see it because its fake provided `fromId`.
      * `QUrl(r"C:\\clips\\a b.mp4")` reads "C:" as a URL SCHEME. Every local
        video and song was handed to the player as `c:\\clips\\a b.mp4`, so Qt
        tried to fetch a protocol that does not exist and the user was told their
        own file could not be played. No test built a QUrl at all.
      * The audio bar was parented to a wrapper that was never added to any
        layout, so "play some music" answered correctly and showed nothing.
        `test_video_wiring.py` only read the AST, and the AST said the call was
        there — which it was.

    So this file does the thing those three avoided: it imports `ui/window.py`
    and builds the window. Qt is not installable in this sandbox (libGL and
    libxkbcommon are absent and apt is blocked), so a stub stands in — but a
    DELIBERATELY NARROW one, written from PyQt6's own `.pyi` stubs. That is the
    point: the previous fakes invented `fromId` because I wrote them from the
    code instead of from the API, which made the fake agree with the bug.

    Any name a stub has to invent to satisfy the window is a name the window
    uses — and it is checked below against the real API surface where that is
    possible from a `.pyi` file.
"""
from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

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
        self._style = ""
        self._enabled = True
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

    def setCheckable(self, _on):
        pass

    def isChecked(self):
        return False

    def setChecked(self, _on):
        pass

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
    try:
        widget._parent = parent
    except Exception:
        pass
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

        def __eq__(self, _other):
            return False

        def __hash__(self):
            return 0

    core.Qt = _Enum()
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


@pytest.fixture(scope="module")
def window_module():
    saved = {k: v for k, v in sys.modules.items() if k == "PyQt6" or k.startswith("PyQt6.")}
    stubs = _install_qt()
    sys.modules.update(stubs)
    for name in ("ui", "ui.window", "ui.audio", "ui.chat_log", "ui.video_fallback",
                 "ui.theme", "ui.metrics", "ui.overlays"):
        sys.modules.pop(name, None)
    # `ui/__init__.py` imports the whole window and re-exports it; importing the
    # package is the path main.py takes, so this is the real thing.
    try:
        import ui
        yield ui
    finally:
        for name in list(sys.modules):
            if name == "ui" or name.startswith("ui."):
                sys.modules.pop(name, None)
        for name in stubs:
            sys.modules.pop(name, None)
        sys.modules.update(saved)


@pytest.fixture()
def window(window_module, monkeypatch):
    """A constructed MainWindow. Needs the Qt stub above and nothing else."""
    # The config and the icon renderer both reach outside this process; the
    # window only wants them to answer, not to do anything.
    import memory.config_manager as cfg
    monkeypatch.setattr(cfg, "get_assistant_name", lambda: "JARVIS", raising=False)
    monkeypatch.setattr(cfg, "get_output_device", lambda: "", raising=False)
    win = window_module.MainWindow("face.png")
    # Qt shows the window on the event loop; the stub has no event loop, so a
    # visibility assertion would otherwise fail for a reason that is the
    # fixture's fault rather than the code's.
    win.show()
    yield win
    try:
        win.hide()
    except Exception:
        pass


# ── the three bugs ─────────────────────────────────────────────────────────

def test_the_audio_bar_is_in_a_layout_and_can_actually_appear(window):
    """"I played a song and saw nothing." The bar has to be inside the widget
    tree of the window — being constructed is not the same as being shown."""
    bar = window._audio_cont
    assert bar.parentWidget() is not None, (
        "the audio bar has no parent, so nothing can ever lay it out")

    # Walk up to the window and prove the bar is reachable from it.
    node, hops = bar, 0
    while node is not None and hops < 20:
        if node is window:
            break
        node, hops = node.parentWidget(), hops + 1
    assert node is window, "the audio bar is not inside the window's widget tree"


def test_playing_audio_shows_the_bar_and_its_panel(window):
    """A widget cannot be visible inside a hidden parent — the first version of
    the bar was shown inside one, and "play some music" drew nothing."""
    window._on_audio_open("song.mp3", "Song", 0.5, False)
    bar = window._audio_cont
    assert bar.isVisible(), "the bar stayed hidden"

    parent = bar.parentWidget()
    while parent is not None and parent is not window:
        assert parent.isVisible(), (
            f"the bar's parent ({type(parent).__name__}) is hidden, so the bar "
            "shows nothing however visible it says it is")
        parent = parent.parentWidget()


def test_stopping_a_song_hides_the_bar_again(window):
    window._on_audio_open("song.mp3", "Song", 0.5, False)
    window._on_audio_stop()
    assert not window._audio_cont.isVisible(), (
        "the bar stayed on screen after the song stopped")


def test_a_windows_path_reaches_the_player_as_a_file_not_as_scheme_c(window):
    """THE playback bug. `QUrl("C:\\\\clips\\\\a b.mp4")` is a request for scheme
    "c" — a protocol no machine implements — so the user was told their own
    video could not be played."""
    window._on_video_open(r"C:\clips\a b.mp4", "A clip", True, "")
    url = window._video_player.source()

    assert url is not None, "the video player was given no source at all"
    assert url.scheme() != "c", (
        "the video source was built with QUrl(...); Qt read the drive letter as "
        "a scheme and the player was asked to fetch c:\\... over a protocol "
        "that does not exist")
    assert url.isLocalFile() or url.scheme() == "file"


def test_a_local_song_reaches_the_audio_player_as_a_file(window):
    window._on_audio_open("/home/me/Music/My Song.mp3", "My Song", 0.5, False)
    url = window._audio_player.source()

    assert url is not None
    assert url.scheme() != "c"
    assert url.isLocalFile() or url.scheme() == "file", (
        "a local file must go through QUrl.fromLocalFile, not QUrl(...)")


def test_an_http_stream_is_still_passed_straight_through(window):
    """The other half: a googlevideo URL must NOT be re-encoded as a path, or
    its signature breaks and YouTube returns 403."""
    url_in = "https://r1.googlevideo.com/videoplayback?id=1&sig=abc"
    window._on_video_open(url_in, "YouTube", True, "")
    url = window._video_player.source()
    assert url.scheme() in ("https", "http")
    assert "sig=abc" in url.toString(), "the query string was mangled"


def test_the_chosen_output_device_is_used_or_the_default_kept(window):
    """`QAudioDevice.fromId` does not exist in PyQt6. The call raised inside a
    swallowed try/except, so the chosen speaker was ignored and every song came
    out of the default device."""
    import memory.config_manager as cfg
    window_module = sys.modules["ui"]
    _ = window_module

    from ui import audio as audio_mod
    assert hasattr(audio_mod.AudioMixin, "_audio_device_for")
    # The device is looked up by description now; fromId must be gone.
    import inspect
    import re
    src = inspect.getsource(audio_mod.AudioMixin._audio_device_for)
    # Comments explain the history; only CODE counts as a call.
    code = re.sub(r"#.*", "", src)
    code = re.sub(r'""".*?"""', "", code, flags=re.S)
    assert "fromId" not in code, (
        "QAudioDevice.fromId does not exist in PyQt6; it raised AttributeError "
        "and was swallowed, so the chosen device was never applied")
    assert "audioOutputs" in code

    # And it really resolves one of the outputs the stub reports.
    audio_mod._ = None
    dev = window._audio_device_for("Xiaomi Bluetooth Headphones")
    assert dev is not None and not dev.isNull()
    assert dev.description() == "Xiaomi Bluetooth Headphones"

    # A device that is not plugged in any more falls back rather than raising.
    assert window._audio_device_for("A headset from 2019") is None
    _ = cfg


def test_the_video_and_audio_surfaces_do_not_share_a_player(window):
    """A song must not take the screen, and a video must not stop a song."""
    assert window._video_player is not window._audio_player
    assert window._video_audio is not window._audio_out


def test_a_403_video_swaps_to_next_candidate_and_searches_when_exhausted(window):
    logs = []
    window._log_sig.connect(logs.append)
    exhausted_reasons = []

    def on_exhausted(reason):
        exhausted_reasons.append(reason)
        return True

    window._on_video_open(
        "https://r1.googlevideo.com/first",
        "Test Clip",
        True,
        "",
        fallbacks={
            "video": [{"url": "https://r2.googlevideo.com/second",
                       "audio": "https://r2.googlevideo.com/audio1"}],
            "audio": ["https://r2.googlevideo.com/audio2"],
        },
        on_exhausted=on_exhausted,
    )
    assert window._video_on is True
    assert window._video_split is False

    # First stream gets 403 Forbidden -> swaps transparently to candidate #2.
    window._video_player._error = "server replied: Forbidden (403)"
    window._on_video_error()
    assert window._video_on is True
    assert window._video_split is True
    assert window._video_player.source().toString() == "https://r2.googlevideo.com/second"
    assert window._video_sound.source().toString() == "https://r2.googlevideo.com/audio1"
    assert any("403" in line or "Forbidden" in line for line in logs)

    # Separate soundtrack fails -> tries backup audio URL before muting.
    window._video_sound._error = "HTTP 403"
    window._on_video_sound_error()
    assert window._video_split is True
    assert window._video_sound.source().toString() == "https://r2.googlevideo.com/audio2"

    # Candidate #2 also fails -> triggers alternative source search callback.
    window._video_player._error = "403 Forbidden"
    window._on_video_error()
    assert exhausted_reasons == ["403 Forbidden"]
    assert window._video_on is False
    assert any("searching" in line.lower() for line in logs)


def test_remote_overlay_connect_does_not_crash_without_assistant_name(window):
    """Connecting a phone while RemoteKeyOverlay is visible previously crashed
    with AttributeError on `_assistant_name`, causing HTTP 500 on /login and
    /auto-login."""
    calls = {"n": 0}

    def fake_remote_clicked():
        calls["n"] += 1
        key = f"ABCD123{calls['n']}"
        return ("http://192.168.1.5:8000", key,
                f"http://192.168.1.5:8000/auto-login?key={key}",
                "192.168.1.5:8000", "")

    window.on_remote_clicked = fake_remote_clicked
    window._open_remote()
    ov = window._remote_overlay
    assert ov is not None and ov.isVisible()

    # Emulate both the background signal path (from FastAPI) and direct slot call.
    window._phone_connected_sig.emit()
    window.notify_phone_connected()
    assert "JARVIS" in ov._timer_lbl.text()

    # Generating a new key after connecting also works cleanly.
    ov._refresh_key()
    assert ov._key_lbl.text() == "ABCD1232"




def test_desktop_shell_hosts_the_original_panels_and_dock(window):
    """The shell must reparent the real session widgets, not copies or placeholders."""
    windows = window._desktop_windows
    assert set(windows) == {"chat", "assistant", "navigation", "video", "camera", "files"}
    assert windows["chat"] is windows["assistant"]
    assert window._right_panel.parentWidget() is window._assistant_panel
    assert window._assistant_panel.parentWidget().parentWidget() is windows["assistant"]
    assert window._left_panel.parentWidget().parentWidget() is windows["navigation"]
    assert windows["chat"].parentWidget() is window._desktop_mdi
    keys = {key for _, key in window._workspace_dock}
    assert keys == {"workspace.chat", "workspace.files", "browser.title", "workspace.editors", "workspace.media",
                    "workspace.trading", "workspace.apps", "desktop.settings"}
    actions = {key for _, key in window._workspace_dock_actions}
    assert {"workspace.code", "workspace.image", "workspace.video", "workspace.camera",
            "workspace.order", "model.title", "desktop.plugins"} <= actions
    assert window._center_split.parentWidget() is window._assistant_panel


def test_video_is_independent_from_camera_and_close_stops_it(window, monkeypatch):
    """Opening, retrying or closing a video must not stop or replace a live camera."""
    camera_indices = []
    monkeypatch.setattr(window._hud_cam_stack, "setCurrentIndex", camera_indices.append)
    window._on_cam_stream(True)
    assert camera_indices == []
    assert window._camera_cont.parentWidget().parentWidget() is window._desktop_windows["camera"]
    window._cam_stop.clear()
    window._on_video_open("https://example.com/video.mp4", "Video", True)
    assert not window._cam_stop.is_set()
    assert window._video_on
    assert camera_indices == []
    assert window._video_cont.parentWidget().parentWidget() is window._desktop_windows["video"]
    window._swap_video_stream("https://example.com/fallback.mp4")
    assert camera_indices == [] and not window._cam_stop.is_set()
    window._on_video_close()
    assert not window._video_on and camera_indices == []
    assert not window._cam_stop.is_set()


def test_video_window_close_requests_stop(window, monkeypatch):
    called = []
    monkeypatch.setattr(window, "_on_video_close", lambda: called.append(True))
    event = types.SimpleNamespace(ignore=lambda: called.append("ignored"))
    window._desktop_windows["video"].closeEvent(event)
    assert called == [True, "ignored"]


def test_document_is_hosted_inside_movable_desktop(window):
    from ui.desktop_workspace import show_document
    document = _Object()
    subwindow = show_document(window, document)
    assert document.parentWidget().parentWidget() is subwindow
    assert subwindow.parentWidget() is window._desktop_mdi


def test_video_controls_pause_and_seek_picture_and_sound_together(window, monkeypatch):
    from ui import video_controls as controls
    window._on_video_open("https://example.com/video.mp4", "Video", True,
                          "https://example.com/audio.mp4")
    controls.toggle_pause(window)
    assert window._video_player.playbackState() == QMediaPlayer.PlaybackState.PausedState
    assert window._video_sound.playbackState() == QMediaPlayer.PlaybackState.PausedState
    controls.duration_changed(window, 120000)
    controls.seekable_changed(window, True)
    monkeypatch.setattr(window._video_seek, "value", lambda: 45000)
    controls.seek(window)
    assert window._video_player.position() == 45000
    assert window._video_sound.position() == 45000
    controls.toggle_pause(window)
    assert window._video_player.playbackState() == QMediaPlayer.PlaybackState.PlayingState
    assert window._video_sound.playbackState() == QMediaPlayer.PlaybackState.PlayingState
    controls.seekable_changed(window, False)
    monkeypatch.setattr(window._video_seek, "value", lambda: 90000)
    controls.seek(window)
    assert window._video_player.position() == 45000
    window._on_video_close()
    assert not window._video_seekable and window._video_duration_ms == 0


def test_closing_camera_panel_stops_capture_without_stopping_video(window, monkeypatch):
    stopped = []
    monkeypatch.setattr(window, "stop_camera_stream", lambda: stopped.append(True))
    event = types.SimpleNamespace(ignore=lambda: None)
    window._video_on = True
    window._desktop_windows["camera"].closeEvent(event)
    assert stopped == [True]
    assert window._video_on


def test_stopping_camera_does_not_hide_video_or_replace_avatar(window, monkeypatch):
    changes = []
    monkeypatch.setattr(window._hud_cam_stack, "setCurrentIndex", changes.append)
    window._on_video_open("https://example.com/v.mp4", "Video", True)
    window._on_cam_stream(True)
    window._on_cam_stream(False)
    assert window._video_on and not changes
    assert window._desktop_windows["camera"]._visible is False


def test_duplicate_camera_start_does_not_spawn_or_clear_stop(window, monkeypatch):
    import threading
    started = threading.Event()
    release = threading.Event()
    def capture():
        started.set()
        release.wait(2)
    monkeypatch.setattr(window, "_cam_loop", capture)
    try:
        window.start_camera_stream()
        assert started.wait(1)
        original = window._cam_thread
        window.stop_camera_stream()
        window.start_camera_stream()
        assert window._cam_thread is original and window._cam_stop.is_set()
    finally:
        release.set()
        window._cam_thread.join(2)


def test_app_close_checks_all_unsaved_documents_without_closing_early(window):
    from ui.desktop_workspace import confirm_shutdown
    checked = []
    class Document:
        def __init__(self, answer): self.answer = answer
        def _may_discard(self):
            checked.append(self.answer)
            return self.answer
    window._creative_dialogs = {Document(True)}
    window._image_editors = {Document(False)}
    assert not confirm_shutdown(window)
    assert checked == [True, False]
    window._image_editors = {Document(True)}
    assert confirm_shutdown(window)


def test_image_flatten_cancel_and_undo_restore_layers(window_module, monkeypatch):
    import ui.image_editor as editor
    from core.image_layers import make_text_layer
    instance = editor.ImageEditor.__new__(editor.ImageEditor)
    instance._image = "original"
    layer = make_text_layer("hello", 0, 5, 12, 100, 100)
    instance._layers = [layer]
    instance._undo_state = None
    instance._dirty = False
    instance._status = _Object()
    instance._update_layers = lambda: None
    instance._render = lambda: None
    buttons = types.SimpleNamespace(Yes=1, No=2)
    monkeypatch.setattr(editor, "QMessageBox", types.SimpleNamespace(
        StandardButton=buttons, question=lambda *a: 2))
    instance._change("flat")
    assert instance._image == "original" and instance._layers == [layer] and not instance._dirty
    monkeypatch.setattr(editor.QMessageBox, "question", lambda *a: 1)
    instance._change("flat")
    assert instance._image == "flat" and instance._layers == [] and instance._dirty
    instance.undo()
    assert instance._image == "original" and instance._layers == [layer]


def test_video_open_button_opens_local_selection_muted(window, monkeypatch):
    from ui import video_controls as controls
    monkeypatch.setattr(controls.QFileDialog, "getOpenFileName",
                        lambda *a: ("/home/user/sample clip.mp4", "Videos"), raising=False)
    controls.open_local(window)
    assert window._video_on and window._video_player.source().isLocalFile()
    assert window._video_audio.isMuted()


def test_app_close_refusal_keeps_media_running(window, monkeypatch):
    import ui.desktop_workspace as workspace
    monkeypatch.setattr(workspace, "confirm_shutdown", lambda _: False)
    calls = []
    monkeypatch.setattr(window, "stop_camera_stream", lambda: calls.append("camera"))
    monkeypatch.setattr(window, "_on_video_close", lambda: calls.append("video"))
    event = types.SimpleNamespace(ignore=lambda: calls.append("ignored"))
    window.closeEvent(event)
    assert calls == ["ignored"]


def test_queued_camera_started_signal_does_not_reopen_after_stop(window):
    window._cam_stop.set()
    window._on_cam_stream(True)
    assert not window._camera_active
    assert window._desktop_windows["camera"]._visible is False


def test_desktop_drawer_fits_under_compact_menu_and_inside_screen(window, monkeypatch):
    geometry = []
    drawer = types.SimpleNamespace(setFixedWidth=lambda _w: None, adjustSize=lambda: None,
                                   sizeHint=lambda: types.SimpleNamespace(height=lambda: 300),
                                   setGeometry=lambda *args: geometry.append(args))
    monkeypatch.setattr(window._desktop_menu_bar, "height", lambda: 30)
    monkeypatch.setattr(window.centralWidget(), "width", lambda: 820)
    window._place_drawer(drawer, 790)
    assert geometry == [(600, 30, 220, 300)]


def test_jarvis_state_is_forwarded_to_the_ui(window, monkeypatch):
    from ui.window import JarvisUI

    observed = []
    monkeypatch.setattr(window, "_state_sig", types.SimpleNamespace(emit=observed.append))
    JarvisUI.set_state(types.SimpleNamespace(_win=window), "THINKING")
    assert observed == ["THINKING"]


def test_hand_control_activation_uses_configured_camera_without_external_plugin(window, monkeypatch, tmp_path):
    import memory.config_manager as cfg

    calls = []
    config_file = tmp_path / "api_keys.json"
    config_file.write_text('{"camera_index": 3}', encoding="utf-8")
    monkeypatch.setattr(cfg, "CONFIG_FILE", config_file)
    monkeypatch.setattr(cfg, "_LAST_GOOD", {})
    monkeypatch.setattr(window._workspace_gestures, "update", lambda _samples: None)
    monkeypatch.setattr(window._hand_controller, "start", lambda camera: calls.append(camera))
    assert window._hand_controller.thread is None
    window._hand_toggle()
    assert calls == [3]


def test_hand_control_does_not_start_while_confirmation_is_open(window, monkeypatch):
    calls = []
    window._hand_closing_confirm = True
    monkeypatch.setattr(window._workspace_gestures, "update", lambda _samples: None)
    monkeypatch.setattr(window._hand_controller, "start", lambda camera: calls.append(camera))
    window._hand_toggle()
    assert calls == []


def test_attachment_panel_can_be_opened_without_replacing_session(window):
    drop = window._drop_zone
    log = window._log
    assert drop._visible is False
    window._attachment_toggle.toggled.emit(True)
    assert drop._visible is True
    assert window._log is log
    window._attachment_toggle.toggled.emit(False)
    assert drop._visible is False


def test_initial_desktop_geometry_keeps_panels_above_dock(window):
    from ui.desktop_workspace import initial_window_geometry
    for width, height in ((1366, 738), (820, 550)):
        for x, y, w, h in initial_window_geometry(width, height):
            assert x >= 0 and y >= 0
            assert x + w <= width
            assert y + h <= height - 90


def test_wide_desktop_reserves_left_lower_area_for_editor(window):
    from ui.desktop_workspace import initial_window_geometry
    width, height = 1366, 738
    files, assistant = initial_window_geometry(width, height)
    # Match the approved composition: a shorter file window above an editor,
    # with a taller assistant beside the central avatar.
    assert files[3] == int(height * .36)
    assert files[1] + files[3] < height * .46
    assert assistant[1] == int(height * .10)
    assert assistant[3] > files[3]
    assert assistant[1] + assistant[3] <= height - 90


def test_initial_editor_respects_disabled_plugin_and_only_attempts_once(window_module):
    from ui.desktop_workspace import open_initial_editor
    viewport = types.SimpleNamespace(width=lambda: 1366, height=lambda: 738)
    mdi = types.SimpleNamespace(viewport=lambda: viewport)
    calls = []
    host = types.SimpleNamespace(_desktop_mdi=mdi, _workspace_documents={},
                                 get_plugins=lambda: calls.append(True) or [])
    open_initial_editor(host)
    open_initial_editor(host)
    assert calls == [True] and host._initial_editor_attempted
    compact = types.SimpleNamespace(_desktop_mdi=types.SimpleNamespace(
        viewport=lambda: types.SimpleNamespace(width=lambda: 800, height=lambda: 600)),
        _workspace_documents={}, get_plugins=lambda: pytest.fail("compact desktop must not open editor"))
    open_initial_editor(compact)


def test_initialising_does_not_claim_microphone_is_active(window):
    from core.i18n import label
    window.hud.state = "INITIALISING"
    window._muted = False
    window._deaf = False
    window._style_mute_btn()
    assert window._mute_btn.text() == label("ui.mic.initialising")
    window.hud.state = "LISTENING"
    window._style_mute_btn()
    assert window._mute_btn.text() == label("ui.mic.active")


def test_workspace_commands_use_original_windows_and_refuse_document_close(window, monkeypatch):
    from ui.workspace_commands import execute
    files = window._desktop_windows["files"]
    assert execute(window, {"action": "close", "target": "files"})["ok"]
    assert files._visible is False
    document = _Object()
    from ui.desktop_workspace import show_document
    sub = show_document(window, document, "code_editor")
    assert window._workspace_documents["doc-1"] == ("code_editor", sub)
    result = execute(window, {"action": "close", "target": "doc-1"})
    assert not result["ok"] and "unsaved" in result["message"]
    assert sub._visible is True
    monkeypatch.setattr(window._workspace_file_browser, "navigate", lambda path: False)
    assert not execute(window, {"action": "navigate", "text": "/missing"})["ok"]


def test_workspace_camera_start_and_stop_are_reported_as_requests(window, monkeypatch):
    from ui.workspace_commands import execute
    calls = []
    monkeypatch.setattr(window, "start_camera_stream", lambda: calls.append("start"))
    monkeypatch.setattr(window, "stop_camera_stream", lambda: calls.append("stop"))
    window._camera_active = False
    assert "requested" in execute(window, {"action": "open", "target": "camera"})["message"]
    assert "requested" in execute(window, {"action": "close", "target": "camera"})["message"]
    assert calls == ["start", "stop"]


def test_model_viewer_command_does_not_start_camera(window, monkeypatch):
    from ui.workspace_commands import execute
    opened = []
    monkeypatch.setattr(window, "_open_model_viewer", lambda: opened.append(True))
    monkeypatch.setattr(window, "start_camera_stream", lambda: pytest.fail("camera started"))
    assert execute(window, {"action": "open", "target": "model_viewer"})["ok"]
    assert opened == [True]


def test_remote_https_button_saves_setting_and_says_restart(window, isolated_config):
    from core.i18n import label
    isolated_config.set_config_values(dashboard_https=False, assistant_name="keep")
    window.on_remote_clicked = lambda: ("http://192.168.1.5:8000", "ABCDEFGH", "", "", "")
    window._open_remote()
    overlay = window._remote_overlay
    assert overlay._https_status.text() == label("remote.http.warning")
    overlay._enable_https()
    assert isolated_config.load_api_keys()["dashboard_https"] is True
    assert isolated_config.load_api_keys()["assistant_name"] == "keep"
    assert overlay._https_status.text() == label("remote.https.restart")
    assert overlay._manual_url.startswith("http://")


def test_remote_https_save_failure_is_visible(window, isolated_config, monkeypatch):
    from core.i18n import label
    monkeypatch.setattr(isolated_config, "set_config_values", lambda **_: False)
    window.on_remote_clicked = lambda: ("http://192.168.1.5:8000", "ABCDEFGH", "", "", "")
    window._open_remote()
    window._remote_overlay._enable_https()
    assert window._remote_overlay._https_status.text() == label("remote.https.save_failed")


def test_remote_security_status_reports_running_protocol(window, isolated_config):
    from core.i18n import label
    isolated_config.set_config_values(dashboard_https=True)
    window.on_remote_clicked = lambda: ("http://192.168.1.5:8000", "ABCDEFGH", "", "", "")
    window._open_remote()
    assert window._remote_overlay._https_status.text() == label("remote.https.restart")
    window.on_remote_clicked = lambda: ("https://192.168.1.5:8001", "ABCDEFGH", "", "", "")
    window._open_remote()
    assert window._remote_overlay._https_status.text() == label("remote.https.active")


def test_mt5_emergency_stop_and_confirmed_resume_controls(window, monkeypatch):
    from core import trade_gate
    from core.i18n import label
    from ui import mt5_trade as view
    trade_gate.resume()
    dialog = view.OrderDialog.__new__(view.OrderDialog)
    dialog.gate_status = _Object()
    dialog.stop_button = _Object()
    dialog.resume_button = _Object()
    dialog.review = _Object()
    dialog.mode = types.SimpleNamespace(currentData=lambda: "OFF", setCurrentIndex=lambda _: None)
    dialog._busy = False
    answers = types.SimpleNamespace(Yes=1, No=2)
    monkeypatch.setattr(view, "QMessageBox", types.SimpleNamespace(
        StandardButton=answers, question=lambda *args: answers.No))
    try:
        dialog._emergency_stop()
        assert trade_gate.stopped() and dialog.gate_status.text() == label("trade.stopped")
        dialog._resume_trading()
        assert trade_gate.stopped()
        monkeypatch.setattr(view.QMessageBox, "question", lambda *args: answers.Yes)
        dialog._resume_trading()
        assert not trade_gate.stopped()
        assert dialog.gate_status.text() == label("trade.stop_ready")
    finally:
        trade_gate.resume()


def test_graphite_desktop_layout_uses_new_wallpaper_and_conversation_is_primary(window):
    from ui.desktop_workspace import initial_window_geometry
    from ui.theme import C
    assert C.DESKTOP_PANEL == '#15212f'
    assert C.DESKTOP_TEXT == '#eef5fd'
    files, assistant = initial_window_geometry(1366, 738)
    assert files[0] + files[2] < assistant[0]
    assert assistant[0] > files[0]
    assert (ROOT / 'assets/workspace/jarvis-desktop-wave.png').is_file()


def test_app_shutdown_confirms_ssh_before_disconnecting_any_session(window):
    from ui.desktop_workspace import confirm_shutdown
    events = []
    class Panel:
        def disconnect_session(self): events.append('disconnected')
    class Manager:
        def __init__(self, answer): self.answer, self.panel = answer, Panel()
        def shutdown_panels(self): return [self.panel]
        def _confirm_close(self, panels):
            events.append('asked')
            return self.answer
    first, second = Manager(True), Manager(False)
    window._creative_dialogs = set()
    window._image_editors = set()
    window._workspace_documents = {
        'one': ('ssh_manager', types.SimpleNamespace(_document=first)),
        'two': ('ssh_manager', types.SimpleNamespace(_document=second)),
    }
    assert not confirm_shutdown(window)
    assert events == ['asked', 'asked']
    events.clear()
    second.answer = True
    assert confirm_shutdown(window)
    assert events == ['asked', 'asked', 'disconnected', 'disconnected']


def test_workspace_theme_has_shared_focus_and_menu_states(window):
    from ui.theme import workspace_stylesheet
    style = workspace_stylesheet()
    assert 'QPushButton#WorkspacePrimary' in style
    assert 'QLineEdit:focus' in style and 'QTabBar::tab:selected' in style
    assert 'QMenu::item:selected' in style
    assert window._workspace_file_browser is not None


def test_retranslate_workspace_updates_open_browser_and_ssh_without_rebuilding(window):
    from ui.desktop_workspace import retranslate
    events = []
    class Document:
        def __init__(self, name): self.name = name
        def retranslate(self): events.append(('translate', self.name))
        def windowTitle(self): return self.name
    class Sub:
        def __init__(self, name): self._document = Document(name)
        def setWindowTitle(self, value): events.append(('title', value))
    browser, ssh = Sub('browser'), Sub('ssh')
    window._workspace_documents = {'1': ('workspace_browser', browser), '2': ('ssh_manager', ssh)}
    retranslate(window)
    assert events == [('translate', 'browser'), ('title', 'browser'), ('translate', 'ssh'), ('title', 'ssh')]
    assert window._workspace_documents['1'][1] is browser
    assert window._workspace_documents['2'][1] is ssh


def test_hand_badge_reflects_real_controller_status(window, monkeypatch):
    from core.i18n import label
    controller = window._hand_controller
    monkeypatch.setattr(window._workspace_gestures, 'update', lambda _samples: None)
    controller.thread = types.SimpleNamespace(is_alive=lambda: True)
    controller._stop.clear()
    controller.status = 'starting'
    window._hand_refresh()
    assert window._hand_badge._visible
    assert window._hand_badge.text() == label('gesture.badge_starting')
    controller.status = 'active'
    window._hand_refresh()
    assert window._hand_badge.text() == label('gesture.badge_active')
    controller.stop()
    window._hand_refresh()
    assert not window._hand_badge._visible


def test_model_viewer_loads_bounded_obj_and_preserves_model_on_failure(window, tmp_path):
    from ui.model_viewer import ModelViewer
    viewer = ModelViewer(window)
    path = tmp_path / 'model.obj'
    path.write_text('v -2 0 0\nv -1 0 0\nv -1 1 0\nv 1 0 0\nv 2 0 0\nv 1 1 0\nf 1 2 3\nf 4 5 6\n')
    assert viewer.load_file(path)
    assert viewer.canvas.parts == 2
    viewer._explode(50)
    assert viewer.canvas.explode == .5
    assert not viewer.load_file(tmp_path / 'missing.obj')
    assert viewer.canvas.parts == 2


def test_model_file_selection_pauses_hand_control(window, monkeypatch, tmp_path):
    import ui.model_viewer as model_viewer
    viewer = model_viewer.ModelViewer(window)
    model_path = tmp_path / 'connected.obj'
    model_path.write_text('v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n')
    calls = []
    monkeypatch.setattr(window._hand_controller, 'stop', lambda: calls.append('stop'))
    monkeypatch.setattr(model_viewer.QFileDialog, 'getOpenFileName',
                        lambda *args: (str(model_path), ''))
    viewer.open_file()
    assert calls == ['stop'] and viewer.canvas.parts == 1
    assert not viewer.explode_slider.isEnabled()


def test_hand_visual_panel_tracks_real_status_and_stop_never_restarts(window, monkeypatch):
    from ui.hand_gesture import QApplication
    controller = window._hand_controller
    gestures = window._workspace_gestures
    monkeypatch.setattr(window, 'isActiveWindow', lambda: True)
    monkeypatch.setattr(QApplication, 'activeModalWidget', staticmethod(lambda: None), raising=False)
    monkeypatch.setattr(QApplication, 'activePopupWidget', staticmethod(lambda: None), raising=False)
    hands = ((.25, .25, True, False), (.5, .25, True, False))
    monkeypatch.setattr(controller, 'sample', lambda: hands)
    monkeypatch.setattr(gestures, 'update', lambda _samples: setattr(gestures, 'mode', 'resize'))
    controller.thread = types.SimpleNamespace(is_alive=lambda: True)
    controller._stop.clear()
    controller.status = 'active'
    window._hand_refresh()
    assert window._hand_visual_panel._visible
    assert gestures.link.points == ((.25, .25), (.5, .25))
    from core.i18n import label
    assert window._hand_visual_mode.text() == label('gesture.mode_transform')
    monkeypatch.setattr(QApplication, 'activeModalWidget', staticmethod(lambda: object()), raising=False)
    window._hand_refresh()
    assert not window._hand_visual_panel._visible and not gestures.link.points
    monkeypatch.setattr(QApplication, 'activeModalWidget', staticmethod(lambda: None), raising=False)
    monkeypatch.setattr(controller, 'start', lambda *_args: pytest.fail('stop restarted camera'))
    stop_slot = next(slot for slot in reversed(window._hand_visual_stop.clicked.slots)
                     if getattr(slot, '__name__', '') == 'stop_from_panel')
    stop_slot()
    assert controller._stop.is_set() and not window._hand_visual_panel._visible
    assert not gestures.link.points


def test_workspace_avatar_uses_live_face_and_respects_orb_preference(window, monkeypatch):
    mdi = window._desktop_mdi
    viewport = mdi.viewport()
    monkeypatch.setattr(viewport, 'width', lambda: 1366)
    monkeypatch.setattr(viewport, 'height', lambda: 738)
    avatar = types.SimpleNamespace(SPAN=2.6)
    window.hud._avatar = avatar
    window.hud.hud_style = 'face'
    mdi.position_emblem()
    assert mdi._avatar_stage.hud is window.hud
    assert mdi._avatar_stage._visible and not mdi._emblem._visible
    window.hud.hud_style = 'orb'
    mdi.position_emblem()
    assert not mdi._avatar_stage._visible and mdi._emblem._visible
    window.hud.hud_style = 'face'
    monkeypatch.setattr(viewport, 'width', lambda: 820)
    mdi.position_emblem()
    assert not mdi._avatar_stage._visible and not mdi._emblem._visible


def test_desktop_face_repaints_even_if_assistant_panel_hidden(window, monkeypatch):
    hud = window.hud
    calls = []
    hud._avatar = types.SimpleNamespace(step=lambda *args, **kwargs: calls.append('step'))
    hud.hud_style = 'face'
    hud.state = 'IDLE'
    hud._paint_tick = 2
    monkeypatch.setattr(hud, '_on_screen', lambda: False)
    stage = hud._desktop_stage
    monkeypatch.setattr(stage, 'isVisible', lambda: True)
    monkeypatch.setattr(stage, 'window', lambda: types.SimpleNamespace(isMinimized=lambda: False,
                                                                       isHidden=lambda: False))
    monkeypatch.setattr(stage, 'update', lambda: calls.append('paint'))
    hud._step()
    assert calls == ['step', 'paint']


def test_clap_batch_restore_preserves_original_window_state(window_module):
    from ui.desktop_workspace import WallpaperArea

    class Sub:
        def __init__(self, hidden=False, minimized=False, maximized=False):
            self.visible, self.minimized, self.maximized = not hidden, minimized, maximized
        def isVisible(self):
            return self.visible
        def isMinimized(self):
            return self.minimized
        def isMaximized(self):
            return self.maximized
        def showMinimized(self):
            self.minimized = True
            self.maximized = False
        def showNormal(self):
            self.minimized = self.maximized = False
        def showMaximized(self):
            self.minimized, self.maximized = False, True

    normal, maximized, prior, hidden = Sub(), Sub(maximized=True), Sub(minimized=True), Sub(hidden=True)
    area = types.SimpleNamespace(_clap_windows=[], subWindowList=lambda: [normal, maximized, prior, hidden],
                                 position_dock=lambda: None)
    WallpaperArea.minimize_for_clap(area)
    assert normal.minimized and maximized.minimized and prior.minimized and not hidden.minimized
    WallpaperArea.restore_clap_windows(area)
    assert not normal.minimized and maximized.maximized and prior.minimized and not hidden.visible
    assert area._clap_windows == []


def test_suggested_action_drafts_without_sending_or_overwriting(window, monkeypatch):
    sent = []
    monkeypatch.setattr(window, '_send', lambda: sent.append(True))
    button, key = window._suggestion_buttons[0]
    from core.i18n import label
    window._input.setText('')
    draft = next(slot for slot in reversed(button.clicked.slots)
                 if getattr(slot, '__name__', '') == 'draft' and slot.__defaults__[-1] == key)
    draft(False)
    assert window._input.text() == label(key)
    assert not sent
    window._input.setText('existing draft')
    draft(False)
    assert window._input.text() == 'existing draft'
    assert not sent


def test_conversation_formats_messages_as_plain_selectable_blocks(window_module, monkeypatch):
    from ui import chat_log as module
    formats = []

    class Block:
        def __init__(self):
            self.values = {}
        def setTopMargin(self, value):
            self.values['top'] = value
        def setBottomMargin(self, value):
            self.values['bottom'] = value
        def setAlignment(self, value):
            self.values['align'] = value
        def setLeftMargin(self, value):
            self.values['left'] = value
        def setRightMargin(self, value):
            self.values['right'] = value
        def setBackground(self, value):
            self.values['background'] = value
        def setProperty(self, key, value):
            self.values.setdefault('properties', {})[key] = value

    class Cursor:
        MoveOperation = types.SimpleNamespace(End=1)
        def hasSelection(self):
            return False
        def movePosition(self, _position):
            pass
        def setBlockFormat(self, value):
            formats.append(value.values)
        def charFormat(self):
            return types.SimpleNamespace(setForeground=lambda _value: None)
        def insertText(self, value, *_args):
            self.inserted = value

    monkeypatch.setattr(module, 'QTextBlockFormat', Block)
    log = module.LogWidget()
    cursor = Cursor()
    monkeypatch.setattr(log, 'textCursor', lambda: cursor)
    monkeypatch.setattr(log, 'viewport', lambda: types.SimpleNamespace(width=lambda: 400, update=lambda: None))
    monkeypatch.setattr(log, 'verticalScrollBar', lambda: types.SimpleNamespace(
        value=lambda: 0, maximum=lambda: 0, setValue=lambda _value: None))
    for tag in ('you', 'ai', 'sys'):
        log._tag, log._pos, log._text = tag, 0, '<unsafe>'
        log._step()
        assert cursor.inserted == '<'  # not interpreted as rich HTML
    assert formats[0]['left'] > formats[0]['right']
    assert formats[1]['right'] > formats[1]['left']
    assert all('background' not in fmt for fmt in formats)
    assert formats[0]['properties'][module.LogWidget._bubble_property] == 'you'
    assert formats[1]['properties'][module.LogWidget._bubble_property] == 'ai'
    assert formats[0]['properties'][module.LogWidget._message_property] != formats[1]['properties'][module.LogWidget._message_property]
    assert formats[0]['left'] == formats[1]['right'] == 130
    assert module.LogWidget._bubble_margin(140) == 0
    assert module.LogWidget._bubble_margin(300) == 90


def test_claw_changes_only_active_model_slider_and_loss_cancels(window, monkeypatch):
    import ui.hand_gesture as hand

    class Point:
        def __init__(self, x, y):
            self._x, self._y = x, y
        def x(self):
            return self._x
        def y(self):
            return self._y
        def __sub__(self, other):
            return Point(self._x - other._x, self._y - other._y)
        def manhattanLength(self):
            return abs(self._x) + abs(self._y)

    class Slider:
        def __init__(self):
            self.current = 20
        def isEnabled(self):
            return True
        def value(self):
            return self.current
        def setValue(self, value):
            self.current = max(0, min(100, value))

    monkeypatch.setattr(hand, 'QPoint', Point)
    monkeypatch.setattr(hand.QApplication, 'activeModalWidget', staticmethod(lambda: None), raising=False)
    monkeypatch.setattr(hand.QApplication, 'activePopupWidget', staticmethod(lambda: None), raising=False)
    monkeypatch.setattr(window, 'isActiveWindow', lambda: True)
    gestures = window._workspace_gestures
    gestures.reset()
    monkeypatch.setattr(gestures, 'show_cursors', lambda _samples: None)
    viewport = window._desktop_mdi.viewport()
    monkeypatch.setattr(viewport, 'width', lambda: 500)
    monkeypatch.setattr(viewport, 'height', lambda: 500)
    canvas = types.SimpleNamespace(height=lambda: 200)
    slider = Slider()
    viewer = types.SimpleNamespace(canvas=canvas, explode_slider=slider)
    sub = types.SimpleNamespace(isVisible=lambda: True)
    window._model_viewer = viewer
    window._desktop_windows['model_viewer'] = sub
    monkeypatch.setattr(window._desktop_mdi, 'activeSubWindow', lambda: sub)
    monkeypatch.setattr(gestures, '_hit', lambda _point: canvas)
    clock = [1.0]
    monkeypatch.setattr(hand.time, 'monotonic', lambda: clock[0])
    sample = lambda y: ((.5, y, False, False, True),)
    gestures.update(sample(.5))
    assert gestures.mode is None
    clock[0] += .41
    gestures.update(sample(.5))
    assert gestures.mode == 'claw'
    gestures.update(sample(.4))
    assert slider.value() > 20
    gestures.update(())
    assert gestures.mode is None
    previous = slider.value()
    monkeypatch.setattr(window._desktop_mdi, 'activeSubWindow', lambda: None)
    gestures.update(sample(.5))
    clock[0] += 1
    gestures.update(sample(.4))
    assert slider.value() == previous and gestures.mode is None


def test_editor_assistance_requires_consent_and_checks_revision(window_module, monkeypatch):
    import ui.editor_assist as assist
    from core.editor_assist import EditorRequest, revision, validate

    class Code:
        text = 'old code'
        _assist_token = 'tab-token'
        def toPlainText(self):
            return self.text
        def textCursor(self):
            return types.SimpleNamespace(SelectionType=types.SimpleNamespace(Document=1),
                                         select=lambda _selection: None,
                                         insertText=lambda value: setattr(self, 'text', value))
        def setTextCursor(self, _cursor):
            pass
    code = Code()
    editor = types.SimpleNamespace(_code=code, _path=None, _allowed=lambda _name: True,
                                   _tabs=types.SimpleNamespace(currentIndex=lambda: 0))
    sub = types.SimpleNamespace(_document=editor, isHidden=lambda: False, isMinimized=lambda: False)
    window = types.SimpleNamespace(_workspace_documents={'doc-1': ('code_editor', sub)},
                                   _desktop_mdi=types.SimpleNamespace(activeSubWindow=lambda: sub),
                                   _confirm_overlay=None, _hand_closing_confirm=False)
    decisions = {'approved': False, 'changed': False}

    class Box:
        StandardButton = types.SimpleNamespace(Yes=1, No=2)
        def __init__(self, _parent):
            pass
        def setWindowTitle(self, *_): pass
        def setTextFormat(self, *_): pass
        def setText(self, *_): pass
        def setDetailedText(self, *_): pass
        def setStandardButtons(self, *_): pass
        def setDefaultButton(self, *_): pass
        def reject(self): pass
        def exec(self):
            if decisions['changed']:
                code.text = 'user changed while reviewing'
            return 1 if decisions['approved'] else 2

    monkeypatch.setattr(assist, 'QMessageBox', Box)
    req = EditorRequest(validate('read', 'doc-1'))
    assist.execute(window, req)
    assert not req.wait(0)['ok']
    decisions['approved'] = True
    req = EditorRequest(validate('read', 'doc-1'))
    assist.execute(window, req)
    read = req.wait(0)
    assert read['code'] == 'old code' and read['revision'] == revision('old code', code._assist_token)
    req = EditorRequest(validate('replace', 'doc-1', 'new code', revision('old code', code._assist_token)))
    decisions['changed'] = True
    assist.execute(window, req)
    assert not req.wait(0)['ok'] and code.text == 'user changed while reviewing'
    decisions['changed'] = False
    req = EditorRequest(validate('replace', 'doc-1', 'new code', revision(code.text, code._assist_token)))
    assist.execute(window, req)
    assert req.wait(0)['ok'] and code.text == 'new code'
    req = EditorRequest(validate('replace', 'doc-1', 'other code', revision('stale')))
    assist.execute(window, req)
    assert not req.wait(0)['ok'] and code.text == 'new code'
    # Identical text in another file tab must never reuse a revision.
    other = Code()
    other.text, other._assist_token = code.text, 'different-tab'
    old_revision = revision(code.text, code._assist_token)
    editor._code = other
    req = EditorRequest(validate('replace', 'doc-1', 'wrong tab', old_revision))
    assist.execute(window, req)
    assert not req.wait(0)['ok'] and other.text == 'new code'


def test_multifile_editor_preserves_unsaved_tabs_and_save_targets(window_module, monkeypatch, tmp_path):
    import ui.creative as creative

    class Doc:
        def __init__(self):
            self.modified = False
            self.modificationChanged = _Signal()
        def isModified(self):
            return self.modified
        def setModified(self, value):
            self.modified = value
            self.modificationChanged.emit(value)

    class Code:
        def __init__(self):
            self.doc = Doc()
            self.cursorPositionChanged = _Signal()
            self.content = ''
            self.highlighter = types.SimpleNamespace(set_language=lambda _language: None)
        def document(self): return self.doc
        def setPlainText(self, value): self.content = value
        def toPlainText(self): return self.content
        def setAccessibleName(self, _value): pass
        def setFont(self, _value): pass
        def _update_gutter_width(self): pass
        def setPlaceholderText(self, _value): pass
        def deleteLater(self): pass
        def textCursor(self): return types.SimpleNamespace(blockNumber=lambda: 0, positionInBlock=lambda: 0)

    class Tabs:
        def __init__(self): self.tabs, self.active, self.names = [], -1, {}
        def addTab(self, code, _name):
            self.tabs.append(code)
            return len(self.tabs) - 1
        def setCurrentIndex(self, index): self.active = index
        def currentIndex(self): return self.active
        def widget(self, index): return self.tabs[index] if 0 <= index < len(self.tabs) else None
        def count(self): return len(self.tabs)
        def indexOf(self, code): return self.tabs.index(code)
        def removeTab(self, index):
            self.tabs.pop(index)
            self.active = min(self.active, len(self.tabs) - 1)
        def setTabText(self, index, text): self.names[index] = text
        def setTabToolTip(self, *_args): pass
        def setCurrentWidget(self, code): self.active = self.tabs.index(code)

    monkeypatch.setattr(creative, 'CodeEditor', Code)
    editor = creative.CreativeWorkspace.__new__(creative.CreativeWorkspace)
    editor._paths = {}
    editor._file_tabs = Tabs()
    editor._file_label = types.SimpleNamespace(setText=lambda _value: None)
    editor._editor_status = types.SimpleNamespace(setText=lambda _value: None)
    editor._output = types.SimpleNamespace(setPlainText=lambda _value: None)
    first = editor._add_code_tab('first', dirty=True)
    second = editor._add_code_tab('second', dirty=True)
    assert editor._code is second and first.toPlainText() == 'first'
    first_path, second_path = tmp_path / 'a.py', tmp_path / 'b.py'
    assert editor._write(str(second_path)) and second_path.read_text() == 'second'
    editor._file_tabs.setCurrentIndex(0)
    editor._select_file_tab(0)
    assert editor._code is first and editor._path is None
    assert not editor._write(str(second_path))  # cannot alias another tab
    assert editor._write(str(first_path)) and first_path.read_text() == 'first'
    first.document().setModified(True)
    monkeypatch.setattr(editor, '_confirm_discard', lambda code: code is not first)
    assert not editor._may_discard()
    editor._close_file_tab(0)
    assert editor._file_tabs.count() == 2  # declining keeps the tab
    monkeypatch.setattr(editor, '_confirm_discard', lambda _code: True)
    editor._close_file_tab(0)
    assert editor._code is second and editor._path == str(second_path)
    editor._close_file_tab(0)
    assert editor._file_tabs.count() == 1 and editor._code.toPlainText() == ''


def test_project_open_rejects_missing_and_outside_paths(window_module, tmp_path):
    from ui.creative import CreativeWorkspace
    from core.i18n import label
    project = tmp_path / 'project'
    project.mkdir()
    inside, outside = project / 'main.py', tmp_path / 'outside.py'
    inside.write_text('inside', encoding='utf-8')
    outside.write_text('outside', encoding='utf-8')
    opened, errors = [], []
    editor = types.SimpleNamespace(_project_root=project.resolve(),
                                   _open_path=lambda path: opened.append(path) or True,
                                   _output=types.SimpleNamespace(setPlainText=errors.append))
    assert CreativeWorkspace._open_project_path(editor, str(inside))
    assert opened == [str(inside.resolve())]
    assert not CreativeWorkspace._open_project_path(editor, str(outside))
    assert not CreativeWorkspace._open_project_path(editor, str(project / 'missing.py'))
    assert not CreativeWorkspace._open_project_path(editor, str(project))
    assert opened == [str(inside.resolve())]
    assert errors == [label('editor.project_outside')] * 3
    link = project / 'escape.py'
    try:
        link.symlink_to(outside)
    except OSError:
        pass  # Windows often requires elevated privileges to create symlinks.
    else:
        assert not CreativeWorkspace._open_project_path(editor, str(link))
        assert opened == [str(inside.resolve())]


def test_removed_canvas_route_refuses_legacy_requests(window_module):
    from ui.creative import open_workspace
    logs = []
    host = types.SimpleNamespace(write_log=logs.append,
                                 get_plugins=lambda: pytest.fail('legacy request must not open editor'))
    open_workspace(host, {'kind': 'creative_workspace', 'tab': 'canvas', 'prompt': 'example'})
    assert len(logs) == 1


def test_editor_dock_keeps_image_editor_but_not_ai_image(window):
    keys = [key for _, key in window._workspace_dock_actions]
    assert 'workspace.code' in keys and 'workspace.image' in keys
    assert 'workspace.ai_image' not in keys


def test_ssh_assistant_requires_approval_and_revalidates_session(window_module, monkeypatch):
    import ui.ssh_assist as assist
    from core.ssh_assist import SSHAssistRequest

    class Field:
        def __init__(self, value=''): self.value = value
        def text(self): return self.value
        def setText(self, value): self.value = value
        def clear(self): self.value = ''
    commands = []
    tab = types.SimpleNamespace(session=object(), generation=1, _assist_session='a'*32,
                                _share_output=False, _shared_output='private', _status_key='ssh.connected', connected=True, busy=False,
                                command=Field(), user=Field('alice'), host=Field('server'),
                                port=types.SimpleNamespace(value=lambda: 22),
                                _start_approved_command=lambda *args: commands.append(args))
    tabs = types.SimpleNamespace(currentWidget=lambda: tab)
    sub = types.SimpleNamespace(_document=types.SimpleNamespace(tabs=tabs), isHidden=lambda: False,
                                isMinimized=lambda: False)
    window = types.SimpleNamespace(_workspace_documents={'doc-1': ('ssh_manager', sub)},
                                   _desktop_mdi=types.SimpleNamespace(activeSubWindow=lambda: sub),
                                   _confirm_overlay=None, _hand_closing_confirm=False)
    decision = {'yes': False, 'change': False}
    class Box:
        StandardButton = types.SimpleNamespace(Yes=1, No=2)
        def __init__(self, _parent): pass
        def setWindowTitle(self, *_): pass
        def setTextFormat(self, *_): pass
        def setText(self, *_): pass
        def setStandardButtons(self, *_): pass
        def setDefaultButton(self, *_): pass
        def reject(self): pass
        def exec(self):
            if decision['change']:
                tab.session = object()
                tab.generation += 1
            return 1 if decision['yes'] else 2
    monkeypatch.setattr(assist, 'QMessageBox', Box)
    monkeypatch.setattr(assist, 'allowed', lambda _host: True)
    monkeypatch.setattr(assist.QApplication, 'activeModalWidget', staticmethod(lambda: None), raising=False)
    monkeypatch.setattr(assist.QApplication, 'activePopupWidget', staticmethod(lambda: None), raising=False)
    def request(action, **kwargs):
        req = SSHAssistRequest({'action': action, 'target': 'doc-1', **kwargs})
        assist.execute(window, req)
        return req.wait(0)
    inspect = request('inspect')
    assert inspect['ok'] and not inspect['sharing'] and 'output' not in inspect
    tab._share_output = True
    assert request('inspect')['output'] == 'private'
    assert not request('execute', session='a'*32, command='pwd')['ok'] and not commands
    assert tab.command.text() == 'pwd'  # declined draft remains visible, not executed
    tab.command.clear()
    decision.update(yes=True, change=True)
    assert not request('execute', session='a'*32, command='pwd')['ok'] and not commands
    tab.command.clear()
    decision['change'] = False
    assert not request('execute', session='b'*32, command='pwd')['ok'] and not commands
    result = request('execute', session='a'*32, command='pwd')
    assert result['ok'] and 'not yet confirmed' in result['message']
    assert len(commands) == 1 and commands[0][0] == 'pwd'
    tab.command.setText('my draft')
    assert not request('execute', session='a'*32, command='pwd')['ok']
    assert tab.command.text() == 'my draft' and len(commands) == 1


def test_ssh_output_sharing_is_explicit_revocable_and_session_scoped(window_module, monkeypatch):
    import ui.ssh_manager as ssh
    tab = ssh.SSHTab.__new__(ssh.SSHTab)
    tab._share_output, tab._shared_output, tab._assist_session = False, 'old data', 'a'*32
    tab.connected, tab.busy, tab.generation, tab.session = True, False, 1, object()
    tab.host_app = object()
    tab._update_sharing = lambda: None
    tab._set_status = lambda _key: None
    tab._sync = lambda: None
    tab.secret = types.SimpleNamespace(clear=lambda: None)
    tab.state_changed = types.SimpleNamespace(emit=lambda: None)
    tab.session = types.SimpleNamespace(request_close=lambda: None)
    monkeypatch.setattr(ssh, 'allowed', lambda _host: True)
    yes_no = types.SimpleNamespace(Yes=1, No=2)
    decision = [2]
    monkeypatch.setattr(ssh, 'QMessageBox', types.SimpleNamespace(StandardButton=yes_no,
                                                                 question=lambda *_args: decision[0]))
    tab.toggle_sharing()
    assert not tab._share_output and tab._shared_output == 'old data'
    decision[0] = 1
    tab.toggle_sharing()
    assert tab._share_output and tab._shared_output == ''
    class Output:
        def __init__(self): self.text = ''
        def appendPlainText(self, text): self.text += text + '\n'
        def toPlainText(self): return self.text
        def setPlainText(self, text): self.text = text
    tab.output = Output()
    tab._on_command(1, (b'result', 0, 'finished'))
    assert 'result' in tab._shared_output
    tab.toggle_sharing()
    assert not tab._share_output and tab._shared_output == ''
    tab._on_command(1, (b'private', 0, 'finished'))
    assert tab._shared_output == ''
    tab._share_output, tab._shared_output = True, 'secret'
    tab.disconnect_session()
    assert not tab._share_output and tab._shared_output == '' and tab._assist_session == ''
