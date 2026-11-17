"""Real Paramiko protocol over a local socketpair, never a network server."""
import socket
import threading

import pytest

paramiko = pytest.importorskip('paramiko')

from core.ssh_session import SSHSession, UnknownHostKey  # noqa: E402


class Server(paramiko.ServerInterface):
    def __init__(self):
        self.command = None
        self.received = threading.Event()

    def check_auth_password(self, username, password):
        return (paramiko.AUTH_SUCCESSFUL if (username, password) == ('alice', 'secret')
                else paramiko.AUTH_FAILED)

    def get_allowed_auths(self, username):
        return 'password'

    def check_channel_request(self, kind, chanid):
        return paramiko.OPEN_SUCCEEDED if kind == 'session' else paramiko.OPEN_FAILED_ADMINISTRATIVELY_PROHIBITED

    def check_channel_exec_request(self, channel, command):
        self.command = command
        self.received.set()
        return True


def exercise(known):
    host_key = paramiko.RSAKey.generate(2048)
    client_sock, server_sock = socket.socketpair()
    server = Server()
    transport = paramiko.Transport(server_sock)
    transport.add_server_key(host_key)
    errors = []

    def serve():
        try:
            transport.start_server(server=server)
            channel = transport.accept(5)
            if channel is not None and server.received.wait(5):
                channel.sendall(b'hello from test')
                channel.send_exit_status(0)
                channel.close()
        except (EOFError, OSError, paramiko.SSHException) as exc:
            errors.append(exc)

    worker = threading.Thread(target=serve, daemon=True)
    worker.start()

    class Client(paramiko.SSHClient):
        def load_system_host_keys(self):
            if known:
                self.get_host_keys().add('example.test', host_key.get_name(), host_key)
        def connect(self, **kwargs):
            super().connect(sock=client_sock, **kwargs)

    session = SSHSession(Client)
    try:
        if known:
            assert session.connect('example.test', 22, 'alice', 'password', 'secret')
            output, status, state = session.execute('echo hello')
            assert (output, status, state) == (b'hello from test', 0, 'finished')
            assert server.command == b'echo hello'
        else:
            with pytest.raises(UnknownHostKey):
                session.connect('example.test', 22, 'alice', 'password', 'secret')
            assert server.command is None
    finally:
        session.close()
        transport.close()
        client_sock.close()
        server_sock.close()
        worker.join(6)
    assert not worker.is_alive()
    if known:
        assert not errors


def test_known_key_and_manual_command_over_real_protocol():
    exercise(True)


def test_unknown_key_is_rejected_over_real_protocol():
    exercise(False)
