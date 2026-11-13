"""The two loaders: they must survive anything a file can do, and say why.

WHY THIS FILE EXISTS
    `core/action_loader.py` and `core/plugin_loader.py` are the most dangerous
    code in the project in one specific way: they EXECUTE every file in a
    folder at startup. Their whole contract is that a broken file cannot take
    the app down — "import errors, validation errors, and name collisions are
    logged and the offending file is skipped, they NEVER raise".

    That contract was untested. The CI job "load every action" proved the files
    that ship with the repo load; it could not prove anything about the file
    somebody downloads tomorrow, which is the case the contract is written for.

    So every test here writes a plugin or an action to tmp_path and asserts two
    things at once: the good files still load, AND the bad one is rejected with
    a message a non-programmer can act on. A loader that survives by skipping
    silently is a loader whose bugs are invisible.
"""
from __future__ import annotations

import json
import textwrap
from pathlib import Path

import pytest

from core.action_loader import discover_actions
from core.plugin_loader import discover_plugins
from core.plugin_loader import _load_error


# ── helpers ──────────────────────────────────────────────────────────────────

def write(folder: Path, name: str, body: str) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    path.write_text(textwrap.dedent(body), encoding="utf-8")
    return path


def action(name: str = "good_tool", **meta) -> str:
    fields = {"name": name, "description": "does a thing", "handler": "ok"}
    fields.update(meta)
    lines = ",\n    ".join(f'"{k}": {v!r}' if not callable(v) else f'"{k}": {v}'
                           for k, v in fields.items() if k != "handler")
    return (
        "def ok(parameters, **kw):\n"
        "    return 'ran'\n\n"
        "TOOL = {\n"
        f"    {lines},\n"
        '    "handler": ok,\n'
        "}\n"
    )


def plugin(name: str = "good_plugin", **meta) -> str:
    fields = {"name": name, "description": "does a thing"}
    fields.update(meta)
    lines = "\n    ".join(f'"{k}": {v!r},' for k, v in fields.items())
    return (
        "def run(parameters, player=None, session_memory=None):\n"
        "    return 'ran'\n\n"
        "PLUGIN = {\n"
        f"    {lines}\n"
        "}\n"
    )


def logs() -> tuple[list[str], callable]:
    lines: list[str] = []
    return lines, lines.append


# ── actions ──────────────────────────────────────────────────────────────────

def test_a_good_action_is_discovered_and_runs(tmp_path):
    folder = tmp_path / "actions"
    write(folder, "good_tool.py", action())
    lines, log = logs()

    reg = discover_actions(folder, set(), log)

    assert reg.names() == {"good_tool"}
    assert reg.has("good_tool")
    assert reg.run("good_tool", {}) == "ran"
    assert any("good_tool" in line for line in lines)


def test_an_action_with_a_syntax_error_does_not_stop_the_others(tmp_path):
    """The one contract the whole loader exists for."""
    folder = tmp_path / "actions"
    write(folder, "broken.py", "def oops(:\n    this is not python\n")
    write(folder, "good_tool.py", action())

    reg = discover_actions(folder, set(), lambda _m: None)

    assert reg.names() == {"good_tool"}


@pytest.mark.parametrize("body,expected", [
    ("TOOL = 'not a dict'\n", "No module-level TOOL dict"),
    ('TOOL = {"description": "d", "handler": len}\n', "name"),
    ('TOOL = {"name": "9bad", "description": "d", "handler": len}\n', "not a valid identifier"),
    ('TOOL = {"name": "tool", "description": "  ", "handler": len}\n', "description"),
    ('TOOL = {"name": "tool", "description": "d", "parameters": [], "handler": len}\n',
     '"type": "OBJECT"'),
    ('TOOL = {"name": "tool", "description": "d", "handler": 42}\n', "handler"),
])
def test_every_way_an_action_can_be_wrong_is_named(tmp_path, body, expected):
    folder = tmp_path / "actions"
    write(folder, "candidate.py", body)
    lines, log = logs()

    reg = discover_actions(folder, set(), log)

    assert reg.names() == set()
    assert expected in "\n".join(lines), lines


def test_an_action_may_not_take_a_reserved_name(tmp_path):
    folder = tmp_path / "actions"
    write(folder, "mine.py", action("already_taken"))

    reg = discover_actions(folder, {"already_taken"}, lambda _m: None)

    assert reg.names() == set()


