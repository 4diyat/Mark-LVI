"""Reminders: the text is sanitised, the scripts land in our own folder.

actions/reminder.py had no test — it shells out to `systemd-run`, `at`,
`schtasks` and `launchctl`, which is exactly the kind of module where a
quote-in-the-text or a space-in-the-path is discovered by a user whose reminder
silently never fires.

No real scheduler is touched: every subprocess is stubbed, and HOME points at
tmp_path so the generated scripts are written somewhere disposable.
"""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from actions import reminder as reminder_mod


@pytest.fixture()
def home(tmp_path, monkeypatch):
    root = tmp_path / "home"
    root.mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: root))
    return root


# ── the sanitiser ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("given,expected", [
    ('say "hi"', "say hi"),
    ("it's late", "its late"),
    ("line\nbreak", "line break"),
    ("back\\slash", "backslash"),
    ("cr\rhere", "crhere"),
    ("  padded  ", "padded"),
])
def test_quotes_and_newlines_cannot_reach_a_scheduler(given, expected):
    assert reminder_mod._sanitise(given) == expected


def test_a_long_message_is_capped():
    assert len(reminder_mod._sanitise("x" * 500)) == 200
    assert len(reminder_mod._sanitise("y" * 500, max_len=10)) == 10


# ── the generated script ────────────────────────────────────────────────────

def test_the_script_is_written_inside_the_reminders_folder(home):
    path = reminder_mod._write_notify_script("Task_1", "Stretch", "linux")

    assert path.parent == home / ".jarvis" / "reminders"
    assert path.name == "Task_1.py"
    assert path.is_file()


def test_the_message_is_a_json_literal_not_interpolated_code(home):
    """The message goes through json.dumps, so a quote cannot end the string."""
    nasty = 'x"; import os; os.system("touch /tmp/pwned"); "'
    path = reminder_mod._write_notify_script("Task_2", nasty, "linux")

    text = path.read_text(encoding="utf-8")
    assert "touch /tmp/pwned" in text          # the words are kept …
    assert 'x\\"; import os' in text           # … but escaped, not live
    # And it is valid Python: compile() is the proof that the escape held.
    compile(text, str(path), "exec")


def test_the_task_name_cannot_climb_out_of_the_folder(home):
    path = reminder_mod._write_notify_script("../escape", "hi", "linux")
    assert path.parent == home / ".jarvis" / "reminders"


# ── scheduling: which command, with what arguments ──────────────────────────

def test_linux_prefers_systemd_run_and_passes_an_argument_vector(home, monkeypatch):
    calls = []

    class _Result:
        returncode = 0
        stdout = ""
        stderr = ""

    def fake_run(argv, **kwargs):
        calls.append((argv, kwargs))
        return _Result()

    monkeypatch.setattr(reminder_mod.shutil, "which", lambda name: f"/usr/bin/{name}")
    monkeypatch.setattr(reminder_mod.subprocess, "run", fake_run)

    script = home / ".jarvis" / "reminders" / "T.py"
    when = datetime(2030, 1, 2, 15, 4)
    assert reminder_mod._schedule_linux(when, "T", script) == "T"

    argv, _kwargs = calls[0]
    assert argv[0] == "systemd-run"
    assert "--on-calendar=2030-01-02 15:04:00" in argv
    assert argv[-1] == str(script)
    assert isinstance(argv, list)          # never a shell string


def test_linux_falls_back_to_at_and_quotes_the_path(home, monkeypatch):
    calls = []

    class _Result:
        returncode = 1 if False else 0
        stdout = ""
        stderr = ""

    def fake_run(argv, **kwargs):
        calls.append((argv, kwargs))
        return _Result()

    def fake_which(name):
        return None if name == "systemd-run" else "/usr/bin/at"

    monkeypatch.setattr(reminder_mod.shutil, "which", fake_which)
    monkeypatch.setattr(reminder_mod.subprocess, "run", fake_run)

    # A folder with a space is where an unquoted path becomes two words for `at`.
    script = home / "my reminders" / "T.py"
    assert reminder_mod._schedule_linux(datetime(2030, 1, 2, 15, 4), "T", script) == "T"

    argv, kwargs = calls[0]
    assert argv[0] == "at"
    assert str(script) in kwargs["input"]
    assert '"' in kwargs["input"] or "'" in kwargs["input"]


def test_linux_says_so_when_neither_tool_exists(home, monkeypatch, capsys):
    monkeypatch.setattr(reminder_mod.shutil, "which", lambda name: None)

    assert reminder_mod._schedule_linux(datetime.now(), "T", Path("x.py")) == ""
    assert "Neither systemd-run nor at" in capsys.readouterr().out


def test_a_refused_schedule_returns_empty_rather_than_a_fake_id(home, monkeypatch):
    """An empty string is the caller's "it did not get scheduled" signal."""
    class _Result:
        returncode = 1
        stdout = ""
        stderr = "nope"

    monkeypatch.setattr(reminder_mod.shutil, "which",
                        lambda name: "/usr/bin/at" if name == "at" else None)
    monkeypatch.setattr(reminder_mod.subprocess, "run", lambda *a, **k: _Result())

    assert reminder_mod._schedule_linux(datetime.now(), "T", Path("x.py")) == ""
