"""actions/handoff.py — the phone handoff context-transfer adapter
(board 5.6, the transfer half).

WHAT THIS DOES
    Reads the real memory and history, asks the pure policy in `core.handoff`
    to build a bounded context bundle, and — for the phone side — validates a
    bundle that arrives. This module is the one place that touches the
    memory store and the transcript; the policy decides what goes in and
    whether a received bundle is intact.

WHY THE ADAPTERS SPLIT
    The policy in `core/handoff.py` is pure — it takes two lists and returns
    a bundle or a verdict. That is so a test can drive every path with
    fixtures. This adapter reads the memory panel rows and the recent
    history through their existing readers and passes them through unchanged,
    so the policy never learns where the records came from.

WHAT IT DOES NOT DO
    It does not open a socket and it does not send anything. `prepare` returns
    a plain dict the existing dashboard channel ships; `receive` validates one
    that came back. The transport's security is the dashboard's existing
    TLS + per-device session key, which this module neither replaces nor
    weakens.
"""
from __future__ import annotations


def _memory_rows() -> list[dict]:
    """The memory rows the panel shows, or [] if the store cannot be read.

    An unreadable store yields an empty memory in the bundle, not a crash:
    the handoff still goes out with the history and the phone resumes with
    less context. The absence is a fact, not a failure to hand off.
    """
    try:
        from memory.memory_manager import all_entries_for_ui
        return all_entries_for_ui()
    except Exception:                              # noqa: BLE001
        return []


def _history_turns(turns: int = 100) -> list[dict]:
    """The most recent history turns, or [] if the transcript cannot be read."""
    try:
        from core.history import tail
        return tail(turns)
    except Exception:                              # noqa: BLE001
        return []


def prepare(scope: str, *, turns: int = 100) -> "object":
    """Build the handoff bundle for a scope, from the real stores.

    `scope` is `command` (memory + history) or `read` (memory only). The
    returned object is a `HandoffBundle`; call `.to_dict()` to serialise it
    for the dashboard channel.
    """
    from core.handoff import build_bundle

    return build_bundle(scope, _memory_rows(), _history_turns(turns))


def receive(bundle) -> "tuple[bool, str]":
    """Validate a bundle that arrived from the phone side.

    Returns `(ok, reason)`. A bundle that fails is refused with the reason,
    so the caller can report exactly what was wrong rather than resuming a
    conversation from an unreadable context.
    """
    from core.handoff import validate_bundle

    return validate_bundle(bundle)


__all__ = ["prepare", "receive"]
