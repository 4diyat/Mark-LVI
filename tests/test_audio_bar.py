"""The audio bar, actually executed — with a stand-in for Qt and a fake player.

WHY EXECUTE IT AT ALL
    `tests/test_playback.py` checks the rules and `tests/test_video_wiring.py`
    checks that the window still consults them. Neither of those runs
    `ui/audio.py`, so neither would notice the failure this bar actually has:
    a slot that raises because an attribute was named differently, a `QUrl`
    built from the wrong thing, a loop that restarts the wrong player. Those are
    `AttributeError` and `TypeError` lines in the log file, not rules.

    So the mixin is loaded by PATH (past `ui/__init__.py`, which pulls in the
    whole 7,000-line window) with a minimal Qt in `sys.modules`, and a fake
    QMediaPlayer records what the bar asked of it. What this cannot prove is that
    a codec decodes a file — that needs a codec, and no test has one.

WHY THE STUB IS REMOVED AFTERWARDS
    A stub left in `sys.modules` shadows the real Qt for every test that runs
    later; the first version of tests/test_avatar_paint.py did exactly that and
    made an unrelated import fail. The fixture restores what it found.
"""
from __future__ import annotations

import sys
import types
from pathlib import Path

import pytest

AUDIO = Path(__file__).resolve().parent.parent / "ui" / "audio.py"


# ── a minimal Qt ────────────────────────────────────────────────────────────

class _Signal:
    def __init__(self):
        self.slots = []

    def connect(self, fn):
        self.slots.append(fn)

    def emit(self, *a):
        for s in self.slots:
            s(*a)


class FakePlayer:
    """Records the calls the bar makes. Deliberately records, not prints."""

    def __init__(self):
        self.state = "stopped"
        self.pos = 0
        self.source = None
        self.mediaStatusChanged = _Signal()
        self.errorOccurred = _Signal()

    def setSource(self, url):
        self.source = url

    def play(self):
        self.state = "playing"

    def pause(self):
        self.state = "paused"

    def stop(self):
        self.state = "stopped"
        self.pos = 0

    def position(self):
        return self.pos

    def setPosition(self, p):
        self.pos = p

    def playbackState(self):
        return self.state

    def errorString(self):
        return "a codec this machine does not have"


class FakeOutput:
    def __init__(self):
        self.muted = False
        self.volume_value = 1.0
        self.device = None

    def setMuted(self, m):
        self.muted = m

    def isMuted(self):
        return self.muted

    def setVolume(self, v):
        self.volume_value = v

    def volume(self):
        return self.volume_value

    def setDevice(self, d):
        self.device = d


class FakeDevice:
    """A Qt audio output, described the way the AUDIO DEVICES panel names it."""

    def __init__(self, description):
        self._desc = description

    def description(self):
        return self._desc

    def isNull(self):
        return False

    def id(self):
        return b"qt:" + self._desc.encode()


class _Widget:
    def __init__(self, *a, **k):
        self.visible = False
        self.text = ""
        self.parent = None

    # Real, not a catch-all lambda: the bar asks its parent whether it is the
    # splitter before touching splitter geometry, and a `__getattr__` that
    # answered None would make that branch untestable.
    def parentWidget(self):
        return self.parent

    def setParent(self, p):
        self.parent = p

    def __getattr__(self, name):
        if name.startswith("__"):
            raise AttributeError(name)
        return lambda *a, **k: None

    def show(self):
        self.visible = True

    def hide(self):
        self.visible = False

    def setText(self, t):
        self.text = t

    def blockSignals(self, _b):
        pass

    def setValue(self, v):
        self._value = v


