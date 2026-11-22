"""How the last command reached the assistant — spoken, typed, or unknown.

WHY THIS IS A MODULE OF ITS OWN AND NOT A FIELD ON THE BANNER
    The risk dialog (board 14a) prints "ASAL PERMINTAAN / Perintah suara ·
    14:31 · tercatat di audit log", and the first third of that line is a fact
    only the entry points know. Two doors exist — the microphone and the typed
    field — and until this module there was no record of which one was used, so
    the honest caption would have been "tidak diketahui" on every request.

    It CANNOT live in `ui/confirm_banner.py`, because the two callers are in
    `main.py`'s audio loop and its text handler: `ui.confirm_banner` imports
    PyQt6 at module level, and an import that needs a display has no business
    running inside an audio callback on a machine that has no Qt at all. This
    module imports NOTHING — not even `core.i18n` — so it always loads.

    It is also not a shell attribute. `core/confirm` builds the dialog and has
    no shell; threading a source through `request()` would change an API that
    four actions already call, for one line of caption text.
"""
from __future__ import annotations

SOURCE_VOICE = "voice"
SOURCE_TYPED = "typed"

# Module-level rather than a class: the value belongs to the process, the same
# way the last user speech time does, and there is exactly one assistant.
_SOURCE = ""


def mark(source: str) -> None:
    """Record how the last command arrived. Never raises.

    Called from an audio callback and from a Qt click handler. A caption must
    never be able to interrupt either, so this swallow is the point of the
    function rather than a shortcut.
    """
    global _SOURCE
    _SOURCE = str(source or "").strip().lower()


def current() -> str:
    """The recorded source: "voice", "typed", or "" when nothing was recorded.

    Empty is a real answer and is shown as "Tidak diketahui". A plugin, a
    timer, or a `jarvis://` link can start an irreversible action with no human
    input in the last minute, and calling those "spoken commands" is how the
    caption becomes untrustworthy everywhere.
    """
    return _SOURCE


def reset() -> None:
    """Back to unknown. For tests and for a privacy erase."""
    global _SOURCE
    _SOURCE = ""
