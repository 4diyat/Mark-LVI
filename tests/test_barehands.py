"""The optional Barehands bridge uses only the local server and real ring states."""
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from plugins import _barehands, barehands


@pytest.fixture
def bridge(tmp_path, monkeypatch):
    (tmp_path / "server.py").touch()
    (tmp_path / "stage.html").touch()
    (tmp_path / "state").mkdir()
    seen = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            seen.append((self.path, json.loads(self.rfile.read(int(self.headers["Content-Length"])))))
            self.send_response(204)
            self.end_headers()

        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(json.dumps({"items": [{"type": "card", "title": "Test", "x": 0}]}).encode())

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    (tmp_path / "barehands.json").write_text(json.dumps({"port": server.server_port}))
    monkeypatch.setattr("memory.config_manager.get_plugin_config", lambda _: {"enabled": True, "directory": str(tmp_path)})
    yield tmp_path, seen
    server.shutdown()
    server.server_close()
    thread.join()


def test_board_command_and_last_heartbeat(bridge):
    _, seen = bridge
    answer = barehands.run({"action": "add_card", "title": "Hello", "body": "World", "x": 0})
    assert "queued" in answer and "only if" in answer
    assert seen == [("/cmd", {"a": "add_card", "title": "Hello", "body": "World", "x": 0})]
    answer = barehands.run({"action": "look"})
    assert "may be stale" in answer and '"x": 0' in answer and "Test" in answer


@pytest.mark.parametrize("src", ["../secret", "/etc/passwd", "C:\\secret", "C:/secret", "sub/../../secret"])
def test_media_cannot_escape_airlock(bridge, src):
    _, seen = bridge
    assert "relative path" in barehands.run({"action": "add_img", "src": src})
    assert not seen


def test_disabled_and_invalid_actions_do_not_send(bridge, monkeypatch):
    _, seen = bridge
    assert "Unsupported" in barehands.run({"action": "reset"})
    monkeypatch.setattr("memory.config_manager.get_plugin_config", lambda _: {})
    assert "disabled" in barehands.run({"action": "look"})
    assert not seen


def test_actual_ring_states_are_written_only_when_enabled(bridge, monkeypatch):
    root, _ = bridge
    _barehands._write_state(_barehands._STATES["THINKING"])
    assert (root / "state" / "state").read_text() == "thinking"
    _barehands._write_state(_barehands._STATES["NO MIC"])
    assert (root / "state" / "state").read_text() == "idle"
    monkeypatch.setattr("memory.config_manager.get_plugin_config", lambda _: {})
    with pytest.raises(ValueError, match="disabled"):
        _barehands._write_state("speaking")
    assert (root / "state" / "state").read_text() == "idle"
