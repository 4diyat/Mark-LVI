"""The JARVIS profile has to find the window in both of its shapes.

WHY THIS TEST EXISTS
    `core/code_checks.py` carries a profile that teaches dev_agent about this
    project: where plugins may import widgets from, and which thread-safe
    `player` methods they are allowed to call instead. Both answers used to be
    read from `ui.py` — one file, named in two places.

    When the window became a package, those two places still named the file.
    Nothing raised. The profile simply stopped recognising this repository and
    stopped telling the coding model about `player` at all, so every plugin it
    then wrote had a one-in-two chance of importing Qt on a worker thread.

    Recognising both shapes is the fix; this is what keeps the next move of the
    window from doing the same thing silently.
"""
from __future__ import annotations

from pathlib import Path

from core.code_checks import _JarvisProfile, _is_the_window

ROOT = Path(__file__).resolve().parent.parent


def test_profile_finds_the_window_where_it_is_today():
    assert _JarvisProfile().detect(ROOT) is True


def test_profile_still_recognises_an_older_project_with_ui_py(tmp_path):
    """Projects written by an earlier JARVIS are not this repository's shape."""
    (tmp_path / "core").mkdir()
    (tmp_path / "core" / "plugin_loader.py").write_text("", encoding="utf-8")
    (tmp_path / "ui.py").write_text(
        "class JarvisUI:\n"
        "    def write_log(self, text):\n"
        "        '''Thread-safe: callable from any thread.'''\n",
        encoding="utf-8")

    profile = _JarvisProfile()
    assert profile.detect(tmp_path) is True
    assert "write_log" in profile.guide(tmp_path)


def test_profile_is_not_fooled_by_a_folder_with_both_missing(tmp_path):
    (tmp_path / "core").mkdir()
    (tmp_path / "core" / "plugin_loader.py").write_text("", encoding="utf-8")
    assert _JarvisProfile().detect(tmp_path) is False
    assert _JarvisProfile().guide(tmp_path) == ""


def test_only_the_window_may_create_a_qapplication():
    assert _is_the_window("ui.py")
    assert _is_the_window("ui/window.py")
    assert _is_the_window("ui/overlays/setup.py")
    assert not _is_the_window("plugins/quiz.py")
    assert not _is_the_window("actions/browser_control.py")
    # Windows paths arrive with backslashes from the model's own file list.
    assert _is_the_window("ui\\window.py")
    assert not _is_the_window("actions\\quiz.py")
