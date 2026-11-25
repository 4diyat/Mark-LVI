"""core/custom_voice.py — the pure policy behind the custom voice enrollment
(board 5.8, the part that was missing).

WHAT THIS DECIDES
    Board 5.8 draws a voice page where the user can record a short sample to
    use as their own voice, with level feedback and a preview, and delete it
    later. The provider engine that synthesises a custom voice is out of
    scope here; what this module decides is the ENROLLMENT STATE MACHINE —
    whether a recording is long enough, whether the level is acceptable,
    whether the user has opted in, and whether a stored custom voice is
    complete and deletable. No audio, no file, no Qt.

WHY THE DECISION IS PURE
    Whether a sample is too short, whether a level meter reading is in range,
    and whether the stored record is well-formed are arithmetic over plain
    values (seconds, a level, a record). The actual recording and the
    synthesis are the adapter's job; deciding what the values mean is
    policy. A test can hand in a sample duration and a level and assert
    exactly what the page should show.

OPT-IN IS A STATE, NOT A CHECKBOX LOOK
    Custom voice is biometric-adjacent: a recording of the user's voice is
    personal data. The policy requires an explicit `consent` before a
    recording can be accepted as an enrollment; a sample recorded without
    consent is refused, not stored. Consent can be withdrawn by deleting,
    which is the only way a stored custom voice leaves the machine.

WHAT THIS DOES NOT DO
    It does not record audio, run a model, or synthesise speech. It validates
    and gates the records the adapter produces. The provider engine that
    turns a sample into a usable custom voice is a separate concern, and this
    policy states plainly that a recording is only accepted when it is long
    enough and the level is in range — it never claims a voice is usable
    without the engine.
"""
from __future__ import annotations

from dataclasses import dataclass

# Enrollment thresholds. A sample must be long enough to capture the voice
# and loud enough to be usable; too short or too quiet is refused with a
# reason the user can act on (record longer / speak up).
MIN_SAMPLE_SECONDS = 25.0
MAX_SAMPLE_SECONDS = 60.0
MIN_LEVEL = 0.02
MAX_LEVEL = 1.0

# The states a custom-voice enrollment can be in.
IDLE = "idle"          # no recording in progress
RECORDING = "recording"
READY = "ready"        # a valid sample is held, awaiting accept
ACCEPTED = "accepted"  # the user accepted it as their custom voice
REJECTED = "rejected"  # a sample failed validation


@dataclass
class Sample:
    """One recorded sample: how long, how loud, and whether consented."""

    seconds: float
    level: float
    consented: bool = False


@dataclass
class CustomVoice:
    """The stored custom voice record, or an empty one.

    `present` is whether a custom voice is stored at all. A stored voice
    carries its sample stats and the consent it was enrolled under. A record
    that is not complete (no sample) is not a usable custom voice, and the
    policy says so rather than treating it as one.
    """

    present: bool = False
    seconds: float = 0.0
    level: float = 0.0
    consented: bool = False

    def summary(self) -> str:
        if not self.present:
            return "Tidak ada suara kustom yang disimpan."
        return (f"Suara kustom disimpan "
                f"({self.seconds:.0f} s, level {self.level:.2f}).")


def is_level_in_range(level: float) -> bool:
    """Whether a level-meter reading is in the usable range."""
    try:
        value = float(level)
    except (TypeError, ValueError):
        return False
    return MIN_LEVEL <= value <= MAX_LEVEL


def is_length_ok(seconds: float) -> bool:
    """Whether a sample is long enough (and not absurdly long)."""
    try:
        value = float(seconds)
    except (TypeError, ValueError):
        return False
    return MIN_SAMPLE_SECONDS <= value <= MAX_SAMPLE_SECONDS


def validate_sample(sample: Sample) -> tuple[bool, str, str]:
    """Validate one recorded sample.

    Returns `(ok, state, reason)`. The order matters: consent is checked
    FIRST. A sample recorded without consent is refused before its length or
    level is even considered — the user's opt-in is the gate, and a perfect
    recording made without it must not be accepted. A sample that fails
    validation is `rejected` with a reason the page can show; one that passes
    is `ready` for the user to accept.
    """
    if not sample.consented:
        return False, REJECTED, "Rekam tanpa persetujuan tidak diterima."
    if not is_length_ok(sample.seconds):
        return (False, REJECTED,
                f"Rekam terlalu pendek atau terlalu panjang "
                f"({sample.seconds:.0f} s; yang diterima "
                f"{MIN_SAMPLE_SECONDS:.0f}–{MAX_SAMPLE_SECONDS:.0f} s).")
    if not is_level_in_range(sample.level):
        return (False, REJECTED,
                f"Tingkat suara di luar jangkauan "
                f"({sample.level:.2f}; yang diterima "
                f"{MIN_LEVEL:.2f}–{MAX_LEVEL:.2f}).")
    return True, READY, "Sampel siap untuk diterima."


def accept(sample: Sample) -> tuple[bool, str]:
    """Accept a validated sample as the stored custom voice.

    Only a sample that passes `validate_sample` can be accepted. Accepting
    an invalid sample would store a voice the engine cannot use and the page
    would then claim a custom voice that does not exist — the exact honesty
    failure this policy exists to prevent.
    """
    ok, state, reason = validate_sample(sample)
    if not ok:
        return False, f"Sampel tidak bisa diterima: {reason}"
    voice = CustomVoice(present=True, seconds=sample.seconds,
                        level=sample.level, consented=sample.consented)
    return True, voice.summary()


def build_stored(
    present: bool,
    seconds: float = 0.0,
    level: float = 0.0,
    consented: bool = False,
) -> CustomVoice:
    """Assemble a `CustomVoice` from stored values, validating completeness.

    A record that claims to be present but has no sample is NOT a usable
    custom voice: it is treated as absent, because a "custom voice" with no
    recording behind it is a claim the engine cannot honour. The policy says
    so in the returned record rather than letting the page show a voice that
    does not exist.
    """
    if present and (not is_length_ok(seconds) or not is_level_in_range(level)):
        return CustomVoice(present=False)
    return CustomVoice(present=present, seconds=seconds,
                       level=level, consented=consented)


def delete(stored: CustomVoice) -> tuple[bool, str]:
    """Delete a stored custom voice. Returns (did_delete, reason).

    Deleting is the way a user withdraws consent and removes their voice
    from the machine. Deleting a voice that is not present changes nothing
    and says so — the operation is idempotent, and reporting a deletion that
    did not happen would be the lie this module exists to prevent.
    """
    if not stored.present:
        return False, "Tidak ada suara kustom yang dihapus."
    return True, "Suara kustom dihapus dari mesin ini."


__all__ = [
    "MIN_SAMPLE_SECONDS", "MAX_SAMPLE_SECONDS", "MIN_LEVEL", "MAX_LEVEL",
    "IDLE", "RECORDING", "READY", "ACCEPTED", "REJECTED",
    "Sample", "CustomVoice",
    "is_level_in_range", "is_length_ok", "validate_sample", "accept",
    "build_stored", "delete",
]