def test_two_actions_with_one_name_cannot_both_load(tmp_path):
    """Which one wins must be deterministic, and the loser must be reported.

    Files are sorted, so in a collision the FIRST file keeps the name; the
    other is rejected with the winner's filename, which is the only way a
    user can tell which of their two files is being ignored.
    """
    folder = tmp_path / "actions"
    write(folder, "a_first.py", action("same"))
    write(folder, "b_second.py", action("same"))
    lines, log = logs()

    reg = discover_actions(folder, set(), log)

    assert reg.names() == {"same"}
    joined = "\n".join(lines)
    assert "already used by action 'a_first.py'" in joined


def test_a_file_without_a_TOOL_dict_is_ignored_silently(tmp_path):
    """Shared helpers live in actions/ too, and are not news at startup."""
    folder = tmp_path / "actions"
    write(folder, "helper.py", "def shared():\n    return 1\n")

    reg = discover_actions(folder, set(), lambda _m: None)

    assert reg.names() == set()


def test_a_file_starting_with_underscore_is_never_an_action(tmp_path):
    folder = tmp_path / "actions"
    write(folder, "_private.py", action("hidden"))

    reg = discover_actions(folder, set(), lambda _m: None)

    assert reg.names() == set()


def test_a_crashing_action_answers_the_model_instead_of_raising(tmp_path):
    """A tool that raises must become a sentence, not a dead session."""
    folder = tmp_path / "actions"
    write(folder, "boom.py", (
        "def ok(parameters, **kw):\n"
        "    raise RuntimeError('kaboom')\n\n"
        'TOOL = {"name": "boom", "description": "d", "handler": ok}\n'
    ))
    lines, log = logs()
    reg = discover_actions(folder, set(), log)

    result = reg.run("boom", {})

    assert "kaboom" in result and "boom" in result
    assert any("crashed" in line for line in lines)


def test_an_unknown_action_answers_the_model_instead_of_raising(tmp_path):
    reg = discover_actions(tmp_path / "actions", set(), lambda _m: None)
    assert "not available" in reg.run("nope", {})


def test_declarations_carry_bookkeeping_that_vendors_must_not_see(tmp_path):
    """tier/brief ride along for the budget code and are stripped before Gemini.

    If they stop being produced the local engine loses its ranking; if they
    stop being strippable Gemini answers with a schema error, which is a
    feature that silently stops working for local models only.
    """
    folder = tmp_path / "actions"
    write(folder, "good_tool.py", action(tier="core", brief="short", behavior="NON_BLOCKING"))
    reg = discover_actions(folder, set(), lambda _m: None)

    decl = reg.get_tool_declarations()[0]

    assert decl["tier"] == "core"
    assert decl["brief"] == "short"
    assert decl["behavior"] == "NON_BLOCKING"

    from core.action_loader import strip_meta
    assert set(strip_meta([decl])[0]) == {"name", "description", "parameters", "behavior"}


def test_a_typo_in_an_optional_field_is_not_fatal(tmp_path):
    """`behavior: "NONBLOCKING"` is a typo, not a reason to lose the tool."""
    folder = tmp_path / "actions"
    write(folder, "good_tool.py", action(behavior="NONBLOCKING", tier="important", brief=" "))

    reg = discover_actions(folder, set(), lambda _m: None)

    assert reg.names() == {"good_tool"}
    decl = reg.get_tool_declarations()[0]
    assert "behavior" not in decl and "tier" not in decl and "brief" not in decl


# ── plugins ──────────────────────────────────────────────────────────────────

def test_a_good_plugin_is_discovered_and_runs(tmp_path):
    folder = tmp_path / "plugins"
    write(folder, "good_plugin.py", plugin())
    lines, log = logs()

    reg = discover_plugins(folder, set(), log)

    assert reg.has("good_plugin")
    assert reg.run("good_plugin", {}) == "ran"
    assert [p["name"] for p in reg.list_for_ui()] == ["good_plugin"]


def test_run_receives_only_the_arguments_it_declares(tmp_path):
    """A minimal `def run(parameters)` has worked since plugins existed."""
    folder = tmp_path / "plugins"
    write(folder, "minimal.py", (
        "seen = {}\n\n"
        "def run(parameters):\n"
        "    seen.update(parameters)\n"
        "    return 'ok'\n\n"
        'PLUGIN = {"name": "minimal", "description": "d"}\n'
    ))
    reg = discover_plugins(folder, set(), lambda _m: None)

    assert reg.run("minimal", {"a": 1}) == "ok"


