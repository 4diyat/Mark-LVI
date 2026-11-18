"""Editor contracts without real credentials, display, or network."""
import ast
from pathlib import Path

import pytest

from core.plugin_loader import discover_plugins
from core.plugin_manifest import verify as verify_manifest
from plugins import _creative, code_editor

ROOT = Path(__file__).resolve().parents[1]


class Player:
    def __init__(self):
        self.jobs = []
    def show_code_job(self, job):
        self.jobs.append(job)


def test_editor_only_opens_the_desktop_and_does_not_run(monkeypatch):
    monkeypatch.setattr(_creative, "run_code", lambda *_: pytest.fail("unexpected execution"))
    player = Player()
    assert "Opening" in code_editor.run({"code": "print('hi')", "path": "/tmp/no.py"}, player)
    assert player.jobs[-1] == {"kind": "creative_workspace", "tab": "editor", "code": "print('hi')"}
    assert "desktop" in code_editor.run({}, None)


def test_plugin_manifests_and_default_consent(isolated_config):
    for name, permissions in (("code_editor", {"files", "shell"}),):
        path = ROOT / "plugins" / f"{name}.py"
        result = verify_manifest(path)
        assert result.ok, result.problems
        assert set(result.permissions) == permissions
    registry = discover_plugins(ROOT / "plugins", set(), lambda _: None)
    items = {row["name"]: row for row in registry.list_for_ui()}
    assert items["code_editor"]["valid"] and not items["code_editor"]["enabled"]
    assert "image_canvas" not in items


def test_open_save_and_execute_python_file(tmp_path):
    path = tmp_path / "demo.py"
    _creative.write_code(str(path), 'print("hello editor")\n')
    assert _creative.read_code(str(path)) == 'print("hello editor")\n'
    rc, output = _creative.run_code(str(path))
    assert rc == 0 and output.splitlines() == ["hello editor"]


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


def test_workspace_guards_each_capability_and_wires_codejob_on_qt_thread():
    path = ROOT / "ui" / "creative.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "CreativeWorkspace")
    for name, permission in (("_run_file", "code_editor"), ("_save_file", "code_editor"),
                             ("_open_file", "code_editor")):
        method = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == name)
        assert f"self._require('{permission}')" in ast.unparse(method)
    assert "QMessageBox.question" in ast.unparse(cls)
    window = (ROOT / "ui" / "window.py").read_text(encoding="utf-8")
    assert '"creative_workspace", "trading_terminal"' in window
    assert 'self._codejob_sig.connect(self._show_code_job)' in window


def test_removed_ai_canvas_has_no_plugin_or_workspace_target():
    from core.workspace_control import validate
    assert not (ROOT / 'plugins/image_canvas.py').exists()
    assert not (ROOT / 'plugins/image_canvas.json').exists()
    assert not hasattr(_creative, 'generate_image')
    with pytest.raises(ValueError):
        validate({'action': 'open', 'target': 'ai_image'})
