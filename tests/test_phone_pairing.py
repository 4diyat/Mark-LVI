"""Tests for the board 16 phone-pairing policy (no network or filesystem).

`core.phone_pairing.PairingSession` is a pure policy: it mints one-time codes,
consumes them against an injectable clock, records paired devices with a scope,
and decides handoffs. Every rule is tested with a fake clock so expiry and
one-time-use are deterministic.
"""
import pytest

from core.phone_pairing import (
    PAIRING_CHARS,
    PAIRING_CODE_LENGTH,
    SCOPE_COMMAND,
    SCOPE_READ,
    PairedDevice,
    PairingError,
    PairingSession,
)


def _session(now=1000.0):
    """A session on a fixed clock; pass a number or a mutable holder."""
    return PairingSession(_now=lambda: now)


# -- minting -------------------------------------------------------------
def test_mint_code_is_the_right_length_and_alphabet():
    code = _session().mint_code()
    assert len(code.code) == PAIRING_CODE_LENGTH
    assert all(c in PAIRING_CHARS for c in code.code)


def test_mint_code_expires_at_ttl_after_the_clock():
    s = _session(now=100.0)
    code = s.mint_code(ttl=60)
    assert code.expires_at == 160.0


def test_mint_code_replaces_a_pending_one():
    s = _session()
    first = s.mint_code()
    second = s.mint_code()
    assert first.code != second.code
    assert s.pending_code.code == second.code


def test_pending_code_is_none_when_none_minted():
    assert _session().pending_code is None


# -- consuming ----------------------------------------------------------
def test_consume_valid_code_pairs_the_device():
    s = _session()
    code = s.mint_code()
    device = s.consume_code(code.code, "Pixel 8", SCOPE_COMMAND)
    assert device.name == "Pixel 8"
    assert device.scope == SCOPE_COMMAND
    assert s.paired_names() == ["Pixel 8"]


def test_consume_is_one_time_use():
    s = _session()
    code = s.mint_code()
    s.consume_code(code.code, "A")
    with pytest.raises(PairingError):
        s.consume_code(code.code, "B")


def test_consume_rejects_a_wrong_code():
    s = _session()
    s.mint_code()
    with pytest.raises(PairingError):
        s.consume_code("WRONGCO", "A")


def test_consume_rejects_when_no_code_pending():
    with pytest.raises(PairingError):
        _session().consume_code("ANYCODE", "A")


def test_consume_rejects_an_expired_code_and_clears_it():
    s = _session(now=100.0)
    code = s.mint_code(ttl=60)
    s._now = lambda: 200.0                          # past expiry
    with pytest.raises(PairingError):
        s.consume_code(code.code, "A")
    assert s.pending_code is None                   # expired code is gone


def test_consume_rejects_an_unknown_scope():
    s = _session()
    code = s.mint_code()
    with pytest.raises(PairingError):
        s.consume_code(code.code, "A", "admin")


def test_consume_is_case_insensitive_and_trims():
    s = _session()
    code = s.mint_code()
    device = s.consume_code(f"  {code.code.lower()}  ", "A")
    assert device.name == "A"


# -- scope ---------------------------------------------------------------
def test_command_scope_implies_read():
    device = PairedDevice("A", SCOPE_COMMAND, 0)
    assert device.allows(SCOPE_COMMAND) is True
    assert device.allows(SCOPE_READ) is True


def test_read_scope_does_not_imply_command():
    device = PairedDevice("A", SCOPE_READ, 0)
    assert device.allows(SCOPE_READ) is True
    assert device.allows(SCOPE_COMMAND) is False


def test_unknown_scope_is_refused():
    device = PairedDevice("A", SCOPE_COMMAND, 0)
    assert device.allows("admin") is False


# -- inspection & handoff ------------------------------------------------
def test_find_returns_the_device_or_none():
    s = _session()
    code = s.mint_code()
    s.consume_code(code.code, "Pixel 8")
    assert s.find("Pixel 8") is not None
    assert s.find("Other") is None


def test_handoff_to_a_paired_command_device_is_allowed():
    s = _session()
    code = s.mint_code()
    s.consume_code(code.code, "Pixel 8", SCOPE_COMMAND)
    device = s.handoff("Pixel 8", SCOPE_COMMAND)
    assert device.name == "Pixel 8"
    assert s.handoff_target == "Pixel 8"


def test_handoff_to_an_unpaired_device_is_refused():
    s = _session()
    with pytest.raises(PairingError):
        s.handoff("Nobody", SCOPE_COMMAND)


def test_handoff_needs_the_scope_the_caller_asks_for():
    s = _session()
    code = s.mint_code()
    s.consume_code(code.code, "Reader", SCOPE_READ)
    with pytest.raises(PairingError):
        s.handoff("Reader", SCOPE_COMMAND)


def test_handoff_read_to_a_read_device_is_allowed():
    s = _session()
    code = s.mint_code()
    s.consume_code(code.code, "Reader", SCOPE_READ)
    assert s.handoff("Reader", SCOPE_READ).name == "Reader"
