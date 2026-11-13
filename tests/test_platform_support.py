"""What this machine permits, and how the assistant is told about it.

WHY THIS IS WORTH 20 TESTS
    Every fact in `core/platform_support.py` corresponds to a way the assistant
    could claim something it did not do. On Wayland, `pyautogui.click()` returns
    successfully and nothing happens; on macOS without Accessibility the same.
    The app used to say "clicked it" — because from inside the process it had.

    `describe_for_model` is the fix, so it is the thing that has to be right:
    the sentences are an instruction NOT to claim an outcome, and they are
    checked here as text, because that is what the model reads.
"""
from __future__ import annotations

import platform
import shutil

import pytest

from core import platform_support as ps


@pytest.fixture()
def machine(monkeypatch):
    """Pretend to be another OS, with a chosen session and tools installed."""
    def configure(system: str, session: str = "", wayland: bool = False,
                  display: bool = False, tools: tuple[str, ...] = ()) -> None:
        monkeypatch.setattr(platform, "system", lambda: system)
        monkeypatch.delenv("XDG_SESSION_TYPE", raising=False)
        monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
        monkeypatch.delenv("DISPLAY", raising=False)
        if session:
            monkeypatch.setenv("XDG_SESSION_TYPE", session)
        if wayland:
            monkeypatch.setenv("WAYLAND_DISPLAY", "wayland-0")
        if display:
            monkeypatch.setenv("DISPLAY", ":0")
        monkeypatch.setattr(shutil, "which", lambda name: f"/usr/bin/{name}"
                            if name in tools else None)
    return configure


# ── what each machine can do ────────────────────────────────────────────────

def test_windows_is_the_one_platform_without_caveats(machine):
    machine("Windows")

    support = ps.detect()

    assert support.os_name == "Windows"
    assert support.fully_capable is True
    assert support.notes == []


def test_macos_works_but_warns_about_the_two_permissions(machine):
    """The permissions fail SILENTLY, which is why the warning is not optional."""
    machine("Darwin")

    support = ps.detect()

    assert support.fully_capable is True          # nothing is known to be off
    assert len(support.notes) == 1
    assert "Accessibility" in support.notes[0]
    assert "Screen Recording" in support.notes[0]
    assert "appear to succeed" in support.notes[0]


def test_no_graphical_session_means_none_of_the_three(machine):
    machine("Linux")

    support = ps.detect()

    assert (support.can_control_input, support.can_capture_screen,
            support.can_focus_windows) == (False, False, False)
    assert "No graphical session" in support.notes[0]
    # ...and it says what still works, so the user does not think the app died.
    assert "Voice, memory, files and the web still work" in support.notes[0]


def test_wayland_refuses_all_three_and_explains_that_it_is_by_design(machine):
    machine("Linux", session="wayland")

    support = ps.detect()

    assert support.fully_capable is False
    note = support.notes[0]
    assert "by design, not by fault" in note
    assert "Xorg" in note, "the note has to say what the user can do about it"


def test_x11_permits_everything_when_a_window_tool_is_installed(machine):
    machine("Linux", session="x11", tools=("xdotool",))

    support = ps.detect()

    assert support.fully_capable is True
    assert support.notes == []


def test_x11_without_a_window_tool_can_still_do_the_rest(machine):
    machine("Linux", session="x11", tools=())

    support = ps.detect()

    assert support.can_control_input is True
    assert support.can_capture_screen is True
    assert support.can_focus_windows is False
    assert "xdotool" in support.notes[0] and "wmctrl" in support.notes[0]


def test_wmctrl_alone_is_enough_to_focus(machine):
    machine("Linux", session="x11", tools=("wmctrl",))

    assert ps.detect().can_focus_windows is True


# ── reading the session, which is the fiddly part ───────────────────────────

def test_the_session_variable_wins_when_it_is_set(machine):
    machine("Linux", session="wayland", display=True)     # XWayland sets DISPLAY too

    assert ps._linux_session() == "wayland"


def test_a_compositors_own_variable_is_the_second_opinion(machine):
    machine("Linux", wayland=True)

    assert ps._linux_session() == "wayland"


def test_display_alone_is_the_last_resort(machine):
    machine("Linux", display=True)

    assert ps._linux_session() == "x11"


def test_no_variables_at_all_is_not_a_graphical_session(machine):
    machine("Linux")

    assert ps._linux_session() == ""


def test_an_unknown_session_value_falls_through_to_the_next_opinion(machine):
    """XDG_SESSION_TYPE can be 'tty' or something newer than this code."""
    machine("Linux", session="tty", display=True)

    assert ps._linux_session() == "x11"


# ── what the model is told ─────────────────────────────────────────────────

def test_the_model_is_told_it_cannot_act_and_must_not_claim_to_have(machine):
    machine("Linux", session="wayland")

    lines = ps.describe_for_model(ps.detect())

    text = "\n".join(lines)
    assert "CANNOT type, click" in text
    assert "do not report having done it" in text
    assert "CANNOT see the screen" in text


def test_the_focus_limit_is_not_mentioned_when_input_is_already_impossible(machine):
    """One cause, one sentence — not three restatements of the same fact."""
    machine("Linux", session="wayland")

    lines = ps.describe_for_model(ps.detect())

    assert len(lines) == 2
    assert not any("bring an already-running application" in line for line in lines)


def test_the_focus_limit_is_mentioned_when_it_is_the_only_one(machine):
    machine("Linux", session="x11", tools=())

    lines = ps.describe_for_model(ps.detect())

    assert len(lines) == 1
    assert "cannot bring an already-running application to the front" in lines[0]


def test_a_windows_machine_is_told_nothing_because_nothing_is_limited(machine):
    machine("Windows")

    assert ps.describe_for_model(ps.detect()) == []


def test_the_user_gets_the_notes_under_the_app_prefix(machine):
    machine("Linux", session="wayland")

    lines = ps.describe_for_user(ps.detect())

    assert lines and all(line.startswith("SYS: ") for line in lines)


# ── the object itself ──────────────────────────────────────────────────────

def test_fully_capable_needs_all_three():
    assert ps.Support(os_name="x").fully_capable is True
    assert ps.Support(os_name="x", can_focus_windows=False).fully_capable is False
    assert ps.Support(os_name="x", can_capture_screen=False).fully_capable is False
    assert ps.Support(os_name="x", can_control_input=False).fully_capable is False


def test_every_note_is_a_field_of_its_own():
    """Two Supports must not share a notes list — the dataclass default is per
    instance, and a shared one would accumulate every machine's notes."""
    a, b = ps.Support(os_name="a"), ps.Support(os_name="b")
    a.notes.append("only mine")

    assert b.notes == []