def test_a_plugin_that_crashes_is_reported_not_raised(tmp_path):
    folder = tmp_path / "plugins"
    write(folder, "boom.py", (
        "def run(parameters, player=None, session_memory=None):\n"
        "    raise ValueError('nope')\n\n"
        'PLUGIN = {"name": "boom", "description": "d"}\n'
    ))
    notices: list[str] = []
    reg = discover_plugins(folder, set(), lambda _m: None, notices.append)

    result = reg.run("boom", {})

    assert "nope" in result
    assert any("failed" in n for n in notices)


def test_a_plugin_colliding_with_a_core_tool_is_rejected_by_name(tmp_path):
    folder = tmp_path / "plugins"
    write(folder, "mine.py", plugin("open_app"))

    reg = discover_plugins(folder, {"open_app"}, lambda _m: None)

    assert not reg.has("open_app")
    assert "collides with a core tool" in reg.list_for_ui()[0]["error"]


@pytest.mark.parametrize("body,expected", [
    ("x = 1\n", "Missing PLUGIN dict"),
    ('PLUGIN = {"description": "d"}\n', "name"),
    ('PLUGIN = {"name": "p", "description": ""}\n', "description"),
    ('PLUGIN = {"name": "p", "description": "d", "parameters": {"type": "ARRAY"}}\n',
     '"type": "OBJECT"'),
    ('PLUGIN = {"name": "p", "description": "d"}\n', "run(parameters"),
])
def test_every_way_a_plugin_can_be_wrong_is_named(tmp_path, body, expected):
    folder = tmp_path / "plugins"
    write(folder, "candidate.py", body)
    lines, log = logs()

    reg = discover_plugins(folder, set(), log)

    assert not reg.has("candidate")
    assert expected in "\n".join(lines), lines


def test_a_broken_plugin_does_not_stop_the_others(tmp_path):
    folder = tmp_path / "plugins"
    write(folder, "broken.py", "import a_module_that_does_not_exist\n")
    write(folder, "good_plugin.py", plugin())

    reg = discover_plugins(folder, set(), lambda _m: None)

    assert reg.has("good_plugin")


def test_a_plugin_helper_that_is_missing_is_named_as_a_file(tmp_path):
    """The support question this exists for: 'it says No module named plugins._x'."""
    folder = tmp_path / "plugins"
    write(folder, "wants_helper.py", (
        "from plugins._shared_helper import thing\n\n"
        "def run(parameters, player=None, session_memory=None):\n"
        "    return thing()\n\n"
        'PLUGIN = {"name": "wants_helper", "description": "d"}\n'
    ))
    lines, log = logs()

    reg = discover_plugins(folder, set(), log)

    error = reg.list_for_ui()[0]["error"]
    assert "_shared_helper.py" in error
    assert "same folder" in error


def test_a_plugin_written_against_a_newer_app_is_not_sent_to_pip(tmp_path):
    """'pip install core' is supply-chain advice, not a fix.

    A plugin importing something this app owns but this copy does not have
    means the app is older than the plugin. Naming a package that happens to
    share the name is how a user installs a stranger's code to fix a typo.
    """
    folder = tmp_path / "plugins"
    write(folder, "from_future.py", (
        "from core.a_module_this_app_does_not_have_yet import thing\n\n"
        "def run(parameters, player=None, session_memory=None):\n"
        "    return thing()\n\n"
        'PLUGIN = {"name": "from_future", "description": "d"}\n'
    ))

    reg = discover_plugins(folder, set(), lambda _m: None)

    error = reg.list_for_ui()[0]["error"]
    assert "part of this app" in error
    assert "pip install core" not in error
    assert "Update the app" in error


def test_an_installed_third_party_package_is_still_advice_to_install():
    """The opposite case must stay a pip line — that one IS a missing package."""
    error = _load_error(Path("/tmp/p.py"), Path("/tmp/plugins"),
                        ModuleNotFoundError("No module named 'pandas'", name="pandas"))
    assert "pip install pandas" in error


def test_plugin_settings_schemas_are_deduped_by_namespace(tmp_path):
    folder = tmp_path / "plugins"
    schema = (
        "PLUGIN_SETTINGS = {'namespace': 'printer', 'title': 'Printer',\n"
        "                   'fields': [{'key': 'ip', 'type': 'text'}]}\n"
    )
    write(folder, "printer_one.py", plugin("printer_one", ) + schema)
    write(folder, "printer_two.py", plugin("printer_two") + schema)

    reg = discover_plugins(folder, set(), lambda _m: None)

    sections = reg.settings_schemas()
    assert len(sections) == 1
    assert sections[0]["namespace"] == "printer"
    assert sections[0]["fields"] == [{"key": "ip", "type": "text"}]


