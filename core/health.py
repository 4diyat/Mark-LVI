"""core/health.py — the pure policy behind the Health / Status panel (board 5.2).

WHAT THIS DECIDES
    Whether the assistant can report its own condition honestly. Board 5.2
    draws a Health page with cards for the active provider (quota, latency),
    the audio devices (microphone, speaker), the camera, and the machine
    (CPU/memory), plus a Diagnostics action. This module turns the raw signals
    those cards read into a classified report — each component is ok / warn /
    down, with a sentence a human can act on — without touching a config file,
    a device, or a Qt widget.

WHY THE DECISION IS PURE
    Health is a READ of many independent facts, and the classification is
    arithmetic over each fact's threshold. Whether a mic is present, whether a
    provider has quota, whether the CPU is overloaded are facts supplied by the
    caller (the adapter reads them); deciding what they mean is policy. A panel
    that classified inside the read would be a control whose verdict depended on
    which device happened to answer, and a test could not drive it.

WHAT IS INJECTED, AND WHY
    Every fact is a callable or a plain value handed to `build_report`, never
    imported here. The adapter supplies real reads (`audio_devices`, the
    provider registry, `system_monitor`); the tests supply fixtures. Importing
    the real readers into the policy would make a health check that cannot run
    without a microphone fail in a headless test — the same mistake the rest of
    the repo avoids by keeping I/O out of `core/`.

THE CLASSIFICATION IS HONEST, NOT OPTIMISTIC
    A fact that cannot be read is `warn`, never `ok`. "I could not tell" is a
    real and common state for a device that is unplugged or a provider that
    answered nothing; reporting it as healthy would be the one claim this page
    exists to stop making. A fact that raises is treated as unreadable, not as
    a passing reading.

WHAT THIS DOES NOT DO
    It does not diagnose a hang, and it does not run `tools_diag`. It reports
    the condition of the components the board draws. The Diagnostics button on
    the page runs the existing diagnostic tool; this policy only classifies the
    snapshot it is handed.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

# The three verdicts, in the order they escalate. A component is never
# reported as more healthy than its weakest unreadable signal.
OK = "ok"
WARN = "warn"
DOWN = "down"

# Machine load thresholds. The panel draws a bar; these decide the verdict.
# Deliberately generous: a health page that warns at 40 % CPU would warn on
# almost every machine, which trains the user to ignore it.
CPU_WARN = 80.0
CPU_DOWN = 95.0
MEM_WARN = 85.0
MEM_DOWN = 95.0


@dataclass
class Component:
    """One card's verdict: a name, a status, and the sentence behind it.

    `status` is one of OK / WARN / DOWN. `detail` is what a human reads; an
    empty detail on an OK card is fine (there is nothing to say), but a WARN
    or DOWN card must explain itself — a red card with no reason is a control
    the user cannot act on.
    """

    name: str
    status: str
    detail: str = ""


@dataclass
class HealthReport:
    """The assembled page: every card plus one summary sentence.

    `provider`, `devices` and `system` are the raw sections; `summary` is the
    single line the page's header shows. `generated_at` is stamped by the
    adapter (the policy does not own a clock), so a report can be told apart
    from a stale one.
    """

    provider: Component = field(
        default_factory=lambda: Component("provider", OK, ""))
    microphone: Component = field(
        default_factory=lambda: Component("microphone", OK, ""))
    speaker: Component = field(
        default_factory=lambda: Component("speaker", OK, ""))
    camera: Component = field(
        default_factory=lambda: Component("camera", OK, ""))
    system: Component = field(
        default_factory=lambda: Component("system", OK, ""))
    generated_at: str = ""

    def worst(self) -> str:
        """The most severe status across all cards, or OK if every card is OK.

        The summary line is driven by this: the page must not claim "all
        healthy" while one card is down, and must not stay quiet about a
        component that is failing.
        """
        order = {OK: 0, WARN: 1, DOWN: 2}
        cards = (self.provider, self.microphone, self.speaker,
                 self.camera, self.system)
        top = OK
        for card in cards:
            if order.get(card.status, 0) > order.get(top, 0):
                top = card.status
        return top

    def summary(self) -> str:
        """The header sentence, from the worst verdict alone."""
        state = self.worst()
        if state == OK:
            return "Semua komponen sehat."
        if state == WARN:
            return "Sebagian komponen perlu perhatian."
        return "Ada komponen yang perlu diperbaiki."


def _classify(read: Callable[[], object]) -> tuple[object, bool]:
    """Run a fact reader, returning (value, was_readable).

    A reader that raises, or returns None, is UNREADABLE — the caller decides
    what that means (for a mic, warn; for a quota, warn). This is the single
    place that turns an exception into the honest "could not tell" answer
    instead of letting it escape as a crash.
    """
    try:
        value = read()
    except Exception:                               # noqa: BLE001
        return None, False
    return value, value is not None


def classify_provider(read) -> Component:
    """The active-provider card: a provider name plus its quota/latency facts.

    `read` returns a dict (or a callable returning one) with any of:
    `name`, `quota` (0..1 or None), `latency_ms` (number or None). A provider
    with no name is unreadable → warn, because the card cannot name it. A
    provider whose quota is exhausted is DOWN — it cannot answer at all. A
    provider that is present but whose latency is high is WARN.
    """
    value, ok = _classify(read)
    if not ok or not isinstance(value, dict):
        return Component("provider", WARN,
                         "Provider aktif tidak bisa dibaca.")
    name = str(value.get("name") or "").strip()
    if not name:
        return Component("provider", WARN,
                         "Tidak ada provider aktif yang tercatat.")
    quota = value.get("quota")
    latency = value.get("latency_ms")
    # Quota exhausted is a hard failure: the assistant cannot answer.
    try:
        if quota is not None and float(quota) <= 0.0:
            return Component("provider", DOWN,
                             f"Kuota {name} habis — provider tidak bisa menjawab.")
    except (TypeError, ValueError):
        quota = None
    # A very high latency is a warning, not a failure: it still answers.
    try:
        if latency is not None and float(latency) >= 5000.0:
            return Component("provider", WARN,
                             f"Latensi {name} tinggi ({latency:.0f} ms).")
    except (TypeError, ValueError):
        latency = None
    detail_bits = []
    if quota is not None:
        detail_bits.append(f"kuota {float(quota) * 100:.0f} %")
    if latency is not None:
        detail_bits.append(f"latensi {float(latency):.0f} ms")
    detail = f"{name} aktif"
    if detail_bits:
        detail += " (" + ", ".join(detail_bits) + ")"
    return Component("provider", OK, detail)


def classify_audio(kind: str, read) -> Component:
    """A microphone or speaker card.

    `read` returns a truthy value (a device list, a count, a level) when the
    device is usable, or None/empty when it is not. Present-but-unusable and
    absent-and-unreadable are both WARN, not DOWN: the assistant can still
    speak without a microphone, and silence is not a failure — but claiming a
    device healthy when it is not is the lie this page exists to prevent.
    """
    value, ok = _classify(read)
    if not ok:
        return Component(kind, WARN,
                         f"Perangkat {kind} tidak bisa diperiksa.")
    # A present device: anything truthy (a non-empty list, a count > 0, a
    # positive level). An empty list or a zero is "not usable".
    usable = False
    if isinstance(value, (list, tuple, set, str)):
        usable = len(value) > 0
    else:
        try:
            usable = float(value) > 0
        except (TypeError, ValueError):
            usable = bool(value)
    if not usable:
        return Component(kind, WARN,
                         f"Tidak ada perangkat {kind} yang bisa digunakan.")
    return Component(kind, OK, f"Perangkat {kind} tersedia.")


def classify_camera(read) -> Component:
    """The camera card. A lease being held, or a device list, means usable.

    The camera is opt-in and often absent on a headless machine, so absent is
    WARN, not DOWN: the page says so plainly rather than calling it failed.
    """
    value, ok = _classify(read)
    if not ok:
        return Component("camera", WARN,
                         "Kamera tidak bisa diperiksa.")
    usable = bool(value)
    if isinstance(value, (list, tuple, set)):
        usable = len(value) > 0
    if not usable:
        return Component("camera", WARN,
                         "Tidak ada kamera yang bisa digunakan.")
    return Component("camera", OK, "Kamera tersedia.")


def classify_system(read) -> Component:
    """The machine card: CPU and memory, from a dict of percentages.

    `read` returns a dict with `cpu_percent` and `ram_percent`. Both are
    classified against the thresholds; the worse of the two wins. A machine
    whose CPU is at 95 % is DOWN — it will not be able to answer promptly.
    """
    value, ok = _classify(read)
    if not ok or not isinstance(value, dict):
        return Component("system", WARN, "Status sistem tidak bisa dibaca.")
    cpu = value.get("cpu_percent")
    mem = value.get("ram_percent")
    worst = OK
    detail_bits = []
    try:
        cpu_v = float(cpu) if cpu is not None else None
    except (TypeError, ValueError):
        cpu_v = None
    try:
        mem_v = float(mem) if mem is not None else None
    except (TypeError, ValueError):
        mem_v = None
    if cpu_v is None and mem_v is None:
        return Component("system", WARN, "CPU dan memori tidak bisa dibaca.")
    # Track the worst verdict seen. Escalation order OK < WARN < DOWN.
    order = {OK: 0, WARN: 1, DOWN: 2}

    def _escalate(current: str, candidate: str) -> str:
        return candidate if order[candidate] > order[current] else current

    if cpu_v is not None:
        if cpu_v >= CPU_DOWN:
            worst = _escalate(worst, DOWN)
            detail_bits.append(f"CPU {cpu_v:.0f} %")
        elif cpu_v >= CPU_WARN:
            worst = _escalate(worst, WARN)
            detail_bits.append(f"CPU {cpu_v:.0f} %")
    if mem_v is not None:
        if mem_v >= MEM_DOWN:
            worst = _escalate(worst, DOWN)
            detail_bits.append(f"memori {mem_v:.0f} %")
        elif mem_v >= MEM_WARN:
            worst = _escalate(worst, WARN)
            detail_bits.append(f"memori {mem_v:.0f} %")
    if worst == OK:
        return Component("system", OK, "CPU dan memori dalam batas.")
    if worst == DOWN:
        return Component("system", DOWN,
                         "Sumber daya tinggi: " + ", ".join(detail_bits) + ".")
    return Component("system", WARN,
                     "Sumber daya meningkat: " + ", ".join(detail_bits) + ".")


def build_report(
    provider_read: Callable[[], object],
    mic_read: Callable[[], object],
    speaker_read: Callable[[], object],
    camera_read: Callable[[], object],
    system_read: Callable[[], object],
    *,
    generated_at: str = "",
) -> HealthReport:
    """Assemble the full page from five injected readers.

    Each reader is called once. A reader that raises is caught by the
    classifiers above and reported as unreadable — `build_report` itself never
    raises, because a health page that crashed on one bad device would hide
    the very problem it exists to show.
    """
    return HealthReport(
        provider=classify_provider(provider_read),
        microphone=classify_audio("microphone", mic_read),
        speaker=classify_audio("speaker", speaker_read),
        camera=classify_camera(camera_read),
        system=classify_system(system_read),
        generated_at=generated_at,
    )


__all__ = [
    "OK", "WARN", "DOWN",
    "CPU_WARN", "CPU_DOWN", "MEM_WARN", "MEM_DOWN",
    "Component", "HealthReport",
    "classify_provider", "classify_audio", "classify_camera",
    "classify_system", "build_report",
]
