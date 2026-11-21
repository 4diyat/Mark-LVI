"""Transcript cleaning and the HUD's loudness number.

Both lived in `main.py` and could only be reached by importing the Live SDK,
sounddevice, numpy and Qt — so neither had a test. They are where incoming audio
becomes something the user sees, and both have a history:

  * control markers (`<ctrl23>`) reaching the activity log verbatim, so the log
    showed a sentence the user never heard the model say;
  * the server re-sending the tail of an answer across the several
    turn_completes a tool-using turn produces, so the log showed it twice.
"""
from __future__ import annotations

import ast
from pathlib import Path

import numpy as np

from core import transcript

ROOT = Path(__file__).resolve().parent.parent


# ── loudness ──────────────────────────────────────────────────────────────

def _pcm(amplitude, n=480):
    """A square block at `amplitude` — an easy, exact RMS."""
    return np.full(n, amplitude, dtype=np.int16).tobytes()


def test_room_silence_reads_as_zero_not_as_a_quiet_bar():
    """The floor is room tone, not zero: a silent room must not move the
    waveform, or the HUD breathes while nobody is talking."""
    assert transcript.pcm_level(_pcm(0)) == 0.0
    assert transcript.pcm_level(_pcm(40)) == 0.0


def test_a_full_scale_block_reads_as_one_and_not_above():
    assert transcript.pcm_level(_pcm(32767, 64)) == 1.0


def test_ordinary_speech_lands_between_the_two_ends():
    """Tuned so speech sits mid-range rather than pinned to an end."""
    level = transcript.pcm_level(_pcm(1200))
    assert 0.3 < level < 0.8, level


def test_a_block_that_is_not_audio_returns_zero_instead_of_raising():
    """THE PROPERTY THAT MATTERS.

    This runs inside the microphone callback and the receive loop. An exception
    here costs the session rather than one bar of the waveform, so the function
    must survive anything the device hands it.
    """
    assert transcript.pcm_level(b"") == 0.0
    assert transcript.pcm_level(None) == 0.0
    assert transcript.pcm_level(np.array([np.nan])) == 0.0
    assert transcript.pcm_level(object()) == 0.0
    assert transcript.pcm_level([1, 2, "three"]) == 0.0


def test_an_empty_block_is_zero_and_does_not_warn_every_frame():
    """`size == 0` is checked explicitly, and it is not redundant.

    The non-finite guard below would also catch it, but only after
    `np.mean([])` has emitted a RuntimeWarning — once per audio frame, at fifty
    frames a second, for the whole session. Silence is not a diagnostic, and a
    warning nobody can act on is noise that hides the one that matters.
    """
    import warnings

    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        assert transcript.pcm_level(np.array([], dtype=np.int16)) == 0.0
        assert transcript.pcm_level(b"") == 0.0
    assert [w for w in caught if issubclass(w.category, RuntimeWarning)] == []


def test_the_level_never_exceeds_one_whatever_arrives():
    for amplitude in (0, 1, 100, 5000, 32767):
        level = transcript.pcm_level(_pcm(amplitude, 32))
        assert 0.0 <= level <= 1.0, (amplitude, level)


# ── transcript cleaning ───────────────────────────────────────────────────

def test_a_control_marker_never_reaches_the_log():
    """The log used to show `<ctrl23>` as if the model had said it."""
    assert transcript.clean_transcript("Hello <ctrl23>there") == "Hello there"


def test_a_control_marker_is_stripped_in_any_case_and_at_any_number():
    assert transcript.clean_transcript("<CTRL4>") == ""
    assert transcript.clean_transcript("a<ctrl1234>b") == "ab"


def test_unprintable_bytes_are_removed_but_newlines_are_kept():
    """\\n and \\t are printable enough to be legitimate in a transcript; the
    rest of the control range is not."""
    cleaned = transcript.clean_transcript("one\x00two\x07\nthree\tfour")
    assert "\x00" not in cleaned and "\x07" not in cleaned
    assert "\n" in cleaned and "\t" in cleaned


def test_cleaning_does_not_mangle_ordinary_text():
    text = "Tolong buka browser, lalu cari 'Bandung cuaca' — 25°C."
    assert transcript.clean_transcript(text) == text


def test_leading_and_trailing_whitespace_is_trimmed():
    assert transcript.clean_transcript("  hi  ") == "hi"


def test_cleaning_never_raises_on_a_partial_chunk():
    """Half a multi-byte character can arrive mid-frame; the receive loop must
    not die for one bad chunk."""
    assert transcript.clean_transcript(None) == ""
    assert transcript.clean_transcript("") == ""


# ── repeat detection ──────────────────────────────────────────────────────

def test_a_long_chunk_already_in_the_turn_is_a_repeat():
    buf = ["The first answer.", "And the second part of it."]
    assert transcript.is_repeat_chunk("And the second part of it.", buf)


def test_a_long_chunk_that_is_new_is_not_a_repeat():
    buf = ["The first answer."]
    assert not transcript.is_repeat_chunk("A completely different sentence.", buf)


def test_a_short_chunk_may_legitimately_repeat():
    """"yes, yes" is a real sentence: a short chunk is compared only with the
    immediately previous one, never with the whole turn."""
    buf = ["yes"]
    assert transcript.is_repeat_chunk("yes", buf)
    buf = ["ok", "yes"]
    assert transcript.is_repeat_chunk("ok", buf) is False, \
        "a short chunk was matched against the whole turn"


def test_a_short_chunk_against_an_empty_turn_is_not_a_repeat():
    assert not transcript.is_repeat_chunk("hi", [])


def test_the_threshold_is_where_the_docstring_says_it_is():
    """The boundary is load-bearing and was a bare magic number in main.py."""
    short = "a" * (transcript.REPEAT_MIN - 1)
    long = "a" * transcript.REPEAT_MIN
    assert transcript.is_repeat_chunk(short, [short, "other"]) is False
    assert transcript.is_repeat_chunk(long, ["x" * 100 + long]) is True


def test_repeat_detection_never_raises_on_a_missing_buffer():
    assert not transcript.is_repeat_chunk("hi", ())


# ── the wiring stays wiring ───────────────────────────────────────────────

def test_main_delegates_instead_of_keeping_a_second_copy():
    tree = ast.parse((ROOT / "main.py").read_text(encoding="utf-8"))
    source = (ROOT / "main.py").read_text(encoding="utf-8")

    # The regexes and thresholds that used to live here are gone.
    assert "_CTRL_RE" not in source
    assert "_LEVEL_FLOOR" not in source
    assert "_REPEAT_MIN =" not in source

    # And the names main.py still calls are delegates to the module.
    funcs = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)}
    assert ast.unparse(funcs["_pcm_level"]).count("_transcript.pcm_level") == 1
    assert ast.unparse(funcs["_clean_transcript"]).count(
        "_transcript.clean_transcript") == 1


def test_the_module_does_not_import_the_application():
    """It must stay testable without the Live SDK, sounddevice or Qt."""
    tree = ast.parse((ROOT / "core" / "transcript.py").read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert imported <= {"__future__", "re", "numpy"}, imported