def _signed(folder: Path, name: str, permissions: list[str],
            schema: str = "") -> None:
    """A plugin plus a manifest that actually verifies, so `_enabled` sees the
    permissions it was declared with (a bare PLUGIN[...] key does nothing —
    permissions come from the manifest, and a manifest must carry the hash)."""
    from core.plugin_manifest import sha256_of
    py = write(folder, f"{name}.py", plugin(name) + schema)
    (folder / f"{name}.json").write_text(
        json.dumps({"name": name, "version": "1.0",
                    "permissions": permissions, "sha256": sha256_of(py)}),
        encoding="utf-8")


def test_a_disabled_plugin_still_offers_its_settings_form(tmp_path, isolated_config):
    """THE BUG THE USER REPORTED, IN ONE TEST.

    `prayer_times` declares a settings form AND a network permission, so it
    arrives switched OFF and `_enabled` is False. The panel used to filter on
    exactly that flag, so every shipped plugin with a form was invisible and the
    panel claimed there was nothing to configure — while the manager listed all
    five plugins. A form is how the user learns what a plugin wants configured;
    asking for consent must not hide it.
    """
    folder = tmp_path / "plugins"
    _signed(folder, "creds", ["network"],
            "PLUGIN_SETTINGS = {'namespace': 'creds', 'title': 'Creds',\n"
            "                   'fields': [{'key': 'key', 'type': 'text'}]}\n")
    reg = discover_plugins(folder, set(), lambda _m: None)

    assert reg.list_for_ui()[0]["enabled"] is False       # not consented...
    sections = reg.settings_schemas()
    assert len(sections) == 1                             # ...but still listed
    assert sections[0]["enabled"] is False                # the panel is told so
    assert sections[0]["namespace"] == "creds"


def test_an_enabled_plugin_says_so(tmp_path, isolated_config):
    """And the flag must be able to say yes: a panel that greys out everything
    is not a fix, it is the same panel with a different complaint."""
    folder = tmp_path / "plugins"
    _signed(folder, "open_plugin", [],
            "PLUGIN_SETTINGS = {'namespace': 'open_plugin', 'fields': [{'key': 'a'}]}\n")
    section = discover_plugins(folder, set(), lambda _m: None).settings_schemas()[0]
    assert section["enabled"] is True


def test_every_loaded_plugin_gets_a_section(tmp_path, isolated_config):
    """The panel's promise, in the form the user complained about.

    Five plugins ship with this repository. Four declare no settings schema at
    all. The old `settings_schemas()` returned the intersection of "declares a
    schema" and "is enabled", so it returned nothing — and the settings panel
    told the user no plugins were installed. One section per plugin, schema or
    not, is the fix; the panel decides how to draw a plugin with no fields.
    """
    folder = tmp_path / "plugins"
    write(folder, "with_form.py", plugin("with_form") +
          "PLUGIN_SETTINGS = {'namespace': 'wf', 'fields': [{'key': 'a'}]}\n")
    write(folder, "without_form.py", plugin("without_form"))
    reg = discover_plugins(folder, set(), lambda _m: None)

    sections = {s["plugin"]: s for s in reg.settings_schemas()}
    assert set(sections) == {"with_form", "without_form"}
    assert sections["with_form"]["schema"] is True
    assert [f["key"] for f in sections["with_form"]["fields"]] == ["a"]
    assert sections["without_form"]["schema"] is False
    assert sections["without_form"]["fields"] == []
    assert sections["without_form"]["enabled"] is True


def test_the_repository_own_plugins_all_reach_the_panel(isolated_config):
    """Not a tmp_path fixture: the real `plugins/` folder, the real manifests.

    This is the regression that matters, because it is the one the user hit.
    `prayer_times` is the interesting row — it declares a form AND a network
    permission, so it is switched OFF; it must still appear, marked disabled.
    """
    reg = discover_plugins(Path(__file__).resolve().parent.parent / "plugins",
                           set(), lambda _m: None)

    sections = {s["plugin"]: s for s in reg.settings_schemas()}
    managed = {row["name"] for row in reg.list_for_ui()}
    assert managed == {"currency_rates", "market_price", "mt5_orb",
                       "prayer_times", "quick_notes"}
    assert set(sections) == managed                # the panel lists them all

    prayer = sections["prayer_times"]
    assert prayer["schema"] is True and prayer["enabled"] is False
    assert {f["key"] for f in prayer["fields"]} == {"city", "country", "method", "school"}


