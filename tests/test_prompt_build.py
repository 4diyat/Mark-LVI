"""What the model is told about itself.

These three functions lived in `main.py` with no tests, because reaching them
meant importing the Live SDK, sounddevice, numpy and Qt. They build the only
description the model ever gets of its own abilities — so a bug here is the
assistant claiming sight on a machine with no camera, or refusing to hear on a
machine with a working microphone. Both of those are in this file's history.
"""
from __future__ import annotations

import ast
from datetime import datetime
from pathlib import Path

from core import prompt_build as pb

ROOT = Path(__file__).resolve().parent.parent


# ── names, from whichever shape a declaration has ─────────────────────────

def test_a_name_is_read_from_a_dict_or_an_object():
    """Declarations arrive as dicts from the registries and as objects from the
    provider SDK, and the same expression used to be written out seven times."""
    assert pb.tool_name({"name": "screen_process"}) == "screen_process"
    assert pb.tool_name(type("D", (), {"name": "close_camera"})()) == "close_camera"


def test_a_missing_name_is_empty_not_None():
    """`in` against a set containing None quietly never matches; an empty string
    is the shape every caller here already handles."""
    assert pb.tool_name({}) == ""
    assert pb.tool_name(object()) == ""


# ── the capability list ───────────────────────────────────────────────────

def test_every_tool_gets_one_line_and_its_own_description():
    text = pb.describe_tools([
        {"name": "open_app", "description": "Opens an application."},
        {"name": "close_camera", "description": "Closes the camera."},
    ])
    assert "- open_app: Opens an application." in text
    assert "- close_camera: Closes the camera." in text


def test_a_tool_without_a_description_still_appears():
    """The model must be able to call a tool it was never described; dropping
    the line entirely would hide the capability."""
    assert pb.describe_tools([{"name": "ping"}]) == "- ping"


def test_a_long_description_is_cut_not_swallowed():
    text = pb.describe_tools([{"name": "x", "description": "y" * 400}])
    assert len(text) < 200 and text.startswith("- x: ")


def test_a_multiline_description_becomes_one_line():
    """A newline in a description would break the one-line-per-tool shape and
    read as an extra, unnamed capability."""
    text = pb.describe_tools([{"name": "x", "description": "one\n\n  two   three"}])
    assert text == "- x: one two three"


def test_one_malformed_declaration_does_not_lose_the_others():
    class Explodes:
        @property
        def name(self):
            raise RuntimeError("boom")

    text = pb.describe_tools([Explodes(), {"name": "good"}])
    assert text == "- good"


def test_no_declarations_is_an_empty_list_not_an_error():
    assert pb.describe_tools([]) == ""
    assert pb.describe_tools(None) == ""


# ── the limits, which is where the honesty lives ──────────────────────────

def test_a_deaf_build_is_told_it_cannot_hear():
    """THE BUG THIS FILE EXISTS FOR.

    The microphone flag used to be the constant `True`, so a machine with no
    microphone was instructed to listen, then sat silent while the user spoke
    into nothing — and the user had no way to know which side was broken.
    """
    text = pb.describe_limits(has_vision=True, has_mic=False)
    assert "microphone is unavailable" in text
    assert "Do not pretend to hear" in text


def test_a_hearing_build_is_told_about_the_mute_not_about_a_missing_mic():
    text = pb.describe_limits(has_vision=True, has_mic=True)
    assert "microphone is unavailable" not in text
    assert "while the microphone is muted" in text


def test_a_blind_build_is_told_it_has_no_sight():
    text = pb.describe_limits(has_vision=False, has_mic=True)
    assert "no sight at all" in text
    assert "not continuous" not in text


def test_a_seeing_build_is_told_its_sight_is_not_continuous():
    """Otherwise the model promises to watch something for a while, which it
    cannot do: it sees one frame per call and nothing between calls."""
    text = pb.describe_limits(has_vision=True, has_mic=True)
    assert "not continuous" in text
    assert "cannot watch" in text


def test_the_platforms_refusals_come_before_the_builds_gaps():
    """A Wayland session is a different fact from a missing camera, and the
    model must be able to name the one that applies."""
    text = pb.describe_limits(
        has_vision=True, has_mic=True,
        platform_lines=("- This session is Wayland: no synthetic input.",))
    assert text.index("Wayland") < text.index("not continuous")


def test_platform_lines_default_to_none_and_say_nothing():
    """Called with no platform input — a probe that failed — the prompt must
    still be complete, just without that paragraph."""
    assert "Wayland" not in pb.describe_limits(True, True)


def test_every_limit_line_starts_as_a_bullet():
    """The prompt is read by a model, and the rest of it uses bullets; an
    unbulleted paragraph here reads as a continuation of the previous rule."""
    lines = pb.describe_limits(True, True).splitlines()
    assert lines and all(ln.startswith("- ") for ln in lines)


# ── the template fill ─────────────────────────────────────────────────────

def test_a_token_is_replaced_everywhere_it_appears():
    assert pb.render("{a}-{a}", {"a": "x"}) == "x-x"


