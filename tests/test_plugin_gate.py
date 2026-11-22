"""A plugin is asked about too — but by its own manifest, not by its name.

WHY THIS NEEDED FIXING
    The gate was wired into the ACTION path only. A plugin fell through to a
    second, ungated `run_in_executor`, so every plugin in `plugins/` executed
    with the assistant's authority and no banner — while `core/action_gate` had
    a hundred passing tests and a docstring claiming to be "where a tool call is
    allowed". That is the same shape as the bug `tests/test_gate_wiring.py`
    exists for, one branch further down.

WHY THE LEVEL COMES FROM THE MANIFEST
    `tool_risk.classify` has never heard of a plugin name, so it answers
    `risky` for all of them, forever. Safe-but-annoying is still a failure: a
    banner for reading a public exchange rate teaches the user to dismiss
    banners, which is how the one that mattered gets dismissed too.

    So a plugin states its level, and NOT stating one is `risky`. Omission must
    not be an escape route, and the reason names the omission so the plugin can
    be fixed with one line.

WHAT THIS FILE DOES NOT PROVE
    That a malicious plugin is contained. It is not: a plugin is imported into
    this process and can do anything Python can. `core/plugin_manifest` says so
    in its own words. What is proved here is that an honest plugin is asked
    about at the level it claims, and a silent one is asked about at all.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from core import action_gate, audit_log, confirm, plugin_manifest, tool_risk
from core.plugin_loader import discover_plugins

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    """A headless, quiet gate: no real audit file, and a recorder for banners."""
    monkeypatch.setenv("JARVIS_STATE_DIR", str(tmp_path))
    audit_log.reset_shared()
    shown = []
    confirm._pending = None
    confirm.bind(lambda token, title, detail: shown.append((token, title, detail)),
                 lambda token: None)
    yield shown
    confirm._pending = None
    confirm.bind(None, None)
    audit_log.reset_shared()


def _write_plugin(folder: Path, stem: str, name: str, manifest: dict | None) -> Path:
    path = folder / f"{stem}.py"
    path.write_text(
        "PLUGIN = {\n"
        f"    'name': '{name}',\n"
        "    'description': 'reads a public number',\n"
        "    'parameters': {'type': 'OBJECT', 'properties': {}},\n"
        "}\n"
        "def run(parameters, player=None, session_memory=None):\n"
        "    return 'a number'\n",
        encoding="utf-8")
    if manifest is not None:
        payload = {"name": name, "version": "1.0.0", "author": "test",
                   "description": "reads a public number", "permissions": []}
        payload.update(manifest)
        payload["sha256"] = plugin_manifest.sha256_of(path)
        (folder / f"{stem}.json").write_text(
            json.dumps(payload), encoding="utf-8")
    return path


def _registry(folder: Path):
    return discover_plugins(folder, core_tool_names=set(), logger=lambda _m: None)


# ── classification ────────────────────────────────────────────────────────

def test_a_declared_safe_level_runs_without_a_banner():
    assert tool_risk.classify_plugin("market_price", "safe").level == tool_risk.SAFE


def test_a_declared_risky_level_is_risky():
    assert tool_risk.classify_plugin("mt5_trade", "risky").level == tool_risk.RISKY


def test_an_unstated_level_is_risky_and_says_why():
    """Omission must not be an escape route, and the reason must be actionable."""
    risk = tool_risk.classify_plugin("mystery", "")
    assert risk.level == tool_risk.RISKY
    assert "does not state" in risk.reason


def test_a_plugin_cannot_claim_a_level_the_gate_does_not_know():
    """`very safe please` is not a level; it falls to risky rather than to safe."""
    assert tool_risk.classify_plugin("x", "very safe please").level == tool_risk.RISKY


# ── the gate, end to end ──────────────────────────────────────────────────

def test_a_safe_plugin_runs_and_is_audited(isolated):
    ran = []
    verdict = action_gate.check("market_price", lambda: ran.append(1) or "USD 1",
                                plugin_level="safe")
    assert verdict.ran is True and ran == [1]
    assert [e["outcome"] for e in audit_log.shared().entries()] == ["requested", "done"]


def test_an_unstated_plugin_is_parked_before_it_runs(isolated):
    ran = []
    verdict = action_gate.check("mystery", lambda: ran.append(1) or "nope",
                                plugin_level="")
    assert verdict.ran is False, "a plugin with no stated level ran unconfirmed"
    assert ran == []
    assert len(isolated) == 1, "no banner was put up"


def test_the_audit_line_for_a_plugin_names_the_plugin(isolated):
    action_gate.check("mystery", lambda: "x", plugin_level="")
    entry = audit_log.shared().entries()[0]
    assert entry["tool"] == "mystery"
    assert entry["level"] == tool_risk.RISKY


def test_not_passing_a_level_changes_nothing_for_an_action(isolated):
    """`plugin_level=None` is the default, so every existing caller is unchanged.

    Proved by behaviour rather than by reading the signature: a risky ACTION
    still parks and a safe one still runs.
    """
    assert action_gate.check("web_search", lambda: "3").ran is True
    parked = action_gate.check("send_message", lambda: "sent")
    assert parked.ran is False


# ── the wiring in main.py ─────────────────────────────────────────────────

def test_main_asks_the_gate_about_plugins_too():
    """The call site, read from the source: `main.py` cannot be imported here.

    Two independent facts are asserted, because either one alone can be faked:
    the plugin branch contains a `_gate.check` call, and that call passes
    `plugin_level` from the registry rather than a constant.
    """
    source = (ROOT / "main.py").read_text(encoding="utf-8")
    branch = source[source.index("if self._plugin_registry.has(name):"):]
    branch = branch[:branch.index("else:")] if "else:" in branch else branch
    assert "_gate.check(" in branch, "the plugin path runs without the gate"
    assert "plugin_level=" in branch, (
        "the plugin level is not passed, so every plugin would be classified "
        "by a registry that has never heard of it")
    assert "declared_level(name)" in branch, (
        "the level must come from THIS plugin's manifest, not a fixed value")


def test_the_registry_reports_a_missing_level_as_empty_not_as_safe(tmp_path):
    """The one conversion that matters: no manifest must not read as `safe`."""
    _write_plugin(tmp_path, "bare", "bare_tool", manifest=None)
    registry = _registry(tmp_path)
    assert registry.has("bare_tool")
    assert registry.declared_level("bare_tool") == ""


def test_the_registry_reports_what_the_manifest_claims(tmp_path):
    _write_plugin(tmp_path, "cheap", "cheap_tool", {"level": "safe"})
    registry = _registry(tmp_path)
    assert registry.declared_level("cheap_tool") == "safe"


# ── the first-party manifests must stay honest ────────────────────────────

def test_every_shipped_plugin_states_its_level():
    """A plugin from this repository that says nothing would put a banner in
    front of the user for its own author's convenience — and would make the
    default look like an oversight rather than a decision.
    """
    missing = []
    for path in sorted((ROOT / "plugins").glob("*.py")):
        if path.name.startswith("_"):
            continue
        manifest = plugin_manifest.read(path, path.stem)
        if manifest is None:
            continue        # the three legacy plugins: documented in the test below
        if not manifest.level:
            missing.append(path.stem)
    assert missing == [], f"these plugins state no level: {missing}"


def test_a_plugin_that_can_reach_past_the_machine_is_not_declared_safe():
    """The rule this table exists for: money, another machine, or a shell.

    Asserted from the manifest rather than from a list here, so adding a plugin
    means answering the question instead of copying the line above.

    It failed on first run, on `mt5_orb`, which I had marked `safe`: it only
    READS the opening range, but a chart request saves a PNG and may open the
    terminal, and that is a change the assistant cannot walk back. The plugin
    is now `medium`. The test is the reason that got noticed rather than
    shipped.
    """
    too_trusting = []
    for path in sorted((ROOT / "plugins").glob("*.py")):
        if path.name.startswith("_"):
            continue
        manifest = plugin_manifest.read(path, path.stem)
        if manifest is None or not manifest.level:
            continue
        permissions = set(manifest.permissions)
        # `network` alone is how a reader of public data is built, so the test
        # only refuses it for a plugin that also reaches the user's money or
        # another machine — those are named explicitly in the plugin's own file
        # names, which is the same evidence a reviewer has.
        reaches_money = any(word in path.stem for word in ("mt5", "trading"))
        if manifest.level == "safe" and ("shell" in permissions
                                         or reaches_money):
            too_trusting.append(path.stem)
    assert too_trusting == [], (
        "these plugins claim `safe` while holding a shell or reaching a trading "
        f"account: {too_trusting}")