def test_a_refused_plugin_never_reaches_the_settings_panel(tmp_path, isolated_config):
    """A section carries a schema, which is code the file declared.

    The loader replaces a refused plugin's record precisely so nothing it
    declared survives — so there is no section for it, however clean the import
    was, and the manager (which reports the reason) is where the user looks.
    """
    folder = tmp_path / "plugins"
    write(folder, "broken_with_form.py",
          plugin("broken_with_form") +
          "PLUGIN_SETTINGS = {'namespace': 'bf', 'fields': [{'key': 'x'}]}\n")
    (folder / "broken_with_form.json").write_text(
        json.dumps({"name": "broken_with_form", "permissions": ["telepathy"]}),
        encoding="utf-8")
    reg = discover_plugins(folder, set(), lambda _m: None)

    row = reg.list_for_ui()[0]
    assert row["valid"] is False and row["error"]     # in the manager, with why
    assert reg.settings_schemas() == []               # and not in the panel


def test_a_namespace_claimed_by_two_plugins_is_listed_once(tmp_path, isolated_config):
    """`settings_schemas` dedupes by namespace — and now that every plugin gets
    a section, the plugin WITHOUT a schema must not be able to claim a
    namespace the schema owner already took (that would list it twice)."""
    folder = tmp_path / "plugins"
    schema = ("PLUGIN_SETTINGS = {'namespace': 'printer', 'title': 'Printer',\n"
              "                   'fields': [{'key': 'ip'}]}\n")
    write(folder, "printer_one.py", plugin("printer_one") + schema)
    write(folder, "printer_two.py", plugin("printer_two"))
    reg = discover_plugins(folder, set(), lambda _m: None)

    sections = reg.settings_schemas()
    assert [s["namespace"] for s in sections] == ["printer", "printer_two"]


def test_the_summary_line_counts_active_and_rejected(tmp_path):
    """The CI step greps these lines, so their shape is part of the contract."""
    folder = tmp_path / "plugins"
    write(folder, "good_plugin.py", plugin())
    write(folder, "bad.py", "x = 1\n")
    lines, log = logs()

    discover_plugins(folder, set(), log)

    summary = [line for line in lines if "discovery complete" in line]
    assert summary and "1 active" in summary[0] and "1 rejected" in summary[0]


def test_a_rejected_plugin_reaches_the_user_once(tmp_path):
    """The console gets every detail; the HUD gets one line, or nothing."""
    folder = tmp_path / "plugins"
    write(folder, "bad_one.py", "x = 1\n")
    write(folder, "bad_two.py", "y = 2\n")
    notices: list[str] = []

    discover_plugins(folder, set(), lambda _m: None, notices.append)

    assert len(notices) == 1
    assert "2 plugin(s)" in notices[0]


def test_a_second_scan_of_another_folder_does_not_reuse_the_first(tmp_path):
    """THE BUG THIS SUITE FOUND.

    Discovered modules are cached in `sys.modules` under the file's stem
    (`actions.same`). Two folders can hold one name — a test scanning a
    tmp_path, dev_agent smoke-testing a project it just wrote, a user comparing
    two versions of an action. Keyed by name alone, the second scan got the
    FIRST file's module and never executed the second: the old TOOL, the old
    handler, and no message anywhere saying so.
    """
    # Distinct stems per folder would test nothing; the cache key IS the stem.
    one, two = tmp_path / "one", tmp_path / "two"
    write(one, "same.py", action("from_one"))
    write(two, "same.py", action("from_two"))

    first = discover_actions(one, set(), lambda _m: None)
    second = discover_actions(two, set(), lambda _m: None)

    assert first.names() == {"from_one"}
    assert second.names() == {"from_two"}, "the second folder's file was never run"


def test_scanning_one_folder_twice_still_reuses_its_modules(tmp_path):
    """The other half of the same decision.

    The eager reuse exists so a handler is the same object the rest of the app
    already holds — a second scan must not re-execute the file and hand back a
    different function. Making the cache check stricter must not quietly turn
    that into a re-import on every scan.
    """
    folder = tmp_path / "actions"
    write(folder, "good_tool.py", action())

    first = discover_actions(folder, set(), lambda _m: None)
    again = discover_actions(folder, set(), lambda _m: None)

    assert (again._actions["good_tool"].handler
            is first._actions["good_tool"].handler), "the file was executed twice"
