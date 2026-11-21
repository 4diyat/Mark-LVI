"""
Local wake-word detection for JARVIS ("Hey Jarvis").

Design goals:
  • ZERO cost when the feature is off — openwakeword is imported ONLY inside
    start()/install helpers, never at module load. If the user never enables
    wake word, none of this touches the app.
  • ZERO latency on the audio path — the microphone callback only ever does a
    cheap, non-blocking queue push (feed()); the actual model inference runs in
    this module's own background thread, so the real-time audio thread and the
    Gemini stream are never slowed.
  • Fully local & offline — audio fed here never leaves the machine; there is no
    network call except the one-time model download the user triggers from the UI.

openwakeword ships small ONNX models (a few MB each) and runs comfortably on a
CPU. The pretrained wake phrase used here is "Hey Jarvis".
"""
from __future__ import annotations

import importlib
import importlib.util
import queue
import subprocess
import sys
import threading
from pathlib import Path
from typing import Callable

# Pretrained openwakeword model that listens for "Hey Jarvis".
WAKE_MODEL = "hey_jarvis"
# Score in [0,1]; above this counts as a detection. Tunable per environment.
DEFAULT_THRESHOLD = 0.5
# Mic frames arrive at 16 kHz int16; this is just the detector's input rate.
SAMPLE_RATE = 16000

# The package imports its own model submodule while initializing. Importing
# that submodule concurrently with the package can expose a half-built package
# to Model on some Python versions. Serialize our imports/construction and
# initialize the package first. Readiness checks never import it at all.
_MODEL_LOCK = threading.RLock()


def is_installed() -> bool:
    """True if the openwakeword package is importable (no model check)."""
    try:
        return importlib.util.find_spec("openwakeword") is not None
    except Exception:
        return False


def is_ready() -> bool:
    """True if openwakeword is installed AND its model files are present on disk.

    This is a cheap, DETERMINISTIC file-existence check. It deliberately does NOT
    construct a Model to probe readiness — doing that is slow and, worse, can clash
    with the detector's own Model when it's already running, which intermittently
    returned False and made the UI flicker to 'not downloaded'. Never raises.
    """
    try:
        spec = importlib.util.find_spec("openwakeword")
        if not spec or not spec.submodule_search_locations:
            return False
        for location in spec.submodule_search_locations:
            models_dir = Path(location) / "resources" / "models"
            # start() uses ONNX, so tflite-only files do not mean ready.
            if (any(models_dir.glob(f"{WAKE_MODEL}*.onnx"))
                    and any(models_dir.glob("melspectrogram*.onnx"))
                    and any(models_dir.glob("embedding_model*.onnx"))):
                return True
        return False
    except Exception:
        return False


def install_and_download(logger: Callable[[str], None] = print,
                         notify: Callable[[str], None] | None = None) -> tuple[bool, str]:
    """
    One-click setup for the UI button: pip-install openwakeword if missing, then
    download the wake model. Returns (ok, message). Never raises — every failure
    is reported through the returned message and the logger.
    """
    _tell = notify or (lambda _msg: None)
    try:
        if not is_installed():
            logger("Wake word: installing openwakeword (one-time)…")
            _tell("Wake word: installing openwakeword (one-time)…")
            r = subprocess.run(
                [sys.executable, "-m", "pip", "install", "openwakeword"],
                capture_output=True, text=True, encoding="utf-8", errors="replace",
            )
            if r.returncode != 0:
                tail = (r.stderr or r.stdout or "").strip().splitlines()[-1:] or [""]
                return False, f"pip install failed: {tail[0][:160]}"
        # Download the pretrained melspectrogram/embedding + wake models.
        logger("Wake word: downloading models…")
        _tell("Wake word: downloading models…")
        try:
            with _MODEL_LOCK:
                # Import the package before its submodule, matching start().
                importlib.import_module("openwakeword")
                _u = importlib.import_module("openwakeword.utils")
            try:
                _u.download_models([WAKE_MODEL])
            except TypeError:
                _u.download_models()   # older signature downloads the default set
        except Exception as e:
            return False, f"model download failed: {e}"

        if not is_ready():
            return False, "installed, but the wake model could not be loaded."
        logger("Wake word: ready.")
        return True, "Wake word installed and ready."
    except Exception as e:
        return False, f"setup error: {e}"


