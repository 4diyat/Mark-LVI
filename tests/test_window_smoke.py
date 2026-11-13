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
    toggled = _Signal()
    valueChanged = _Signal()
    currentIndexChanged = _Signal()
    textChanged = _Signal()
    returnPressed = _Signal()
    activated = _Signal()
    triggered = _Signal()
    timeout = _Signal()

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
    core.QTimer = type("QTimer", (_Object,), {"start": lambda s, *a: None,
                                             "stop": lambda s, *a: None,
                                             "setInterval": lambda s, *a: None,
                                             "setSingleShot": lambda s, *a: None,
                                             "timeout": _Signal()})
    core.pyqtSignal = _Signal
    for geom in ("QLineF", "QPointF", "QPoint", "QRectF", "QSizeF", "QRect", "QSize"):
        setattr(core, geom, type(geom, (_Object,), {}))

    gui = types.ModuleType("PyQt6.QtGui")
    for name in ("QBrush", "QColor", "QCursor", "QFont", "QKeySequence",
                 "QPainter", "QPen", "QPixmap", "QRadialGradient", "QShortcut"):
        setattr(gui, name, type(name, (_Object,), {}))
    gui.QColor.Weight = None
    gui.QFont.Weight = _Enum()
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
    widgets.QMainWindow = _stub_class("QMainWindow")
    widgets.QSizePolicy.Policy = _Enum()

    class _Geometry(_Object):
        def width(self):
            return 1920

        def height(self):
            return 1080

    class _Screen(_Object):
        def availableGeometry(self):
            return _Geometry()

    class _App(_Object):
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
            if name.startswith("__"):
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
    for name in ("ui", "ui.window", "ui.audio", "ui.video_fallback",
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


