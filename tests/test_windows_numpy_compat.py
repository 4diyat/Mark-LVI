"""The normal and fallback installers must not request conflicting wheels."""
from pathlib import Path
from unittest.mock import patch

from core import installer


def test_requirements_limit_numpy_and_opencv_on_windows_python_311_312():
    text = (Path(__file__).resolve().parents[1] / "requirements.txt").read_text(encoding="utf-8")
    assert 'numpy>=1.24,<2; sys_platform == "win32" and python_version < "3.13"' in text
    assert 'opencv-python>=4.8,<4.12; sys_platform == "win32" and python_version < "3.13"' in text
    assert 'sys_platform != "win32" or python_version >= "3.13"' in text


def test_fallback_installer_limits_numpy_and_opencv_on_windows(monkeypatch):
    packages = []
    monkeypatch.setattr(installer.platform, "system", lambda: "Windows")
    monkeypatch.setattr(installer, "_available", lambda name: name not in {"numpy", "cv2"})
    monkeypatch.setattr(installer, "_pip", lambda package, log: packages.append(package))
    with patch.object(installer.sys, "version_info", (3, 11, 0)):
        installer.install_for_config({})
    assert packages == ["numpy>=1.24,<2", "opencv-python>=4.8,<4.12"]
