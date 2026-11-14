"""Package initialization order and readiness without importing heavy runtime."""
import importlib.util
import sys
import threading
import types

from core import wake_word


def test_readiness_uses_files_without_importing_package(tmp_path, monkeypatch):
    model_dir = tmp_path / "resources" / "models"
    model_dir.mkdir(parents=True)
    for name in ("hey_jarvis_v0.1.onnx", "melspectrogram.onnx", "embedding_model.onnx"):
        (model_dir / name).touch()
    spec = types.SimpleNamespace(submodule_search_locations=[str(tmp_path)])
    monkeypatch.setattr(importlib.util, "find_spec", lambda name: spec)
    monkeypatch.setattr(wake_word.importlib, "import_module", lambda name: (_ for _ in ()).throw(AssertionError(name)))
    assert wake_word.is_ready()
    (model_dir / "embedding_model.onnx").unlink()
    (model_dir / "embedding_model.tflite").touch()
    assert not wake_word.is_ready()


def test_start_initializes_package_before_submodule_and_is_idempotent(monkeypatch):
    imports, created = [], []
    package = types.SimpleNamespace(initialized=False)
    class Model:
        def __init__(self, **kwargs):
            assert package.initialized
            created.append(kwargs)
    def importer(name):
        imports.append(name)
        if name == "openwakeword":
            package.initialized = True
            return package
        assert name == "openwakeword.model" and package.initialized
        return types.SimpleNamespace(Model=Model)
    monkeypatch.setattr(wake_word.importlib, "import_module", importer)
    monkeypatch.setattr(wake_word.WakeWordDetector, "_loop", lambda self: None)
    detector = wake_word.WakeWordDetector(lambda: None, logger=lambda _: None)
    threads = [threading.Thread(target=detector.start) for _ in range(5)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert imports == ["openwakeword", "openwakeword.model"]
    assert created == [{"wakeword_models": ["hey_jarvis"], "inference_framework": "onnx"}]
    detector.stop()


def test_start_reports_failure_and_stays_unready(monkeypatch):
    def fail(name):
        raise AttributeError("partially initialized module")
    monkeypatch.setattr(wake_word.importlib, "import_module", fail)
    logs, notices = [], []
    detector = wake_word.WakeWordDetector(lambda: None, logger=logs.append, notify=notices.append)
    assert not detector.start() and not detector.ready
    assert "partially initialized" in logs[0]
    assert "disable wake word" in notices[0]


def test_package_and_submodule_import_order_is_safe(tmp_path, monkeypatch):
    # Mimic the real package's __init__, which imports its model before defining
    # the function the Model constructor later reads from the parent package.
    pkg = tmp_path / "openwakeword"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("from openwakeword.model import Model\ndef get_pretrained_model_paths(): return ['ready']\n")
    (pkg / "model.py").write_text("import openwakeword\nclass Model:\n def __init__(self, **kw):\n  assert openwakeword.get_pretrained_model_paths() == ['ready']\n")
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.delitem(sys.modules, "openwakeword", raising=False)
    monkeypatch.delitem(sys.modules, "openwakeword.model", raising=False)
    monkeypatch.setattr(wake_word.WakeWordDetector, "_loop", lambda self: None)
    detector = wake_word.WakeWordDetector(lambda: None, logger=lambda _: None)
    try:
        assert detector.start()
    finally:
        detector.stop()
        sys.modules.pop("openwakeword.model", None)
        sys.modules.pop("openwakeword", None)
