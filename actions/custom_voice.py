"""actions/custom_voice.py — the custom voice enrollment adapter (board 5.8).

WHAT THIS DOES
    Records a sample through the existing audio plumbing, hands it to the
    pure policy in `core.custom_voice` for validation and acceptance, and
    reads/deletes the stored custom-voice record. This module is the one
    place that touches the microphone and the store; the policy decides what
    a sample means and whether it may be accepted.

WHY THE ADAPTERS SPLIT
    The policy in `core/custom_voice.py` is pure — it validates a sample's
    length and level and gates acceptance. That is so a test can drive every
    path with fixtures. This adapter does the I/O the policy cannot: it
    measures a real sample with `audio_devices.measure_input`, builds a
    `Sample`, and asks the policy to validate it. The policy never opens a
    microphone.

WHAT IT DOES NOT DO
    It does not synthesise a voice and it does not send a sample anywhere.
    A sample is measured locally, validated, and — only if the user accepts
    it — stored on this machine. The provider engine that turns the sample
    into a usable custom voice is a separate concern; this adapter records
    and stores, and the policy states plainly that acceptance is gated on
    consent and validity.
"""
from __future__ import annotations


def _stored_path() -> "object":
    """Where the stored custom-voice record lives.

    Kept beside the other local, personal biometric-adjacent data so a user
    can find and remove it in one place.
    """
    from memory.memory_manager import get_base_dir
    return get_base_dir() / "memory" / "custom_voice.json"


def read_stored() -> "object":
    """The stored custom voice, or an absent record if none/unreadable.

    An unreadable or incomplete record is reported as absent rather than
    raising: the page must show "no custom voice" for a corrupt file, not
    crash on it.
    """
    from core.custom_voice import build_stored
    import json

    path = _stored_path()
    try:
        if not path.exists():
            return build_stored(present=False)
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return build_stored(present=False)
        return build_stored(
            present=bool(data.get("present", False)),
            seconds=float(data.get("seconds", 0.0) or 0.0),
            level=float(data.get("level", 0.0) or 0.0),
            consented=bool(data.get("consented", False)),
        )
    except Exception:                              # noqa: BLE001
        return build_stored(present=False)


def record(consented: bool, seconds: float = 30.0) -> "tuple[bool, str, str]":
    """Record a sample through the audio plumbing and validate it.

    Returns `(ok, state, reason)` straight from the policy. If the
    microphone cannot be reached, the sample is reported as rejected with a
    reason naming the microphone — the user asked to record and the machine
    could not, which is a real outcome the page must show rather than a
    silent failure.
    """
    from core.custom_voice import Sample, validate_sample

    try:
        from core.audio_devices import measure_input
        result = measure_input(seconds=seconds)
        level = float(result.get("level", 0.0) or 0.0)
    except Exception as exc:                      # noqa: BLE001
        return False, "rejected", f"Mikrofon tidak bisa direkam: {exc}"

    return validate_sample(Sample(seconds=seconds, level=level,
                                  consented=consented))


def accept(sample) -> "tuple[bool, str]":
    """Accept a validated sample and persist it as the custom voice.

    The policy's `accept` decides whether the sample may be accepted; this
    adapter writes the resulting record to disk. A write that fails returns
    the policy's acceptance sentence anyway — the in-memory decision is the
    user's, and a failed write is reported by the next `read_stored` reading
    the absent record, not by undoing the acceptance silently.
    """
    from core.custom_voice import accept as _accept
    import json

    ok, reason = _accept(sample)
    if not ok:
        return False, reason

    record_dict = {
        "present": True,
        "seconds": sample.seconds,
        "level": sample.level,
        "consented": sample.consented,
    }
    try:
        _stored_path().write_text(json.dumps(record_dict), encoding="utf-8")
    except Exception as exc:                      # noqa: BLE001
        print(f"[Custom voice] simpan gagal: {exc}")
    return True, reason


def delete() -> "tuple[bool, str]":
    """Delete the stored custom voice.

    Removes the record file. Returns `(did_delete, reason)` from the
    policy, so a delete of an absent voice is reported as a no-op rather
    than a success.
    """
    from core.custom_voice import delete as _delete

    stored = read_stored()
    ok, reason = _delete(stored)
    if ok:
        try:
            _stored_path().unlink(missing_ok=True)
        except Exception as exc:                  # noqa: BLE001
            print(f"[Custom voice] hapus gagal: {exc}")
    return ok, reason


__all__ = ["read_stored", "record", "accept", "delete"]
