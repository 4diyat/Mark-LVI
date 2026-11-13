"""No microphone: the app keeps running, and says so.

WHY THIS FILE EXISTS
    `_listen_audio` used to be one try/except that re-raised, and it runs inside
    the session's `asyncio.TaskGroup`. On a machine with no microphone — a
    desktop with line-out only, a laptop whose internal mic is disabled in Device
    Manager, a Windows profile with microphone access switched off — the open
    raised, the TaskGroup cancelled its siblings, and the whole conversation
    died. The assistant can SPEAK without a microphone. It can run every tool.
    You can type to it. Losing all of that over a missing input device is the
    bug, and none of it produced an error message a user could act on.

    So the tests here are about two properties:
      1. `open_input_stream` reports "no microphone" as a RESULT — a stream or
         None plus a sentence — and never raises.
      2. `main.py` does not tear the session down when it gets that result: it
         stays in a loop, says it once, and picks the device up again when one
         appears.

    sounddevice is not installed here and PortAudio is not present, which is
    convenient: the "cannot even query" path is the real one on this machine.
    The rest is simulated with fakes, because there is no audio hardware to
    break.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import audio_devices  # noqa: E402

MAIN = ROOT / "main.py"


def _method(tree, cls: str, name: str):
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == cls:
            for sub in node.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)) and sub.name == name:
                    return sub
    raise AssertionError(f"{cls}.{name} not found — did it move or rename?")


def _raises_anything(node) -> list[ast.Raise]:
    """Every bare `raise` inside a def, NOT counting ones in a nested def."""
    found = []
    stack = list(node.body)
    while stack:
        current = stack.pop()
        if isinstance(current, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
            continue
        if isinstance(current, ast.Raise):
            found.append(current)
        stack.extend(ast.iter_child_nodes(current))
    return found


# ── the device question ─────────────────────────────────────────────────────

def test_the_hint_is_unknown_before_anything_asks(monkeypatch):
    """'Unknown' must not read as 'no microphone': the caller then tries to
    open, which is the only authority on the matter."""
    monkeypatch.setattr(audio_devices, "_MIC_KNOWN", False)
    monkeypatch.setattr(audio_devices, "_MIC_PRESENT", True)
    assert audio_devices._MIC_PRESENT is True


def test_a_machine_with_no_input_device_says_no(monkeypatch):
    monkeypatch.setattr(audio_devices, "_query_devices_fake", None, raising=False)

    class SD:
        @staticmethod
        def query_devices():
            return [{"name": "Speakers", "max_input_channels": 0,
                     "max_output_channels": 2}]

    monkeypatch.setitem(sys.modules, "sounddevice", SD)
    assert audio_devices.input_available(refresh=True) is False


def test_a_machine_with_a_microphone_says_yes(monkeypatch):
    class SD:
        @staticmethod
        def query_devices():
            return [{"name": "Mic", "max_input_channels": 2, "max_output_channels": 0},
                    {"name": "Speakers", "max_input_channels": 0,
                     "max_output_channels": 2}]

    monkeypatch.setitem(sys.modules, "sounddevice", SD)
    assert audio_devices.input_available(refresh=True) is True
    assert audio_devices.count_inputs() == 1


def test_a_query_that_explodes_is_unknown_not_no(monkeypatch):
    """PortAudio missing, a broken driver, no audio session in a container: the
    caller must still try, because the failure is not evidence of a missing
    microphone."""
    class SD:
        @staticmethod
        def query_devices():
            raise RuntimeError("PortAudio library not found")

    monkeypatch.setitem(sys.modules, "sounddevice", SD)
    assert audio_devices.input_available(refresh=True) is True
    assert audio_devices.count_inputs() == -1


def test_a_failing_query_warns_once_not_every_two_seconds(monkeypatch, capsys):
    """The connect loop polls while there is no device. On a machine where the
    QUERY itself fails (no PortAudio) that would be a line every two seconds,
    burying the console the user is trying to read."""
    class SD:
        @staticmethod
        def query_devices():
            raise RuntimeError("PortAudio library not found")

    monkeypatch.setitem(sys.modules, "sounddevice", SD)
    monkeypatch.setattr(audio_devices, "_MIC_WARNED", "")
    for _ in range(5):
        audio_devices.input_available(refresh=True)
    lines = [line for line in capsys.readouterr().out.splitlines()
             if "Input device query failed" in line]
    assert len(lines) == 1


# ── opening, when there is nothing to open ─────────────────────────────────

class Opener:
    """Records what it was asked to open and fails or succeeds on demand."""

    def __init__(self, fail_with=None):
        self.fail_with = fail_with or {}
        self.calls = []

    def __call__(self, device):
        self.calls.append(device)
        error = self.fail_with.get(device)
        if error is not None:
            raise error
        return f"stream(device={device})"


@pytest.fixture()
def says(monkeypatch):
    lines = []
    monkeypatch.setattr(audio_devices, "input_available", lambda refresh=False: True)
    return lines


def test_a_working_microphone_returns_a_stream_and_nothing_to_say(says):
    opener = Opener()
    stream, problem = audio_devices.open_input_stream(opener, 3, say=says.append)
    assert stream == "stream(device=3)"
    assert problem == ""
    assert says == []
    assert opener.calls == [3]


def test_the_chosen_device_falls_back_to_the_default(says):
    opener = Opener({3: OSError("Device unavailable")})
    stream, _problem = audio_devices.open_input_stream(opener, 3, say=says.append)
    assert stream == "stream(device=None)"
    assert opener.calls == [3, None]
    assert any("system default" in line for line in says)


def test_no_microphone_at_all_returns_none_and_a_sentence(says):
    opener = Opener({3: OSError("Device unavailable"),
                     None: OSError("No input device")})
    stream, problem = audio_devices.open_input_stream(opener, 3, say=says.append)
    assert stream is None
    # The sentence names the FIRST error — the device the user chose — because
    # a default endpoint's refusal says less about what to do.
    assert "Device unavailable" in problem
    assert "type" in problem.lower() or "still works" in problem
    # Said once, not once per attempt.
    assert len([line for line in says if line.startswith("SYS:")]) == 1


def test_no_hint_of_any_device_does_not_even_try(monkeypatch, says):
    monkeypatch.setattr(audio_devices, "input_available", lambda refresh=False: False)
    opener = Opener()
    stream, problem = audio_devices.open_input_stream(opener, 0, say=says.append)
    assert stream is None
    assert "No microphone is available" in problem
    assert opener.calls == [], "tried to open a device the OS says is not there"


def test_the_hint_is_never_allowed_to_refuse_on_its_own():
    """A device list is not a promise: a USB headset can appear between the
    query and the open. `open_input_stream` therefore only skips WORK on a
    negative hint — the sentence it returns still explains, and the caller
    retries."""
    source = (ROOT / "core" / "audio_devices.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    fn = next(node for node in ast.walk(tree)
              if isinstance(node, ast.FunctionDef) and node.name == "open_input_stream")
    assert _raises_anything(fn) == [], "open_input_stream must never raise"


# ── the session loop ───────────────────────────────────────────────────────

def test_listen_audio_no_longer_raises_out_of_the_taskgroup():
    """The exact regression: a `raise` inside _listen_audio cancels the session."""
    tree = ast.parse(MAIN.read_text(encoding="utf-8"))
    fn = _method(tree, "JarvisLive", "_listen_audio")
    raises = _raises_anything(fn)
    assert raises == [], (
        "_listen_audio raises — it runs inside the session TaskGroup, so a "
        "missing microphone would cancel the conversation again")


def test_listen_audio_keeps_looping_instead_of_returning_without_a_mic():
    tree = ast.parse(MAIN.read_text(encoding="utf-8"))
    fn = _method(tree, "JarvisLive", "_listen_audio")
    calls = [node for node in ast.walk(fn)
             if isinstance(node, ast.Attribute) and node.attr == "_wait_for_microphone"]
    assert calls, "_listen_audio must wait for a microphone, not fall out of the loop"
    assert any(isinstance(node, ast.While) for node in ast.walk(fn)), \
        "the open/retry path has to be inside a loop"


def test_the_wait_helper_does_not_open_a_second_stream():
    """Two streams on one device is the bug that replacing this with a copy of
    the open path would cause. The helper polls and returns; _listen_audio owns
    the open."""
    tree = ast.parse(MAIN.read_text(encoding="utf-8"))
    fn = _method(tree, "JarvisLive", "_wait_for_microphone")
    opened = [node for node in ast.walk(fn)
              if isinstance(node, ast.Attribute) and node.attr == "open_input_stream"]
    assert opened == []
    assert any(isinstance(node, ast.Attribute) and node.attr == "input_available"
               for node in ast.walk(fn))


def test_the_model_is_told_when_there_is_no_microphone():
    """`has_mic=True` was a constant. A deaf build was then instructed to listen
    and sat silent while the user spoke into nothing."""
    source = MAIN.read_text(encoding="utf-8")
    assert "has_mic=not self._deaf" in source
    assert "has_mic=True" not in source


def test_going_deaf_changes_what_the_user_sees():
    """"LISTENING" over a machine with no microphone is the screen lying about
    the one thing the user is trying to fix."""
    source = MAIN.read_text(encoding="utf-8")
    assert 'self.ui.set_state("NO MIC")' in source
    assert "def _apply_listening_state" in source
    # ...and recovery must respect the wake gate rather than always claiming to
    # listen to someone it is still ignoring.
    assert '"LISTENING" if self._awake else "SLEEPING"' in source


# ── the window ─────────────────────────────────────────────────────────────

def test_the_microphone_button_admits_there_is_no_microphone():
    window = (ROOT / "ui" / "window.py").read_text(encoding="utf-8")
    fn_start = window.index("    def _style_mute_btn(self):")
    fn_end = window.index("    def ", fn_start + 10)
    body = window[fn_start:fn_end]
    assert "ui.mic.absent" in body
    assert "setEnabled(False)" in body


def test_both_languages_have_the_new_key():
    import json

    for lang in ("en", "id"):
        data = json.loads((ROOT / "assets" / "i18n" / f"{lang}.json")
                          .read_text(encoding="utf-8"))
        assert data.get("ui.mic.absent"), f"{lang} has no label for a missing microphone"
