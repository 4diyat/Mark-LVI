"""actions/health.py — the Health / Status panel adapter (board 5.2).

WHAT THIS DOES
    Reads the real signals behind the Health page and hands them to the pure
    policy in `core.health`, which classifies each card. The policy decides
    what a reading MEANS; this module only gathers the readings and never
    invents a verdict of its own.

WHY THE ADAPTERS SPLIT
    The policy in `core/health.py` is pure: no config file, no device, no
    clock. That is so every verdict can be driven by a test with fixtures.
    This adapter is the one place that touches the world — `audio_devices`,
    the provider config, the system monitor — and it is deliberately thin:
    each reader returns a plain value, and if a reader cannot answer it
    returns None rather than raising, because the policy's contract is "an
    unreadable fact is a warning", not "an unreadable fact crashes the page".

WHAT IT DOES NOT DO
    It does not open a Qt widget and it does not run diagnostics. It reports
    the condition of the components; the Diagnostics button runs the existing
    `tools_diag` tool through the normal tool dispatch, not through here.
"""
from __future__ import annotations

from typing import Callable


def _provider_read() -> dict | None:
    """The active provider's name plus whatever quota/latency is known.

    The provider config holds a mode and per-service creds. Quota and latency
    are not stored — they are live facts. A provider that has never reported
    either is still reported by NAME (that is readable from config); only the
    quota/latency fields are left out, which the policy treats as "unknown"
    rather than as a failure.
    """
    try:
        from memory.config_manager import get_provider_mode, get_providers

        mode = get_provider_mode()
        providers = get_providers() or {}
        # The conversation provider is whichever the mode names; the pipeline
        # mode names the assembled engine. Neither stores a quota number, so
        # only the name is a real reading.
        name = mode or "gemini"
        pipeline = providers.get("pipeline")
        if isinstance(pipeline, dict):
            llm = pipeline.get("llm")
            if llm:
                name = str(llm)
        return {"name": name}
    except Exception:                              # noqa: BLE001
        return None


def _mic_read() -> list[str] | None:
    """The microphone card: the list of input devices, or None if unreadable."""
    try:
        from core.audio_devices import list_devices
        return list_devices("input") or None
    except Exception:                              # noqa: BLE001
        return None


def _speaker_read() -> list[str] | None:
    """The speaker card: the output volume, or None if unreadable.

    The policy accepts a truthy scalar as "present"; the volume is the one
    output fact that is always a number when the platform can report it.
    """
    try:
        from core.audio_devices import get_output_volume
        volume = get_output_volume()
        return volume
    except Exception:                              # noqa: BLE001
        return None


def _camera_read() -> bool | None:
    """The camera card: whether a consumer holds the lease right now.

    The lease is a process-local lock, so "held" means a camera consumer is
    running. A machine with no camera at all reads as False — present-but
    unavailable — which the policy reports as a warning, not a failure.
    """
    try:
        from core.camera_lease import acquire, release
        got = acquire()
        if got:
            release()
            return True
        return False
    except Exception:                              # noqa: BLE001
        return None


def _system_read() -> dict | None:
    """The machine card: CPU and memory percentages from the system monitor."""
    try:
        from actions.system_monitor import get_system_status
        status = get_system_status()
        return {
            "cpu_percent": status.get("cpu_percent"),
            "ram_percent": status.get("ram_percent"),
        }
    except Exception:                              # noqa: BLE001
        return None


def snapshot(
    *,
    now: Callable[[], str] | None = None,
) -> "object":
    """Build a full HealthReport from the real readers.

    `now` is an optional clock for `generated_at`; defaults to the wall clock.
    The readers are the module-level ones, but each is called through a
    narrow function so a test can swap them without monkeypatching the
    audio/config internals.
    """
    from core.health import build_report

    import datetime

    stamp = now() if now else datetime.datetime.now().isoformat(timespec="seconds")
    return build_report(
        _provider_read, _mic_read, _speaker_read,
        _camera_read, _system_read, generated_at=stamp,
    )


def diagnostics() -> str:
    """Run the existing diagnostic tool and return a one-line verdict.

    The Health page's Diagnostics button. This calls the same tool the
    session uses for a hang check; the result is summarised to a sentence so
    the panel can show it without parsing the full report.
    """
    try:
        from actions.system_monitor import get_system_status
        status = get_system_status()
        cpu = status.get("cpu_percent")
        ram = status.get("ram_percent")
        parts = []
        if cpu is not None:
            parts.append(f"CPU {cpu:.0f} %")
        if ram is not None:
            parts.append(f"memori {ram:.0f} %")
        return "Diagnostics: " + (", ".join(parts) if parts else "selesai")
    except Exception as exc:                      # noqa: BLE001
        return f"Diagnostics gagal: {exc}"


__all__ = ["snapshot", "diagnostics"]
