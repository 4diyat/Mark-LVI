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

# The state words `main.py` sends. Kept as a set rather than a dict because
# nothing here maps them to text — the tooltip and the orb each have their own
# opinion, and this list exists so an unknown word is visibly unknown instead
# of silently becoming "listening".
KNOWN_STATES = frozenset({
    "INITIALISING", "THINKING", "PROCESSING", "SPEAKING", "LISTENING",
    "SLEEPING", "NO MIC",
})


class AmbientShell:
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
        self._ui_thread_id = threading.get_ident()

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

    def wait_for_api_key(self) -> None:
        """Block until `_ready`. main.py sets it once the session is up.

        Nothing here can ask the user for a key any more: the setup screen was
        an overlay inside the window. What remains is the loop's contract —
        start when ready — and a machine with no key logs why it is waiting
        instead of hanging silently.
        """
        waited = 0.0
        told = False
        while not self._ready:
            time.sleep(0.1)
            waited += 0.1
            # ONCE, after half a minute, and through the tray as well as stdout.
            # This loop blocks `main.py`'s runner thread, so a silent wait is an
            # app that looks alive and answers nothing. Repeating the notice
            # every tick would turn that into a tray balloon every 30 seconds,
            # which is how a useful message becomes noise the user mutes.
            if not told and waited >= 30.0:
                told = True
                reason = ("Menunggu API key. Tidak ada layar setup di mode "
                          "ambient — isi config/api_keys.json lalu mulai ulang.")
                _note(reason)
                try:
                    self.notify(reason, "API key")
                except Exception as e:              # noqa: BLE001
                    # The loop's job is to wait, not to report. A tray that
                    # refuses is already covered by `_note` above.
                    _note_once("api-key-notice",
                               f"API key notice not shown: {type(e).__name__}: {e}")

    # ── status ──────────────────────────────────────────────────────────────

    def set_state(self, state: str) -> None:
        """One word, mirrored onto every surface that shows it.

        Independent per surface, and that is not defensive habit: the orb
        raising because it has no paint device is exactly the case where the
        TOOLTIP is the only readout left. Updating the tray first and then the
        orb, unguarded, would lose the tooltip in the one situation it matters.
        """
        word = str(state or "").strip().upper() or "INITIALISING"
        self._state = word
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
        self._announce(word)

    def _announce(self, word: str) -> None:
        """Desktop notification for an answer that arrived while nobody looked.

        THE POLICY IS NOT DECIDED HERE. `core.notify.Notifier` owns it: it
        sends one message per finished turn, at most once a minute, and never
        while the interface is on screen. This method only feeds it the state
        and the last answer.

        Config is consulted on EVERY call rather than read once at startup,
        because it is the only way the setting can change without a restart —
        and with no settings screen (see `docs/mockups/NOT-IN-MOCKUP.md`) a
        restart is now the only other option. A read of one JSON key is cheap
        next to the notification it guards.
        """
        try:
            from core.notify import Notifier
            from memory.config_manager import get_desktop_notifications

            if not get_desktop_notifications():
                return
            notifier = self._notifier
            if notifier is None:
                notifier = Notifier(visible=self.interface_visible)
                self._notifier = notifier
            notifier.observe(word, self._last_answer or "")
        except Exception as e:                      # noqa: BLE001
            # A status update must never be the thing that raises — but silence
            # here is "notifications never appear", which is unanswerable.
            _note_once("notify", f"notification policy unavailable — "
                                 f"{type(e).__name__}: {e}")

    def interface_visible(self) -> bool:
        """Whether anything the user can SEE is on screen.

        `Notifier` suppresses a notification while this is True: a banner that
        repeats what is already in front of the reader is the fastest way to get
        the feature switched off. With no window, "visible" means the face.
        """
        bubble = getattr(self, "_bubble", None)
        return bool(getattr(bubble, "visible", False))

    def apply_presence(self, mode: str) -> None:
        """Aktif / Fokus / Senyap, applied to the orb and saved."""
        from ui.ambient_shell import apply_presence_mode
        apply_presence_mode(self, mode)

    def set_audio_level(self, level: float) -> None:
        """A 0..1 live level, from the audio threads.

        A plain float store is atomic under the GIL, so this needs no signal
        and no lock; the orb clamps what it is given because Qt refuses a
        gradient stop outside 0..1 and the failure shows up as a plain ring.
        """
        for attr in ("_orb", "_bubble"):
            target = getattr(self, attr, None)
            callback = getattr(target, "set_audio_level", None)
            if callback is None:
                continue
            try:
                callback(level)
            except Exception:                       # noqa: BLE001
                # Cosmetic and 20×/second: a line per frame would be the
                # problem, not the report. Reported ONCE per process, at the
                # first failure, which is enough to find out the orb is broken
                # without writing a log line 20 times a second.
                _note_once("audio-level", "the orb cannot show the audio level")

    def push_visemes(self, frames, hop: float, at: float) -> None:
        """Mouth frames for the face, if there is a face."""
        bubble = self._bubble
        callback = getattr(bubble, "push_visemes", None)
        if callback is None:
            return
        try:
            callback(frames, hop, at)
        except Exception:                           # noqa: BLE001
            # Same rule as the audio level: once, not per frame.
            _note_once("visemes", "the face cannot animate the mouth")

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
        # The notification body is the last thing the assistant SAID. The log
        # mixes status words with answers, so only a line that came from the
        # assistant is kept — `JarvisLive` prefixes its own speech with none.
        if line and not line.startswith(("SYS:", "ERR:", "USR:", "TOOL:")):
            self._last_answer = line
        toaster = self._toaster
        if toaster is not None:
            try:
                toaster.push(str(text))
            except Exception as e:                  # noqa: BLE001
                _note(f"the toast could not show that — {type(e).__name__}: {e}")

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

        The banner is the topmost mockup surface (artboard 25) and the only one
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
        """main.py's reaction to an auth error: say so, on the only surface."""
        self._ready = False
        self.notify("API key rejected or missing. Edit config/api_keys.json and restart.")

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
