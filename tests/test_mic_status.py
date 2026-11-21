"""What the app says about the microphone.

`_listen_audio` is 155 lines of callback and device loop, and the sentences
inside it are what the user actually experiences. Three were wrong in ways
nobody could see from reading the loop:

  * "Microphone found — listening again" could be SKIPPED, because the flag
    gating it was set when a device appeared and never cleared;
  * "Mic stream open" repeated on every recovery — a debug print behaving like
    a status line;
  * a DIFFERENT failure right after a loss was never named.
"""
from __future__ import annotations

import ast
from pathlib import Path

from core import mic_status as ms

ROOT = Path(__file__).resolve().parent.parent


# ── what a working microphone implies ─────────────────────────────────────

def test_an_awake_assistant_listens():
    assert ms.state_for(awake=True) == "LISTENING"


def test_an_asleep_assistant_does_not_claim_to_be_listening():
    """With the wake word on, the mic is gated. Painting LISTENING would say
    "I am listening to you" while deliberately ignoring what is said."""
    assert ms.state_for(awake=False) == "SLEEPING"


def test_the_state_names_match_the_ui_vocabulary():
    """A typo in a bare string is a silently blank HUD, which is why the names
    live here instead of being spelled at each call site."""
    assert (ms.NO_MIC, ms.LISTENING, ms.SLEEPING) == ("NO MIC", "LISTENING", "SLEEPING")


# ── the recovery sentence ─────────────────────────────────────────────────

def test_the_first_recovery_is_announced():
    log, _ = ms.messages(ms.MicEvent(opened=True, recovered=True,
                                     recovered_first_time=True))
    assert log == "SYS: Microphone found — listening again."


def test_a_later_recovery_is_still_announced():
    """THE BUG. The flag was set on the first recovery and never cleared, so the
    second loss-and-return resumed listening in silence — the user was left
    waiting for a confirmation that never came."""
    log, _ = ms.messages(ms.MicEvent(opened=True, recovered=True,
                                     recovered_first_time=False))
    assert log == "SYS: Microphone found — listening again."


def test_a_normal_open_says_nothing_in_the_log():
    """Opening on startup is not news; the HUD already shows LISTENING."""
    log, line = ms.messages(ms.MicEvent(opened=True))
    assert log is None
    assert "Mic stream open" in line


def test_a_recovery_does_not_print_the_plain_open_line_too():
    """One event, one line. Both fired, so every recovery produced two."""
    _, line = ms.messages(ms.MicEvent(opened=True, recovered=True))
    assert "🎤" in line
    assert line.count("🎤") == 1
    assert "Mic stream open" not in line


# ── the loss sentences ────────────────────────────────────────────────────

def test_a_stream_that_stopped_says_it_is_retrying():
    log, _ = ms.messages(ms.MicEvent(stream_ended=True))
    assert log == "SYS: Microphone stream stopped — retrying."


def test_a_stream_that_failed_names_the_reason_and_what_still_works():
    """Typing and every tool still work; saying so is the difference between a
    degraded app and a broken one."""
    log, _ = ms.messages(ms.MicEvent(lost=True, problem="device busy"))
    assert "device busy" in log
    assert "typing still works" in log


def test_a_failure_without_a_reason_does_not_leave_an_empty_parenthesis():
    log, _ = ms.messages(ms.MicEvent(lost=True))
    assert "()" not in log
    assert "typing still works" in log


def test_stopped_and_failed_are_different_sentences():
    """They call for different reactions: one is a device that went away, the
    other is a device that refused. One sentence for both was the old shape."""
    stopped, _ = ms.messages(ms.MicEvent(stream_ended=True))
    failed, _ = ms.messages(ms.MicEvent(lost=True, problem="x"))
    assert stopped != failed


def test_nothing_happened_means_nothing_is_said():
    assert ms.messages(ms.MicEvent()) == (None, None)


# ── how often the failure may be repeated ─────────────────────────────────

def test_the_first_failure_is_said():
    assert ms.should_repeat_failure(said_already=False) is True


def test_a_failure_still_being_retried_is_not_repeated():
    """The recovery loop runs every two seconds; a log line at that rate is how
    a transcript becomes unreadable."""
    assert ms.should_repeat_failure(said_already=True) is False


# ── the wiring ────────────────────────────────────────────────────────────

def test_main_asks_the_module_and_never_spells_the_sentences():
    source = (ROOT / "main.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    literals = [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant)
                and isinstance(n.value, str)]

    assert "_mic_status.messages(" in source
    assert "_mic_status.state_for(" in source
    assert "_mic_status.should_repeat_failure(" in source

    assert not any("Microphone found" in s for s in literals), "the sentence is written twice"
    assert not any("typing still works" in s for s in literals)
    # The two functions that paint the microphone's own state:
    applying = next(n for n in ast.walk(tree)
                    if isinstance(n, ast.FunctionDef)
                    and n.name == "_apply_listening_state")
    # The BODY only: the docstring explains the rule and is allowed to name it.
    # `body[0]` is the docstring; the rule is about the statements after it.
    statements = applying.body[1:] if (applying.body and isinstance(
        applying.body[0], ast.Expr)) else applying.body
    code = ast.unparse(ast.Module(body=statements, type_ignores=[]))
    assert "NO MIC" not in code, code
    assert "SLEEPING" not in code, code
    # And the mic loop's own NO MIC paints, which used to be spelled inline
    # three times, now come from the module.
    mic_loop = ast.unparse(next(n for n in ast.walk(tree)
                                if isinstance(n, ast.AsyncFunctionDef)
                                and n.name == "_listen_audio"))
    assert 'set_state("NO MIC")' not in mic_loop


def test_the_recovered_flag_and_the_first_time_flag_are_separate():
    """Conflating them IS the bug: one asks "did it come back just now", the
    other "has this ever been said"."""
    source = (ROOT / "main.py").read_text(encoding="utf-8")
    assert "_mic_recovered_first" in source
    # And the first-time flag must be CLEARED once used, or it is the same bug
    # with a new name.
    assert "self._mic_recovered_first = False" in source


def test_the_module_decides_nothing_about_hardware():
    """Whether a device exists is `core/audio_devices.py`; whether it works is
    the host's answer. This module only decides what is worth saying."""
    source = (ROOT / "core" / "mic_status.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert imported <= {"__future__", "dataclasses"}, imported
