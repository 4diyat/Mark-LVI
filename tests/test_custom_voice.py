"""Board 5.8's custom voice policy: enrollment gating and deletion.

These test the pure policy in `core.custom_voice` with no microphone and no
file. The point is the consent gate and honesty: a sample recorded without
consent is refused before its quality is even considered, and a stored
record that is incomplete is reported as absent rather than shown as a
custom voice that does not exist.
"""
from __future__ import annotations

from core.custom_voice import (MAX_LEVEL, MAX_SAMPLE_SECONDS,
                               MIN_LEVEL, MIN_SAMPLE_SECONDS, REJECTED, READY,
                               Sample, accept, build_stored, delete,
                               is_length_ok, is_level_in_range,
                               validate_sample)


def _good() -> Sample:
    return Sample(seconds=30.0, level=0.5, consented=True)


# ── thresholds ───────────────────────────────────────────────────────────

def test_a_length_in_range_is_ok():
    assert is_length_ok(MIN_SAMPLE_SECONDS)
    assert is_length_ok(MAX_SAMPLE_SECONDS)


def test_a_length_out_of_range_is_not_ok():
    assert is_length_ok(10.0) is False
    assert is_length_ok(120.0) is False
    assert is_length_ok("garbage") is False


def test_a_level_in_range_is_ok():
    assert is_level_in_range(MIN_LEVEL)
    assert is_level_in_range(MAX_LEVEL)
    assert is_level_in_range(0.5)


def test_a_level_out_of_range_is_not_ok():
    assert is_level_in_range(0.0) is False
    assert is_level_in_range(1.5) is False
    assert is_level_in_range("x") is False


# ── validate_sample ───────────────────────────────────────────────────────

def test_a_good_consented_sample_is_ready():
    ok, state, reason = validate_sample(_good())
    assert ok is True
    assert state == READY


def test_consent_is_checked_before_quality():
    """A perfect recording made without consent is refused first."""
    ok, state, reason = validate_sample(Sample(seconds=30.0, level=0.5,
                                               consented=False))
    assert ok is False
    assert state == REJECTED
    assert "persetujuan" in reason


def test_a_short_sample_is_rejected():
    ok, state, reason = validate_sample(
        Sample(seconds=5.0, level=0.5, consented=True))
    assert ok is False
    assert state == REJECTED
    assert "pendek" in reason


def test_a_quiet_sample_is_rejected():
    ok, state, reason = validate_sample(
        Sample(seconds=30.0, level=0.001, consented=True))
    assert ok is False
    assert state == REJECTED
    assert "Tingkat" in reason


# ── accept ───────────────────────────────────────────────────────────────

def test_accepting_a_good_sample_reports_the_stored_voice():
    ok, reason = accept(_good())
    assert ok is True
    assert "Suara kustom" in reason


def test_accepting_an_invalid_sample_is_refused():
    ok, reason = accept(Sample(seconds=5.0, level=0.5, consented=True))
    assert ok is False
    assert "tidak bisa diterima" in reason


def test_accepting_without_consent_is_refused():
    ok, _ = accept(Sample(seconds=30.0, level=0.5, consented=False))
    assert ok is False


# ── build_stored ─────────────────────────────────────────────────────────

def test_an_absent_record_is_reported_absent():
    voice = build_stored(present=False)
    assert voice.present is False
    assert "tidak ada" in voice.summary().lower()


def test_a_complete_record_is_reported_present():
    voice = build_stored(present=True, seconds=30.0, level=0.5, consented=True)
    assert voice.present is True
    assert "disimpan" in voice.summary()


def test_an_incomplete_present_record_is_reported_absent():
    """A record that claims present but has no valid sample is not a voice."""
    voice = build_stored(present=True, seconds=1.0, level=0.5)
    assert voice.present is False


# ── delete ───────────────────────────────────────────────────────────────

def test_deleting_a_present_voice_reports_success():
    voice = build_stored(present=True, seconds=30.0, level=0.5, consented=True)
    ok, reason = delete(voice)
    assert ok is True
    assert "dihapus" in reason


def test_deleting_an_absent_voice_is_a_noop():
    ok, reason = delete(build_stored(present=False))
    assert ok is False
    assert "Tidak ada" in reason
