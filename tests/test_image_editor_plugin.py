"""A model can only propose an operation, never pick or write a file."""
from pathlib import Path
from types import SimpleNamespace

from core import plugin_manifest
from core.plugin_loader import discover_plugins
from plugins import image_editor

ROOT = Path(__file__).resolve().parent.parent


def test_editor_suggestion_is_only_a_draft():
    calls = []
    out = image_editor.run({"suggestion": "rotate", "path": "/outside/secret.png"},
                           SimpleNamespace(show_code_job=calls.append))
    assert "no file was changed" in out
    assert calls == [{"kind": "image_editor", "suggestion": "rotate"}]
    image_editor.run({"suggestion": "crop"}, SimpleNamespace(show_code_job=calls.append))
    assert calls[-1] == {"kind": "image_editor", "suggestion": "crop"}
    image_editor.run({"suggestion": "add_text", "text": "Example"}, SimpleNamespace(show_code_job=calls.append))
    assert calls[-1] == {"kind": "image_editor", "suggestion": "add_text", "text": "Example"}
    assert "no image was changed" in image_editor.run(
        {"suggestion": "add_text", "text": "a\nb"}, SimpleNamespace(show_code_job=calls.append))
    assert "no image was changed" in image_editor.run({"suggestion": "delete"}).lower()
    assert "desktop" in image_editor.run({}, None)


def test_image_plugin_requires_opt_in(isolated_config):
    manifest = plugin_manifest.verify(ROOT / "plugins/image_editor.py", "image_editor")
    assert manifest.ok and manifest.permissions == ("files",)
    registry = discover_plugins(ROOT / "plugins", set(), lambda _: None)
    row = next(r for r in registry.list_for_ui() if r["name"] == "image_editor")
    assert row["valid"] and not row["enabled"]
