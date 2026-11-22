"""The face on the desktop: a widget that draws `core.avatar` and nothing else.

WHY THIS REPLACED `HudCanvas`
    `ui/hud_canvas.py` was 619 lines and most of it was a HUD: a grid of dots,
    a metric ring, a status line, a name in a ring, a video frame that took the
    avatar's place, a state machine for the viseme mouth. The floating face
    needs exactly one of those things — the avatar — and the mockup draws the
    face as a 260 px bubble with nothing else in it.

    It was also the last thing in `ui/` that reached into the deleted window:
    every one of its forty-odd attributes was read by `MainWindow`. So the
    avatar stays and the HUD goes, which is the honest version of "keep the
    face bubble" that the owner asked for.

WHAT IT DOES KEEP FROM `HudCanvas`, AND WHY
    * `set_audio_level` is thread-safe and stores the LOUDER of the incoming
      value and the current one, then decays it. The audio callback delivers
      20 ms chunks with gaps between them; without the "louder of" the mouth
      stutters closed on every gap.
    * `push_visemes` takes a SCHEDULE, not a level, because a single averaged
      level moves the mouth five times a second — enough to flap, nowhere near
      enough to articulate.
    * The animation timer runs at ~30 fps and only while the widget is visible:
      a face nobody can see should not be repainting.

WHY IT PAINTS NOTHING WHEN `core.avatar` IS MISSING
    The avatar imports numpy and a mesh. Both are optional in this project —
    cosmetics must never stop the assistant from starting — so a machine
    without them gets a calm ring from `ui.orb_paint` in the same bubble rather
    than a traceback or a grey square. That fallback is a real surface, not a
    placeholder: it is the same painter the orb uses.
"""
from __future__ import annotations

import math
import time

# The drawn head's half-height as a fraction of the widget. Chosen so the
# avatar's shoulders reach the edge of a 260 px bubble without the glow being
# clipped by it.
HEAD_SPAN = 0.34

# 30 fps. The avatar's eyes blink and its mouth moves; both are slower than
# this, and a face is the one surface where smoothness is worth the wake-ups.
#
# THIS IS THE STEP RATE, NOT THE REPAINT RATE. They were the same number, and
# that is what hung the app: every 33 ms tick called `update()`, so every tick
# repainted a 1,554-facet head on the Qt thread — 893 `drawPolygon` calls plus
# their `QPolygonF`/`QPointF`/gradient objects, ~26,790 polygons per second.
# The tray icon appeared (Qt paints it synchronously in `show()`) and then
# answered no clicks at all, because the event loop only ran in the gaps.
FRAME_MS = 33

# An IDLE face is a still picture with a slow blink in it. It is repainted at
# this rate instead — chosen to stay well under the step rate so the ratio is a
# real limit rather than a coincidence — and `IDLE_FACET_STRIDE` keeps the idle
# interior cheap. A SPEAKING face is the one case that needs every frame and
# the full fill, and it is the case where the user is watching the mouth.
IDLE_REPAINT_MS = 200

# Every Nth visible facet for the idle fill. The wireframe and the features are
# drawn in full, so the silhouette, the eyes and the mouth are exact.
IDLE_FACET_STRIDE = 3

#: The specular accent on the iris and the lip cavity. Board 1 has one accent
#: (#4FD8F0) and one highlight (#BFF6FF); the face uses the highlight for the
#: iris ring so the eye reads as lit rather than as a second cyan disc. These
#: are the values from `docs/mockups/build.py`, and copying them beats importing
#: `ui.theme` — that module still carries the retired HUD palette.
FACE_ACCENT = "#BFF6FF"


def should_repaint(now_ms: float, last_ms: float, speaking: bool) -> bool:
    """Whether this tick is worth a repaint. A pure function, so it is testable.

    WHY A FUNCTION AND NOT AN `if` IN `_step`
        The first version of this decision was written inline, and a mutation
        that replaced it with `if True:` passed every test in the file — the
        test was reading source text, not asking the code what it does. Here
        the rule is one expression with a name, and a test can call it.

    A SPEAKING face repaints every step: the mouth is the thing the user is
    looking at. Everything else is a slow blink over a still head, and redrawing
    a 1,554-facet mesh at 30 fps for it is what starved the Qt thread.
    """
    if speaking:
        return True
    return (float(now_ms) - float(last_ms)) >= IDLE_REPAINT_MS

