"""The manifest a third-party plugin carries, and what it is checked against.

WHY THESE TESTS ARE MOSTLY ABOUT WHAT IS REFUSED
    A manifest is a security feature only insofar as it can say no. Each refusal
    below is a plugin that would otherwise be imported and run with the app's
    full authority:

      * a file whose hash no longer matches the manifest — the plugin was
        changed after the user read it;
      * a plugin that calls `requests.get` and declares nothing;
      * a manifest that names a permission nobody defined, which would otherwise
        read as consent to something that was never described;
      * a manifest whose name disagrees with PLUGIN["name"], which decides which
        tool the model calls.

    And the other half, which matters just as much: a plugin from this
    repository with no manifest at all must keep loading, and a plugin that
    over-declares must not be rejected for it.
"""
from __future__ import annotations

import json
import sys
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import plugin_manifest as pm  # noqa: E402


def write_plugin(tmp_path: Path, source: str, manifest: dict | None = None,
                 name: str = "demo", suffix: str = ".json") -> Path:
    py = tmp_path / f"{name}.py"
    py.write_text(textwrap.dedent(source), encoding="utf-8")
    if manifest is not None:
        body = dict(manifest)
        body.setdefault("name", name)
        (tmp_path / f"{name}{suffix}").write_text(json.dumps(body), encoding="utf-8")
    return py


PLAIN = '''
PLUGIN = {"name": "demo"}

def run(parameters, player=None, session_memory=None):
    return "ok"
'''

NETWORKED = '''
import requests

PLUGIN = {"name": "demo"}

def run(parameters, player=None, session_memory=None):
    return requests.get("https://example.invalid").text
'''


# ── discovery of the manifest ───────────────────────────────────────────────

def test_no_manifest_is_none_and_not_an_error(tmp_path):
    """Every plugin in this repository predates manifests and must keep
    loading. `None` says 'did not declare', which the caller can allow."""
    py = write_plugin(tmp_path, PLAIN)
    assert pm.manifest_path(py) is None
    assert pm.read(py) is None
    assert pm.verify(py) is None


def test_both_sidecar_spellings_are_found(tmp_path):
    for suffix in (".json", ".plugin.json"):
        py = write_plugin(tmp_path, PLAIN, {"version": "1.0"}, suffix=suffix)
        assert pm.manifest_path(py) is not None, suffix


def test_a_manifest_that_is_not_json_is_a_problem_not_a_crash(tmp_path):
    py = write_plugin(tmp_path, PLAIN, {"version": "1.0"})
    (tmp_path / "demo.json").write_text("{oops", encoding="utf-8")
    manifest = pm.read(py)
    assert manifest is not None and not manifest.ok
    assert "will not parse" in manifest.problems[0]


# ── the hash ───────────────────────────────────────────────────────────────

def test_a_matching_hash_is_accepted(tmp_path):
    py = write_plugin(tmp_path, PLAIN)
    digest = pm.sha256_of(py)
    py = write_plugin(tmp_path, PLAIN, {"sha256": digest, "version": "1.0"})
    manifest = pm.verify(py)
    assert manifest.ok, manifest.problems
    assert manifest.warnings == []


def test_a_file_changed_after_publication_is_refused(tmp_path):
    """The failure a hash exists for: the user read version 1, and version 2
    arrived in the same file name."""
    py = write_plugin(tmp_path, PLAIN, {"sha256": "0" * 64})
    manifest = pm.verify(py)
    assert not manifest.ok
    assert "sha256 does not match" in manifest.problems[0]


def test_a_missing_hash_is_a_warning_not_a_refusal(tmp_path):
    """Older manifests, and hand-written local plugins, will not have one. The
    user is told the check could not be made rather than blocked from their own
    file."""
    py = write_plugin(tmp_path, PLAIN, {"version": "0.1"})
    manifest = pm.verify(py)
    assert manifest.ok
    assert any("cannot be checked" in w for w in manifest.warnings)


# ── permissions, declared vs. what the code does ────────────────────────────

def test_an_import_scan_finds_the_obvious_ones(tmp_path):
    py = write_plugin(tmp_path, '''
        import subprocess, pyperclip
        from pathlib import Path
        import requests

        def run(parameters, player=None, session_memory=None):
            open("x.txt", "w").write("y")
            return Path("x.txt").read_text()
    ''')
    implied = pm.implied_permissions(py)
    assert {"network", "files", "shell", "clipboard"} <= implied
    assert "audio" not in implied and "input" not in implied


def test_an_undeclared_permission_is_refused_with_a_readable_reason(tmp_path):
    py = write_plugin(tmp_path, NETWORKED, {"permissions": ["files"]})
    manifest = pm.verify(py)
    assert not manifest.ok
    assert "uses network without declaring it" in manifest.problems[0]
    assert "the user consented to: files" in manifest.problems[0]


def test_a_declared_permission_is_accepted(tmp_path):
    py = write_plugin(tmp_path, NETWORKED, {"permissions": ["network"]})
    manifest = pm.verify(py)
    assert manifest.ok, manifest.problems


def test_over_declaring_is_a_warning_never_a_refusal(tmp_path):
    """A plugin that asks for more than the scan can see is being honest, and
    static analysis misses helper modules and getattr(). Refusing it would make
    the feature punish the careful."""
    py = write_plugin(tmp_path, PLAIN, {"permissions": ["audio", "network"]})
    manifest = pm.verify(py)
    assert manifest.ok
    assert any("did not see" in w for w in manifest.warnings)


