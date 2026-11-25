"""core/plugin_permissions.py — the pure policy behind the per-plugin
permission matrix (board 5.7).

WHAT THIS DECIDES
    Board 5.7 draws a plugin page where each plugin shows the permissions it
    needs, a toggle per permission, and a status — trusted / restricted /
    rejected. This module turns the plugin's declared permissions plus the
    user's per-permission decisions into that status, and decides whether a
    plugin may RUN given those decisions. No config file, no plugin file,
    no Qt.

WHY THE DECISION IS PURE
    Whether a plugin is trusted is arithmetic over two sets: the permissions
    it declared and the permissions the user granted. Deciding the status,
    the summary sentence, and whether a run may proceed is policy; the store
    that holds the granted set and the manifest that holds the declared set are
    the adapter's job. A panel that computed the status while reading the
    store would be a control whose verdict depended on read timing.

THE THREE STATUSES, AND WHY THE MIDDLE ONE EXISTS
    trusted     every declared permission is granted.
    restricted  SOME declared permissions are granted and some are not. The
                plugin is offered, but the ungranted permissions are refused
                at run time — this is the point of a matrix: the user can
                allow a plugin's files access without granting its network.
    rejected    no declared permission is granted, or the plugin declared
                nothing to grant. A plugin that is restricted on its most
                dangerous permission is not silently trusted.

ENFORCEMENT IS THE REASON THIS EXISTS
    `may_run` is the check the dispatcher calls before a plugin runs. A plugin
    whose granted set does not cover its declared set is refused, and the
    refusal names the missing permissions, so the user can see exactly what
    is holding it back. A matrix that showed toggles but did not enforce them
    would be decoration — the plugin would still do whatever it does.

WHAT THIS DOES NOT DO
    It does not inspect what a plugin actually does at run time. The manifest
    declares permissions statically; this policy trusts that declaration and
    enforces the user's grants against it. A plugin that does more than it
    declares is the manifest verifier's problem (`core/plugin_manifest`), not
    this module's.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

# The permission vocabulary, matching `core.plugin_manifest.PERMISSIONS`.
# Kept here as the closed set the matrix operates on: a grant for a
# permission the vocabulary does not contain is not a grant this policy can
# reason about, so it is ignored rather than silently accepted.
PERMISSIONS: tuple[str, ...] = (
    "network", "files", "audio", "input", "shell", "clipboard",
)

TRUSTED = "trusted"
RESTRICTED = "restricted"
REJECTED = "rejected"


@dataclass
class PluginPermissions:
    """One plugin's matrix: what it needs, what was granted, and the verdict.

    `declared` is the set the plugin asked for; `granted` is the subset the
    user allowed. `status` is derived from those two. `missing` is the
    declared-but-ungranted set, which is what `may_run` refuses on and what
    the page names so the user can act.
    """

    name: str
    declared: frozenset[str]
    granted: frozenset[str]

    @property
    def missing(self) -> frozenset[str]:
        return self.declared - self.granted

    @property
    def status(self) -> str:
        if not self.declared:
            # A plugin that declared no permission has nothing to grant or
            # refuse. It is offered on the plugin's own terms; there is no
            # permission to toggle, so it is trusted with nothing to decide.
            return TRUSTED
        if self.missing:
            return RESTRICTED if self.granted else REJECTED
        return TRUSTED

    def summary(self) -> str:
        """One sentence for the card, from the verdict alone."""
        if not self.declared:
            return f"{self.name}: tidak meminta izin khusus."
        if self.status == TRUSTED:
            return f"{self.name}: terpercaya (semua izin diizinkan)."
        if self.status == REJECTED:
            return (f"{self.name}: ditolak — "
                    f"izin {', '.join(sorted(self.declared))} tidak diizinkan.")
        missing = ", ".join(sorted(self.missing))
        return (f"{self.name}: dibatasi — {missing} belum diizinkan.")


def normalise_declared(perms: Iterable[str]) -> frozenset[str]:
    """The declared set, filtered to the known vocabulary and de-duplicated.

    A permission outside the vocabulary is dropped: the matrix can only grant
    what it can name, and keeping an unknown string would let a plugin claim
    a grant the policy never reasoned about.
    """
    return frozenset(p for p in (perms or ()) if p in PERMISSIONS)


def normalise_granted(perms: Iterable[str]) -> frozenset[str]:
    """The granted set, filtered to the known vocabulary.

    Granting a permission the plugin did NOT declare is harmless but pointless
    — the plugin cannot use it — so it is kept (the user's intent is recorded)
    but never affects the verdict, because only declared permissions matter.
    """
    return frozenset(p for p in (perms or ()) if p in PERMISSIONS)


def build(name: str, declared, granted) -> PluginPermissions:
    """Assemble one plugin's matrix from raw declared/granted sets."""
    return PluginPermissions(
        name=name,
        declared=normalise_declared(declared),
        granted=normalise_granted(granted),
    )


def may_run(perms: PluginPermissions) -> tuple[bool, str]:
    """Whether a plugin may run, and why if it may not.

    The plugin runs when every DECLARED permission is granted. A plugin with
    nothing declared runs (there is nothing to refuse). The refusal names
    the missing permissions so the page and the log can say exactly what is
    holding the plugin back — a bare "no" is a control the user cannot act on.
    """
    if not perms.declared:
        return True, f"{perms.name}: tidak memerlukan izin, jalan."
    missing = perms.missing
    if missing:
        return (False,
                f"{perms.name} ditolak: izin "
                f"{', '.join(sorted(missing))} belum diizinkan.")
    return True, f"{perms.name}: semua izin diizinkan, jalan."


def matrix(
    entries: Iterable[tuple[str, Iterable[str], Iterable[str]]],
) -> list[PluginPermissions]:
    """Build the whole matrix: (name, declared, granted) triples.

    Used by the page to render every plugin's card in one pass. Each entry
    is normalised independently so one bad triple cannot poison the rest.
    """
    return [build(name, declared, granted)
            for name, declared, granted in entries]


def grant(current: Iterable[str], permission: str) -> frozenset[str]:
    """Return the granted set with `permission` added (if it is a real one).

    Granting an unknown permission is a no-op: the matrix cannot enforce a
    grant it cannot name, so recording it would be a grant that does nothing.
    """
    base = normalise_granted(current)
    if permission in PERMISSIONS:
        return base | {permission}
    return base


def revoke(current: Iterable[str], permission: str) -> frozenset[str]:
    """Return the granted set with `permission` removed.

    Revoking a permission the plugin needs moves it to restricted/rejected;
    revoking one it did not need changes nothing, which is the honest answer.
    """
    base = normalise_granted(current)
    return base - {permission}


__all__ = [
    "PERMISSIONS", "TRUSTED", "RESTRICTED", "REJECTED",
    "PluginPermissions", "normalise_declared", "normalise_granted",
    "build", "may_run", "matrix", "grant", "revoke",
]
