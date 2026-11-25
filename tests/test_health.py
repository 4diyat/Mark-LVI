"""Board 5.2's Health / Status policy: classify a snapshot of the components.

These test the pure policy in `core.health` with no device and no config. The
point is the honesty rule: an unreadable fact is a warning, never a healthy
verdict, and a page never claims "all healthy" while one card is down.
"""
from __future__ import annotations

from core.health import (DOWN, OK, WARN, Component,
                         build_report, classify_audio, classify_camera,
                         classify_provider, classify_system)


# ── classify_provider ───────────────────────────────────────────────────────

def test_a_named_provider_with_no_live_facts_is_ok():
    comp = classify_provider(lambda: {"name": "gemini"})
    assert comp.status == OK
    assert "gemini" in comp.detail


def test_a_provider_with_quota_and_latency_reports_them():
    comp = classify_provider(lambda: {"name": "openai", "quota": 0.7,
                                      "latency_ms": 800})
    assert comp.status == OK
    assert "70 %" in comp.detail
    assert "800 ms" in comp.detail


def test_an_empty_quota_is_down_not_ok():
    comp = classify_provider(lambda: {"name": "openai", "quota": 0.0})
    assert comp.status == DOWN
    assert "habis" in comp.detail


def test_a_very_high_latency_is_a_warning():
    comp = classify_provider(lambda: {"name": "openai", "latency_ms": 9000})
    assert comp.status == WARN
    assert "Latensi" in comp.detail


def test_a_provider_that_cannot_be_read_is_a_warning_not_ok():
    def _boom():
        raise RuntimeError("config locked")

    comp = classify_provider(_boom)
    assert comp.status == WARN
    assert "tidak bisa dibaca" in comp.detail


def test_a_provider_without_a_name_is_a_warning():
    comp = classify_provider(lambda: {})
    assert comp.status == WARN


# ── classify_audio ─────────────────────────────────────────────────────────

def test_a_present_device_is_ok():
    comp = classify_audio("microphone", lambda: ["Built-in Microphone"])
    assert comp.status == OK


def test_an_absent_device_is_a_warning_not_down():
    comp = classify_audio("microphone", lambda: [])
    assert comp.status == WARN
    assert "bisa digunakan" in comp.detail


def _raising():
    raise OSError("device gone")


def test_an_unreadable_device_is_a_warning():
    comp = classify_audio("speaker", _raising)
    assert comp.status == WARN
    assert "tidak bisa diperiksa" in comp.detail


def test_a_zero_volume_speaker_is_not_ok():
    comp = classify_audio("speaker", lambda: 0)
    assert comp.status == WARN


# ── classify_camera ────────────────────────────────────────────────────────

def test_a_held_camera_is_ok():
    assert classify_camera(lambda: True).status == OK


def test_an_unavailable_camera_is_a_warning_not_down():
    comp = classify_camera(lambda: False)
    assert comp.status == WARN


def test_an_unreadable_camera_is_a_warning():
    comp = classify_camera(_raising)
    assert comp.status == WARN


# ── classify_system ───────────────────────────────────────────────────────

def test_a_quiet_machine_is_ok():
    comp = classify_system(lambda: {"cpu_percent": 10.0, "ram_percent": 30.0})
    assert comp.status == OK


def test_a_warn_level_cpu_is_a_warning():
    comp = classify_system(lambda: {"cpu_percent": 82.0, "ram_percent": 30.0})
    assert comp.status == WARN
    assert "CPU" in comp.detail


def test_a_down_level_memory_is_down():
    comp = classify_system(lambda: {"cpu_percent": 10.0, "ram_percent": 97.0})
    assert comp.status == DOWN
    assert "memori" in comp.detail


def test_the_worse_of_cpu_and_memory_wins():
    comp = classify_system(lambda: {"cpu_percent": 82.0, "ram_percent": 97.0})
    assert comp.status == DOWN, "the down memory must dominate the warn cpu"


def test_an_unreadable_machine_is_a_warning():
    comp = classify_system(_raising)
    assert comp.status == WARN


# ── build_report / HealthReport ───────────────────────────────────────────

def test_a_fully_healthy_report_says_so():
    report = build_report(
        lambda: {"name": "gemini"},
        lambda: ["mic"],
        lambda: 50,
        lambda: True,
        lambda: {"cpu_percent": 10.0, "ram_percent": 20.0},
        generated_at="2026-11-25T10:00:00",
    )
    assert report.worst() == OK
    assert report.summary() == "Semua komponen sehat."
    assert report.generated_at == "2026-11-25T10:00:00"


def test_the_summary_reflects_the_worst_card():
    report = build_report(
        lambda: {"name": "gemini"},
        lambda: ["mic"],
        lambda: 50,
        lambda: False,                              # camera down→warn
        lambda: {"cpu_percent": 10.0, "ram_percent": 20.0},
    )
    assert report.worst() == WARN
    assert report.summary() == "Sebagian komponen perlu perhatian."


def test_a_down_provider_dominates_the_summary():
    report = build_report(
        lambda: {"name": "openai", "quota": 0.0},  # down
        lambda: ["mic"],
        lambda: 50,
        lambda: True,
        lambda: {"cpu_percent": 10.0, "ram_percent": 20.0},
    )
    assert report.worst() == DOWN
    assert report.summary() == "Ada komponen yang perlu diperbaiki."


def test_a_reader_that_raises_does_not_crash_the_report():
    """One bad device must not take the whole page down with it."""
    report = build_report(
        lambda: {"name": "gemini"},
        _raising,
        lambda: 50,
        lambda: True,
        lambda: {"cpu_percent": 10.0, "ram_percent": 20.0},
    )
    assert report.microphone.status == WARN
    assert report.worst() == WARN


def test_the_component_dataclass_carries_a_status():
    c = Component("x", OK, "fine")
    assert c.name == "x" and c.status == OK and c.detail == "fine"
