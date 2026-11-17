"""Browser URLs and encrypted local vault, without real network or keychain."""
from pathlib import Path
from types import SimpleNamespace

import pytest

from core.browser_url import https_origin, validate_browser_url
from core.browser_vault import BrowserVault, VaultError
from core.plugin_manifest import verify
from plugins import workspace_browser


class Keyring:
    def __init__(self):
        self.values = {}
    def get_password(self, service, account):
        return self.values.get((service, account))
    def set_password(self, service, account, value):
        self.values[service, account] = value


@pytest.mark.parametrize('value', ['file:///etc/passwd', 'javascript:alert(1)', 'https://a:b@example.com',
                                   'https://a.example:99999', 'https://example.com/\nother', 'https://bad host/'])
def test_bad_urls_rejected(value):
    with pytest.raises(ValueError):
        validate_browser_url(value)


def test_exact_origin_and_credentials_encrypted(tmp_path):
    assert https_origin('https://EXAMPLE.com:443/a') == 'https://example.com'
    assert https_origin('https://[::1]:8443') == 'https://[::1]:8443'
    ring = Keyring()
    vault = BrowserVault(tmp_path / 'vault.db', lambda: ring)
    vault.save('https://example.com', 'alice', 'my-very-secret-password')
    assert vault.get('https://example.com', 'alice') == 'my-very-secret-password'
    assert vault.get('https://example.com:8443', 'alice') is None
    assert vault.list_usernames('https://evil.example.com') == []
    raw = vault.path.read_bytes()
    assert b'example.com' not in raw and b'alice' not in raw and b'my-very-secret-password' not in raw
    assert vault.delete('https://example.com', 'alice')
    assert not vault.list_usernames('https://example.com')
    with pytest.raises(ValueError):
        vault.save('http://example.com', 'alice', 'secret')


def test_missing_key_or_locked_keyring_fails_closed(tmp_path):
    ring = Keyring()
    vault = BrowserVault(tmp_path / 'vault.db', lambda: ring)
    vault.save('https://example.com', 'alice', 'secret')
    ring.values.clear()
    with pytest.raises(VaultError):
        vault.save('https://example.com', 'bob', 'secret2')
    assert not ring.values
    class Locked:
        def get_password(self, *_):
            raise RuntimeError('locked')
    other = BrowserVault(tmp_path / 'other.db', Locked)
    with pytest.raises(VaultError):
        other.save('https://example.com', 'bob', 'secret2')
    assert not other.path.exists()


def test_plugin_only_requests_page_not_vault():
    jobs = []
    result = workspace_browser.run({'url': 'https://example.com'}, SimpleNamespace(show_code_job=jobs.append))
    assert 'Requested' in result and jobs == [{'kind': 'workspace_browser', 'url': 'https://example.com'}]
    assert 'valid' in workspace_browser.run({'url': 'file:///secret'}, SimpleNamespace(show_code_job=jobs.append))
    assert len(jobs) == 1
    assert verify(Path(workspace_browser.__file__), 'workspace_browser').ok
