"""The detector's lifecycle and its queue, tested against a stand-in model.

WHY THIS FILE EXISTS
    Three bugs in the wake word were found by reading, and all three share the
    same property: they do not raise, they do not log, and they make the
    feature "sometimes work". That is the hardest kind to notice and the
    easiest kind to reintroduce, so each is pinned here.

    Nothing here needs openwakeword installed: `start()` builds the model
    through `importlib.import_module`, which is replaced with a fake that
    honours the same contract the real one does.
"""
from __future__ import annotations

import importlib.util
import threading
import time
import types
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "core" / "wake_word.py"


def load_module():
    """Load core/wake_word.py without importing the package around it."""
    spec = importlib.util.spec_from_file_location("wake_word_under_test", SOURCE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FakeModel:
    """Scores 0.9 once it is handed a detection's worth of audio."""

    def __init__(self, **kwargs):
        self.resets = 0
        self.blocks = 0

    def reset(self):
        self.resets += 1

    def predict(self, samples):
        self.blocks += 1
        return {"hey_jarvis_v0.1": 0.9 if len(samples) >= 1024 else 0.0}


@pytest.fixture()
def detector_factory(monkeypatch):
    """WakeWordDetector bound to a fake openwakeword, one per test."""
    module = load_module()
    fake = types.SimpleNamespace(
        import_module=lambda name: (types.SimpleNamespace()
                                    if name == "openwakeword"
                                    else types.SimpleNamespace(Model=FakeModel)))
    monkeypatch.setattr(module, "importlib", fake)

    created = []

    def make(on_detect=lambda: None):
        det = module.WakeWordDetector(on_detect, logger=lambda _m: None)
        created.append(det)
        return det

    yield make
    for det in created:
        det.stop()
    # Do not hand a still-running thread to the next test. `stop()` is bounded
    # on purpose (a settings toggle must not freeze the UI), so a thread that
    # was mid-predict can outlive it by a moment.
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        if not [t for t in threading.enumerate() if t.name == "WakeWordThread"]:
            break
        time.sleep(0.02)


def frames(count=6):
    return [np.zeros(1024, dtype=np.int16) for _ in range(count)]


# ── bug 1: stop() then start() left two inference threads ────────────────────

def test_stop_then_start_leaves_exactly_one_thread(detector_factory, monkeypatch):
    """Toggling the wake word off and on used to leave the old thread alive.

    Both threads then blocked on the same queue and split the frames between
    them, so each saw about half the audio and neither heard a whole phrase.

    The old thread is held INSIDE predict() here on purpose. That is the state
    a real model is in for milliseconds at a time, and the state in which the
    flag alone is not enough: the thread cannot observe `_running == False`
    until it finishes the call it is already in. Without holding it there the
    test passes against the broken code whenever the machine happens to be
    fast enough, which is most of the time.
    """
    module = load_module()
    in_predict = threading.Event()
    release = threading.Event()

    class BlockingModel(FakeModel):
        def predict(self, samples):
            in_predict.set()
            release.wait(timeout=5)
            return super().predict(samples)

    monkeypatch.setattr(module, "importlib", types.SimpleNamespace(
        import_module=lambda name: (types.SimpleNamespace()
                                    if name == "openwakeword"
                                    else types.SimpleNamespace(Model=BlockingModel))))
    detector = module.WakeWordDetector(lambda: None, logger=lambda _m: None)
    try:
        assert detector.start() is True
        detector.feed(np.zeros(1024, dtype=np.int16))
        assert in_predict.wait(timeout=3), "the fake never reached predict()"

        detector.stop()               # must WAIT for the blocked call
        release.set()
        assert detector.start() is True

        # Count BEFORE anything stops it — that is the whole question.
        live = _wake_threads()
        assert len(live) == 1, f"{len(live)} inference threads are competing for one queue"
    finally:
        release.set()
        detector.stop()


def _wake_threads():
    return [t for t in threading.enumerate() if t.name == "WakeWordThread"]


def test_stop_actually_joins_the_thread(detector_factory):
    """A flag alone does not stop a thread; stop() must wait for it to exit."""
    assert _wake_threads() == [], "a previous test leaked a thread"
    detector = detector_factory()
    detector.start()
    detector.stop()
    assert detector._thread is None, "stop() left a thread reference behind"
    assert not [t for t in threading.enumerate() if t.name == "WakeWordThread"]


def test_repeated_start_is_still_a_no_op(detector_factory):
    assert _wake_threads() == [], "a previous test leaked a thread"
    detector = detector_factory()
    assert detector.start() is True
    assert detector.start() is True
    live = [t for t in threading.enumerate() if t.name == "WakeWordThread"]
    assert len(live) == 1


# ── bug 3: the drain swallowed the rest of the utterance ─────────────────────

def test_detection_fires_before_the_queue_is_drained(detector_factory):
    """The user's continuation must reach the window, not the bin.

    "Hey Jarvis, what is the weather" arrives as a burst of frames. The phrase
    is detected partway through, and draining first discarded everything after
    it — so the user had to repeat themselves.

    ORDER, NOT TIMING. The old code called `_drain()` and then `_on_detect()`;
    the new code calls `_on_detect()` and then `_drain()`. Rather than race the
    inference thread and hope to sample the queue mid-flight, the callback
    records the queue depth AT THE MOMENT IT IS CALLED. If the drain has
    already happened, the frames that follow the phrase are gone before anyone
    can act on them, and the depth is zero.
    """
    depth_when_fired = []
    detector = None

    def on_detect():
        depth_when_fired.append(detector._queue.qsize())

    detector = detector_factory(on_detect)
    detector.start()
    for frame in frames(6):
        detector.feed(frame)

    _wait(lambda: depth_when_fired, "the detector never fired")
    assert depth_when_fired[0] > 0, (
        "the queue was already empty when the callback ran — the rest of the "
        "utterance was discarded before the window could wake")
    _wait(lambda: detector._queue.qsize() == 0, "the backlog was never drained")


def test_a_detection_clears_the_models_own_buffers(detector_factory):
    """The queue is not the only place the phrase lingers.

    openwakeword keeps ~10 s of audio and ~30 frames of predictions inside the
    model, so without a reset the next predict() can still see the phrase it
    just heard and fire twice.
    """
    detector = detector_factory()
    detector.start()
    model = detector._model
    for frame in frames(3):
        detector.feed(frame)

    _wait(lambda: model.resets > 0, "the model was never reset after a detection")
    assert model.resets == 1


def test_the_model_is_not_reset_on_ordinary_frames(detector_factory):
    """Resetting constantly would cost the model its rolling context."""
    silent = FakeModel()
    silent.predict = lambda samples: {"hey_jarvis_v0.1": 0.0}
    detector = detector_factory()
    detector.start()
    detector._model = silent

    for frame in frames(3):
        detector.feed(frame)
    time.sleep(0.3)
    assert silent.resets == 0


# ── the queue never blocks the microphone ────────────────────────────────────

def test_a_full_queue_drops_frames_instead_of_blocking(detector_factory):
    """feed() runs on the audio callback; blocking there is audible."""
    detector = detector_factory()
    detector._running = True          # no thread: the queue fills and stays full

    started = time.monotonic()
    for frame in frames(400):          # comfortably past the maxsize of 50
        detector.feed(frame)
    elapsed = time.monotonic() - started

    assert elapsed < 1.0, f"feed() blocked the audio callback for {elapsed:.2f}s"
    assert detector._queue.qsize() == detector._queue.maxsize


def test_feed_before_start_is_a_no_op(detector_factory):
    detector = detector_factory()
    detector.feed(np.zeros(1024, dtype=np.int16))
    assert detector._queue.qsize() == 0


def _wait(predicate, message, timeout=3.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.02)
    pytest.fail(message)
