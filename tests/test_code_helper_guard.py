"""code_helper writes inside the user's folders, and asks before it executes.

Two holes, both fed by model-supplied parameters:

  * `_resolve_save_path` returned an absolute `output_path` verbatim and
    `_save_file` created every parent directory, so "save this code" could write
    `/etc/cron.d/x`, `~/.bashrc` or an SSH `authorized_keys`.
  * `_run_action` executed the named file with seven different interpreters and
    never reached `core/confirm.py` — the gate that exists for exactly this and
    was wired to shutdown/restart alone.

The path rule is pure. The confirmation is checked by stubbing
`core.confirm.request`, which is what the HUD does in the real app.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from actions import code_helper


@pytest.fixture()
def home(tmp_path, monkeypatch):
    root = tmp_path / "home"
    (root / "Desktop").mkdir(parents=True)
    (root / "Documents").mkdir()
    (root / "Downloads").mkdir()
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: root))
    monkeypatch.setattr(code_helper, "DESKTOP", root / "Desktop")
    monkeypatch.setattr(
        code_helper, "_WRITE_ROOTS",
        (root / "Desktop", root / "Documents", root / "Downloads"))
    return root


# ── where a file may be written ─────────────────────────────────────────────

def test_a_relative_name_lands_on_the_desktop(home):
    path = code_helper._resolve_save_path("hello.py", "python")
    assert path == home / "Desktop" / "hello.py"
    assert code_helper._is_writable_path(path)


def test_an_absolute_path_inside_documents_is_allowed(home):
    target = home / "Documents" / "notes.py"
    assert code_helper._is_writable_path(target)


@pytest.mark.parametrize("target", [
    "/etc/cron.d/job",              # absolute, outside every root
    "/root/.bashrc",
    "/tmp/scratch.py",              # tmp is not one of the user's folders
])
def test_an_absolute_path_outside_the_user_folders_is_refused(home, target):
    assert code_helper._is_writable_path(Path(target)) is False


def test_a_traversal_out_of_documents_is_refused(home):
    escape = home / "Documents" / ".." / ".." / "elsewhere" / "x.py"
    assert code_helper._is_writable_path(escape) is False


def test_save_refuses_rather_than_creating_parents_outside(home):
    """The parent must not even be created — mkdir came before the old check."""
    target = home.parent / "outside" / "deep" / "evil.py"

    message = code_helper._save_file(target, "print('x')")

    assert "Refused to save" in message
    assert not target.exists()
    assert not (home.parent / "outside").exists()


def test_save_writes_inside_desktop(home):
    target = home / "Desktop" / "ok.py"
    assert "Saved to:" in code_helper._save_file(target, "print('x')")
    assert target.read_text() == "print('x')"


# ── executing a file has to be confirmed ────────────────────────────────────

def test_run_asks_the_hud_before_executing(home, monkeypatch):
    """The gate is `core.confirm.request`; the token comes from the UI."""
    seen = {}

    def fake_request(key, title, detail, run):
        seen.update(key=key, title=title, detail=detail, run=run)
        return "[CONFIRMATION_PENDING] ask the user"

    monkeypatch.setattr("core.confirm.request", fake_request)
    monkeypatch.setattr("core.confirm.pending_title", lambda: "")

    script = home / "Desktop" / "hello.py"
    script.write_text("print('hi')")

    out = code_helper._run_action(str(script), [], 5, None)

    assert out == "[CONFIRMATION_PENDING] ask the user"
    assert seen["key"] == "code_run"
    assert "hello.py" in seen["title"]
    assert callable(seen["run"])          # what the CONFIRM button will run


def test_run_does_not_stack_two_banners(home, monkeypatch):
    monkeypatch.setattr("core.confirm.pending_title", lambda: "Shut down?")

    script = home / "Desktop" / "hello.py"
    script.write_text("print('hi')")

    out = code_helper._run_action(str(script), [], 5, None)

    assert "already on screen" in out


def test_a_missing_file_is_reported_before_any_confirmation(home, monkeypatch):
    called = []
    monkeypatch.setattr("core.confirm.request",
                        lambda *a, **k: called.append(1) or "requested")

    out = code_helper._run_action(str(home / "nope.py"), [], 5, None)

    assert "File not found" in out
    assert called == []


def test_interpreter_options_are_not_forwarded(home, monkeypatch):
    """`-c`/`-e` turn "run this file" into "run this string"."""
    captured = {}

    class _Result:
        returncode = 0
        stdout = "ok"
        stderr = ""

    def fake_run(argv, **kwargs):
        captured["argv"] = argv
        return _Result()

    monkeypatch.setattr(code_helper.subprocess, "run", fake_run)
    script = home / "Desktop" / "x.py"
    script.write_text("print(1)")

    code_helper._run_file(script, ["--danger", "-c", "evil()"], 5)

    assert "-c" not in captured["argv"]
    assert "evil()" in captured["argv"]       # plain args are still passed


# ── what is read here goes to the model ─────────────────────────────────────
#
# `_read_file` accepts any path the model names and the result is pasted into a
# prompt. "Explain my config" was therefore a way to send config/api_keys.json,
# ~/.ssh/id_rsa or ~/.aws/credentials to a third party. The rule existed in
# core/code_checks.py and was enforced for dev_agent alone.

@pytest.mark.parametrize("name", [
    "api_keys.json",
    ".env",
    ".env.local",
    "secrets.yaml",
    "id_rsa",
    "credentials.json",
    "server.pem",
])
def test_a_secret_file_is_not_read_into_a_prompt(home, name):
    secret = home / "Documents" / name
    secret.write_text("SUPER-SECRET-KEY")

    text, error = code_helper._read_file(str(secret))

    assert text == "", "the contents must not leave the machine"
    assert "Refused to read" in error
    assert "secrets" in error


def test_ordinary_source_still_reads(home):
    source = home / "Documents" / "api_keys.py"     # a NAME, but it is code
    source.write_text("def get():\n    return 1\n")

    text, error = code_helper._read_file(str(source))

    assert error == ""
    assert "def get()" in text


def test_a_missing_file_is_a_different_message(home):
    text, error = code_helper._read_file(str(home / "nope.py"))
    assert text == ""
    assert "File not found" in error


def test_a_directory_is_not_read(home):
    text, error = code_helper._read_file(str(home / "Documents"))
    assert text == ""
    assert "Not a file" in error
