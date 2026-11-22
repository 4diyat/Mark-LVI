"""The shell: the tray, the orb, the command bar, and the face. No window.

WHY THIS REPLACED `JarvisUI` RATHER THAN SHRINKING IT
    `ui/window.py` was 3,797 lines and `JarvisUI` was its facade. Between them
    they built a full-screen HUD, a desktop workspace with an MDI area, a chat
    log, an image editor, a code editor, an SSH panel, a trading terminal, a
    floating-document system and a metrics thread. The mockup (`docs/mockups/
    jarvis-design-system.html`, twelve artboards) draws none of that. It draws
    five things: an orb, a toast, a command bar, a tray panel, and a risk
    confirmation.

    So the window is gone, and what remains is exactly this file. The old
    facade could not simply be trimmed: `main.py` talks to ~30 attributes on
    it, every one of which reached into a widget. Keeping the widget alive to
    serve those call sites is how 3,797 lines survive a design that has no use
    for them.

WHY EVERY METHOD HERE IS SAFE TO CALL WITH NO SURFACE PRESENT
    `main.py` starts talking to the shell before a tray exists and keeps
    talking after the tray dies. It does so from the audio threads, the plugin
    threads and the asyncio loop at once. A status word is not a precondition
    for anything: it is a sentence, and the worst thing it can do is fail to
    find somewhere to put itself. So every method writes to whatever surfaces
    are present, tolerates none of them being present, and never raises.

WHY THE USER-FACING POLICY IS READ, NOT WRITTEN, HERE
    Which mode is in force, whether a toast is allowed, whether a suggestion
    is held — all of that lives in `core/presence_mode` and `core/notify`,
    below the interface, because the scheduler thread asks the same questions
    with no widget anywhere near it. This file asks; it does not decide.

WHAT A CALLER CAN EXPECT FROM THE ATTRIBUTES IT SETS
    `main.py` assigns about fifteen callbacks (`on_text_command`,
    `on_wake_toggle`, ...). They are plain attributes here — main.py assigns
    them, plugins may replace them, and nothing reads them except the surface
    that fires them. That is deliberate: the window used to relay each one
    through a Qt signal because a widget had to be touched on the Qt thread.
    With no widget, there is nothing to relay, and a plain attribute is the
    whole of what those properties were ever doing.
"""
from __future__ import annotations

import threading
import time
from pathlib import Path

# Where the ambient surfaces live is `ui/lifecycle.py`; what they are is this
# file. The two import one way only: shell -> lifecycle -> surfaces, so there
# is no cycle and no second definition of "summon".
from typing import Callable

# The one door for user-visible text, from the module that already owns it for
# the panel. `ui/shell.py` is not a drawer, so importing it here is allowed —
# and `tests/test_i18n.py` checks that every key it asks for exists.
from ui.qt_thread import run_on_qt_thread
from ui.tray_panel_model import _t

# The state words `main.py` sends. Kept as a set rather than a dict because
# nothing here maps them to text — the tooltip and the orb each have their own
# opinion, and this list exists so an unknown word is visibly unknown instead
# of silently becoming "listening".
KNOWN_STATES = frozenset({
    "INITIALISING", "THINKING", "PROCESSING", "SPEAKING", "LISTENING",
    "SLEEPING", "NO MIC",
})


