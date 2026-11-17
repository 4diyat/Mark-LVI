"""Encrypted SQLite browser logins. Never falls back to a file encryption key."""
import hashlib
import json
import os
import platform
import secrets
import sqlite3
import threading
from pathlib import Path

from cryptography.fernet import Fernet
from core.browser_url import https_origin

_LOCK = threading.RLock()
_SERVICE = 'MARK-LVI browser vault'


class VaultError(Exception):
    pass


def os_keyring():
    try:
        import keyring
        backend = keyring.get_keyring()
        allowed = {'Windows': 'keyring.backends.Windows', 'Darwin': 'keyring.backends.macOS',
                   'Linux': 'keyring.backends.SecretService'}
        if type(backend).__module__ != allowed.get(platform.system()):
            raise VaultError('OS keychain unavailable')
        return backend
    except Exception:
        raise VaultError('OS keychain unavailable') from None


class BrowserVault:
    def __init__(self, path=None, keyring_factory=None):
        if path is None:
            from memory.config_manager import BASE_DIR
            path = BASE_DIR / 'memory' / 'browser_vault.db'
        self.path = Path(path).resolve()
        self.account = 'sqlite-v1:' + hashlib.sha256(os.fsencode(str(self.path))).hexdigest()
        self._ring = keyring_factory or os_keyring

    def _run(self, operation, origin, username='', password=''):
        if https_origin(origin) != origin:
            raise ValueError('Exact HTTPS origin required')
        if operation != 'list' and (not isinstance(username, str) or not username or len(username) > 512):
            raise ValueError('Invalid username')
        if operation == 'save' and (not isinstance(password, str) or not password or len(password) > 4096):
            raise ValueError('Invalid password')
        with _LOCK:
            if operation != 'save' and not self.path.exists():
                return [] if operation == 'list' else None
            self.path.parent.mkdir(parents=True, exist_ok=True)
            lockfile = self.path.with_name(self.path.name + '.lock')
            try:
                fd = os.open(str(lockfile), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            except OSError:
                raise VaultError('Vault busy') from None
            try:
                os.close(fd)
                ring = self._ring()
                key = ring.get_password(_SERVICE, self.account)
                if not key:
                    if self.path.exists():
                        raise VaultError('Vault key missing')
                    if operation != 'save':
                        return [] if operation == 'list' else None
                    key = Fernet.generate_key().decode('ascii')
                    ring.set_password(_SERVICE, self.account, key)
                    if ring.get_password(_SERVICE, self.account) != key:
                        raise VaultError('Keychain write failed')
                cipher = Fernet(key.encode('ascii'))
                if not self.path.exists():
                    fd = os.open(str(self.path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                    os.close(fd)
                db = sqlite3.connect(str(self.path), timeout=5)
                try:
                    db.execute('CREATE TABLE IF NOT EXISTS credentials (id TEXT PRIMARY KEY, payload BLOB NOT NULL)')
                    db.execute('BEGIN IMMEDIATE')
                    rows = []
                    for rid, token in db.execute('SELECT id, payload FROM credentials LIMIT 1001'):
                        item = json.loads(cipher.decrypt(bytes(token)).decode('utf-8'))
                        if not isinstance(item, dict) or not all(isinstance(item.get(k), str) for k in ('origin', 'username', 'password')):
                            raise VaultError('Corrupt vault')
                        rows.append((rid, item))
                    if len(rows) > 1000:
                        raise VaultError('Vault full')
                    matches = [(rid, item) for rid, item in rows if item['origin'] == origin]
                    found = next(((rid, item) for rid, item in matches if item['username'] == username), None)
                    if operation == 'list':
                        return sorted(item['username'] for _, item in matches)
                    if operation == 'get':
                        return found[1]['password'] if found else None
                    if operation == 'delete':
                        if found:
                            db.execute('DELETE FROM credentials WHERE id=?', (found[0],))
                        db.commit()
                        return bool(found)
                    if len(rows) >= 1000 and not found:
                        raise VaultError('Vault full')
                    blob = json.dumps({'origin': origin, 'username': username, 'password': password}).encode()
                    db.execute('INSERT OR REPLACE INTO credentials VALUES (?, ?)',
                               (found[0] if found else secrets.token_hex(16), cipher.encrypt(blob)))
                    db.commit()
                    return True
                finally:
                    db.close()
            except (VaultError, ValueError):
                raise
            except Exception:
                raise VaultError('Vault unavailable or corrupt') from None
            finally:
                lockfile.unlink(missing_ok=True)

    def list_usernames(self, origin):
        return self._run('list', origin)

    def get(self, origin, username):
        return self._run('get', origin, username)

    def save(self, origin, username, password):
        return self._run('save', origin, username, password)

    def delete(self, origin, username):
        return self._run('delete', origin, username)