# The level decays by this much per frame when nothing is arriving. 0.06 at
# 30 fps closes a full-scale peak in about half a second, which is roughly how
# long a spoken syllable lasts.
DECAY = 0.06


def build_face_canvas(parent, face_path: str = "", name: str = "J.A.R.V.I.S"):
    """Build the widget. Qt is imported here so this module stays importable.

    Same rule as `ui/orb_overlay._build_canvas`: a `QWidget` subclass needs Qt
    when the CLASS is created, and this module is imported by tests on machines
    that have no PyQt6 and by CI that installs only the test tooling. Building
    the class inside the function keeps the import of this module free.
    """
    from PyQt6.QtCore import Qt, QTimer
    from PyQt6.QtGui import QPainter
    from PyQt6.QtWidgets import QWidget

    try:
        from core.avatar import HoloAvatar
    except Exception:                               # noqa: BLE001
        HoloAvatar = None

    class FaceCanvas(QWidget):
        """The avatar, its glow, and its mouth. No chrome, no text, no ring."""

        def __init__(self, parent=None):
            super().__init__(parent)
            self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground)
            self.state = "IDLE"
            self.speaking = False
            self.muted = False

            self._avatar = None
            if HoloAvatar is not None:
                try:
                    self._avatar = HoloAvatar()
                except Exception:                   # noqa: BLE001
                    self._avatar = None

            # The name is kept because a future settings screen shows it; the
            # painter does not draw it (the mockup's bubble has no label).
            self._name = name
            self._face_path = face_path

            self._live_amp = 0.0
            self._amp_disp = 0.0
            self._visemes = None
            self._vis_i = None
            self._last_t = time.time()
            self._last_paint_ms = 0.0

            self._tmr = QTimer(self)
            self._tmr.timeout.connect(self._step)
            self._tmr.start(FRAME_MS)

        # ── what the shell feeds it ──────────────────────────────────────────

        def set_audio_level(self, level: float) -> None:
            """Thread-safe: the louder of the incoming value and the current one.

            The audio callback hands over 20 ms chunks with gaps between them.
            Taking the value outright makes the mouth snap shut on every gap,
            which reads as a stutter rather than as speech.
            """
            try:
                lv = float(level)
            except (TypeError, ValueError):
                return
            if math.isnan(lv) or math.isinf(lv):
                return
            self._live_amp = max(0.0, min(1.0, lv)) if lv > self._live_amp else self._live_amp

        def push_visemes(self, frames, hop: float, at: float) -> None:
            """Thread-safe: a schedule of (level, openness, width) frames.

            Appended into one continuous timeline rather than swapped in, for
            the reason `core/playback_timing` exists: consecutive batches are
            handed over far faster than they sound, so replacing the schedule
            each time leaves the mouth replaying the opening instant of every
            chunk.
            """
            try:
                if not frames:
                    return
                hop = max(1e-3, float(hop))
                at = float(at)
                new = list(frames)
                cur = self._visemes
                if cur is not None:
                    old, t0, ohop = cur
                    if abs(ohop - hop) < 1e-6:
                        i = int(round((at - t0) / hop))
                        if 0 <= i <= len(old) + 1:
                            merged = old[:i] + new
                            played = int((time.time() - t0) / hop) - 2
                            if played > 60:
                                merged = merged[played:]
                                t0 += played * hop
                                if self._vis_i is not None:
                                    self._vis_i = max(0, self._vis_i - played)
                            self._visemes = (merged, t0, hop)
                            return
                self._visemes = (new, at, hop)
                self._vis_i = None
            except Exception as e:                  # noqa: BLE001
                # A malformed schedule costs one frame of mouth movement, and
                # this is called from the playback thread — raising there would
                # take down the audio path over a cosmetic value.
                print(f"[JARVIS] Face: viseme schedule dropped — "
                      f"{type(e).__name__}: {e}")

        def glance(self, dx: float, dy: float, hold: float = 1.1) -> None:
            try:
                if self._avatar is not None:
                    self._avatar.glance(dx, dy, hold)
            except Exception as e:                  # noqa: BLE001
                print(f"[JARVIS] Face: glance dropped — {type(e).__name__}: {e}")

        # ── the animation ────────────────────────────────────────────────────

        def _viseme_frame(self, now: float):
            """(openness, width, level) for this instant, or None when idle."""
            if self._visemes is None:
                return None
            frames, t0, hop = self._visemes
            idx = int((now - t0) / hop)
            if idx < 0 or idx >= len(frames):
                if idx >= len(frames):
                    self._visemes = None
                return None
            self._vis_i = idx
            return frames[idx]

        def _step(self) -> None:
            now = time.time()
            dt = max(1e-4, min(0.25, now - self._last_t))
            self._last_t = now
            if not self.isVisible():
                return
            frame = self._viseme_frame(now)
            if frame is None:
                self._amp_disp *= (1.0 - DECAY)
                v_open, v_wide, v_level = None, 0.0, None
            else:
                v_open, v_wide, v_level = frame
                self._amp_disp = max(self._amp_disp, float(v_level or 0.0))
            amplitude = max(self._amp_disp, 0.0)
            if self._avatar is not None:
                try:
                    self._avatar.step(dt, amplitude, speaking=self.speaking,
                                      muted=self.muted, state=self.state,
                                      v_open=v_open, v_wide=v_wide,
                                      v_level=v_level)
                except Exception as e:              # noqa: BLE001
                    # The avatar is cosmetics: one bad frame must not stop the
                    # timer, or the face freezes for the rest of the session.
                    print(f"[JARVIS] Face: animation step failed — "
                          f"{type(e).__name__}: {e}")
            # REPAINT ONLY WHEN THE PICTURE CHANGED — see IDLE_REPAINT_MS.
            # A speaking face repaints every step, because the mouth is the
            # thing the user is looking at. Everything else (idle, listening,
            # thinking) is a slow blink over a still head, and repainting the
            # whole mesh 30 times a second for it is what starved the tray.
            now_ms = now * 1000.0
            if should_repaint(now_ms, self._last_paint_ms, self.speaking):
                self._last_paint_ms = now_ms
                self.update()

        # ── painting ─────────────────────────────────────────────────────────

        def paintEvent(self, _event):               # noqa: N802 — Qt's name
            try:
                painter = QPainter(self)
                try:
                    self._paint(painter)
                finally:
                    painter.end()
            except Exception as e:                  # noqa: BLE001
                # A failed repaint costs a frame. Letting it escape takes down
                # the event loop of a window with no other purpose.
                print(f"[JARVIS] Face: could not paint — {type(e).__name__}: {e}")

        def _paint(self, painter) -> None:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            width, height = self.width(), self.height()
            if width < 2 or height < 2:
                return
            cx, cy = width / 2.0, height / 2.0
            radius = min(width, height) * HEAD_SPAN

            if self._avatar is not None:
                # BOARD 1'S TOKENS, NOT THE RETIRED HUD PALETTE.
                #
                # This used `C.PRI` (#4b9fff, blue), `C.WHITE` (#f5f5f7) and
                # `C.MUTED_C` (#ff3366, pink). The floating head therefore drew
                # BLUE rings inside a CYAN orb, and went pink when muted. Every
                # other ambient surface — `orb_paint`, `toast_card`,
                # `tray_pages`, `voice_paint` — declares the design system's
                # numbers directly, so the one surface a user looks at most was
                # the only one in a different palette.
                from ui.orb_paint import CYAN, MUTED
                from ui.theme import qcol

                primary = qcol(MUTED) if self.muted else qcol(CYAN)
                self._avatar.paint(painter, cx, cy, radius, primary,
                                   qcol(FACE_ACCENT), None, wireframe=False,
                                   floating_head=True,
                                   facet_stride=(1 if self.speaking
                                                 else IDLE_FACET_STRIDE))
                return

            # NO AVATAR: a calm ring from the same painter the orb uses. A
            # missing mesh is an install without numpy, which this project
            # supports — so the bubble shows something, and it shows the same
            # something the desktop ring does.
            from ui.orb_paint import paint_ring
            paint_ring(painter, cx, cy, radius,
                       mode="active",
                       state="speaking" if self.speaking else "idle",
                       level=max(self._amp_disp, 0.0),
                       alert=self.muted,
                       phase=(time.time() * 0.35) % 1.0)

    return FaceCanvas(parent)


__all__ = ["HEAD_SPAN", "FRAME_MS", "build_face_canvas"]
