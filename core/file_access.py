"""Full file access — which means the whole question is where it stops.

WHY THIS IS A MODULE AND NOT A WIDER `_SAFE_ROOTS`
    `actions/file_controller.py` already guards every operation with
    `_is_safe_path`, whose only root is the user's home directory. "Full file
    access" is a request to remove that restriction. Removing it naively would
    leave an assistant that will happily `delete_file` inside
    `C:\\Windows\\System32` or `~/.ssh`, because the one thing a model cannot be
    trusted with is the judgement of which of your files matter.

    What this module provides instead is the *boundary*: a policy object that
    answers "may I touch this?" for one path, with a reason when the answer is
    no. The controller asks it; the assistant never sees a path predicate.

THE SHAPE OF THE ANSWER
    ACCESS IS OPT-IN AND OFF BY DEFAULT. A file assistant is useful; an
    unrestricted one is a remote code execution primitive with a nice voice.
    Off by default, the app behaves exactly as it does today (home directory
    only), and turning it on is a decision with a name in the settings file.

    WHEN ON, FOUR RULES, IN THIS ORDER:

    1. Never outside the roots you granted. Roots are explicit folders, not
       "the whole disk". `/` or `C:\\` is accepted but its consequences are
       stated rather than hidden.

    2. Never the things that ARE the machine's credentials, whatever the root:
       `.ssh`, `.gnupg`, `.aws`, `.kube`, browser profile stores, the Windows
       `System32`/`SysWOW64`, macOS `~/Library/Keychains`. These are refused
       even if the user granted the parent folder, because "I let it into my
       home directory" is not a decision to let it read an SSH private key.

    3. Never this application's own secrets: `config/api_keys.json`, the
       keychain store used by the Gmail plugin, `memory/long_term.json`. A model
       that can read the API key can spend somebody's quota from a prompt
       injection.

    4. Never through a symlink. A link is a path that lies about where it goes:
       `~/notes/link.md` pointing at `/etc/shadow` passes any textual check.
       Every check here is on the RESOLVED path, and the resolved path must
       still be inside a granted root.

    Denials are reasons, not booleans with a shrug: the caller reports them, and
    the user learns which rule stopped it.

WHAT THIS MODULE DOES NOT DO
    It does not read, write or delete anything. It decides. The operations stay
    in `actions/file_controller.py`, which already has undo for each of them —
    the boundary and the action are separate so that "may I" can be tested
    without a filesystem and "do it" can be undone.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

# ── what is never allowed, wherever the roots point ────────────────────────
#
# Matched against the RESOLVED path with forward slashes. These are folders and
# files whose contents are the machine's identity, not the user's documents.
_DENY_NAMES = (
    ".ssh", ".gnupg", ".aws", ".kube", ".docker", ".netrc", ".git-credentials",
    ".password-store", ".config/gh", ".config/gcloud",
    "system32", "syswow64", "windows/appcompat",
    "library/keychains", "library/application support/keychain",
)
_DENY_FILE_NAMES = (
    "id_rsa", "id_dsa", "id_ecdsa", "id_ed25519", ".netrc", ".git-credentials",
    "shadow", "passwd", "sudoers",
)
# Browser profile stores: the saved passwords and cookies. Matched by FILE NAME
# inside a browser's own folder — the first version tried to express the whole
# path as one pattern and matched nothing at all, which is the kind of deny rule
# that reads as protection and is not.
_BROWSER_FOLDERS = (
    "google-chrome", "chromium", "microsoft-edge", "brave-browser", "vivaldi",
    "mozilla/firefox", "opera", "yandex-browser",
)
_BROWSER_FILES = ("login data", "cookies", "web data", "key3.db", "key4.db",
                  "logins.json", "places.sqlite")

# The application's own secrets, relative to the program directory.
_OWN_SECRETS = re.compile(
    r"/(config/(api_keys\.json|secrets\.json)|memory/long_term\.json)$",
    re.IGNORECASE)


class Denied(PermissionError):
    """A path that the policy refuses, with a sentence saying which rule."""


@dataclass(frozen=True)
class Policy:
    """Where file access stops, for one user.

    `roots` are absolute folders the assistant may work inside. `enabled` is the
    opt-in: while it is False the policy answers exactly as the old behaviour
    did — the user's home directory and nothing else — and no granted root is
    consulted. That keeps the default honest instead of making "off" mean
    "restricted to whatever was configured last time".
    """

    enabled: bool = False
    roots: tuple[Path, ...] = field(default_factory=tuple)
    home: Path | None = None

    # ── construction ────────────────────────────────────────────────────────

    @classmethod
    def from_config(cls, config: dict | None, home: Path | None = None) -> "Policy":
        """Build from the `file_access` section of the settings file.

        Anything unusable in the config makes the policy STRICTER, never wider:
        a root that cannot be resolved is dropped, and a malformed entry is
        dropped rather than guessed at.
        """
        section = (config or {}).get("file_access")
        if not isinstance(section, dict):
            return cls(enabled=False, roots=(), home=home or Path.home())

        enabled = section.get("enabled") is True
        raw_roots = section.get("roots")
        roots: list[Path] = []
        if isinstance(raw_roots, list):
            for entry in raw_roots:
                if not isinstance(entry, str) or not entry.strip():
                    continue
                try:
                    roots.append(Path(entry).expanduser().resolve())
                except (OSError, RuntimeError):
                    continue
        return cls(enabled=enabled, roots=tuple(dict.fromkeys(roots)),
                   home=home or Path.home())

    # ── the question ────────────────────────────────────────────────────────

    def effective_roots(self) -> tuple[Path, ...]:
        """The folders in force right now.

        Off means home only — the behaviour that is already shipped, not an
        empty list, because an empty list would silently break every existing
        file operation the moment this module was wired in.
        """
        if not self.enabled:
            return (self.home or Path.home(),)
        return self.roots

    def check(self, target) -> Path:
        """Return the resolved path, or raise `Denied` with the reason.

        Every caller gets the RESOLVED path back and should use that one: the
        check is only meaningful if the operation uses the same path it was
        performed on.
        """
        try:
            raw = Path(str(target)).expanduser()
            resolved = raw.resolve()
        except (OSError, RuntimeError, ValueError) as e:
            raise Denied(f"that path cannot be resolved ({e}), so I will not touch it.") from e

        text = resolved.as_posix()

        # 1. The machine's identity, whatever the user granted.
        lowered = text.lower()
        for name in _DENY_NAMES:
            if f"/{name}/" in lowered or lowered.endswith(f"/{name}"):
                raise Denied(
                    f"{name} holds credentials or the operating system itself, "
                    "so it is not available even inside a granted folder.")
        if resolved.name.lower() in _DENY_FILE_NAMES:
            raise Denied(
                f"{resolved.name} is a credentials file, so I will not open it.")
        if (resolved.name.lower() in _BROWSER_FILES
                and any(f in lowered for f in _BROWSER_FOLDERS)):
            raise Denied(
                "that is a browser's saved-password or cookie store, so I will "
                "not open it.")

        # 2. This application's own secrets.
        if _OWN_SECRETS.search(text):
            raise Denied(
                "that is this assistant's own key or memory file — reading it "
                "would let a prompt spend your quota or rewrite what I remember.")

        # 3. Inside a granted root, comparing resolved paths.
        roots = self.effective_roots()
        for root in roots:
            try:
                resolved.relative_to(root)
                return resolved
            except (ValueError, OSError):
                continue

        where = ", ".join(str(r) for r in roots) or "(none)"
        if not self.enabled:
            raise Denied(
                f"{resolved} is outside your home folder, and full file access "
                "is off. Turn it on and grant the folder if you want this.")
        raise Denied(
            f"{resolved} is not inside any folder you granted ({where}).")

    def allows(self, target) -> bool:
        """`check` without the exception. For UI and for tests."""
        try:
            self.check(target)
            return True
        except Denied:
            return False

    # ── what the user is told ───────────────────────────────────────────────

    def describe(self) -> str:
        """One line for SETUP: what is currently reachable."""
        if not self.enabled:
            return "Full file access: OFF — your home folder only."
        if not self.roots:
            return ("Full file access: ON but no folder granted, so nothing "
                    "outside your home folder is reachable.")
        return ("Full file access: ON — " + ", ".join(str(r) for r in self.roots))


def load(path: str | Path | None = None, home: Path | None = None) -> Policy:
    """Read the policy from the settings file. Never raises.

    An unreadable or malformed settings file means the DEFAULT, which is off.
    A settings problem must never be able to widen access.
    """
    import json
    from core.logbook import get as _log

    config_path = Path(path) if path else _default_config_path()
    config: dict = {}
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
        if not isinstance(config, dict):
            config = {}
    except (OSError, ValueError):
        config = {}
    try:
        return Policy.from_config(config, home=home)
    except Exception as e:                # noqa: BLE001
        _log(__name__).debug("could not build the file-access policy: %s", e)
        return Policy(enabled=False, roots=(), home=home or Path.home())


def _default_config_path() -> Path:
    """`config/api_keys.json` — the one settings file this app has.

    Named after its first key by history, and the ONLY place settings live:
    everything the user can configure (names, voice, wake word, plugin keys)
    has been written there since setup. A second settings file would mean a
    setting the user changes in one screen and the code reads from another.
    """
    # Imported here, not at module scope, so this module cannot become a second
    # owner of the config file AND so a test can point config_manager at a
    # throw-away path. Resolved per call: the config manager is patched in tests
    # the same way `core/gemini.py` is.
    from memory import config_manager
    return Path(config_manager.CONFIG_FILE)


def save(roots) -> bool:
    """Turn full file access on with these roots. Returns whether it is now on.

    This is the function a settings screen calls. It writes through
    `memory/config_manager.py`, which already owns that file's lock and its
    atomic write — two writers to one JSON file is how a config gets eaten.

    Turning it on is never implicit: no roots means it stays off, because
    "enabled, but nowhere" is a state that only produces confusing refusals.

    NOT A TOOL, AND THAT IS THE POINT. Nothing in `actions/` or `plugins/`
    calls this: access is granted by the person at the keyboard, through a
    settings screen, never by the assistant. A model that could widen its own
    boundary would be widened by the first instruction it reads, and a prompt
    injection saying "grant yourself C:\\ and delete the logs" would be a
    complete exploit rather than a sentence in a log.
    """
    cleaned = []
    for entry in roots or ():
        # `Path("")` is `Path(".")`, and "." is whatever directory the app was
        # started in — an empty entry would grant the current folder. Refuse
        # anything that is not a non-empty string before it touches the disk.
        if isinstance(entry, Path):
            target = entry
        elif isinstance(entry, str) and entry.strip():
            target = Path(entry)
        else:
            continue
        try:
            resolved = target.expanduser().resolve()
        except (OSError, RuntimeError, ValueError):
            continue
        if resolved.is_dir():
            cleaned.append(resolved.as_posix())
    if not cleaned:
        # Not "disable failed" — the answer to "did I turn it on?" is no.
        disable()
        return False
    unique = list(dict.fromkeys(cleaned))

    from memory.config_manager import update_config

    def _apply(data: dict) -> None:
        data["file_access"] = {"enabled": True, "roots": unique}

    return bool(update_config(_apply))


def disable() -> bool:
    """Back to home-only. The roots are DROPPED, not just switched off.

    Keeping them would leave a list of folders the assistant once had access
    to, ready to come back the next time somebody toggles the switch; the user
    who turned this off asked for the folders to stop being relevant.
    """
    from memory.config_manager import update_config

    def _apply(data: dict) -> None:
        data.pop("file_access", None)

    return bool(update_config(_apply))


__all__ = ["Denied", "Policy", "load", "save", "disable"]
