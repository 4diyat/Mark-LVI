"""The one screen that must exist before anything else: where the key goes.

WHY A WINDOW, WHEN EVERYTHING ELSE IS AMBIENT
    The design cut removed the window and with it the setup overlay that lived
    inside it. That left two bad choices and this is neither of them: `main.py`
    blocked in `wait_for_api_key()` while the tray said "edit
    `config/api_keys.json` and restart" — a first run that cannot finish, solved
    by asking the user to hand-edit JSON. `design/new-ui-proposal-ANALISIS.md` calls
    that a real regression and accepts it; this screen is how it stops being
    one.

    It is a WINDOW and not a tray panel on purpose. The panel is something you
    open and close while the assistant works; setup is a gate, and a gate that
    can be dismissed by clicking elsewhere on the desktop is not a gate. So it
    is shown before the assistant starts, it blocks the runner thread, and it
    has no skip.

NO SKIP, AND THE REASON IS THE HONEST ONE
    The owner's decision (2026-11-22) is that the app cannot start without a
    key. There is no "Lewati" button, not even a disabled one: a button that
    exists and is greyed out reads as "not yet", and this is "never". The way
    out of this screen is a key that works, or closing the application.

WHAT IT DOES WITH THE KEY
    `core/key_check.py` decides — this module only draws the answer. Three
    sentences exist below, one per verdict, and a test asserts that every value
    in `key_check.VERDICTS` has one. Rejected: the screen stays open and says
    why. Offline or unrecognised: the key is saved and the sentence says it was
    not tested, because refusing an offline machine is a worse failure than a
    key that is checked on first real use.

    STORED IN `config/api_keys.json` AND NOWHERE ELSE, through
    `memory/config_manager.save_api_keys()` — the same door every other setting
    uses, so the file keeps its 0600 mode and its atomic write.

WHY THE NETWORK CALL IS NOT ON THE Qt THREAD
    `check()` waits up to 8 seconds. On the Qt thread that is a window that
    stops repainting, which on Windows becomes "Not Responding" and invites the
    user to close the one screen that can finish setup.

    So the split below is strict: `evaluate()` is the whole decision and touches
    no widget; `apply_verdict()` is the only thing that writes to one and runs
    only on the Qt thread. `_deliver()` is the one line between them, and it
    goes through a queued signal — `QTimer.singleShot` from a worker thread
    without a receiver would post to that worker's thread, which has no event
    loop, and the screen would simply never update.
"""
from __future__ import annotations

import threading

from ui.tray_pages import PALETTES, PANEL_H, PANEL_W
from ui.tray_panel_model import _t

# The setup panel is the tray panel's size and header, because it is the same
# product and the mockup has no artboard for this screen to be measured
# against. Anything else would be a second visual language invented at a gate.
SETUP_W, SETUP_H = PANEL_W, PANEL_H

# The three sentences, one per `core.key_check.VERDICTS` value. Kept as keys
# rather than text so the catalogue owns the wording.
RESULT_KEYS = {
    "ok": "ui.setup.result.ok",
    "rejected": "ui.setup.result.rejected",
    "untested": "ui.setup.result.untested",
}


def result_text(kind: str, detail: str = "") -> str:
    """The sentence for one verdict, plus whatever detail the check added.

    Pure, and that is the point: the wording is the part a person rereads ten
    times, and it can be checked on a machine with no display.
    """
    key = RESULT_KEYS.get(kind, RESULT_KEYS["untested"])
    sentence = _t(key)
    detail = str(detail or "").strip()
    return f"{sentence} {detail}" if detail else sentence


