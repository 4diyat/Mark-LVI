"""
Push-to-talk — hold a key, speak, release.

Why this exists
---------------
Wake-word is hands-free but it is not always what you want: in a meeting, in a
noisy room, or when you simply do not feel like saying a name out loud, a key
you hold is faster and never mishears. It is also the natural way to use the
assistant while another window has focus.

How it works, and what it costs
-------------------------------
Zero new dependencies, and a real global hook on all three desktops:

* **Windows** — `GetAsyncKeyState` polled from one small thread. This is
  deliberately *not* `RegisterHotKey`, which only reports a press: push-to-talk
  needs the release too. Polling two virtual-key codes 30 times a second is a
  rounding error of CPU and needs no message loop.
* **Linux (X11)** — `XQueryKeymap` through the Xlib that is already on the
  machine, polled on the same thread. Wayland has no equivalent, so a Wayland
  session reports `window` and the Qt shortcut carries it.
* **macOS** — `CGEventSourceKeyState` from ApplicationServices, again on the
  same thread. It reports nothing without Accessibility permission, so a user
  who has not granted it gets `window` rather than a silent no-op.

The class never raises. If the platform hook cannot be installed it reports
`scope == "window"` and the Qt shortcut carries it — and `ui/lifecycle.py` knows
that in ambient mode there is no window to focus, which is why the scope is
reported rather than assumed.

WHY THE PROBE IS SEPARATE FROM THE LOOP
    This used to be `if _OS == "Windows"` inside `start()`, with the polling
    logic welded to `ctypes.windll.user32`. That made the one thing worth
    testing — the debounce, and what happens when a key vanishes mid-press —
    reachable only by calling `_set_held` directly, which skips the loop
    entirely. The loop is now source-agnostic: `_Source` implementations answer
    "is the chord down right now", and everything above that is tested with a
    fake source, on any machine, with no keyboard.
"""

from __future__ import annotations

import platform
import threading
import time
from typing import Callable, Sequence

_OS = platform.system()

# The default chord. Ctrl+Space is free in most desktop environments and is the
# same finger shape on every keyboard layout, which matters for a worldwide app.
DEFAULT_CHORD = ("ctrl", "space")

# Key codes per platform. Three tables rather than one, because the three
# systems agree on nothing: Windows uses virtual-key codes, X11 divides the
# keyboard at runtime through a keysym table, and macOS has its own kVK_*
# numbering that shares digits with neither.
_VK = {
    "ctrl": 0x11, "shift": 0x10, "alt": 0x12,
    "space": 0x20, "f8": 0x77, "f9": 0x78, "f10": 0x79,
    "capslock": 0x14, "insert": 0x2D,
    # `g` exists for exactly one chord: the gesture pause on board 6
    # (`Ctrl+Alt+G`, printed in the artboard's footnote). It is the ASCII code,
    # which is also the virtual-key code on Windows.
    "g": 0x47,
}

_X11_KEYSYM = {
    "ctrl": "Control_L", "shift": "Shift_L", "alt": "Alt_L",
    "space": "space", "f8": "F8", "f9": "F9", "f10": "F10",
    "capslock": "Caps_Lock", "insert": "Insert", "g": "g",
}

# kVK_* from <HIToolbox/Events.h>. The right-hand modifiers are deliberately not
# accepted: a chord that only works with the right Ctrl is a chord nobody
# discovers.
_MAC_KEYCODE = {
    "ctrl": 0x3B, "shift": 0x38, "alt": 0x3A,
    "space": 0x31, "f8": 0x64, "f9": 0x65, "f10": 0x67,
    "capslock": 0x39, "insert": 0x72,
    # kVK_ANSI_G. Board 6's pause chord, and the one letter this table needs.
    "g": 0x05,
}

# Qt key sequence text for the same chord, used by the windowed fallback.
_QT_NAME = {"ctrl": "Ctrl", "shift": "Shift", "alt": "Alt", "space": "Space",
            "f8": "F8", "f9": "F9", "f10": "F10",
            "capslock": "CapsLock", "insert": "Ins", "g": "G"}

_POLL_HZ = 30.0
# A key has to be down this long before we call it speech. It stops a stray
# brush of the chord from opening the microphone.
_DEBOUNCE_S = 0.06


def chord_label(chord=DEFAULT_CHORD) -> str:
    """Human-readable name of the chord, for the UI and the logs."""
    return "+".join(_QT_NAME.get(k, k.title()) for k in chord)


def qt_sequence(chord=DEFAULT_CHORD) -> str:
    """The same chord as a QKeySequence string."""
    return "+".join(_QT_NAME.get(k, k.title()) for k in chord)


# ── key-state sources ────────────────────────────────────────────────────────