def _install_qt() -> list[str]:
    """Only when the real Qt is unusable here; returns what was added."""
    try:
        import PyQt6.QtGui  # noqa: F401
        return []
    except Exception:
        pass

    core = types.ModuleType("PyQt6.QtCore")

    class QUrl:
        """`fromLocalFile` included because the window now uses it — the API
        has it, and a stub without it hid the fact that QUrl(path) is wrong."""

        def __init__(self, url=""):
            self._url = str(url)
            self._local = False

        @staticmethod
        def fromLocalFile(path):
            u = QUrl(path)
            u._local = True
            return u

        def toString(self):
            return self._url

        def isLocalFile(self):
            return self._local

        def scheme(self):
            if self._local:
                return "file"
            if self._url.lower().startswith(("http://", "https://", "file://")):
                return self._url.split(":", 1)[0].lower()
            return ""

    core.QUrl = QUrl
    core.Qt = types.SimpleNamespace(
        Orientation=types.SimpleNamespace(Horizontal=1),
        PenStyle=types.SimpleNamespace(NoPen=0),
        BrushStyle=types.SimpleNamespace(NoBrush=1),
    )
    gui = types.ModuleType("PyQt6.QtGui")

    class _Colour:
        def __init__(self, *a):
            self._rgb = (0, 0, 0)

        def red(self):
            return 0

        def green(self):
            return 0

        def blue(self):
            return 0

        def rgb(self):
            return 0

    class _Font:
        def __init__(self, *a, **k):
            pass

        class Weight:
            Bold = 1
            Normal = 0

    gui.QColor = _Colour
    gui.QFont = _Font
    gui.QPalette = _Widget

    widgets = types.ModuleType("PyQt6.QtWidgets")
    for name in ("QApplication", "QHBoxLayout", "QLabel", "QSlider", "QWidget",
                 "QVBoxLayout", "QPushButton", "QFrame"):
        setattr(widgets, name, _Widget)

    mm = types.ModuleType("PyQt6.QtMultimedia")
    mm.QMediaPlayer = FakePlayer
    mm.QAudioOutput = FakeOutput
    # NO `fromId`: PyQt6's QAudioDevice has no such method, and a fake that
    # offered one let the window call it and silently lose the setting.
    mm.QAudioDevice = type("QAudioDevice", (), {"description": lambda self: "",
                                               "isNull": lambda self: False})
    mm.QMediaDevices = types.SimpleNamespace(
        audioOutputs=lambda: [FakeDevice("My Headset"), FakeDevice("Speakers")])

    pkg = types.ModuleType("PyQt6")
    pkg.QtCore, pkg.QtGui = core, gui
    pkg.QtWidgets, pkg.QtMultimedia = widgets, mm

    added = []
    for name, mod in (("PyQt6", pkg), ("PyQt6.QtCore", core), ("PyQt6.QtGui", gui),
                      ("PyQt6.QtWidgets", widgets), ("PyQt6.QtMultimedia", mm)):
        sys.modules[name] = mod
        added.append(name)

    # A stub `ui` PACKAGE whose __init__ does nothing: importing `ui.audio`
    # through the real package drags in ui/window.py, and this test needs one
    # mixin, not the window.
    ui_pkg = types.ModuleType("ui")
    ui_pkg.__path__ = [str(AUDIO.parent)]
    sys.modules["ui"] = ui_pkg
    added.append("ui")
    return added


@pytest.fixture(scope="module")
def audio_module():
    added = _install_qt()
    for name in ("ui.audio", "ui.theme"):
        sys.modules.pop(name, None)
    import ui.audio as mod
    try:
        yield mod
    finally:
        for name in added:
            sys.modules.pop(name, None)
        sys.modules.pop("ui.audio", None)
        sys.modules.pop("ui.theme", None)


