"""Manual SSH execution with strict known-host verification and bounded output."""
import ipaddress
import re
import threading
import time

MAX_OUTPUT = 65536


class UnknownHostKey(Exception):
    pass


def validate_connection(host, port, user):
    if not isinstance(host, str) or not isinstance(user, str):
        raise ValueError('Invalid connection')
    host, user = host.strip(), user.strip()
    if not host or len(host) > 253 or not re.fullmatch(r'[A-Za-z0-9_.@-]{1,128}', user):
        raise ValueError('Invalid connection')
    try:
        ipaddress.ip_address(host)
    except ValueError:
        try:
            name = host.encode('idna').decode('ascii')
        except UnicodeError:
            raise ValueError('Invalid host') from None
        if not all(re.fullmatch(r'[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?', p)
                   for p in name.rstrip('.').split('.')):
            raise ValueError('Invalid host') from None
    if isinstance(port, bool):
        raise ValueError('Invalid port')
    try:
        port = int(port)
    except (TypeError, ValueError):
        raise ValueError('Invalid port') from None
    if not 1 <= port <= 65535:
        raise ValueError('Invalid port')
    return host, port, user


def validate_command(command):
    if (not isinstance(command, str) or not command.strip() or len(command) > 4096
            or any(ord(c) < 32 or ord(c) == 127 for c in command)):
        raise ValueError('Invalid command')
    return command


class SSHSession:
    def __init__(self, client_factory=None):
        self._factory = client_factory
        self._client = None
        self._lock = threading.Lock()
        self._cancelled = threading.Event()

    def connect(self, host, port, user, method, secret='', key_file=''):
        host, port, user = validate_connection(host, port, user)
        if method not in ('key', 'password') or (method == 'password' and not secret):
            raise ValueError('Invalid credentials')
        import paramiko
        class RejectUnknown(paramiko.MissingHostKeyPolicy):
            def missing_host_key(self, client, hostname, key):
                raise UnknownHostKey()
        client = self._factory() if self._factory else paramiko.SSHClient()
        with self._lock:
            if self._cancelled.is_set():
                client.close()
                return False
            self._client = client
        try:
            client.load_system_host_keys()
            client.set_missing_host_key_policy(RejectUnknown())
            kwargs = dict(hostname=host, port=port, username=user, timeout=10, banner_timeout=10,
                          auth_timeout=10, allow_agent=method == 'key', look_for_keys=method == 'key')
            if method == 'password':
                kwargs['password'] = secret
            else:
                if key_file: kwargs['key_filename'] = key_file
                if secret: kwargs['passphrase'] = secret
            client.connect(**kwargs)
            if self._cancelled.is_set():
                client.close()
                return False
            return True
        except Exception:
            client.close()
            with self._lock:
                if self._client is client: self._client = None
            raise

    def execute(self, command):
        command = validate_command(command)
        with self._lock: client = self._client
        if self._cancelled.is_set() or client is None:
            raise RuntimeError('Not connected')
        transport = client.get_transport()
        if transport is None or not transport.is_active():
            raise RuntimeError('Not connected')
        channel = transport.open_session(timeout=10)
        output, deadline = bytearray(), time.monotonic() + 30
        try:
            channel.settimeout(10)
            channel.exec_command(command)
            while True:
                for ready, recv in ((channel.recv_ready, channel.recv), (channel.recv_stderr_ready, channel.recv_stderr)):
                    while ready():
                        chunk = recv(min(4096, MAX_OUTPUT + 1 - len(output)))
                        if not chunk: break
                        output.extend(chunk)
                        if len(output) > MAX_OUTPUT:
                            return bytes(output[:MAX_OUTPUT]), None, 'truncated'
                if self._cancelled.is_set(): return bytes(output), None, 'cancelled'
                if channel.exit_status_ready() and not channel.recv_ready() and not channel.recv_stderr_ready():
                    return bytes(output), channel.recv_exit_status(), 'finished'
                if time.monotonic() >= deadline: return bytes(output), None, 'timeout'
                self._cancelled.wait(.02)
        finally:
            channel.close()

    def close(self):
        self._cancelled.set()
        with self._lock:
            client, self._client = self._client, None
        if client is not None: client.close()

    def request_close(self):
        self._cancelled.set()
        threading.Thread(target=self.close, daemon=True, name='ssh-close').start()