def test_an_unknown_token_is_left_alone():
    """It may be somebody's own wording, and the file is meant to be edited."""
    assert pb.render("keep {this}", {"other": "y"}) == "keep {this}"


def test_a_stray_brace_never_raises():
    """`str.format` would take the app down at startup over a typo."""
    assert pb.render("100% { ok } {name}", {"name": "J"}) == "100% { ok } J"


def test_an_empty_template_renders_to_an_empty_prompt():
    assert pb.render("", {"a": "b"}) == ""
    assert pb.render(None, {"a": "b"}) == ""


def test_a_value_that_is_not_a_string_still_renders():
    assert pb.render("n={n}", {"n": 42}) == "n=42"


# ── identity and time ─────────────────────────────────────────────────────

def test_a_named_user_is_addressed_by_name():
    assert "Always call the user 'Diyat'." in pb.identity_block("JARVIS", "Diyat")


def test_an_unnamed_user_gets_a_principle_not_a_hardcoded_word():
    """Address form belongs to the language being spoken; a two-language lookup
    is wrong in every third language."""
    text = pb.identity_block("JARVIS", "")
    assert "respectful form" in text
    assert "Never an archaic" in text


def test_the_identity_states_the_name_twice_on_purpose():
    """A model told its name once drifts back to its training identity."""
    text = pb.identity_block("FRIDAY", "")
    assert text.count("FRIDAY") == 2


def test_an_empty_name_falls_back_rather_than_producing_a_blank():
    assert "Your name is JARVIS." in pb.identity_block("   ", "")


def test_the_time_string_is_the_one_it_was_given():
    """`now` is a parameter: a function that reads the clock cannot be tested
    for what it says, and this is the model's only way to answer without a tool."""
    stamp = datetime(2026, 11, 19, 14, 5)
    text = pb.time_block(stamp)
    assert "November 19, 2026" in text
    assert "02:05 PM" in text


# ── withholding: an engine is not offered what it cannot serve ────────────

DECLS = [{"name": "screen_process"}, {"name": "close_camera"},
         {"name": "open_app"}, {"name": "save_memory"}]


def test_gemini_live_is_untouched():
    """`caps is None` is Gemini Live, and the declaration list must be
    byte-for-byte what it has always been."""
    kept, blocked = pb.withhold(DECLS, None)
    assert kept == DECLS and blocked == 0


def test_an_engine_without_vision_is_not_offered_the_eye_tools():
    kept, blocked = pb.withhold(DECLS, {"vision": False, "tools": True})
    names = [pb.tool_name(d) for d in kept]
    assert names == ["open_app", "save_memory"]
    assert blocked == 2


def test_an_engine_without_tools_is_offered_none_and_a_plugin_added_later_is_caught():
    """The blocked set is built FROM the declarations, not from a constant: a
    plugin added later must be withheld too instead of slipping through on a
    stale allow-list."""
    kept, blocked = pb.withhold(DECLS + [{"name": "brand_new_plugin"}],
                                {"vision": True, "tools": False})
    assert kept == [] and blocked == 5


def test_a_capable_engine_loses_nothing_and_does_not_claim_a_block():
    kept, blocked = pb.withhold(DECLS, {"vision": True, "tools": True})
    assert kept == DECLS and blocked == 0


def test_withholding_does_not_mutate_the_callers_list():
    """`_all_decls` is reused two lines later for the budget; a function that
    filtered in place would change what the omission report compares against."""
    original = list(DECLS)
    pb.withhold(DECLS, {"vision": False, "tools": True})
    assert DECLS == original


def test_the_withheld_names_are_the_ones_the_prompt_stops_promising():
    """The point of sharing this filter with `describe_limits` is that the model
    is told what it lost. Prove the two agree rather than assuming it."""
    kept, _ = pb.withhold(DECLS, {"vision": False, "tools": True})
    text = pb.describe_tools(kept)
    assert "screen_process" not in text
    assert "open_app" in text


# ── the main.py side is wiring, and stays wiring ──────────────────────────

def test_main_asks_the_module_instead_of_carrying_a_second_copy():
    tree = ast.parse((ROOT / "main.py").read_text(encoding="utf-8"))
    source = (ROOT / "main.py").read_text(encoding="utf-8")

    # The machine probe is the ONLY thing main.py still does itself, and it is
    # passed in as data — exactly like `quota_laddered_by` in session_policy.
    assert "_platform_limits()" in source
    assert "platform_lines=_platform_limits()" in source

    # The prompts themselves are not written here any more.
    literals = [n.value for n in ast.walk(tree) if isinstance(n, ast.Constant)
                and isinstance(n.value, str)]
    assert not any("Your sight is not continuous" in s for s in literals), \
        "the limits wording is written twice again"
    assert not any("[IDENTITY]" in s for s in literals), \
        "the identity wording is written twice again"


def test_the_module_does_not_import_the_application():
    """It must stay testable without the Live SDK, sounddevice, numpy or Qt."""
    tree = ast.parse((ROOT / "core" / "prompt_build.py").read_text(encoding="utf-8"))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])
    assert imported <= {"__future__"}, f"prompt_build imports {imported}"
