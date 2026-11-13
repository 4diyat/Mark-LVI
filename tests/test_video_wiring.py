"""Is the video/audio wiring still connected? — checked against the source.

WHY THIS IS A SOURCE CHECK
    The bugs this file guards against are all "a signal that nobody connected"
    or "a rule the window forgot to consult". They cannot be caught by the Qt
    tests (they need a display) and they cannot be caught by reading the diff
    (they look correct). The one thing that WOULD have caught every one of them
    is asking the question directly:

        is `mediaStatusChanged` connected to anything?
        does the close path consult the rule instead of re-deriving it?
        is the audio player's error signal connected, or is a silent video the
        only evidence that it failed?

    So the questions are asked of the parsed source. It is the same approach
    tests/test_ui_setup_wiring.py already takes for the setup screen, and for
    the same reason: a widget test that needs a screen is a widget test that
    never runs.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
WINDOW = ROOT / "ui" / "window.py"
AUDIO = ROOT / "ui" / "audio.py"
TOOL = ROOT / "actions" / "video_player.py"


def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def _class(tree: ast.Module, name: str) -> ast.ClassDef:
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == name:
            return node
    pytest.fail(f"{name} not found")


def _method(cls: ast.ClassDef, name: str) -> ast.FunctionDef:
    for node in cls.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    pytest.fail(f"{cls.name}.{name} not found")


def _method_names(cls: ast.ClassDef) -> set[str]:
    """Defined methods only — a class body also holds whole assignments."""
    return {n.name for n in cls.body if isinstance(n, ast.FunctionDef)}


def _calls(node: ast.AST) -> set[str]:
    """Every function name used in a call: `x.foo()` gives 'foo', `foo()` gives
    'foo'. A plain module-level helper (`qurl_for(source)`) is a `Name`, not an
    `Attribute`, and an earlier version of this helper could not see it — which
    made a wiring test unable to check the wiring it was written for."""
    out = set()
    for sub in ast.walk(node):
        if isinstance(sub, ast.Call):
            if isinstance(sub.func, ast.Attribute):
                out.add(sub.func.attr)
            elif isinstance(sub.func, ast.Name):
                out.add(sub.func.id)
    return out


@pytest.fixture(scope="module")
def window():
    return _tree(WINDOW)


@pytest.fixture(scope="module")
def main_window(window):
    return _class(window, "MainWindow")


# ── the signal nobody listened for ──────────────────────────────────────────

def test_a_finished_video_is_actually_noticed(main_window):
    """THE BUG. Nothing was connected to `mediaStatusChanged`, so EndOfMedia
    went nowhere: the HUD stayed on the last frame, `video_is_playing()` kept
    answering yes, and the microphone closed for the soundtrack stayed closed
    for the rest of the session."""
    init = _method(main_window, "__init__")
    src = ast.unparse(init)
    assert "mediaStatusChanged" in src, "no status handler is connected"
    assert "_on_video_status" in src
    assert "_on_video_status" in _method_names(main_window)


def test_the_separate_soundtrack_reports_its_own_failure(main_window):
    """The soundtrack is a second URL resolved on its own, so it fails on its
    own. Without this connection the result is a silent video whose bar still
    says SOUND ON — indistinguishable from a video with no audio."""
    src = ast.unparse(_method(main_window, "__init__"))
    assert "errorOccurred" in src
    assert "_on_video_sound_error" in src
    assert "_on_video_sound_error" in _method_names(main_window)


# ── the rules are consulted, not re-derived ─────────────────────────────────

def test_closing_a_video_can_be_told_to_give_the_microphone_back(main_window):
    """`_sync_mic_for_video` reads the mute switch — and after a video ends the
    switch may still say "muted", so the microphone would stay closed. The close
    path takes the answer from the rule instead of re-deriving it."""
    close = _method(main_window, "_on_video_close")
    assert "mic_from_rule" in ast.unparse(close)


def test_the_status_handler_uses_the_tested_rules(main_window):
    """The decision lives in core/playback, where it has tests. If the window
    grew its own copy of the rule, those tests would be guarding dead code."""
    handler = _method(main_window, "_on_video_status")
    calls = _calls(handler)
    assert "should_open_from_ended" in calls or "ended_video_effect" in calls


def test_opening_a_video_tears_the_previous_one_down(main_window):
    """A second video opened over a YouTube one left the first soundtrack
    playing underneath it, and the mute button then controlled the wrong
    output."""
    opener = _method(main_window, "_on_video_open")
    calls = _calls(opener)
    assert "opening_while_playing" in calls
    assert "stop" in calls, "nothing is stopped before the new source loads"


def test_the_source_is_classified_once(main_window):
    """A quoted path, a `file://` URL, a bare host and a `m.youtube.com` link
    all have to arrive at the player as the right kind of thing — through the
    one function that knows how, not through `Path(source).exists()`.

    AND THROUGH `qurl_for`, not `QUrl(...)`. `QUrl` reads a Windows drive letter
    as a URL scheme: `QUrl(r"C:\\clips\\a b.mp4").scheme()` is "c", so every
    local file was handed to the player as a request for a protocol that does
    not exist, and the user was told their own video could not be played.
    `tests/test_window_smoke.py` proves it against a QUrl that behaves like
    Qt's; this asserts the wiring cannot quietly go back.
    """
    opener = _method(main_window, "_on_video_open")
    classes = _calls(opener)
    assert "qurl_for" in classes, (
        "the video source is built with QUrl(...) again — a Windows path will "
        "be read as scheme \"c\" and never play")
    # `QUrl()` with no argument is how a player is cleared — that is correct and
    # must stay. `QUrl(source)` is the bug.
    built_from_something = [
        ast.unparse(sub) for sub in ast.walk(opener)
        if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name)
        and sub.func.id == "QUrl" and sub.args]
    assert built_from_something == [], (
        f"QUrl(...) is still handed a source: {built_from_something}")


# ── the audio bar ───────────────────────────────────────────────────────────

def test_the_window_mixes_in_the_audio_bar(main_window):
    """`ui/audio.py` exists because ui/window.py has a ceiling its own test
    enforces; the mixin is only useful if the window actually inherits it."""
    bases = [ast.unparse(b) for b in main_window.bases]
    assert "AudioMixin" in bases, f"MainWindow bases are {bases}"


def test_the_audio_bar_is_built_and_present_in_the_layout(main_window):
    init = _method(main_window, "__init__")
    src = ast.unparse(init)
    assert "_build_audio_bar" in src
    assert "_audio_cont" in src, "the bar is built but never placed"


def test_audio_slots_are_connected(window):
    """Four signals, four slots. A signal emitted into nothing is the failure
    mode this whole file exists for: the tool answers "playing", and the bar
    never appears."""
    main_window = _class(window, "MainWindow")
    # The slots live in the mixin — that is the point of ui/audio.py — so the
    # question is "does the class the window inherits from still define them",
    # not "are they in window.py".
    methods = _method_names(_class(_tree(AUDIO), "AudioMixin"))
    for slot in ("_on_audio_open", "_on_audio_stop", "_on_audio_pause",
                 "_on_audio_volume", "_toggle_audio_pause", "_toggle_audio_loop",
                 "_on_audio_status", "_on_audio_error"):
        assert slot in methods, f"{slot} is missing from AudioMixin"
    init_src = ast.unparse(_method(main_window, "__init__"))
    assert "_audio_open_sig.connect" in init_src
    assert "_audio_stop_sig.connect" in init_src


def test_the_audio_output_follows_the_chosen_device():
    """The user picks a speaker in AUDIO DEVICES. A song that comes out of the
    laptop while the headset sits silent is the complaint that panel exists to
    fix, so the bar must resolve the name rather than take Qt's default."""
    tree = _tree(AUDIO)
    cls = _class(tree, "AudioMixin")
    src = ast.unparse(_method(cls, "_apply_audio_device"))
    assert "resolve" in src and "output" in src
    assert "get_output_device" in src