def test_an_undefined_permission_is_refused_and_lists_the_real_ones(tmp_path):
    """Otherwise 'permissions: ["everything"]' is consent to nothing in
    particular, printed next to a Run button."""
    py = write_plugin(tmp_path, PLAIN, {"permissions": ["everything"]})
    manifest = pm.verify(py)
    assert not manifest.ok
    assert "unknown permission" in manifest.problems[0]
    assert "network" in manifest.problems[0]      # it says what IS available


def test_a_manifest_name_must_match_the_plugin_name(tmp_path):
    """This is the name the model calls. Two answers is a tool nobody can
    reason about — including the tool itself."""
    py = write_plugin(tmp_path, PLAIN, {"name": "something_else"})
    manifest = pm.verify(py, plugin_name="demo")
    assert not manifest.ok
    assert "does not match" in manifest.problems[0]


def test_a_string_permission_is_accepted_as_a_one_item_list(tmp_path):
    """A JSON file written by hand is usually written with one permission."""
    py = write_plugin(tmp_path, NETWORKED, {"permissions": "network"})
    assert pm.verify(py).ok


# ── what the user is shown ─────────────────────────────────────────────────

def test_describe_says_what_each_permission_means(tmp_path):
    py = write_plugin(tmp_path, NETWORKED,
                      {"version": "2.1", "author": "ana", "permissions": ["network"]})
    text = pm.describe(pm.verify(py, "demo"))
    assert "demo 2.1" in text and "by ana" in text
    assert "network: makes outbound requests" in text


def test_describe_never_claims_containment(tmp_path):
    """The one sentence a user must not be able to misread. A manifest is a
    declaration; the plugin runs with the app's authority."""
    py = write_plugin(tmp_path, PLAIN, {"permissions": []})
    text = pm.describe(pm.verify(py))
    assert "not a sandbox" in text


def test_summary_omits_empty_fields(tmp_path):
    py = write_plugin(tmp_path, PLAIN, {"version": "1.0"})
    assert pm.verify(py).summary() == "demo 1.0"


@pytest.mark.parametrize("permission", sorted(pm.PERMISSIONS))
def test_every_permission_has_a_sentence(permission):
    """A permission with no description is one the dialog cannot ask about."""
    assert pm.PERMISSIONS[permission].strip()


# ── and the loader actually refuses ────────────────────────────────────────

def test_a_bad_manifest_stops_the_plugin_loading(tmp_path):
    """The tests above prove `verify()` refuses. This one proves the refusal
    reaches the thing that imports the file — a manifest nobody consults is
    decoration."""
    import textwrap as _tw
    from core.plugin_loader import discover_plugins

    # `requests` is not installed where this suite runs (by design — see
    # requirements-dev.txt), and an import that fails would reject the plugin
    # for the wrong reason. `shutil` implies "files" without the dependency.
    (tmp_path / "rogue.py").write_text(_tw.dedent('''
        import shutil

        PLUGIN = {"name": "rogue", "description": "d",
                  "parameters": {"type": "OBJECT", "properties": {}}}

        def run(parameters, player=None, session_memory=None):
            return "ran"
    '''), encoding="utf-8")
    # Both halves of a refusal: a hash that no longer matches, and a
    # permission the source uses but the manifest never asked for.
    (tmp_path / "rogue.json").write_text(json.dumps(
        {"name": "rogue", "permissions": [], "sha256": "0" * 64}), encoding="utf-8")

    lines: list[str] = []
    registry = discover_plugins(tmp_path, set(), lines.append)

    assert not registry.has("rogue"), "a bad manifest must stop the tool"
    record = next(r for r in registry._all_records if r.file == "rogue.py")
    assert not record.valid
    assert "Manifest check failed" in record.error
    assert "sha256 does not match" in record.error
    assert "uses files without declaring it" in record.error


def test_a_plugin_with_no_manifest_still_loads(tmp_path):
    """The property that makes this shippable: this repository's own plugins,
    and anything a user wrote for themselves, are unaffected."""
    import textwrap as _tw
    from core.plugin_loader import discover_plugins

    (tmp_path / "plain.py").write_text(_tw.dedent('''
        PLUGIN = {"name": "plain", "description": "d",
                  "parameters": {"type": "OBJECT", "properties": {}}}

        def run(parameters, player=None, session_memory=None):
            return "ran"
    '''), encoding="utf-8")
    registry = discover_plugins(tmp_path, set(), lambda _m: None)
    assert registry.has("plain")
    assert next(r for r in registry._all_records if r.file == "plain.py").manifest is None


def test_a_valid_manifest_attaches_to_the_record(tmp_path):
    import textwrap as _tw
    from core.plugin_loader import discover_plugins

    source = _tw.dedent('''
        PLUGIN = {"name": "good", "description": "d",
                  "parameters": {"type": "OBJECT", "properties": {}}}

        def run(parameters, player=None, session_memory=None):
            return "ran"
    ''')
    py = tmp_path / "good.py"
    py.write_text(source, encoding="utf-8")
    (tmp_path / "good.json").write_text(json.dumps({
        "name": "good", "version": "1.0", "permissions": ["files"],
        "sha256": pm.sha256_of(py)}), encoding="utf-8")

    registry = discover_plugins(tmp_path, set(), lambda _m: None)
    assert registry.has("good")
    record = next(r for r in registry._all_records if r.file == "good.py")
    assert record.manifest is not None and record.manifest.permissions == ("files",)
