"""Where the API key lives: the OS keychain when there is one, the file when not.

WHY THIS FILE IS MOSTLY ABOUT FAILURE
    `keyring` is a dependency that works on a developer's laptop and raises on
    a headless server, in a container, in WSL, and on a Linux desktop whose
    keyring has not been unlocked since boot. The dangerous version of this
    feature is the one that assumes the happy path: the app then either refuses
    to start where the CI runs, or writes a key to a store that silently drops
    it and reports success.

    So every test below is a machine where something is missing, and the
    assertion is always the same shape: the app keeps working, and it tells the
    truth about where the key is.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
for p in (str(ROOT), str(ROOT / "core")):
    if p not in sys.path:
        sys.path.insert(0, p)

from core import secrets  # noqa: E402


class FakeKeyring:
    """A keyring that behaves, including the parts that matter: an unknown
    secret is None, not an exception."""

    def __init__(self):
        self.store: dict[tuple[str, str], str] = {}
        self.fail_on: set[str] = set()

    def get_password(self, service, account):
        if "get" in self.fail_on:
            raise RuntimeError("org.freedesktop.Secret.Service is not available")
        return self.store.get((service, account))

    def set_password(self, service, account, value):
        if "set" in self.fail_on:
            raise RuntimeError("locked")
        self.store[(service, account)] = value

    def delete_password(self, service, account):
        if "delete" in self.fail_on:
            raise KeyError(account)
        self.store.pop((service, account), None)


@pytest.fixture()
def keyring(monkeypatch):
    fake = FakeKeyring()
    monkeypatch.setattr(secrets, "_keyring", lambda: fake)
    monkeypatch.setattr(secrets, "_last_error", None, raising=False)
    return fake


@pytest.fixture()
def no_keyring(monkeypatch):
    monkeypatch.setattr(secrets, "_keyring", lambda: None)
    monkeypatch.setattr(secrets, "_last_error", None, raising=False)


# ── the happy path ──────────────────────────────────────────────────────────

def test_a_secret_round_trips_through_the_keychain(keyring):
    assert secrets.set_secret("AIza-secret") is True
    assert secrets.get_secret() == "AIza-secret"


def test_the_service_name_is_stable(keyring):
    """Changing it orphans every key already stored, and the user's next start
    asks them for an API key they already gave."""
    secrets.set_secret("k")
    assert (secrets.SERVICE, secrets.ACCOUNT) in keyring.store


def test_an_unknown_secret_is_none_not_an_exception(keyring):
    assert secrets.get_secret() is None


def test_an_empty_value_is_not_written(keyring):
    """A submitted-empty field is a form the user is halfway through, not a
    decision to delete their key."""
    assert secrets.set_secret("") is False
    assert secrets.set_secret("   ") is False
    assert keyring.store == {}


def test_deleting_a_secret_that_is_not_there_is_not_an_error(keyring):
    """True means "the keychain no longer has it", which is true whether it was
    deleted or never there. The False case is a backend that refuses."""
    assert secrets.delete_secret() is True
    assert secrets.get_secret() is None

    keyring.fail_on.add("delete")
    assert secrets.delete_secret() is False


# ── the machines where there is no keyring ─────────────────────────────────

def test_without_the_package_everything_says_so_and_nothing_raises(no_keyring):
    ok, why = secrets.keychain_status()
    assert ok is False and "not installed" in why
    assert secrets.get_secret() is None
    assert secrets.set_secret("k") is False


def test_a_backend_that_raises_on_read_is_not_usable(keyring):
    """This is the Linux case: get_keyring() returns something, and that
    something fails on the first call. The probe has to be a real read."""
    keyring.fail_on.add("get")
    ok, why = secrets.keychain_status()
    assert ok is False
    assert "Secret.Service" in why          # the reason, not a generic failure


def test_a_failure_while_writing_returns_false_instead_of_raising(keyring):
    keyring.fail_on.add("set")
    assert secrets.set_secret("AIza") is False


def test_describe_tells_the_user_which_store_is_in_use(keyring):
    """A user who thinks their key is in the Keychain when it is in a file has
    been told something false by the application."""
    keyring.store[(secrets.SERVICE, secrets.ACCOUNT)] = "AIza-existing"
    assert "keychain" in secrets.describe()

    secrets.delete_secret()
    assert "no key yet" in secrets.describe()


def test_describe_explains_the_fallback_rather_than_hiding_it(no_keyring):
    text = secrets.describe()
    assert "api_keys.json" in text and "not installed" in text


# ── and what config_manager does with it ───────────────────────────────────

def test_saving_a_key_writes_both_places(isolated_config, keyring):
    isolated_config.save_api_keys("key-aaaaaaaaaaaaaaaa")
    assert keyring.store[(secrets.SERVICE, secrets.ACCOUNT)] == "key-aaaaaaaaaaaaaaaa"
    data = isolated_config.load_api_keys()
    assert data["gemini_api_key"] == "key-aaaaaaaaaaaaaaaa"
    assert data["gemini_api_key_source"] == "keychain"


def test_saving_a_key_without_a_keyring_still_writes_the_file(isolated_config, no_keyring):
    """The whole point of the fallback: a headless machine behaves exactly as
    it did before this feature existed."""
    isolated_config.save_api_keys("key-bbbbbbbbbbbbbbbbbb")
    assert isolated_config.get_gemini_key() == "key-bbbbbbbbbbbbbbbbbb"
    assert "gemini_api_key_source" not in isolated_config.load_api_keys()


def test_the_keychain_wins_over_the_file_when_they_disagree(isolated_config, keyring):
    """A rotated key is written to both, so a disagreement means the file was
    edited by hand — and the store that the app itself writes to is the one to
    trust."""
    isolated_config.save_api_keys("key-old-old-old-old-old")
    keyring.store[(secrets.SERVICE, secrets.ACCOUNT)] = "key-new-new-new-new-new"
    assert isolated_config.get_gemini_key() == "key-new-new-new-new-new"


def test_the_rest_of_the_config_is_untouched_by_a_key_save(isolated_config, keyring):
    isolated_config.save_assistant_config("JARVIS", "Fatih")
    isolated_config.save_ui_language("id")
    isolated_config.save_api_keys("key-cccccccccccccccccc")
    data = isolated_config.load_api_keys()
    assert data["user_name"] == "Fatih" and data["ui_language"] == "id"


def test_a_broken_keyring_does_not_stop_a_save(isolated_config, keyring):
    keyring.fail_on.update({"get", "set"})
    isolated_config.save_api_keys("key-dddddddddddddddddd")
    assert isolated_config.get_gemini_key() == "key-dddddddddddddddddd"