class WakeWordDetector:
    """
    Runs the wake model in a dedicated thread. The mic thread calls feed() with
    raw int16 frames; detections invoke on_detect() (called from this thread —
    the callback must marshal to whatever loop/UI it needs).
    """

    def __init__(self, on_detect: Callable[[], None],
                 threshold: float = DEFAULT_THRESHOLD,
                 logger: Callable[[str], None] = print,
                 notify: Callable[[str], None] | None = None):
        self._on_detect = on_detect
        self._threshold = threshold
        self._logger    = logger
        # See PluginRegistry: `logger` is the console and gets everything,
        # `notify` is the activity log and gets only what the user must act on.
        self._notify    = notify or (lambda _msg: None)
        self._queue: queue.Queue = queue.Queue(maxsize=50)
        self._thread: threading.Thread | None = None
        self._running = False
        self._model = None
        self._ready = False

    def start(self) -> bool:
        """Load the model and spawn the inference thread. Returns True on success.
        Safe to call again — a no-op if already running. Never raises."""
        with _MODEL_LOCK:
            if self._running:
                return True
            # A previous stop() may not have finished winding down (see stop).
            # Starting a second thread on the same queue is the bug that made
            # this unreliable, so wait for the old one rather than race it.
            if self._thread is not None and self._thread.is_alive():
                self._thread.join(timeout=2.0)
                if self._thread.is_alive():
                    self._logger("Wake word: previous thread still busy; not starting another.")
                    return False
            self._thread = None
            try:
                importlib.import_module("openwakeword")
                model_module = importlib.import_module("openwakeword.model")
                self._model = model_module.Model(
                    wakeword_models=[WAKE_MODEL], inference_framework="onnx")
            except Exception as e:
                self._logger(f"Wake word: could not load model — {e}")
                self._notify("Wake word unavailable — use the WAKE NOW button or disable wake word.")
                self._model = None
                return False
            self._running = True
            self._ready = True
            self._thread = threading.Thread(target=self._loop, daemon=True, name="WakeWordThread")
            self._thread.start()
            self._logger("Wake word: listening for 'Hey Jarvis'.")
            return True

    def stop(self) -> None:
        """Stop the inference thread and WAIT for it to exit.

        THE BUG THIS FIXES
            `start()` only checked `_running`, and `stop()` set it False without
            joining. So `stop()` followed by `start()` — which is exactly what
            toggling the wake word off and on in the settings panel does —
            left the OLD thread alive. Both threads then block on the same
            `self._queue` and split the incoming frames between them, so each
            one sees roughly half the audio and neither hears a whole phrase.
            The symptom is not a crash; it is "Hey Jarvis works sometimes".

            A thread is not stopped by a flag until it takes another turn
            around its loop, and it cannot take another turn while it is
            blocked in `predict()` or in `queue.get()`. The join is therefore
            bounded: a model call on a busy machine can take a while, and a
            settings toggle must not freeze the UI thread.
        """
        self._running = False
        # unblock the thread if it's waiting on the queue
        try:
            self._queue.put_nowait(None)
        except queue.Full:
            # The queue is full, so the loop is still holding frames and will
            # see `_running == False` on its next turn anyway. Nothing to do;
            # the alternative was blocking a UI thread on a shutdown.
            pass
        thread = self._thread
        if thread is not None and thread.is_alive() and thread is not threading.current_thread():
            thread.join(timeout=2.0)
            if thread.is_alive():
                # Still inside predict() after two seconds. It will exit on its
                # next loop turn because `_running` is False, so the reference
                # is KEPT: clearing it here would leave nobody able to wait for
                # it, and the next start() would race a thread it cannot see.
                self._logger("Wake word: inference thread still winding down.")
                return
        self._thread = None
        self._model = None
        self._ready = False

    @property
    def ready(self) -> bool:
        return self._ready

    def feed(self, frame_int16) -> None:
        """Called from the mic callback (real-time thread). Must stay cheap and
        never block — the frame is copied and dropped if the queue is backed up."""
        if not self._running:
            return
        try:
            # frame_int16 is a numpy int16 array (possibly 2-D mono) — flatten to 1-D
            data = frame_int16[:, 0].copy() if getattr(frame_int16, "ndim", 1) > 1 else frame_int16.copy()
            self._queue.put_nowait(data)
        except queue.Full:
            pass                # the loop is behind on purpose; drop the frame
        except Exception as e:
            # Not `pass`: this runs on the microphone's real-time callback, and
            # a frame that cannot even be queued means something is wrong with
            # what the device handed us — worth one line, not a traceback.
            self._logger(f"Wake word: frame dropped — {e}")

    def _loop(self) -> None:
        while self._running:
            try:
                frame = self._queue.get()
                if frame is None or not self._running:
                    break
                self._run_one_pass(frame)
            except Exception as e:
                self._logger(f"Wake word: inference error — {e}")

    def _run_one_pass(self, frame=None) -> None:
        """Feed one frame to the model and act on the score.

        Split out of `_loop` so the decision can be exercised without a thread.
        A test that races the inference thread to observe what happens between
        `_drain()` and `_on_detect()` is a test that passes on a fast machine
        and fails on a slow one — which is what happened.
        """
        import numpy as np
        if frame is None:
            frame = self._queue.get()
            if frame is None or not self._running:
                return
        try:
            scores = self._model.predict(np.asarray(frame, dtype=np.int16))
            score = 0.0
            if isinstance(scores, dict):
                # match the jarvis model regardless of exact key suffix
                for k, v in scores.items():
                    if "jarvis" in k.lower():
                        score = max(score, float(v))
                if score == 0.0 and scores:
                    score = max(float(v) for v in scores.values())
            if score >= self._threshold:
                # Fire FIRST, then drain.
                #
                # This used to drain before on_detect(), and the comment
                # said it was "so we don't double-fire on the same
                # utterance". It did prevent the double fire, and it also
                # threw away the rest of the sentence: "Hey Jarvis, what is
                # the weather" arrives as a burst of frames, the phrase is
                # detected partway through, and everything after it was
                # discarded before the window had a chance to become awake.
                # The user then had to repeat themselves — the most common
                # way a wake word "sort of works".
                #
                # Firing first means the window is awake before the frames
                # are dropped, so the audio after the phrase is already
                # going where it should. The drain stays, because without
                # it the remaining frames of the SAME phrase re-trigger.
                try:
                    self._on_detect()
                except Exception as e:
                    self._logger(f"Wake word: on_detect error — {e}")
                self._drain(reset_model=True)
        except Exception as e:
            self._logger(f"Wake word: inference error — {e}")

    def _drain(self, reset_model: bool = False) -> None:
        """Throw away everything queued, so one utterance cannot fire twice.

        `reset_model` also clears the MODEL's own buffers, which are separate
        from this queue and are what actually cause a second detection: the
        preprocessor keeps ~10 s of audio and ~30 frames of predictions, so
        without a reset the next predict() call can still see the phrase it
        just heard. Only done on a real detection — resetting mid-stream would
        cost the model its rolling context on every frame.
        """
        try:
            while True:
                self._queue.get_nowait()
        except queue.Empty:
            pass
        if reset_model and self._model is not None:
            reset = getattr(self._model, "reset", None)
            if callable(reset):
                try:
                    reset()
                except Exception as e:
                    self._logger(f"Wake word: model reset failed — {e}")
