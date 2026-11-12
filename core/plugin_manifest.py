"""core/plugin_manifest.py — what a third-party plugin declares before it runs.

WHY A MANIFEST, AND WHY IT IS NOT A SANDBOX
    A plugin is a Python file that is imported into this process. It can read
    config/api_keys.json, open the microphone, delete a folder. There is no
    "safe" version of that inside one interpreter — a real boundary costs a
    subprocess per call, and this app's plugins are written to talk to `player`
    and to the session, which a subprocess cannot do.

    So the honest goal is not containment; it is **informed consent**. Before a
    plugin from anywhere but this repository runs, three questions have an
    answer somebody can read:

      1. What does it say it does, and who wrote it?           → manifest
      2. What does it need access to?                          → declared permissions
      3. Is it the same file the author published?             → sha256

    A signature would answer (3) better. It also needs a key distribution
    story, a revocation story and a place to keep the public keys — none of
    which exist, and all of which would be invented by the first person to
    deploy this. A hash cannot prove authorship; it can prove that the file a
    user is about to run is the file whose code they read, which is the failure
    that actually happens (a plugin updated between reading and installing).

WHY THE PERMISSIONS ARE CHECKED AGAINST THE SOURCE
    A declared permission list is a promise, and a promise is worth what its
    verification is worth. `audio` means the plugin uses sounddevice; `files`
    means it opens files; `network` means it makes requests. The check here is
    a crude static one — an import scan plus a few call patterns — and it is
    deliberately limited to the direction that matters: a plugin that USES one
    of these without DECLARING it is refused. A plugin that over-declares is
    merely asked to justify itself.

    Crude is the point. A determined plugin can hide an import behind
    importlib; nothing here claims otherwise, and the manifest says so to the
    user in those words. What it does catch is the ordinary case: forty lines
    copied from a tutorial that calls `requests.post` and never mentions it.

THE FORMAT
    A JSON file beside the plugin, same stem (`weather.py` + `weather.json`),
    or a `<stem>.plugin.json` in the same folder. JSON and not TOML/YAML
    because the rest of this project's config is JSON and adding a parser is
    adding a dependency.

    {
      "name": "weather",                 # must equal PLUGIN["name"]
      "version": "1.2.0",
      "author": "someone",
      "description": "…",
      "permissions": ["network"],        # see PERMISSIONS below
      "sha256": "…",                     # of the .py file
      "homepage": "https://…"            # optional
    }
"""
from __future__ import annotations

import ast
import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path

# What a plugin can ask for, and what each one means. Keep this list short: a
# permission that is never checked teaches the reader that the list is
# decorative.
PERMISSIONS = {
    "network": "makes outbound requests (requests, httpx, urllib, sockets)",
    "files": "reads or writes files outside its own folder",
    "audio": "opens the microphone or the speakers",
    "input": "moves the mouse, types, or takes screenshots",
    "shell": "starts another process",
    "clipboard": "reads or writes the clipboard",
}

# The imports that imply each permission. Deliberately the same modules the
# actions/ folder uses, because that is what a plugin author will copy.
_IMPORT_HINTS = {
    "network": {"requests", "httpx", "urllib", "urllib3", "socket", "aiohttp",
                "websocket", "websockets", "google", "openai", "http"},
    "files": {"shutil", "glob", "pathlib", "tempfile"},
    "audio": {"sounddevice", "soundfile", "pyaudio", "wave"},
    "input": {"pyautogui", "pynput", "keyboard", "mouse", "mss", "PIL"},
    "shell": {"subprocess", "shlex", "pexpect"},
    "clipboard": {"pyperclip", "win32clipboard"},
}
# `os` and `io` are too common to imply anything on their own; `open()` is the
# tell for files and is checked separately below.
_AMBIGUOUS = {"os", "io", "sys", "json", "re", "time", "datetime", "math"}

# Calls that are unambiguous enough to imply a permission regardless of imports.
_CALL_HINTS = {
    "open": "files",
    "subprocess.run": "shell",
    "subprocess.Popen": "shell",
    "subprocess.check_output": "shell",
    "os.system": "shell",
    "pyperclip.copy": "clipboard",
    "pyperclip.paste": "clipboard",
}


@dataclass
class Manifest:
    name: str
    version: str = ""
    author: str = ""
    description: str = ""
    permissions: tuple[str, ...] = ()
    sha256: str = ""
    homepage: str = ""
    problems: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems

    def summary(self) -> str:
        """One line for the plugin manager: what it is and what it can do."""
        bits = [f"{self.name} {self.version}".strip()]
        if self.author:
            bits.append(f"by {self.author}")
        if self.permissions:
            bits.append("needs " + ", ".join(self.permissions))
        return " — ".join(bits)


def sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def manifest_path(py_file: Path) -> Path | None:
    """The manifest beside a plugin, or None. Both spellings are accepted
    because the `_template` convention of this repository is `stem.py` and a
    sidecar of the same stem is what an author tries first."""
    for candidate in (py_file.with_suffix(".plugin.json"),
                      py_file.with_suffix(".json")):
        if candidate.is_file():
            return candidate
    return None


