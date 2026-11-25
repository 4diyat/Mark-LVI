"""Board 5.7's per-plugin permission matrix policy: status + enforcement.

These test the pure policy in `core.plugin_permissions` with no manifest and
no config. The point is enforcement: a plugin whose granted set does not cover
its declared set is refused, and the refusal names exactly what is missing —
a matrix that showed toggles but did not enforce them would be decoration.
"""
from __future__ import annotations

from core.plugin_permissions import (REJECTED, RESTRICTED, TRUSTED,
                                     build, grant, may_run, matrix, revoke)


# ── status ────────────────────────────────────────────────────────────────

def test_a_plugin_with_no_declared_permissions_is_trusted():
    perms = build("notes", [], [])
    assert perms.status == TRUSTED


def test_a_plugin_with_every_permission_granted_is_trusted():
    perms = build("gmail", ["network", "files"], ["network", "files"])
    assert perms.status == TRUSTED


def test_a_plugin_with_some_permissions_granted_is_restricted():
    perms = build("gmail", ["network", "files"], ["files"])
    assert perms.status == RESTRICTED


def test_a_plugin_with_none_granted_is_rejected():
    perms = build("gmail", ["network", "files"], [])
    assert perms.status == REJECTED


def test_the_missing_set_names_the_ungranted_permissions():
    perms = build("gmail", ["network", "files"], ["files"])
    assert perms.missing == frozenset({"network"})


# ── summary ──────────────────────────────────────────────────────────────

def test_the_trusted_summary_says_everything_is_allowed():
    perms = build("gmail", ["network"], ["network"])
    assert "terpercaya" in perms.summary()


def test_the_restricted_summary_names_what_is_missing():
    perms = build("gmail", ["network", "files"], ["files"])
    summary = perms.summary()
    assert "dibatasi" in summary
    assert "network" in summary


def test_the_rejected_summary_names_what_was_refused():
    perms = build("gmail", ["network", "files"], [])
    summary = perms.summary()
    assert "ditolak" in summary
    assert "network" in summary


def test_a_no_permission_plugin_says_so():
    perms = build("notes", [], [])
    assert "izin khusus" in perms.summary()


# ── enforcement (may_run) ────────────────────────────────────────────────

def test_a_plugin_with_no_declared_permission_may_run():
    ok, reason = may_run(build("notes", [], []))
    assert ok is True
    assert "tidak memerlukan izin" in reason


def test_a_fully_granted_plugin_may_run():
    ok, reason = may_run(build("gmail", ["network", "files"], ["network", "files"]))
    assert ok is True
    assert "semua izin" in reason


def test_a_restricted_plugin_is_refused_and_names_the_missing():
    perms = build("gmail", ["network", "files"], ["files"])
    ok, reason = may_run(perms)
    assert ok is False
    assert "network" in reason
    assert "belum diizinkan" in reason


def test_a_rejected_plugin_is_refused():
    ok, _ = may_run(build("gmail", ["network"], []))
    assert ok is False


# ── normalisation ─────────────────────────────────────────────────────────

def test_an_unknown_declared_permission_is_dropped():
    perms = build("weird", ["network", "astral"], ["network", "astral"])
    assert perms.declared == frozenset({"network"})
    assert perms.status == TRUSTED


def test_a_grant_for_an_unknown_permission_does_not_change_the_set():
    granted = grant(["network"], "astral")
    assert granted == frozenset({"network"})


def test_revoke_removes_only_the_named_permission():
    granted = revoke(["network", "files"], "network")
    assert granted == frozenset({"files"})


# ── matrix ────────────────────────────────────────────────────────────────

def test_matrix_builds_one_entry_per_plugin():
    entries = [("a", ["network"], ["network"]),
               ("b", ["files"], [])]
    out = matrix(entries)
    assert len(out) == 2
    assert out[0].status == TRUSTED
    assert out[1].status == REJECTED
