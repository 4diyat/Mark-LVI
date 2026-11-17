"""SSH plugin and backend safety with fake transport; no server or keys needed."""
import sys
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from core.plugin_manifest import verify
from core.ssh_session import MAX_OUTPUT, SSHSession, UnknownHostKey, validate_command, validate_connection
from plugins import ssh_manager


def test_plugin_opens_panel_but_never_forwards_commands_or_passwords():
    jobs = []
    result = ssh_manager.run({'command': 'danger', 'password': 'secret'}, SimpleNamespace(show_code_job=jobs.append))
    assert jobs == [{'kind': 'ssh_manager'}] and 'danger' not in result and 'secret' not in result
    assert verify(Path(ssh_manager.__file__), 'ssh_manager').ok


@pytest.mark.parametrize('host,port,user', [('', 22, 'a'), ('evil host', 22, 'a'), ('-host', 22, 'a'),
    ('host', 0, 'a'), ('host', 65536, 'a'), ('host', True, 'a'), ('host', 22, 'a\nb')])
def test_bad_connection_parameters(host, port, user):
    with pytest.raises(ValueError): validate_connection(host, port, user)


@pytest.mark.parametrize('command', ['', 'x\ny', 'x\x1b', 'x'*4097])
def test_invalid_commands(command):
    with pytest.raises(ValueError): validate_command(command)


class FakeClient:
    def __init__(self, unknown=False):
        self.unknown, self.closed, self.loaded = unknown, False, False
    def load_system_host_keys(self): self.loaded = True
    def set_missing_host_key_policy(self, policy): self.policy = policy
    def connect(self, **kwargs):
        assert self.loaded
        self.kwargs = kwargs
        if self.unknown: self.policy.missing_host_key(self, kwargs['hostname'], object())
    def close(self): self.closed = True


def test_known_hosts_enforced_and_auth_modes_separated(monkeypatch):
    monkeypatch.setitem(sys.modules, 'paramiko', SimpleNamespace(MissingHostKeyPolicy=object))
    client = FakeClient(unknown=True)
    session = SSHSession(lambda: client)
    with pytest.raises(UnknownHostKey): session.connect('host', 22, 'user', 'password', 'secret')
    assert client.closed
    client = FakeClient()
    session = SSHSession(lambda: client)
    assert session.connect('host', 22, 'user', 'password', 'secret')
    assert not client.kwargs['allow_agent'] and not client.kwargs['look_for_keys']
    assert client.kwargs['password'] == 'secret' and 'key_filename' not in client.kwargs
    session.close()
    client = FakeClient()
    session = SSHSession(lambda: client)
    assert session.connect('host', 22, 'user', 'key', 'passphrase', '/key')
    assert client.kwargs['allow_agent'] and client.kwargs['key_filename'] == '/key'
    assert client.kwargs['passphrase'] == 'passphrase' and 'password' not in client.kwargs
    session.close()


class Channel:
    def __init__(self, data): self.data, self.closed = data, False
    def settimeout(self, value): pass
    def exec_command(self, value): self.command = value
    def recv_ready(self): return bool(self.data)
    def recv_stderr_ready(self): return False
    def recv(self, amount): chunk, self.data = self.data[:amount], self.data[amount:]; return chunk
    def recv_stderr(self, amount): return b''
    def exit_status_ready(self): return True
    def recv_exit_status(self): return 0
    def close(self): self.closed = True


def test_command_output_is_bounded_and_channel_closed():
    channel = Channel(b'x' * (MAX_OUTPUT + 1))
    transport = SimpleNamespace(is_active=lambda: True, open_session=lambda timeout: channel)
    session = SSHSession()
    session._client = SimpleNamespace(get_transport=lambda: transport, close=lambda: None)
    data, code, state = session.execute('echo hello')
    assert len(data) == MAX_OUTPUT and code is None and state == 'truncated' and channel.closed


def test_close_never_waits_for_transport_on_ui_thread():
    ready, release = threading.Event(), threading.Event()
    class Slow:
        def close(self): ready.set(); release.wait(2)
    session = SSHSession()
    session._client = Slow()
    session.request_close()
    assert ready.wait(1) and session._cancelled.is_set()
    release.set()