class _Source:
    """Answers one question: is the whole chord down right now?

    `open()` reports whether this platform can answer it at all. It is allowed
    to raise — `make_source()` turns that into "no source", which is the honest
    answer — but `down()` is called 30 times a second and its exceptions stop
    the watcher rather than being swallowed, because a driver that fails once
    per frame will fail forever.
    """

    name = "none"

    def open(self) -> bool:
        raise NotImplementedError

    def close(self) -> None:
        """Release anything `open()` acquired. Safe to call twice."""

    def down(self) -> bool:
        raise NotImplementedError


class _WindowsSource(_Source):
    name = "windows"

    def __init__(self, codes: Sequence[int]):
        self._codes = list(codes)
        self._user32 = None

    def open(self) -> bool:
        import ctypes
        self._user32 = ctypes.windll.user32
        # Touch the call so a machine without it fails HERE, in `open()`, where
        # the answer is "no global hook" rather than once per frame later.
        self._user32.GetAsyncKeyState(0)
        return True

    def down(self) -> bool:
        # The high bit of the return value is "currently down".
        return all(self._user32.GetAsyncKeyState(c) & 0x8000 for c in self._codes)


class _X11Source(_Source):
    """XQueryKeymap: a 32-byte bitmap of every key currently held.

    Keysyms have to be resolved to keycodes on the open display, because the
    mapping is per-layout and per-machine. Doing it once at `open()` is the
    point of having `open()` at all.
    """

    name = "x11"

    def __init__(self, keysyms: Sequence[str], display=None):
        self._keysyms = list(keysyms)
        self._display = display
        self._lib = None
        self._codes: list[int] = []

    def open(self) -> bool:
        import ctypes
        lib = None
        for candidate in ("libX11.so.6", "libX11.so"):
            try:
                lib = ctypes.cdll.LoadLibrary(candidate)
                break
            except OSError:
                continue
        if lib is None:
            return False              # no Xlib: not an X11 desktop at all
        lib.XOpenDisplay.restype = ctypes.c_void_p
        lib.XOpenDisplay.argtypes = [ctypes.c_char_p]
        display = lib.XOpenDisplay(self._display)
        if not display:
            # Wayland, or no DISPLAY. libX11 is present on most Linux machines
            # regardless, so this — not the LoadLibrary above — is the check
            # that actually distinguishes X11 from everything else.
            return False
        lib.XStringToKeysym.restype = ctypes.c_ulong
        lib.XStringToKeysym.argtypes = [ctypes.c_char_p]
        lib.XKeysymToKeycode.restype = ctypes.c_ubyte
        lib.XKeysymToKeycode.argtypes = [ctypes.c_void_p, ctypes.c_ulong]

        codes = []
        for name in self._keysyms:
            keysym = lib.XStringToKeysym(name.encode())
            if not keysym:
                self._close_display(lib, display)
                return False
            code = lib.XKeysymToKeycode(display, keysym)
            if not code:
                # The keysym exists in the table but is not on this keyboard
                # layout. Reported as "no global hook", which is the truth for
                # this chord on this machine.
                self._close_display(lib, display)
                return False
            codes.append(int(code))

        self._lib, self._display, self._codes = lib, display, codes
        return True

    @staticmethod
    def _close_display(lib, display) -> None:
        """Give back a display opened for a probe that is not going to be used.

        Every early return from `open()` used to leak one. Twenty attempts at
        enabling a chord the layout does not have would leave twenty open
        connections to the X server.
        """
        try:
            if hasattr(lib, "XCloseDisplay"):
                lib.XCloseDisplay(display)
        except Exception as e:                          # noqa: BLE001
            print(f"[JARVIS] Push-to-talk: could not close a probe display — "
                  f"{type(e).__name__}: {e}")

    def close(self) -> None:
        if self._lib is not None and self._display:
            try:
                self._lib.XCloseDisplay(self._display)
            except Exception as e:                      # noqa: BLE001
                # A display that will not close is a leak, not a crash; the
                # process is usually on its way out. Worth one line.
                print(f"[JARVIS] Push-to-talk: XCloseDisplay failed — "
                      f"{type(e).__name__}: {e}")
        self._lib = None
        self._display = None

    def down(self) -> bool:
        import ctypes
        # XQueryKeymap takes a `char[32]` and FILLS IT; it does not return one.
        # Handing it an immutable bytes object, as an earlier draft did, either
        # raises or leaves the buffer empty — in both cases every frame reads
        # "up" and push-to-talk silently never fires on Linux.
        buf = (ctypes.c_char * 32)()
        ctypes.memset(buf, 0, 32)
        ok = self._lib.XQueryKeymap(self._display, buf)
        if not ok:
            return False              # the server refused; treat as "up"
        keys = bytes(buf)             # copy before indexing
        for code in self._codes:
            if not (keys[code // 8] >> (code % 8)) & 1:
                return False
        return True


class _MacSource(_Source):
    name = "quartz"

    def __init__(self, keycodes: Sequence[int]):
        self._codes = list(keycodes)
        self._app = None

    def open(self) -> bool:
        import ctypes, ctypes.util
        path = ("/System/Library/Frameworks/ApplicationServices.framework/"
                "ApplicationServices")
        try:
            app = ctypes.cdll.LoadLibrary(path)
        except OSError:
            return False
        if not hasattr(app, "CGEventSourceKeyState"):
            return False
        app.CGEventSourceKeyState.restype = ctypes.c_bool
        app.CGEventSourceKeyState.argtypes = [ctypes.c_int32, ctypes.c_uint16]
        self._app = app
        return True

    def down(self) -> bool:
        # 0 == kCGEventSourceStateCombinedSessionState, which sees keys held in
        # any application. Without Accessibility permission this returns False
        # for everything, which is why `scope` is reported rather than promised.
        return all(self._app.CGEventSourceKeyState(0, code) for code in self._codes)


def make_source(chord=DEFAULT_CHORD, os_name: str | None = None) -> "_Source | None":
    """The key-state source for this machine and this chord, or None.

    Returns an UNOPENED source: `open()` is the part that can be slow, can need
    a display, and can fail. Callers decide what "no source" means — for
    push-to-talk it means the windowed shortcut, which is a real answer.
    """
    os_name = os_name or _OS
    chord = tuple(chord)
    if os_name == "Windows":
        if not all(k in _VK for k in chord):
            return None
        return _WindowsSource([_VK[k] for k in chord])
    if os_name == "Darwin":
        if not all(k in _MAC_KEYCODE for k in chord):
            return None
        return _MacSource([_MAC_KEYCODE[k] for k in chord])
    # Everything else is assumed to be an X11 desktop until proven otherwise:
    # `open()` fails on a Wayland session or with no DISPLAY, and the caller
    # falls back to the window. Assuming Windows would be a much worse guess.
    if not all(k in _X11_KEYSYM for k in chord):
        return None
    return _X11Source([_X11_KEYSYM[k] for k in chord])


class PushToTalk:
    """Calls `on_change(held: bool)` whenever the chord is pressed or released.

    Start it once; it is safe to start and stop repeatedly, and safe to stop a
    detector that never started.

    `source` is for tests and for callers that already know which probe to use;
    leave it None and `make_source()` decides.
    """

    def __init__(self, on_change: Callable[[bool], None], chord=DEFAULT_CHORD,
                 source: "_Source | None" = None, os_name: str | None = None):
        self._on_change = on_change
        self._chord = tuple(chord)
        self._given_source = source
        self._os_name = os_name
        self._source = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._held = False
        self._scope = "window"

    # ── state ───────────────────────────────────────────────────────────────

    @property
    def held(self) -> bool:
        return self._held

    @property
    def scope(self) -> str:
        """'global' once a system-wide hook is running, else 'window'."""
        return self._scope

    @property
    def source_name(self) -> str:
        """Which platform probe is in use ('windows', 'x11', 'quartz'), or ''."""
        return self._source.name if self._source is not None else ""

    @property
    def label(self) -> str:
        return chord_label(self._chord)

    # ── lifecycle ───────────────────────────────────────────────────────────

    def start(self) -> str:
        """Begin watching. Returns the scope actually achieved."""
        self.stop()
        self._stop.clear()

        source = self._given_source or make_source(self._chord, self._os_name)
        if source is not None and self._open(source):
            self._scope = "global"
            self._thread = threading.Thread(
                target=self._poll_loop, args=(source,),
                name="push-to-talk", daemon=True)
            self._thread.start()
        else:
            self._scope = "window"
        return self._scope

    def _open(self, source: "_Source") -> bool:
        """Open a source, treating any failure as "this platform cannot"."""
        try:
            return bool(source.open())
        except Exception as e:                          # noqa: BLE001
            # Not silent: a probe that fails on a machine where it should work
            # is the difference between "no global hook here" and "a bug", and
            # the log is the only place that distinction survives.
            print(f"[JARVIS] Push-to-talk: {source.name} probe failed — "
                  f"{type(e).__name__}: {e}")
            return False

    def stop(self) -> None:
        self._stop.set()
        t, self._thread = self._thread, None
        if t is not None and t.is_alive():
            t.join(timeout=1.0)
        source, self._source = self._source, None
        if source is not None:
            try:
                source.close()
            except Exception as e:                      # noqa: BLE001
                print(f"[JARVIS] Push-to-talk: close failed — "
                      f"{type(e).__name__}: {e}")
        self._set_held(False)

    # ── the windowed fallback drives this directly ──────────────────────────

    def set_held(self, held: bool) -> None:
        """Feed a press/release from a Qt shortcut (no global hook available)."""
        self._set_held(bool(held))

    # ── internals ───────────────────────────────────────────────────────────

    def _set_held(self, held: bool) -> None:
        if held == self._held:
            return
        self._held = held
        try:
            self._on_change(held)
        except Exception as e:                          # noqa: BLE001
            # A listener fault must never kill the watcher — but a watcher that
            # reports presses nobody hears is indistinguishable from a broken
            # key, so the failure is said out loud.
            print(f"[JARVIS] Push-to-talk: listener failed — "
                  f"{type(e).__name__}: {e}")

    def _poll_loop(self, source: "_Source") -> None:
        """Poll the source, apply the debounce, report transitions.

        Separated from which source it is: this is the part with the rules in
        it (a stray brush must not open the mic; a key that vanishes must still
        report a release), and it is the part a test can drive.
        """
        self._source = source
        period = 1.0 / _POLL_HZ
        down_since = 0.0

        while not self._stop.is_set():
            try:
                down = bool(source.down())
            except Exception as e:                      # noqa: BLE001
                # Driver or session teardown. Fall back to the windowed chord
                # rather than spinning on a source that will never work again.
                print(f"[JARVIS] Push-to-talk: {source.name} stopped answering — "
                      f"{type(e).__name__}: {e}")
                break
            now = time.monotonic()
            if down:
                if down_since == 0.0:
                    down_since = now
                elif now - down_since >= _DEBOUNCE_S:
                    self._set_held(True)
            else:
                down_since = 0.0
                self._set_held(False)
            self._stop.wait(period)

        self._set_held(False)
        self._scope = "window"


class HotkeyTap:
    """A global chord that fires ONCE on each press, for summoning the UI.

    The same sources as `PushToTalk`, different rule: push-to-talk wants the
    release as well, this only wants the press edge. Edge detection is here
    rather than in each source because every source reports a LEVEL ("is it
    down now") and none of them reports a transition.

    Deliberately no debounce: `_DEBOUNCE_S` exists to stop a stray brush
    opening the microphone, and a stray summon is a window appearing — cheap,
    visible, and undone with the same key.
    """

    def __init__(self, on_press: Callable[[], None], chord=DEFAULT_CHORD,
                 source: "_Source | None" = None, os_name: str | None = None):
        self._on_press = on_press
        self._chord = tuple(chord)
        self._given_source = source
        self._os_name = os_name
        self._source = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._scope = "window"
        self._was_down = False

    @property
    def scope(self) -> str:
        return self._scope

    @property
    def label(self) -> str:
        return chord_label(self._chord)

    def start(self) -> str:
        self.stop()
        self._stop.clear()
        source = self._given_source or make_source(self._chord, self._os_name)
        if source is None:
            self._scope = "window"
            return self._scope
        try:
            ready = bool(source.open())
        except Exception as e:                          # noqa: BLE001
            print(f"[JARVIS] Summon hotkey: {source.name} probe failed — "
                  f"{type(e).__name__}: {e}")
            ready = False
        if not ready:
            self._scope = "window"
            return self._scope
        self._scope = "global"
        self._thread = threading.Thread(
            target=self._loop, args=(source,), name="summon-hotkey", daemon=True)
        self._thread.start()
        return self._scope

    def _loop(self, source: "_Source") -> None:
        self._source = source
        period = 1.0 / _POLL_HZ
        while not self._stop.is_set():
            try:
                down = bool(source.down())
            except Exception as e:                      # noqa: BLE001
                print(f"[JARVIS] Summon hotkey: {source.name} stopped answering — "
                      f"{type(e).__name__}: {e}")
                break
            if down and not self._was_down:
                self._was_down = True
                try:
                    self._on_press()
                except Exception as e:                  # noqa: BLE001
                    print(f"[JARVIS] Summon hotkey: handler failed — "
                          f"{type(e).__name__}: {e}")
            elif not down:
                self._was_down = False
            self._stop.wait(period)
        self._scope = "window"

    def stop(self) -> None:
        self._stop.set()
        t, self._thread = self._thread, None
        if t is not None and t.is_alive():
            t.join(timeout=1.0)
        source, self._source = self._source, None
        if source is not None:
            try:
                source.close()
            except Exception as e:                      # noqa: BLE001
                print(f"[JARVIS] Summon hotkey: close failed — "
                      f"{type(e).__name__}: {e}")
        self._was_down = False
