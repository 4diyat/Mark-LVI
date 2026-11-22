"""The file-access policy, called directly — it never needed a window.

WHY THIS FILE EXISTS
    `core/file_access.py` was on the coverage map's CANNOT_RUN_HERE list with
    the reason "its prompt was a widget; there is no window to ask with". That
    reason is half true and half a mistake. The PROMPT was a widget, and the
    widget is gone with the controls drawer. But the module is not the prompt:
    `Policy` is a data structure plus a path check, and `actions/file_controller`
    still consults it on every file operation. The exemption described a caller
    that had died, not a module that could not be executed — and an exemption
    with a stale reason is the failure mode the map's own docstring warns about.

    So the policy is tested here, on a real temporary directory, with no Qt.

WHAT IS GUARANTEED, AND WHY EACH ONE MATTERS
    Off is the default, and off means the home folder and nothing else. A
    settings file that is missing, malformed, or of the wrong shape must make
    the policy STRICTER — never wider. Every one of those is a way a broken
    config could otherwise grant a folder nobody chose.
"""
from __future__ import annotations

import json

import pytest

from core import file_access


@pytest.fixture()
def home(tmp_path):
    root = tmp_path / "home"
    (root / "documents").mkdir(parents=True)
    (root / "documents" / "notes.txt").write_text("x", encoding="utf-8")
    return root


@pytest.fixture()
def elsewhere(tmp_path):
    root = tmp_path / "elsewhere"
    (root / "project").mkdir(parents=True)
    (root / "project" / "data.csv").write_text("x", encoding="utf-8")
    return root


# ── the default is closed ───────────────────────────────────────────────────

def test_off_by_default_means_home_and_nothing_else(home, elsewhere):
    policy = file_access.Policy(home=home)
    assert policy.enabled is False
    assert policy.allows(home / "documents" / "notes.txt") is True
    assert policy.allows(elsewhere / "project" / "data.csv") is False, (
        "a policy that is off must not reach outside the home folder")


def test_a_granted_root_is_ignored_while_the_switch_is_off(home, elsewhere):
    """"Off" must not mean "whatever was granted last time". A user who turns
    the feature off expects the folder access to stop, not to persist."""
    policy = file_access.Policy(enabled=False, roots=(elsewhere,), home=home)
    assert policy.allows(elsewhere / "project" / "data.csv") is False


def test_turning_it_on_ADDS_a_root_and_never_takes_home_away(home, elsewhere):
    """The bug this test was written for.

    `effective_roots()` returned ONLY the granted roots while the feature was
    on, so granting one extra folder silently revoked the home folder — every
    file operation that worked a second earlier started being refused. The
    function's own docstring promised "off means home only ... not an empty
    list", which is the promise it broke on the other branch.
    """
    policy = file_access.Policy(enabled=True, roots=(elsewhere,), home=home)
    assert policy.allows(elsewhere / "project" / "data.csv") is True
    assert policy.allows(home / "documents" / "notes.txt") is True, (
        "turning file access ON took away a folder the user already had")


def test_on_with_no_root_granted_still_reaches_home(home):
    """"Enabled, but nowhere" is home-only, not nothing — otherwise a single
    hand-edited `enabled: true` would break the assistant's own file ops."""
    policy = file_access.Policy(enabled=True, roots=(), home=home)
    assert policy.allows(home / "documents" / "notes.txt") is True
    assert policy.describe().startswith("Full file access: ON")


# ── turning it on cannot be done from a bad file ────────────────────────────

def test_a_missing_config_is_off(home):
    policy = file_access.load(path="/nonexistent/api_keys.json", home=home)
    assert policy.enabled is False


@pytest.mark.parametrize("body", [
    "not json at all",
    "[]",
    '"a string"',
    '{"file_access": "yes"}',
    '{"file_access": []}',
])
def test_a_broken_config_is_off_rather_than_open(tmp_path, home, body):
    """Every malformed shape has to land on OFF. The dangerous direction is the
    other one: a config error that grants a folder is a permission the user
    never gave."""
    path = tmp_path / "api_keys.json"
    path.write_text(body, encoding="utf-8")
    policy = file_access.load(path=path, home=home)
    assert policy.enabled is False


def test_enabled_needs_the_literal_true(tmp_path, home, elsewhere):
    """`"true"`, `1` and `"yes"` are all things a hand-edited JSON file
    contains, and none of them is a decision to grant access."""
    path = tmp_path / "api_keys.json"
    for value in ('"true"', "1", '"yes"'):
        path.write_text(
            '{"file_access": {"enabled": %s, "roots": ["%s"]}}'
            % (value, str(elsewhere).replace("\\", "\\\\")),
            encoding="utf-8")
        policy = file_access.load(path=path, home=home)
        assert policy.enabled is False, f"{value!r} turned file access on"


def test_a_real_config_turns_it_on(tmp_path, home, elsewhere):
    """The positive direction, or every test above passes on a module that
    always says no."""
    path = tmp_path / "api_keys.json"
    path.write_text(json.dumps({
        "file_access": {"enabled": True, "roots": [str(elsewhere)]},
    }), encoding="utf-8")
    policy = file_access.load(path=path, home=home)
    assert policy.enabled is True
    assert policy.allows(elsewhere / "project" / "data.csv") is True


# ── what stays closed even when the switch is on ────────────────────────────

@pytest.mark.parametrize("dangerous", [
    ".ssh/id_rsa",
    ".ssh",
])
def test_credentials_are_refused_even_inside_a_granted_root(
        home, elsewhere, dangerous):
    """Full file access is about FOLDERS, not about keys. A granted root that
    happens to contain `~/.ssh` must not become a way to read a private key."""
    target = home / dangerous
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("secret", encoding="utf-8")
    policy = file_access.Policy(enabled=True, roots=(home,), home=home)
    assert policy.allows(target) is False, (
        f"{dangerous} became readable because the whole home was granted")


def test_an_unresolvable_root_is_dropped_not_guessed(home):
    """A root that cannot be resolved makes the policy stricter. Guessing at it
    is how a typo in a config becomes a granted folder."""
    policy = file_access.Policy.from_config(
        {"file_access": {"enabled": True, "roots": ["", "   ", None, 42]}},
        home=home)
    assert policy.roots == (), f"unusable roots survived: {policy.roots}"


def test_save_with_no_roots_refuses_to_switch_on(tmp_path, home, monkeypatch):
    """"Enabled, but nowhere" is a state that only produces confusing refusals,
    so it is not a state. `save([])` must leave the switch off."""
    from memory import config_manager

    path = tmp_path / "api_keys.json"
    path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(config_manager, "CONFIG_FILE", path)
    monkeypatch.setattr(config_manager, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(config_manager, "_LAST_GOOD", {})

    assert file_access.save([]) is False
    policy = file_access.load(path=path, home=home)
    assert policy.enabled is False
