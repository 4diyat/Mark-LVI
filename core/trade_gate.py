"""Session-local emergency stop for JARVIS's reviewed MT5 submission path.

This is not an account-wide stop: it cannot cancel a request already admitted
for submission, revoke broker orders, or control external applications/plugins.
"""
import threading

_lock = threading.Lock()
_stopped = False
_generation = 0


def snapshot() -> int | None:
    """Issue a generation for a new review, or None when stopped."""
    with _lock:
        return None if _stopped else _generation


def valid(generation: int) -> bool:
    """Test whether a review still belongs to the active generation."""
    with _lock:
        return not _stopped and generation == _generation


def stop() -> None:
    """Stop new submissions and invalidate every previously issued review."""
    global _stopped, _generation
    with _lock:
        _stopped = True
        _generation += 1


def resume() -> None:
    """Allow new reviews; this never revalidates a review from before stop."""
    global _stopped
    with _lock:
        _stopped = False


def stopped() -> bool:
    with _lock:
        return _stopped


def admit_submission(generation: int) -> bool:
    """Linearize a submission against stop; a successful admission is in flight.

    A later stop cannot revoke that admission or guarantee the broker has not
    received it. The lock is intentionally not held across an external API call.
    """
    return valid(generation)
