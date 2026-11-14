"""Editor/canvas contracts without real credentials, display, or network."""
import ast
from pathlib import Path
from types import SimpleNamespace

import pytest

from core.plugin_loader import discover_plugins
from core.plugin_manifest import verify as verify_manifest
from plugins import _creative, code_editor, image_canvas

ROOT = Path(__file__).resolve().parents[1]


class Player:
    def __init__(self):
        self.jobs = []
    def show_code_job(self, job):
        self.jobs.append(job)


def test_plugins_only_open_the_desktop_and_do_not_run_or_generate(monkeypatch):
    monkeypatch.setattr(_creative, "run_code", lambda *_: pytest.fail("unexpected execution"))
    monkeypatch.setattr(_creative, "generate_image", lambda *_: pytest.fail("unexpected generation"))
    player = Player()
    assert "Opening" in code_editor.run({"code": "print('hi')", "path": "/tmp/no.py"}, player)
    assert player.jobs[-1] == {"kind": "creative_workspace", "tab": "editor", "code": "print('hi')"}
    assert "Opening" in image_canvas.run({"prompt": "an orange cat"}, player)
    assert player.jobs[-1] == {"kind": "creative_workspace", "tab": "canvas", "prompt": "an orange cat"}
    assert "desktop" in code_editor.run({}, None)
    assert "desktop" in image_canvas.run({}, None)


def test_plugin_manifests_and_default_consent(isolated_config):
    for name, permissions in (("code_editor", {"files", "shell"}),
                              ("image_canvas", {"files", "network"})):
        path = ROOT / "plugins" / f"{name}.py"
        result = verify_manifest(path)
        assert result.ok, result.problems
        assert set(result.permissions) == permissions
    registry = discover_plugins(ROOT / "plugins", set(), lambda _: None)
    items = {row["name"]: row for row in registry.list_for_ui()}
    assert items["code_editor"]["valid"] and not items["code_editor"]["enabled"]
    assert items["image_canvas"]["valid"] and not items["image_canvas"]["enabled"]


def test_open_save_and_execute_python_file(tmp_path):
    path = tmp_path / "demo.py"
    _creative.write_code(str(path), 'print("hello editor")\n')
    assert _creative.read_code(str(path)) == 'print("hello editor")\n'
    rc, output = _creative.run_code(str(path))
    assert rc == 0 and output == "hello editor\n"


def test_execution_failure_timeout_and_output_bound(tmp_path):
    path = tmp_path / "demo.py"
    path.write_text('import sys; print("problem", file=sys.stderr); sys.exit(3)', encoding="utf-8")
    rc, output = _creative.run_code(str(path))
    assert rc == 3 and "problem" in output
    path.write_text('import time; time.sleep(10)', encoding="utf-8")
    rc, output = _creative.run_code(str(path), timeout=0.1)
    assert rc is None and "Timed out" in output
    path.write_text('print("x" * 200000)', encoding="utf-8")
    rc, output = _creative.run_code(str(path))
    assert rc == 0 and "Output truncated" in output
    assert len(output) < _creative.MAX_OUTPUT_BYTES + 100


def test_editor_refuses_unsupported_types_and_oversized_files(tmp_path):
    with pytest.raises(ValueError):
        _creative.write_code(str(tmp_path / "big.py"), "x" * (_creative.MAX_CODE_BYTES + 1))
    path = tmp_path / "bad.txt"
    path.write_text("not executable", encoding="utf-8")
    with pytest.raises(ValueError, match="Only Python and JavaScript"):
        _creative.run_code(str(path))
    path.write_bytes(b"x" * (_creative.MAX_CODE_BYTES + 1))
    with pytest.raises(ValueError):
        _creative.read_code(str(path))


def test_generate_image_uses_configured_key_model_and_extracts_response():
    calls = []
    part = SimpleNamespace(inline_data=SimpleNamespace(data=b"image bytes", mime_type="image/png"))
    response = SimpleNamespace(candidates=[SimpleNamespace(content=SimpleNamespace(parts=[part]))])
    class Client:
        def __init__(self, **kwargs):
            calls.append(kwargs)
            self.models = self
        def generate_content(self, **kwargs):
            calls.append(kwargs)
            return response
    image, mime = _creative.generate_image("orange cat", "test-key", client_factory=Client)
    assert (image, mime) == (b"image bytes", "image/png")
    assert calls[0]["api_key"] == "test-key"
    assert calls[1]["model"] == "gemini-2.5-flash-image"
    assert calls[1]["contents"] == "orange cat"
    assert "IMAGE" in calls[1]["config"]["response_modalities"]


def test_generate_image_errors_are_explicit():
    with pytest.raises(ValueError, match="API key"):
        _creative.generate_image("cat", "")
    with pytest.raises(ValueError, match="prompt"):
        _creative.generate_image("", "key")
    class Client:
        def __init__(self, **_):
            self.models = self
        def generate_content(self, **_):
            return SimpleNamespace(candidates=[])
    with pytest.raises(ValueError, match="did not return an image"):
        _creative.generate_image("cat", "key", client_factory=Client)


def test_workspace_guards_each_capability_and_wires_codejob_on_qt_thread():
    path = ROOT / "ui" / "creative.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "CreativeWorkspace")
    for name, permission in (("_run_file", "code_editor"), ("_save_file", "code_editor"),
                             ("_open_file", "code_editor"), ("_generate", "image_canvas"),
                             ("_save_image", "image_canvas")):
        method = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == name)
        assert f"self._require('{permission}')" in ast.unparse(method)
    assert "QMessageBox.question" in ast.unparse(cls)
    window = (ROOT / "ui" / "window.py").read_text(encoding="utf-8")
    assert '"creative_workspace", "trading_terminal"' in window
    assert 'self._codejob_sig.connect(self._show_code_job)' in window