# ── the tool ────────────────────────────────────────────────────────────────

def test_the_tool_can_reach_the_audio_surface():
    """A sound file sent to the picture player is a black page and a decoder
    error, where the user asked for music."""
    tree = _tree(TOOL)
    src = ast.unparse(tree)
    assert "play_audio" in src and "stop_audio" in src


def test_the_tool_declares_the_actions_it_implements():
    """A model can only call what the schema offers. The audio actions were
    implemented before they were declared once, and the tool was unreachable for
    a whole test run because of it."""
    src = ast.unparse(_tree(TOOL))
    enum_start = src.index("'enum'")
    assert "play_audio" in src[enum_start:enum_start + 400], \
        "play_audio is implemented but not in the action enum"
    for action in ("play", "stop", "play_audio", "stop_audio",
                   "pause_audio", "resume_audio", "volume"):
        assert f"'{action}'" in src[enum_start:enum_start + 400], \
            f"{action} is missing from the action enum"


def test_the_window_wires_video_fallback_and_retry(main_window):
    """Forbidden or invalid video streams must try fallback candidates and
    trigger alternative-source search rather than giving up immediately."""
    bases = [ast.unparse(b) for b in main_window.bases]
    assert "VideoFallbackMixin" in bases, f"MainWindow bases are {bases}"
    assert "_try_next_video_source" in _calls(_method(main_window, "_on_video_error"))
    assert "_try_next_video_source" in _calls(_method(main_window, "_on_video_status"))
    assert "_try_next_video_sound" in _calls(_method(main_window, "_on_video_sound_error"))
    assert "_set_video_fallbacks" in _calls(_method(main_window, "_on_video_open"))
    assert "_clear_video_fallbacks" in _calls(_method(main_window, "_on_video_close"))