class SetupWindow:
    """One 460x660 panel: a title, a password field, one button, one sentence.

    Deliberately not a `QWidget` subclass — no Qt class at module scope is a
    rule `tests/test_ui_split.py` pins, and this module is imported by
    `ui/shell.py` on machines with no display. The widgets are built inside
    `build()`, once, and every method tolerates them being absent.
    """

    def __init__(self, on_done=None, checker=None, saver=None, app=None):
        # `on_done(verdict)`: called once, after the key was saved.
        # `checker(key) -> Verdict` and `saver(key) -> bool` are injected so a
        # test can drive all three outcomes with no network and no real file.
        self._on_done = on_done
        self._checker = checker
        self._saver = saver
        self._app = app
        self._window = None
        self._field = None
        self._button = None
        self._bridge = None
        self._labels: dict = {}
        self._notes: list = []
        self._error = ""
        self._busy = False
        self._last = None
        self._done = False

    # ── what happened ────────────────────────────────────────────────────────

    @property
    def available(self) -> bool:
        return self._window is not None

    @property
    def error(self) -> str:
        return self._error

    @property
    def notes(self) -> tuple:
        return tuple(self._notes)

    @property
    def verdict(self):
        """The last verdict this screen acted on, or None before the first try."""
        return self._last

    @property
    def finished(self) -> bool:
        """True once the screen closed itself, which happens only after a save."""
        return self._done

    def _note(self, text: str) -> None:
        line = f"Setup: {text}"
        self._notes.append(line)
        print(f"[JARVIS] {line}", flush=True)

    # ── the decision, with no widget in it ───────────────────────────────────

    def default_checker(self, key: str):
        from core import key_check

        return key_check.check(key)

    def default_saver(self, key: str) -> bool:
        """Save the key, then forget the cached one — in that order.

        THE CACHE IS THE POINT. `core.gemini.api_key()` memoises the key for the
        life of the process; a setup screen that wrote the file and left the old
        (empty) value in that memo would hand the session a blank key and
        reconnect straight back into the `NEEDS_KEY` it just escaped.
        """
        from memory import config_manager

        saved = bool(config_manager.save_api_keys(key))
        if saved:
            try:
                from core import gemini

                gemini.api_key(refresh=True)
            except Exception as e:                  # noqa: BLE001
                self._note(f"the key cache was not refreshed — {type(e).__name__}: {e}")
        return saved

    def evaluate(self, key: str):
        """Check one key, then save it or refuse it. Returns a Verdict.

        SYNCHRONOUS AND WIDGET-FREE, so it can run on a worker thread and in a
        test. "" is refused before anything else happens: a click on Simpan with
        an empty field is not a failed check, it is a form not yet filled in.
        """
        from core import key_check

        text = str(key or "").strip()
        if not text:
            return key_check.Verdict(key_check.REJECTED, _t("ui.setup.empty"))
        checker = self._checker or self.default_checker
        try:
            verdict = checker(text)
        except Exception as e:                      # noqa: BLE001
            # `check()` promises never to raise; this is the belt for the day
            # an injected checker does. UNTESTED is the honest answer — the app
            # cannot know, and refusing would block an offline machine.
            verdict = key_check.Verdict(
                key_check.UNTESTED,
                f"The check itself failed — {type(e).__name__}: {e}")

        if getattr(verdict, "kind", "") == key_check.REJECTED:
            # NOT SAVED. Writing a key the service just refused would leave the
            # file holding a known-bad value, and the next start would fail in
            # a place with no screen left to explain it.
            return verdict

        saver = self._saver or self.default_saver
        try:
            saved = bool(saver(text))
        except Exception as e:                      # noqa: BLE001
            return key_check.Verdict(
                key_check.REJECTED,
                f"The key could not be saved — {type(e).__name__}: {e}")
        if not saved:
            return key_check.Verdict(key_check.REJECTED, _t("ui.setup.save_failed"))
        return verdict

    def submit(self, key: str | None = None) -> str:
        """Evaluate and apply on the calling thread. Returns the verdict kind.

        The synchronous door, used by tests and by `main.py` when it has no Qt.
        The window's button does NOT use it directly — see `_pressed`.
        """
        text = key if key is not None else self._field_value()
        verdict = self.evaluate(text)
        self.apply_verdict(verdict)
        return getattr(verdict, "kind", "untested")

    # ── the widget half, Qt thread only ──────────────────────────────────────

    def apply_verdict(self, verdict) -> None:
        """Put one verdict on screen, and close the window if it was saved."""
        self._last = verdict
        kind = str(getattr(verdict, "kind", "untested") or "untested")
        self.show_result(kind, str(getattr(verdict, "detail", "") or ""))
        if kind in ("ok", "untested"):
            self.finish()
        else:
            self._rtl_after_reject()

    def show_result(self, kind: str, detail: str = "") -> None:
        """One of the three sentences. The key itself is never echoed."""
        label = self._labels.get("result")
        if label is None:
            return
        try:
            label.setText(result_text(kind, detail))
        except Exception as e:                      # noqa: BLE001
            self._note(f"the result line could not be set — {type(e).__name__}: {e}")

    def _rtl_after_reject(self) -> None:
        """Re-enable, refocus and select, so the fix is retype-and-Enter."""
        self._set_busy(False)
        if self._field is None:
            return
        try:
            self._field.setFocus()
            self._field.selectAll()
        except Exception as e:                      # noqa: BLE001
            self._note(f"the field could not be refocused — {type(e).__name__}: {e}")

    def finish(self) -> None:
        """Close the window and tell the caller. Idempotent."""
        if self._done:
            return
        self._done = True
        window, self._window = self._window, None
        if window is not None:
            try:
                window.hide()
                window.deleteLater()
            except Exception as e:                  # noqa: BLE001
                self._note(f"the window could not be removed — {type(e).__name__}: {e}")
        callback = self._on_done
        if callback is not None:
            try:
                callback(self._last)
            except Exception as e:                  # noqa: BLE001
                self._note(f"the done handler failed — {type(e).__name__}: {e}")

    # ── the Qt half ──────────────────────────────────────────────────────────

    def build(self) -> bool:
        """Create the window once. False (with `error`) if Qt cannot.

        NEVER RAISES, like every other surface in this package: `main.py` calls
        this before the event loop is running, and a traceback here is an
        application whose first run ends in a stack trace.
        """
        if self._window is not None:
            return True
        try:
            from PyQt6.QtCore import Qt, pyqtSignal
            from PyQt6.QtWidgets import QLabel, QLineEdit, QPushButton, QWidget

            class _Bridge(QWidget):
                """The queued hop from the worker thread back to this one.

                A QObject subclass with ONE signal, built here rather than at
                module scope: `import ui.setup_window` has to work with no Qt
                installed, and the shell imports it on exactly such a machine.
                """

                answered = pyqtSignal(object)

            window = QWidget()
            window.setWindowFlags(Qt.WindowType.Window
                                  | Qt.WindowType.WindowStaysOnTopHint)
            window.setWindowTitle(_t("ui.setup.title"))
            window.setFixedSize(SETUP_W, SETUP_H)
            self._window = window
            bridge = _Bridge(window)
            bridge.answered.connect(self.apply_verdict)
            self._bridge = bridge
            self._build_body(window, QLabel, QLineEdit, QPushButton)
            self._style()
            return True
        except Exception as e:                      # noqa: BLE001
            self._window = None
            self._bridge = None
            self._error = f"{type(e).__name__}: {e}"
            self._note(f"could not build — {self._error}")
            return False

    def _build_body(self, window, QLabel, QLineEdit, QPushButton) -> None:
        labels = self._labels
        labels["title"] = _placed(window, QLabel, 24, 28, 412, 26,
                                  _t("ui.setup.title"))
        labels["subtitle"] = _placed(window, QLabel, 24, 60, 412, 40,
                                     _t("ui.setup.subtitle"))
        labels["subtitle"].setWordWrap(True)
        labels["title"].setStyleSheet("color:#f3f8ff;font-size:20px;font-weight:700;")
        # The only progress the screen can honestly show: one screen, one step.
        # A four-segment bar like board 7's would promise three more screens
        # that do not exist.
        labels["step"] = _placed(window, QLabel, 24, 112, 412, 18,
                                 _t("ui.setup.step"))
        labels["field_label"] = _placed(window, QLabel, 24, 150, 412, 18,
                                        _t("ui.setup.field"))
        field = QLineEdit(window)
        field.setGeometry(24, 174, 412, 44)
        # PASSWORD, not plain text: the field is on a desktop that may be
        # shared, and a key pasted into a screenshot is a key that has to be
        # rotated.
        field.setEchoMode(QLineEdit.EchoMode.Password)
        field.setPlaceholderText(_t("ui.setup.placeholder"))
        field.returnPressed.connect(self._pressed)
        self._field = field

        button = QPushButton(_t("ui.setup.save"), window)
        button.setGeometry(24, 234, 412, 44)
        button.clicked.connect(self._pressed)
        self._button = button

        labels["result"] = _placed(window, QLabel, 24, 296, 412, 92, "")
        labels["result"].setWordWrap(True)
        labels["footer"] = _placed(window, QLabel, 24, SETUP_H - 88, 412, 60,
                                   _t("ui.setup.footer"))
        labels["footer"].setWordWrap(True)
        # Decoration only: this is not a session or microphone indicator.
        try:
            from ui.brand_art import brand_pixmap
            labels["brand"] = _placed(window, QLabel, 180, 424, 100, 100, "")
            labels["brand"].setPixmap(brand_pixmap(100))
        except Exception as exc:  # noqa: BLE001
            self._note(f"brand art unavailable: {exc}")
        # THE X BUTTON IS NOT A SKIP BUTTON, and Qt gives every window one.
        # Without this handler, closing the window hid it and left
        # `wait_for_api_key` waiting on a screen nobody could see — the exact
        # silent hang this screen exists to end. Refusing the close is the
        # owner's decision applied to the one control they did not draw.
        window.closeEvent = self._on_close_event

    def _on_close_event(self, event) -> None:
        """Refuse to close before a key is saved. Qt thread only.

        EVERY PATH THAT SAVES CALLS `finish()`, WHICH SETS `_done` FIRST and
        then hides the window itself — so a close arriving after a save is
        simply ignored here and the hide has already happened. A close before a
        save is answered on screen rather than fought silently: the window stays,
        the sentence says why, and the field keeps the focus.
        """
        if self._done:
            return
        try:
            event.ignore()
        except Exception as e:                      # noqa: BLE001
            self._note(f"the close event could not be refused — {type(e).__name__}: {e}")
        self.show_result("rejected", _t("ui.setup.cannot_skip"))
        if self._field is not None:
            try:
                self._field.setFocus()
            except Exception as e:                  # noqa: BLE001
                self._note(f"the field could not be refocused — {type(e).__name__}: {e}")

    def _style(self) -> None:
        """The dark palette, fixed.

        Setup happens before `memory/config_manager` has a theme setting to
        read — the setting lives in the same file as the key this screen is
        asking for. Board 5's dark palette is what the product looks like at
        rest, and it is what the first screen a user ever sees should be.
        """
        pal = PALETTES["dark"]
        window = self._window
        if window is None:
            return
        try:
            window.setStyleSheet(f"""
                QWidget {{ background:{pal['panel']};color:{pal['text']}; }}
                QLabel {{ background:transparent;color:{pal['muted']}; }}
                QPushButton {{ background:{pal['accent']};color:{pal['on_accent']};
                              border:none;border-radius:10px;font-weight:600; }}
                QPushButton:disabled {{ background:{pal['card']};color:{pal['muted']}; }}
                QLineEdit {{ background:{pal['card']};color:{pal['text']};
                            border:1px solid {pal['line']};border-radius:10px;
                            padding-left:14px; }}
            """)
        except Exception as e:                      # noqa: BLE001
            self._note(f"stylesheet refused — {type(e).__name__}: {e}")

    def show(self) -> bool:
        """Build if needed, then show and focus the field. False if Qt refused."""
        if self._window is None and not self.build():
            return False
        try:
            window = self._window
            window.show()
            window.raise_()
            window.activateWindow()
            if self._field is not None:
                self._field.setFocus()
            return True
        except Exception as e:                      # noqa: BLE001
            self._error = f"{type(e).__name__}: {e}"
            self._note(f"could not show — {self._error}")
            return False

    def close(self) -> None:
        """Hide without reporting success. Used when the app is quitting."""
        window, self._window = self._window, None
        self._bridge = None
        if window is None:
            return
        try:
            window.hide()
            window.deleteLater()
        except Exception as e:                      # noqa: BLE001
            self._note(f"could not hide — {type(e).__name__}: {e}")

    # ── the click, and the thread it starts ──────────────────────────────────

    def _field_value(self) -> str:
        try:
            return self._field.text() if self._field is not None else ""
        except Exception:                           # noqa: BLE001
            return ""

    def _set_busy(self, busy: bool) -> None:
        self._busy = bool(busy)
        button = self._button
        if button is None:
            return
        try:
            button.setEnabled(not busy)
            button.setText(_t("ui.setup.checking") if busy else _t("ui.setup.save"))
        except Exception as e:                      # noqa: BLE001
            self._note(f"the button could not be updated — {type(e).__name__}: {e}")

    def _pressed(self) -> None:
        """The button and Enter. Starts the worker; never waits for it."""
        if self._busy or self._done:
            return
        text = self._field_value().strip()
        if not text:
            self.show_result("rejected", _t("ui.setup.empty"))
            return
        self._set_busy(True)
        self.show_result("untested", _t("ui.setup.checking_now"))
        threading.Thread(target=self._run_check, args=(text,),
                         name="setup-check", daemon=True).start()

    def _run_check(self, text: str) -> None:
        """On the worker thread. Touches no widget — see `_deliver`."""
        try:
            verdict = self.evaluate(text)
        except Exception as e:                      # noqa: BLE001
            from core import key_check

            verdict = key_check.Verdict(
                key_check.UNTESTED,
                f"The check itself failed — {type(e).__name__}: {e}")
        self._deliver(verdict)

    def _deliver(self, verdict) -> None:
        """Hop to the Qt thread. The only line in this file that crosses back."""
        bridge = self._bridge
        if bridge is None:
            # No bridge means no window was built (a test, a headless build),
            # so there is no thread to hop to and nothing that can race.
            self.apply_verdict(verdict)
            return
        try:
            bridge.answered.emit(verdict)
        except Exception as e:                      # noqa: BLE001
            self._note(f"the answer could not reach the window — {type(e).__name__}: {e}")
            self.apply_verdict(verdict)


def _placed(parent, cls, x: int, y: int, w: int, h: int, text: str):
    """One positioned label with text. The same helper the tray pages use."""
    label = cls(parent)
    label.setGeometry(x, y, w, h)
    label.setText(text)
    return label


__all__ = ["RESULT_KEYS", "SETUP_H", "SETUP_W", "SetupWindow", "result_text"]