def make_host(mixin):
    """Just enough of MainWindow for the mixin: the widgets it owns, and a log.

    Built as a real subclass. An earlier version swapped `self.__class__` after
    the fact, which quietly dropped every method defined on the class doing the
    swapping — the fixture failed, not the code, and in a way that looked like
    the code was wrong.
    """

    class Host(mixin):
        def __init__(self):
            self._audio_player = FakePlayer()
            self._audio_out = FakeOutput()
            self._audio_lbl = _Widget()
            self._audio_pause_btn = _Widget()
            self._audio_loop_btn = _Widget()
            self._audio_vol = _Widget()
            self._audio_cont = _Widget()
            self._audio_on = False
            self._audio_paused = False
            self._audio_loop = False
            self.logs = []

        def write_log(self, message):
            self.logs.append(message)

        def _status_word(self, status):
            # The real window translates Qt's enums here; the fake player
            # already speaks the words, which is the whole point of that
            # translation living in one method.
            return str(status)

    return Host()


@pytest.fixture()
def bar(audio_module):
    host = make_host(audio_module.AudioMixin)
    host._audio_player.mediaStatusChanged.connect(host._on_audio_status)
    host._audio_player.errorOccurred.connect(host._on_audio_error)
    return host


# ── playing ─────────────────────────────────────────────────────────────────

def test_opening_audio_shows_the_bar_and_starts_the_player(bar):
    bar._on_audio_open("https://cdn.example/a.m4a", "My Song", 0.5, False)

    assert bar._audio_cont.visible
    assert bar._audio_player.state == "playing"
    assert bar._audio_out.volume_value == pytest.approx(0.5)
    assert bar.audio_is_playing() is True
    assert "My Song" in bar._audio_lbl.text


def test_volume_is_applied_to_the_output_not_just_remembered(bar):
    """A slider that moves without changing the sound is the bug people report
    as "the volume does nothing"."""
    bar._on_audio_open("a.mp3", "A", 0.7, False)
    bar._on_audio_volume_slider(30)
    assert bar._audio_out.volume_value == pytest.approx(0.30)


def test_pausing_is_not_playing(bar):
    """`audio_is_playing()` answers the tool. A paused song that still answers
    yes makes the model say "it is playing" over silence."""
    bar._on_audio_open("a.mp3", "A", 0.7, False)
    bar._on_audio_pause(True)
    assert bar._audio_player.state == "paused"
    assert bar.audio_is_playing() is False
    assert "RESUME" in bar._audio_pause_btn.text

    bar._on_audio_pause(False)
    assert bar._audio_player.state == "playing"
    assert bar.audio_is_playing() is True


def test_the_toggle_button_goes_both_ways(bar):
    bar._on_audio_open("a.mp3", "A", 0.7, False)
    bar._toggle_audio_pause()
    assert bar._audio_paused is True
    bar._toggle_audio_pause()
    assert bar._audio_paused is False


def test_the_loop_switch_changes_the_button(bar):
    bar._on_audio_open("a.mp3", "A", 0.7, False)
    assert "REPEAT" in bar._audio_loop_btn.text
    bar._toggle_audio_loop()
    assert bar._audio_loop is True
    assert "REPEATING" in bar._audio_loop_btn.text


# ── finishing and failing ───────────────────────────────────────────────────

def test_a_finished_song_closes_the_bar(bar):
    bar._on_audio_open("a.mp3", "A", 0.7, False)
    bar._on_audio_status("ended")
    assert not bar._audio_cont.visible
    assert bar.audio_is_playing() is False
    assert any("finished" in m.lower() for m in bar.logs)


def test_a_looped_song_starts_again_instead_of_stopping(bar):
    """Someone playing background music asked for it to keep going; closing the
    bar on each repeat would make the feature useless for its main use."""
    bar._on_audio_open("a.mp3", "A", 0.7, True)
    bar._audio_player.pos = 42_000
    bar._on_audio_status("ended")

    assert bar._audio_cont.visible, "the bar closed on a looped track"
    assert bar._audio_player.pos == 0, "it did not go back to the start"
    assert bar._audio_player.state == "playing"


def test_a_failure_is_reported_and_the_bar_closes(bar):
    """A bar that stays open over silence is indistinguishable from one that is
    playing quietly, and the user has no way to tell."""
    bar._on_audio_open("a.mp3", "A", 0.7, False)
    bar._on_audio_error()
    assert not bar._audio_cont.visible
    assert any("could not be played" in m.lower() for m in bar.logs)


