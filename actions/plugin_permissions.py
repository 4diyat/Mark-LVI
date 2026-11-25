"""actions/plugin_permissions.py — the per-plugin permission matrix adapter
(board 5.7).

WHAT THIS DOES
    Reads each plugin's declared permissions (from its manifest) and the
    user's granted set (from config), and hands both to the pure policy in
    `core.plugin_permissions`, which decides the status and whether the plugin
    may run. This module is the one place that touches the manifest and the
    config; it never computes a verdict itself.

WHY THE ADAPTERS SPLIT
    The policy in `core/plugin_permissions.py` is pure — it takes two sets and
    returns a verdict. That is so a test can drive every status with fixtures.
    This adapter is where the sets come from: the declared set from the plugin
    manifest (`core.plugin_manifest`), the granted set from the per-plugin
    grant store in config. Reading them here keeps the policy free of both.

WHAT IT DOES NOT DO
    It does not load or run a plugin, and it does not write a grant on its
    own. `grant` and `revoke` are policy functions the page calls with the
    current granted set; this adapter only reads, so a read can never change
    the matrix the user set up.
"""
from __future__ import annotations

from typing import Iterable


def _grant_store() -> dict:
    """The per-plugin granted-permission sets from config, or {} if unset.

    Stored as `plugins_grants[<plugin>] = [permission, ...]`. A read that
    fails returns an empty store rather than raising: a panel that cannot
    read the grants must still render every plugin, with nothing granted,
    rather than crash on one plugin's entry.
    """
    try:
        from memory.config_manager import load_api_keys
        store = load_api_keys().get("plugins_grants", {})
        return store if isinstance(store, dict) else {}
    except Exception:                              # noqa: BLE001
        return {}


def granted_for(plugin_name: str) -> frozenset[str]:
    """The permissions the user granted to one plugin.

    A plugin with no grant entry is granted nothing — which, for a plugin
    that declared permissions, makes it rejected until the user grants. That
    is the consent default the loader already applies, made explicit here so
    the matrix agrees with the dispatcher.
    """
    from core.plugin_permissions import normalise_granted
    raw = _grant_store().get(plugin_name, [])
    if not isinstance(raw, (list, tuple, set)):
        return frozenset()
    return normalise_granted(raw)


def declared_for(plugin_name: str, manifest=None) -> frozenset[str]:
    """The permissions a plugin's manifest declares, or nothing if it has none.

    `manifest` may be passed in (the loader already has it); when omitted, the
    manifest is read by name. A plugin with no manifest — a first-party plugin
    that never declared — declares nothing, which the policy treats as
    "no permission to decide".
    """
    from core.plugin_permissions import normalise_declared
    if manifest is not None:
        perms = list(getattr(manifest, "permissions", ()) or ())
        return normalise_declared(perms)
    try:
        from core.plugin_manifest import verify
        from core.appidentity import plugins_dir
        declared = verify(plugins_dir / f"{plugin_name}.py",
                          plugin_name)
        perms = list(getattr(declared, "permissions", ()) or ())
        return normalise_declared(perms)
    except Exception:                              # noqa: BLE001
        return frozenset()


def build_matrix(entries: Iterable[tuple[str, object]]) -> list:
    """Build the full matrix from (plugin_name, manifest_or_None) pairs.

    Each entry's declared set comes from the manifest (or the on-disk
    manifest when none is passed) and its granted set from the store. The
    policy does the verdict; this only assembles the inputs.
    """
    from core.plugin_permissions import build
    out = []
    for name, manifest in entries:
        declared = declared_for(name, manifest)
        granted = granted_for(name)
        out.append(build(name, declared, granted))
    return out


def grant(plugin_name: str, permission: str) -> frozenset[str]:
    """Add one grant to a plugin's granted set and persist it.

    Returns the NEW granted set so the page can re-render immediately. The
    policy's `grant` is applied first (an unknown permission is a no-op),
    then the result is written to the store. A write that fails returns the
    set that was intended, not an empty set — the in-memory decision is the
    user's, and a failed write must not silently undo it.
    """
    from core.plugin_permissions import grant as _grant
    from memory.config_manager import update_config

    current = granted_for(plugin_name)
    new = _grant(current, permission)
    if new == current:
        return new

    def _apply(data: dict) -> None:
        store = data.get("plugins_grants")
        if not isinstance(store, dict):
            store = {}
        store[plugin_name] = sorted(new)
        data["plugins_grants"] = store

    try:
        update_config(_apply)
    except Exception as exc:                  # noqa: BLE001
        print(f"[Plugin permissions] grant tidak disimpan untuk "
              f"{plugin_name}: {exc}")
    return new


def revoke(plugin_name: str, permission: str) -> frozenset[str]:
    """Remove one grant from a plugin's granted set and persist it.

    Returns the NEW granted set. Revoking a permission the plugin needs
    moves it to restricted/rejected; the page re-renders from the return.
    """
    from core.plugin_permissions import revoke as _revoke
    from memory.config_manager import update_config

    current = granted_for(plugin_name)
    new = _revoke(current, permission)
    if new == current:
        return new

    def _apply(data: dict) -> None:
        store = data.get("plugins_grants")
        if not isinstance(store, dict):
            store = {}
        store[plugin_name] = sorted(new)
        data["plugins_grants"] = store

    try:
        update_config(_apply)
    except Exception as exc:                  # noqa: BLE001
        print(f"[Plugin permissions] revoke tidak disimpan untuk "
              f"{plugin_name}: {exc}")
    return new


__all__ = ["granted_for", "declared_for", "build_matrix", "grant", "revoke"]
