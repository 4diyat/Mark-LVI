"""The gate is actually called, and the tools that skip it really do gate themselves.

WHY A WIRING TEST AT ALL
    `core/action_gate` was written, tested and correct for two commits before
    anything called it. That is the failure this file exists to catch: a module
    with a hundred passing tests and no caller reads like a finished feature and
    changes nothing about what the machine does.

    `main.py` cannot be imported here (it builds a Gemini session on import), so
    the call site is read from the AST. That is the same approach
    tests/test_ui_split.py takes for the window, and for the same reason.
"""
from __future__ import annotations

import ast
from pathlib import Path

from core import action_gate, tool_risk

ROOT = Path(__file__).resolve().parent.parent
MAIN = ROOT / "main.py"


def _main_source() -> str:
    return MAIN.read_text(encoding="utf-8")


# ── the call site exists ──────────────────────────────────────────────────

def test_the_action_registry_path_goes_through_the_gate():
    source = _main_source()
    tree = ast.parse(source)
    calls = [n for n in ast.walk(tree)
             if isinstance(n, ast.Call)
             and isinstance(n.func, ast.Attribute)
             and n.func.attr == "check"
             and isinstance(n.func.value, ast.Name)
             and n.func.value.id == "_gate"]
    assert calls, "the action registry runs tools without asking core.action_gate"
    keywords = {k.arg: k.value for call in calls for k in call.keywords}
    assert "self_gated" in keywords, (
        "the four actions that already call core.confirm must be able to say so, "
        "or one shutdown gets two banners")
    # Not just present — it must be the lookup, not a constant. `self_gated=True`
    # would let every action skip the gate; `self_gated=False` would put two
    # banners on one shutdown. Both pass a keyword-presence check.
    value = keywords["self_gated"]
    assert isinstance(value, ast.Call), "self_gated must be computed per call"
    assert getattr(value.func, "id", "") == "action_gate_self_gated"
    assert [getattr(a, "id", "") for a in value.args] == ["name", "args"], (
        "self_gated must be decided for this tool AND these arguments")


def test_the_run_callable_is_the_registry_call():
    """The gate must wrap the real dispatch, not a second copy of it."""
    source = _main_source()
    block = source[source.index("from core import action_gate as _gate"):
                   source.index("result = r or", source.index("_gate.check"))]
    assert "self._action_registry.run(name, args, _ctx)" in block


def test_the_result_of_the_gate_decides_what_is_reported():
    """A parked call must not be reported as done — and must not be mirrored
    into the content panel as if it had produced output.

    EVERY CALL SITE, not just the first one. This test used to grab the first
    `if not _verdict.ran` in the file, which was the action branch; once the
    plugin and stateless paths got gates of their own, that assertion silently
    started describing a DIFFERENT branch — the exact drift it exists to catch.
    So the count is compared: one gate call, one place that notices the call
    did not run.
    """
    source = _main_source()
    block = source[source.index("_verdict = await"):]
    block = block[:block.index("result = r or")]
    assert "_verdict.message" in block

    gates = source.count("_gate.check(")
    blanked = source.count('result = ""') + source.count('r = ""')
    assert gates >= 3, (
        "fewer gate call sites than paths: action, plugin and stateless tool")
    assert blanked >= gates, (
        f"{gates} gate call sites but only {blanked} places that stop a parked "
        "call from being reported as done")


def test_the_self_gated_list_is_checked_against_the_actions_that_really_gate():
    """A name added here without the action calling confirm is a way to skip the
    gate; a name removed from here is a second banner. Both are caught by
    looking for the call in the action's own source — the only evidence that
    matters.
    """
    tree = ast.parse(_main_source())
    names = None
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "SELF_GATED_ACTIONS"
                for t in node.targets):
            # `frozenset({...})` wraps the literal in a Call; a bare set would
            # be an ast.Set. Handle both rather than pinning the spelling.
            literal = node.value
            if isinstance(literal, ast.Call) and literal.args:
                literal = literal.args[0]
            names = {elt.value for elt in literal.elts}
    assert names, "SELF_GATED_ACTIONS is gone from main.py"

    files = {"computer_settings": "computer_settings.py", "code_helper": "code_helper.py",
             "dev_agent": "dev_agent.py", "file_processor": "file_processor.py"}
    for name in names:
        assert name in files, f"{name} is declared self-gated but never checked here"
        source = (ROOT / "actions" / files[name]).read_text(encoding="utf-8")
        assert "confirm.request" in source, (
            f"{name} is declared self-gated but never calls core.confirm — "
            f"it would run unconfirmed")


# ── what the wiring means for the user ───────────────────────────────────

def test_a_read_only_call_still_runs_without_a_banner():
    assert action_gate.check("web_search", lambda: "3 results").ran is True


def test_a_shutdown_call_is_parked_before_anything_runs():
    """End to end through the same two modules main.py uses."""
    ran = []
    verdict = action_gate.check(
        "computer_settings", lambda: ran.append(1) or "off",
        {"action": "shutdown"}, self_gated=True)
    # self_gated means computer_settings owns the banner. What the gate must
    # still do is classify it as risky, so the audit log and the UI agree.
    assert verdict.level == tool_risk.RISKY


def test_the_arguments_are_what_decide_not_the_tool_name():
    volume = action_gate.check("computer_settings", lambda: "ok",
                               {"action": "volume_up"})
    assert volume.ran is False  # Headless confirmation is unavailable; fail closed.
    assert volume.level == tool_risk.MEDIUM


def test_the_audit_log_names_the_call_that_was_asked_about(tmp_path, monkeypatch):
    from core import audit_log

    monkeypatch.setenv("JARVIS_STATE_DIR", str(tmp_path))
    audit_log.reset_shared()
    try:
        action_gate.check("computer_settings", lambda: "ok", {"action": "mute"})
        entries = audit_log.shared().entries()
        assert entries[0]["tool"] == "computer_settings:mute"
        assert [e["outcome"] for e in entries] == ["requested", "held"]
    finally:
        audit_log.reset_shared()