def test_an_invalid_source_is_treated_as_a_failure(bar):
    bar._on_audio_open("a.mp3", "A", 0.7, False)
    bar._on_audio_status("invalid")
    assert not bar._audio_cont.visible


def test_stopping_gives_the_splitter_its_height_back(bar):
    """A song must not leave the window permanently 40 px shorter."""
    class _Split:
        def __init__(self):
            self._sizes = [600, 200, 0, 40]
            self.set_calls = []

        def sizes(self):
            return list(self._sizes)

        def setSizes(self, s):
            self._sizes = list(s)
            self.set_calls.append(list(s))

    split = _Split()
    bar._center_split = split
    # The bar must look like it lives in that splitter.
    # `parentWidget()` must answer the splitter, because that is the condition
    # the real code checks before touching splitter geometry.
    bar._audio_cont.setParent(split)
    bar._on_audio_open("a.mp3", "A", 0.7, False)
    bar._on_audio_stop()

    assert split.sizes()[3] == 0, "the bar's height was not released"
    assert split.sizes()[0] > 600, "the height did not go back to the HUD"


def test_stopping_closes_the_bar_and_latches_off(bar):
    bar._on_audio_open("a.mp3", "A", 0.7, False)
    bar._on_audio_stop()
    assert bar._audio_player.state == "stopped"
    assert not bar._audio_cont.visible
    assert bar.audio_is_playing() is False


# ── the device ──────────────────────────────────────────────────────────────

def test_the_chosen_output_device_is_used(bar, monkeypatch):
    """The user picks a speaker in AUDIO DEVICES. A song from the laptop while
    their headset sits silent is exactly the complaint that panel exists for."""
    import core.audio_devices as real_devices
    import memory.config_manager as real_config

    calls = []
    monkeypatch.setattr(real_devices, "resolve",
                        lambda name, kind: (calls.append((name, kind)) or 7))
    monkeypatch.setattr(real_config, "get_output_device", lambda: "My Headset")

    bar._apply_audio_device()

    assert calls == [("My Headset", "output")]
    # The device Qt was actually handed must be the one the user picked. A
    # `.description()` check, because sounddevice indices and Qt device ids are
    # two different spaces and the name is the only thing they share.
    assert bar._audio_out.device is not None
    assert bar._audio_out.device.description() == "My Headset"


def test_an_unresolvable_device_does_not_stop_playback(bar, monkeypatch):
    """Falling back to the system default is what would have happened anyway;
    raising here would turn a missing speaker into a failed song."""
    import core.audio_devices as real_devices
    import memory.config_manager as real_config

    def explode(_name, _kind):
        raise RuntimeError("no such device")

    monkeypatch.setattr(real_devices, "resolve", explode)
    monkeypatch.setattr(real_config, "get_output_device", lambda: "Ghost")

    bar._apply_audio_device()
    bar._on_audio_open("a.mp3", "A", 0.7, False)
    assert bar._audio_player.state == "playing"


def test_a_403_audio_stream_tries_backup_then_searches_alternative(bar):
    exhausted = []
    bar._on_audio_open(
        "https://cdn.example/bad.m4a",
        "My Song",
        0.5,
        False,
        fallbacks=["https://cdn.example/backup.webm"],
        on_exhausted=lambda reason: (exhausted.append(reason) or True),
    )
    bar._on_audio_error(1, "server replied: Forbidden (403)")
    assert bar._audio_cont.visible is True
    assert bar._audio_player.source.toString() == "https://cdn.example/backup.webm"
    assert bar._audio_player.state == "playing"

    # Backup also returns 403 -> triggers alternative search and closes bar.
    bar._on_audio_error(1, "403 Forbidden")
    assert exhausted == ["403 Forbidden"]
    assert bar._audio_cont.visible is False

