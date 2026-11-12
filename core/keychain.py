"""core/keychain.py — where the API key lives when the OS will hold it.

WHY THIS EXISTS
    Every credential this app owns is a line in config/api_keys.json: the Gemini
    key, the dashboard's TLS key password, the OAuth tokens the Google plugins
    write, and the WhatsApp session next to them. The file is chmod 0600 and it
    is in .gitignore, and that is the right answer for a project that must run
    on a machine with no desktop keyring.

    It is the wrong answer for the one secret that is actually a key. A file is
    readable by anything running as the user — a plugin, a build script, a
    screenshot of a `cat` — and it survives in backups that people share. Every
    desktop OS has shipped a place for exactly this for fifteen years: Keychain
    on macOS, Credential Manager on Windows, Secret Service (GNOME Keyring, KWallet)
    on Linux. `keyring` is the library that speaks all three.

WHY THE FILE IS STILL THE FALLBACK, AND NOT A LESSER ONE
    keyring needs a desktop session. A headless Linux server (which is where the
    dashboard runs), a WSL box, a container, a lock screen that has not been
    unlocked yet since boot: all of them raise on the first call. Making the
    app refuse to start there would trade a small risk for a broken install.

    So: try the keychain, fall back to the file, and SAY WHICH ONE IS IN USE —
    in the settings panel, from `describe()`. A user who believes their key is
    in the Keychain when it is in a file has been told something false by the
    application, which is the failure mode this whole project keeps fixing.

WHAT THIS MODULE DOES NOT DO
    It does not migrate every credential. Plugin tokens (Gmail, Calendar,
    WhatsApp) are written by code in `plugins/` that has its own idea of where
    files go, and a key is the one secret worth a migration path. `migrate()`
    moves the Gemini key and leaves the rest alone, deliberately: a half-moved
    credential set is harder to reason about than an unmoved one.

THE TWO-WAY WRITE
    When the keychain works, the key is stored in BOTH places: the keychain is
    authoritative and the file copy is what a `keyring`-less environment (or a
    reinstall that forgot to install it) still reads. The file copy is what the
    old code wrote, so nothing breaks — and `config/api_keys.json` is 0600 and
    git-ignored, so the copy is exactly as safe as it was before this module.
"""
from __future__ import annotations

# WHY THIS IS NOT CALLED secrets.py
#     It was, for one push. `core/` is on sys.path in several places (the
#     suite adds it, and a frozen build flattens it), so `import secrets`
#     resolved to this file instead of the standard library's, and
#     `from secrets import randbits` inside `uuid`/`random`/`keyring` raised
#     ImportError on every runner. The name of a module is part of its
#     interface; this one now says what it is.

# The service name is what the user sees in Keychain Access / seahorse. Keeping
# it stable matters: changing it orphans every key already stored.
SERVICE = "MARK-LVI"
ACCOUNT = "gemini_api_key"

# Set by keychain_status() so a failure is explained once, not on every read.
_last_error: str | None = None


def _keyring():
    """The real `keyring` module, or None. Imported late and on purpose: it is
    an OPTIONAL dependency, and this module is imported by the path that every
    startup takes."""
    try:
        import keyring  # noqa: PLC0415 — optional, and costly to import
        return keyring
    except Exception:
        return None


def keychain_status() -> tuple[bool, str]:
    """(usable, why not). Cheap enough to call from a settings panel.

    A backend that exists but cannot work is the common case on Linux, and the
    exception it raises on get_password() is the only reliable way to tell:
    `keyring.get_keyring()` happily returns a chain whose every member will
    fail. So the probe is an actual read of a secret that does not exist.
    """
    global _last_error
    kr = _keyring()
    if kr is None:
        return False, "the `keyring` package is not installed"
    try:
        kr.get_password(SERVICE, "__probe__")
    except Exception as e:
        _last_error = f"{type(e).__name__}: {e}"
        return False, _last_error
    return True, ""


def available() -> bool:
    return keychain_status()[0]


def get_secret(account: str = ACCOUNT) -> str | None:
    """The stored secret, or None. Never raises: this is read during startup
    and during every session connect, and neither can afford an exception from
    a keyring that broke because the user locked their screen."""
    ok, _why = keychain_status()
    if not ok:
        return None
    try:
        return _keyring().get_password(SERVICE, account) or None
    except Exception as e:
        global _last_error
        _last_error = f"{type(e).__name__}: {e}"
        return None


def set_secret(value: str, account: str = ACCOUNT) -> bool:
    """Store `value` in the OS keychain. False means "not stored", and the
    caller is expected to have written its file copy already.

    An empty value does not delete: deleting a key because a form was submitted
    empty is how a user loses their key while editing an unrelated field. Use
    `delete_secret()` for that.
    """
    value = (value or "").strip()
    if not value:
        return False
    ok, _why = keychain_status()
    if not ok:
        return False
    try:
        _keyring().set_password(SERVICE, account, value)
        return True
    except Exception as e:
        global _last_error
        _last_error = f"{type(e).__name__}: {e}"
        return False


def delete_secret(account: str = ACCOUNT) -> bool:
    if not available():
        return False
    try:
        _keyring().delete_password(SERVICE, account)
        return True
    except Exception:
        # Nothing stored, or a backend that refuses deletes. Neither is worth
        # a message: the caller asked for the secret to not be there.
        return False


def describe() -> str:
    """One sentence for a person: where the key is, in the state it is in.

    Reads the secret rather than the backend, because the question a user is
    really asking is "is my key in there?" — and the answer must be about the
    key, not about the library.
    """
    ok, why = keychain_status()
    if not ok:
        return f"Your API key is in config/api_keys.json (0600). {why}."
    if get_secret():
        return ("Your API key is in this system's keychain, and a copy is in "
                "config/api_keys.json (0600) for a start without a desktop "
                "session.")
    return ("The keychain is available but holds no key yet; the key in "
            "config/api_keys.json will move there the next time it is saved.")