class AmbientShell:
    #: The thread that owns the widgets. Declared on the CLASS, not only set
    #: in `__init__`, so a shell assembled by `__new__` in a test — the usual
    #: way these tests build one, with no config read and no Qt — still
    #: answers the question instead of raising inside `set_state`. `None`
    #: means "every thread", which collapses the marshal to a direct call.
    _ui_thread_id = None
    """Everything JARVIS has on screen when there is no window.

    Construct it once, on the Qt thread, after the QApplication exists. Every
    other method is callable from any thread; the ones that touch a widget hand
    off to Qt themselves (see `ui/toast_queue.py` and `ui/orb_overlay.py`).
    """

    def __init__(self, face_path: str = "face.png", assistant_name: str = "J.A.R.V.I.S",
                 app=None):
        self._app = app
        self._face_path = face_path
        self._assistant_name = assistant_name

        # Surfaces. None means "this machine could not have it", which is a
        # normal state and never an error: a desktop with no notification area
        # still has the orb.
        self._tray = None
        self._bubble = None
        self._orb = None
        self._command_bar = None
        self._bar_hotkey = None
        self._summon_hotkey = None
        self._toaster = None
        self._confirm_banner = None
        self._setup = None

        # State that `main.py` reads.
        self._muted = False
        self._state = "INITIALISING"
        self._pending_state: str | None = None
        self._ambient = True
        self._ready = False
        self._current_file: str | None = None
        self._launch = None
        self._program_path = ""

        # The callbacks main.py assigns. Declared so `getattr` on a shell built
        # by a test does not have to guess whether the attribute exists.
        self.on_text_command: Callable[[str], None] | None = None
        self.on_remote_clicked: Callable[[], None] | None = None
        self.on_interrupt: Callable[[], None] | None = None
        self.on_voice_change: Callable[[str], None] | None = None
        self.on_audio_device_change: Callable[[str], None] | None = None
        self.on_push_to_talk: Callable[[bool], None] | None = None
        self.on_wake_toggle: Callable[[bool], str] | None = None
        self.on_wake_manual: Callable[[], None] | None = None
        self.on_wake_install: Callable[[], tuple] | None = None
        self.on_wake_sleep_timeout: Callable[[float], None] | None = None
        self.ptt_hold: Callable[[bool], None] | None = None
        self.wake_get_state: Callable[[], dict] | None = None
        self.wake_is_ready: Callable[[], bool] | None = None
        self.request_say: Callable[[str], None] | None = None
        self.get_plugins: Callable[[], list] | None = None
        self.get_plugin_settings: Callable[[], list] | None = None
        # The thread that built this object, which `main.py` makes the Qt thread
        # by creating it there. Everything that touches a widget is marshalled
        # onto it — see `_on_qt_thread`.
        self._ui_thread_id = threading.get_ident()

        # The newest audio level and whether a flush is already queued. Both are
        # written from the audio threads; a stale float is harmless and a queue
        # of them is not.
        self._pending_level = 0.0
        self._level_flush_queued = False

    # ── what main.py asks about ──────────────────────────────────────────────

    @property
    def ambient(self) -> bool:
        """True when no window is up. Always true now, and kept because
        `main.py` and the tray menu ask it."""
        return self._ambient

    @property
    def muted(self) -> bool:
        return self._muted

    @muted.setter
    def muted(self, value: bool) -> None:
        self._muted = bool(value)
        # Muting is the one state the orb shows in amber: a microphone that is
        # off is the only warning this widget has, and the design reserves
        # amber for warnings.
        orb = self._orb
        if orb is not None:
            try:
                orb.set_alert(self._muted)
            except Exception as e:                  # noqa: BLE001
                _note(f"the orb could not show mute — {type(e).__name__}: {e}")

    @property
    def current_file(self) -> str | None:
        """The file the user last dropped or asked about.

        There is no drop zone to receive one any more, so this is whatever a
        caller set. Kept as an attribute rather than deleted because
        `file_processor` and `dev_agent` read it and an attribute that is
        always None is a smaller change than two call sites that crash.
        """
        return self._current_file

    @current_file.setter
    def current_file(self, value: str | None) -> None:
        self._current_file = value

    @property
    def assistant_name(self) -> str:
        return self._assistant_name

    @property
    def tray_available(self) -> bool:
        tray = self._tray
        return tray is not None and getattr(tray, "available", False)

    def mark_ready(self) -> None:
        """The key is accepted: let `main.py`'s runner start.

        THIS WAS MISSING. `_ready` had two writes, both `False`, and nothing set
        it `True` — so `wait_for_api_key()` waited forever on every start, key
        or no key. Idempotent, callable from any thread.
        """
        self._ready = True

    def wait_for_api_key(self) -> None:
        """Block until `_ready`. With no key, the setup screen is the wait.

        Called on `main.py`'s runner thread, never the Qt thread. When Qt cannot
        build the screen it says so once and keeps waiting: a tray app that
        exits because it could not draw a dialog is worse than one that prints
        where to put the key.
        """
        from ui.setup_screen import has_key

        if self._ready or has_key():
            # A KEY IS THE GATE, NOT THE SESSION. This used to wait for
            # `_ready`, which only a SAVED key sets — so a working install with
            # a key already in the file waited forever too. The session tries
            # that key, and a rejected one comes back through
            # `prompt_reconfig()`, which is the one place `_ready` is cleared.
            return
        if not self.open_setup():
            self.notify(_t("ui.setup.waiting"))
        waited, told = 0.0, False
        while not self._ready:
            time.sleep(0.1)
            waited += 0.1
            # ONCE, after half a minute. This loop blocks the runner thread, so
            # a silent wait is an app that looks alive and answers nothing —
            # and a notice every tick would be a tray balloon every 30 s, which
            # is how a useful message becomes noise the user mutes.
            if not told and waited >= 30.0:
                told = True
                if self._setup is not None:
                    continue    # the screen is up and the user can see it
                reason = _t("ui.setup.waiting")
                _note(reason)
                try:
                    self.notify(reason, "API key")
                except Exception as e:              # noqa: BLE001
                    _note_once("api-key-notice",
                               f"API key notice not shown: {type(e).__name__}: {e}")

    def open_setup(self) -> bool:
        """Show the setup window on the Qt thread. False if Qt is not here."""
        from ui.setup_screen import open_setup

        return open_setup(self)

    def _setup_done(self, verdict) -> None:
        """The screen closed on a saved key: let the runner go.

        REACHED ONLY AFTER A SAVE — `SetupWindow.finish()` is called from the
        success path and nowhere else — so this is a statement about the file,
        not an optimistic guess.
        """
        self._setup = None
        _note(f"API key saved ({getattr(verdict, 'kind', '?')})")
        self.mark_ready()

    # ── status ──────────────────────────────────────────────────────────────

    def set_state(self, state: str) -> None:
        """One word, mirrored onto every surface that shows it.

        Independent per surface, and that is not defensive habit: the orb
        raising because it has no paint device is exactly the case where the
        TOOLTIP is the only readout left. Updating the tray first and then the
        orb, unguarded, would lose the tooltip in the one situation it matters.

        ON THE QT THREAD, ALWAYS — and this docstring used to claim otherwise.
            `main.py` calls this from the asyncio runner thread: 17 call sites,
            including the microphone recovery loop every two seconds. The
            module docstring said "the ones that touch a widget hand off to Qt
            themselves", and this one did not — it called `QSystemTrayIcon`,
            `QWidget` and the orb's `_repaint()` straight from that thread.

            Qt has one event dispatcher and it is not re-entrant across
            threads: touching a widget from a foreign thread is undefined
            behaviour, and on Windows it presents as a UI that is painted and
            will not answer, because the dispatcher's lock is held by a thread
            that is not pumping. That is the reported symptom, exactly.

            So the work is marshalled and the caller returns immediately. A
            caller on the Qt thread would deadlock waiting for itself, so that
            case runs inline — `ui/qt_thread.py` is where that rule lives.
        """
        word = str(state or "").strip().upper() or "INITIALISING"
        self._state = word            # plain assignment: readable from anywhere
        run_on_qt_thread(self._ui_thread_id, lambda: self._apply_state(word))
        # Notification policy is thread-safe and consults config each call;
        # it does not touch a widget, so it needs no queue.
        from ui.notify_bridge import announce
        announce(self, word)

    def _apply_state(self, word: str) -> None:
        """The half of `set_state` that touches widgets. Qt thread only."""
        for attr, method in (("_tray", "set_state"),
                             ("_bubble", "set_state"),
                             ("_orb", "set_state")):
            target = getattr(self, attr, None)
            callback = getattr(target, method, None)
            if callback is None:
                continue
            try:
                callback(word.lower())
            except Exception as e:                  # noqa: BLE001
                _note(f"{attr} could not show '{word}' — {type(e).__name__}: {e}")

        # THE FULL-SCREEN SURFACE LAST, and after the small ones. If the overlay
        # is what fails, the orb, the tray and the bubble have already been
        # told; if it is what WORKS, the user sees the answer on the surface
        # they were already looking at rather than only on the edge of a frame.
        from ui import voice_wiring

        voice_wiring.sync(self)

    def apply_presence(self, mode: str) -> None:
        """Aktif / Fokus / Senyap, applied to the orb and saved."""
        from ui.ambient_shell import apply_presence_mode
        apply_presence_mode(self, mode)

    def set_audio_level(self, level: float) -> None:
        """A 0..1 live level, from the audio threads. Marshalled to Qt."""
        from ui.qt_thread import set_audio_level
        set_audio_level(self, level)

    def push_visemes(self, frames, hop: float, at: float) -> None:
        """Mouth frames for the face, if there is a face. Marshalled to Qt."""
        from ui.qt_thread import push_visemes
        push_visemes(self, frames, hop, at)

    # ── the surfaces main.py drives ─────────────────────────────────────────

    def write_log(self, text: str) -> None:
        """The activity line. Thread-safe, and never a reason to fail.

        `main.py` calls this 48 times and from every thread it has. The window
        used to relay it through a signal to a chat log; with no chat log the
        line goes where it can still be read: stdout, which main.py's own log
        file captures.
        """
        line = str(text or "")
        print(f"[JARVIS] {line}", flush=True)

        # BOARD 6 IS FED FROM HERE, and from nowhere else. Every sentence the
        # user says and every sentence the assistant answers already arrives
        # at this one method with a `You: ` or `<name>: ` prefix — adding a
        # second call site in `main.py` would mean two paths to keep in step,
        # and the one that drifted would be the one on the full-screen surface.
        #
        # MARSHALLED, because this is called from the audio thread, the runner
        # thread and the process reader. The exchange above only sets fields;
        # everything below reaches a widget, so it goes through the one door.
        run_on_qt_thread(self._ui_thread_id, lambda: self._show_exchange(line))

    def _show_exchange(self, line: str) -> None:
        """The board-6 half of `write_log`. Qt thread only."""
        from ui import voice_wiring

        voice_wiring.show_exchange(self, line)

        # The notification body is the last thing the assistant SAID. The log
        # mixes status words with answers, so only a line that came from the
        # assistant is kept — `JarvisLive` prefixes its own speech with none.
        self._remember_answer(line)
        toaster = self._toaster
        if toaster is not None:
            try:
                toaster.push(str(line))
            except Exception as e:                  # noqa: BLE001
                _note(f"the toast could not show that — {type(e).__name__}: {e}")

    def _remember_answer(self, line: str) -> None:
        if line and not line.startswith(("SYS:", "ERR:", "USR:", "TOOL:")):
            self._last_answer = line

    #: The last thing the assistant said, for the notification body. Kept here
    #: because the chat log that used to own it went with the window.
    _last_answer = ""

    #: The token of the question currently on screen. One at a time, because
    #: `core/confirm` holds one pending action for the whole process.
    _confirm_token = ""

    notify = write_log

    def show_content(self, title: str, text: str) -> None:
        """A result the user asked for. A toast is the only surface that can
        show it now: there is no content panel, and inventing one would be a
        new window the mockup does not have."""
        self.notify(f"{str(title or '').strip()}: {str(text or '').strip()}"[:240])

    def show_confirm(self, token: str, title: str, detail: str) -> None:
        """Raise the trusted-UI gate. Called from `core/confirm`, possibly off
        the Qt thread.

        `core/confirm` calls this from whatever thread the action runs on, and
        Qt may only build widgets on the thread that owns them. So the banner is
        created inside `singleShot(0, ...)` — a queued call that lands on the
        event loop instead of in the middle of an audio callback.
        """
        try:
            from PyQt6.QtCore import QTimer
        except Exception as e:                      # noqa: BLE001
            _note(f"no Qt: cannot ask about '{title}' — {type(e).__name__}: {e}")
            return
        QTimer.singleShot(0, lambda: self._show_confirm_now(token, title, detail))

    def _show_confirm_now(self, token: str, title: str, detail: str) -> None:
        """Build and place the banner on the Qt thread.

        The banner is the topmost mockup surface (artboard 14a) and the only one
        that must be visible on a desktop with nothing else on it, so it is a
        window of its own: frameless, always on top, bottom-centre. Parenting it
        to the orb would clip a 430 px banner to a 28 px window, which is
        exactly the "invisible but blocking" failure `tests/test_blocking_
        surfaces.py` was written about.
        """
        try:
            banner = self._confirm_banner
            if banner is None:
                from ui.confirm_banner import build_confirm_window

                banner = build_confirm_window()
                banner.answered.connect(self._resolve_answered)
                self._confirm_banner = banner
                self._confirm_token = ""
            self._confirm_token = token
            banner.set_title(title, detail)
            # Board 14a's "ASAL PERMINTAAN": who asked, when, and that it is on
            # the record. The time is taken HERE rather than inside the banner
            # so the line describes the request, not the repaint.
            from datetime import datetime

            banner.set_origin(when=datetime.now().strftime("%H:%M"))
            banner.adjustSize()
            banner.show()
            banner.raise_()
            banner.activateWindow()
        except Exception as e:                      # noqa: BLE001
            # The action is still pending and will expire on its own; refusing
            # is core/confirm's job, so losing the banner is a lost question,
            # not a safety hole. It must be said, though — a gate nobody can
            # see is the failure this whole file exists to avoid.
            _note(f"the confirmation could not be shown — {type(e).__name__}: {e}")
            self.notify(f"Konfirmasi tidak bisa ditampilkan: {title}")

    def hide_confirm(self, token: str) -> None:
        """Take the banner down. Safe to call for a token that is not up."""
        banner = self._confirm_banner
        if banner is None or token != self._confirm_token:
            return
        try:
            banner.hide()
        except Exception as e:                      # noqa: BLE001
            _note(f"the confirmation could not be hidden — {type(e).__name__}: {e}")

    def _resolve_answered(self, accepted: bool) -> None:
        """CONFIRM or CANCEL, from the banner, on the Qt thread.

        The banner is hidden FIRST, then `core/confirm` is told. In that order
        an answer that arrives after the 90-second expiry still clears the
        dialog — the action is refused either way, and a dialog that outlives
        its question is the one thing the user would then have to dismiss
        without knowing what it was about.
        """
        token, self._confirm_token = self._confirm_token, ""
        banner = self._confirm_banner
        if banner is not None:
            try:
                banner.hide()
            except Exception as e:                  # noqa: BLE001
                _note(f"the confirmation could not be hidden — {type(e).__name__}: {e}")
        if token:
            self._resolve_confirm(token, bool(accepted))

    @staticmethod
    def _resolve_confirm(token: str, accepted: bool) -> None:
        from core import confirm
        confirm.resolve(token, accepted)

    def prompt_reconfig(self) -> None:
        """main.py's reaction to an auth error: ask for a new key, on screen.

        IT USED TO SAY "edit config/api_keys.json and restart", which is an
        instruction to hand-edit JSON from a tray balloon — and it cleared
        `_ready` without ever offering a way to set it again, so the two wait
        loops this flag gates had no exit. Now the setup screen comes back,
        pre-verified, and `mark_ready()` runs when a new key is saved.

        Called from the asyncio loop, which is not the Qt thread: `open_setup`
        is what marshals the build.
        """
        self._ready = False
        if self.open_setup():
            return
        self.notify(_t("ui.setup.rejected_notice"))

    def notify_phone_connected(self) -> None:
        self.notify("Phone connected.")

    # ── things the removed window used to do ────────────────────────────────
    # Each of these stays as a no-op with a reason, NOT as a silent deletion.
    # main.py calls them; a missing attribute would be an AttributeError in the
    # middle of a call that has nothing to do with cameras or video.

    def start_camera_stream(self) -> None:
        """No camera preview: artboard 6 draws a gesture overlay, and the
        gesture work itself is gone with the window."""
        _note_once("camera", "camera preview is not part of the ambient shell")

    def stop_camera_stream(self) -> None:
        return

    def glance(self, dx: float, dy: float, hold: float = 1.1) -> None:
        """There is no avatar to look anywhere. The face bubble has its own."""
        return

    def start_speaking(self) -> None:
        self.set_state("SPEAKING")

    def stop_speaking(self) -> None:
        if not self._muted:
            self.set_state("LISTENING")

    # ── lifecycle pass-throughs ──────────────────────────────────────────────
    # Thin by design: the work is in `ui/lifecycle.py`, and every caller —
    # main.py, the tray, a plugin — keeps saying `shell.summon()`.

    def summon(self) -> None:
        from ui import lifecycle
        lifecycle.summon(self)

    def dismiss(self) -> None:
        from ui import lifecycle
        lifecycle.dismiss(self)

    def toggle_interface(self) -> None:
        from ui import lifecycle
        lifecycle.toggle_interface(self)

    def request_wake(self) -> None:
        from ui import lifecycle
        lifecycle.request_wake(self)

    def request_sleep(self) -> None:
        from ui import lifecycle
        lifecycle.request_sleep(self)

    def summon_settings(self) -> None:
        from ui import lifecycle
        lifecycle.summon_settings(self)

    def quit(self) -> None:
        from ui import lifecycle
        lifecycle.quit_app(self)

    def _face_path_or_default(self) -> str:
        return self._face_path or "face.png"


# ── notes ────────────────────────────────────────────────────────────────────

_seen: set[str] = set()
_seen_lock = threading.Lock()


def _note(text: str) -> None:
    """A line on stdout. Not `logging`: this runs on whatever thread raised."""
    print(f"[JARVIS] {text}", flush=True)


def _note_once(key: str, text: str) -> None:
    """The same, but once per process.

    Some of these are called per camera start or per frame. A capability that
    is simply not there should be said once, not 20 times a second — which is
    the difference between a note and noise.
    """
    with _seen_lock:
        if key in _seen:
            return
        _seen.add(key)
    _note(text)


def default_face_path() -> str:
    """Where the face image lives, or '' if this install has none."""
    path = Path(__file__).resolve().parent.parent / "face.png"
    return str(path) if path.exists() else ""