def implied_permissions(py_file: Path) -> set[str]:
    """What the source actually does, as far as an import scan can tell."""
    try:
        tree = ast.parse(py_file.read_text(encoding="utf-8"))
    except Exception:
        # A file that will not parse is the loader's problem, not this one.
        return set()
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = {alias.name.split(".")[0] for alias in node.names}
        elif isinstance(node, ast.ImportFrom):
            names = {(node.module or "").split(".")[0]}
        else:
            if isinstance(node, ast.Call):
                target = _call_name(node.func)
                permission = _CALL_HINTS.get(target)
                if permission:
                    found.add(permission)
            continue
        for permission, modules in _IMPORT_HINTS.items():
            if names & modules:
                found.add(permission)
    return found


def _call_name(func) -> str:
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        parts = []
        node = func
        while isinstance(node, ast.Attribute):
            parts.append(node.attr)
            node = node.value
        if isinstance(node, ast.Name):
            parts.append(node.id)
            return ".".join(reversed(parts))
    return ""


def read(py_file: Path, plugin_name: str = "") -> Manifest | None:
    """The parsed manifest, or None when the plugin has none.

    None is not an error: every plugin in this repository predates manifests and
    must keep loading. It IS news for a plugin from outside — that distinction
    belongs to the caller (`verify`), not here.
    """
    path = manifest_path(py_file)
    if path is None:
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        return Manifest(name=plugin_name or py_file.stem,
                        problems=[f"manifest will not parse: {e}"])
    if not isinstance(raw, dict):
        return Manifest(name=plugin_name or py_file.stem,
                        problems=["manifest is not a JSON object"])

    name = str(raw.get("name") or "").strip()
    problems: list[str] = []
    if not name:
        problems.append("manifest has no name")
    elif plugin_name and name != plugin_name:
        # The name in the file and the name in PLUGIN decide which tool the
        # model calls. Two different answers is a plugin that cannot be
        # reasoned about, so it is a problem, not a warning.
        problems.append(
            f"manifest name {name!r} does not match PLUGIN['name'] {plugin_name!r}")

    declared = raw.get("permissions", [])
    if isinstance(declared, str):
        declared = [declared]
    if not isinstance(declared, list):
        problems.append("permissions must be a list")
        declared = []
    unknown = [p for p in declared if p not in PERMISSIONS]
    if unknown:
        problems.append(
            "unknown permission(s) " + ", ".join(sorted(map(str, unknown)))
            + " — the list a user can consent to is: " + ", ".join(sorted(PERMISSIONS)))

    return Manifest(
        name=name or plugin_name or py_file.stem,
        version=str(raw.get("version") or ""),
        author=str(raw.get("author") or ""),
        description=str(raw.get("description") or ""),
        permissions=tuple(str(p) for p in declared if p in PERMISSIONS),
        sha256=str(raw.get("sha256") or "").strip().lower(),
        homepage=str(raw.get("homepage") or ""),
        problems=problems,
    )


def verify(py_file: Path, plugin_name: str = "") -> Manifest | None:
    """Read the manifest and check it against the file it describes.

    Returns None when there is no manifest — the caller decides whether that is
    acceptable (this repository's own plugins: yes; anything from a marketplace:
    no).
    """
    manifest = read(py_file, plugin_name)
    if manifest is None:
        return None

    actual = sha256_of(py_file)
    if not manifest.sha256:
        manifest.warnings.append(
            "no sha256 in the manifest, so this file cannot be checked against "
            "the one that was published")
    elif manifest.sha256 != actual:
        manifest.problems.append(
            "sha256 does not match the manifest — the file changed after it was "
            f"published (manifest {manifest.sha256[:12]}…, file {actual[:12]}…)")

    implied = implied_permissions(py_file)
    undeclared = implied - set(manifest.permissions)
    if undeclared:
        manifest.problems.append(
            "uses " + ", ".join(sorted(undeclared)) + " without declaring "
            + ("it" if len(undeclared) == 1 else "them")
            + " — the user consented to: "
            + (", ".join(manifest.permissions) or "nothing"))
    extra = set(manifest.permissions) - implied
    if extra:
        # Not a problem: static analysis misses things (a helper module, a
        # getattr), and a plugin that asks for more than it needs is honest
        # about it rather than hiding it.
        manifest.warnings.append(
            "declares " + ", ".join(sorted(extra)) + " that the scan did not see")
    return manifest


def describe(manifest: Manifest) -> str:
    """The sentences a confirmation dialog can show, weakest claims last."""
    lines = [manifest.summary()]
    for permission in manifest.permissions:
        lines.append(f"  • {permission}: {PERMISSIONS[permission]}")
    if manifest.warnings:
        lines += [f"  ! {w}" for w in manifest.warnings]
    lines.append("A manifest is a declaration, not a sandbox: a plugin runs "
                 "inside this app and can do what this app can do.")
    return "\n".join(lines)
