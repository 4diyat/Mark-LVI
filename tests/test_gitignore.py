"""`.gitignore` has no inline comments, and the file that says so proved it.

WHAT WAS WRONG
    The "Secrets" block of `.gitignore` was written as

        config/api_keys.json          # your Gemini API key, plus per-plugin credentials

    which reads as one file name whose text includes the `#` and everything
    after it. It matched nothing. Every rule in that block — the Gemini key, the
    dashboard's TLS private key, the WhatsApp session, the Google OAuth tokens,
    the audit log — was decorative, and `config/api_keys.json` was tracked by git
    the whole time. The comment above the block said "Committing any of these
    publishes them", in a file that made committing them invisible rather than
    impossible.

WHY THIS IS A TEST AND NOT A NOTE
    The failure is silent by construction: a rule that matches nothing looks
    exactly like a rule that matches everything, and `git status` shows nothing
    either way. Only asking git about a path can tell the two apart, which is
    what this file does — for EVERY rule, not just the ones that were wrong.

WHAT IS NOT ASSERTED HERE
    Whether a tracked file is a secret. `config/api_keys.json` holds settings as
    well as the key, and the fix was to stop tracking it; a test that guessed at
    file contents would fail on somebody's perfectly ordinary config.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
GITIGNORE = ROOT / ".gitignore"

# A sample path for each rule that names a DIRECTORY or a glob, so the rule can
# be exercised. Kept next to the test rather than in `.gitignore` because the
# point of the test is that a name in `.gitignore` is what git reads, not what a
# human meant.
SAMPLE_FOR = {
    # secrets
    "config/certs/": "config/certs/server.pem",
    "config/whatsapp_web/": "config/whatsapp_web/Default/leveldb/x",
    "**/token*.json": "config/token_gmail.json",
    "config/.calendar-token-*": "config/.calendar-token-1234",
    "**/client_secret*.json": "config/client_secret_web.json",
    "*credentials*.json": "config/my-credentials.json",
    # python build noise — globs cannot be tested by their own text, which is
    # why this table exists rather than `rule.rstrip("/")` doing the work
    "__pycache__/": "__pycache__/x.pyc",
    "*.py[cod]": "module.pyc",
    "*$py.class": "module$py.class",
    "*.so": "module.so",
    "build/": "build/x",
    "dist/": "dist/x",
    "*.egg-info/": "package.egg-info/PKG-INFO",
    ".eggs/": ".eggs/x",
    # virtual environments
    ".venv/": ".venv/bin/python",
    "venv/": "venv/bin/python",
    "env/": "env/bin/python",
    "ENV/": "ENV/bin/python",
    # editors and operating systems
    ".vscode/": ".vscode/settings.json",
    ".idea/": ".idea/workspace.xml",
    "*.swp": "notes.swp",
    "*.log": "jarvis.log",
    "logs/": "logs/today.txt",
    "downloads/": "downloads/a.zip",
    "screenshots/": "screenshots/a.png",
    "providers/voices/": "providers/voices/en_US.onnx",
    # coverage output
    ".coverage": ".coverage",
    "htmlcov/": "htmlcov/index.html",
}


def _rules() -> list[str]:
    """Every effective rule in `.gitignore`, with comments and blanks removed.

    A rule is effective only if the line has no `#` in it — that is the bug this
    file exists for, so the parser refuses such a line rather than trimming it,
    and the assertion below names the offender.
    """
    rules = []
    for number, line in enumerate(GITIGNORE.read_text(encoding="utf-8").splitlines(), 1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        assert "#" not in stripped, (
            f".gitignore line {number} has an inline comment, so git reads the "
            f"whole line as one file name and the rule matches nothing: {line!r}")
        rules.append((number, stripped))
    return rules


def _ignored(path: str) -> bool:
    result = subprocess.run(
        ["git", "check-ignore", "-q", "--no-index", path],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )
    return result.returncode == 0


@pytest.mark.parametrize("number,rule", _rules(),
                         ids=[rule for _, rule in _rules()])
def test_every_rule_actually_matches_something(number, rule):
    """The claim is not "the line is there" — it is "git acts on it"."""
    sample = SAMPLE_FOR.get(rule, rule.rstrip("/"))
    assert _ignored(sample), (
        f".gitignore:{number} {rule!r} does not ignore {sample!r}. "
        "A rule that matches nothing is decorative.")


def test_the_four_secrets_that_were_tracked_are_ignored_and_untracked():
    """`git rm --cached` left them on disk; the rule keeps them out.

    Both halves matter: `--cached` alone is undone by the next `git add -A`,
    and the rule alone would not have untracked what was already in the index.
    """
    if not (ROOT / ".git").exists():
        pytest.skip("not a git checkout")

    for path in ("config/api_keys.json", "config/audit.jsonl"):
        assert _ignored(path), f"{path} is still not ignored"
        tracked = subprocess.run(
            ["git", "ls-files", "--error-unmatch", path],
            cwd=ROOT, capture_output=True, text=True, check=False,
        )
        assert tracked.returncode != 0, (
            f"{path} is still TRACKED — `git add -A` will publish it")


def test_the_example_config_is_committed_and_carries_no_key():
    """A clone with nothing must still have the shape the app reads.

    That is what `api_keys.example.json` is for: the file the app creates is
    ignored, so a fresh checkout would otherwise have no reference for what
    belongs in it.
    """
    example = ROOT / "config" / "api_keys.example.json"
    assert example.exists(), "the example config went missing with the real one"
    data = json.loads(example.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    assert data.get("gemini_api_key") == "", "the example must ship empty"
    # And it must be OUTSIDE the ignore rule, or the template itself is invisible.
    assert not _ignored("config/api_keys.example.json")


def test_no_rule_ignores_the_example_config():
    """A broad `config/*.json` rule would hide the template and defeat it."""
    assert not _ignored("config/api_keys.example.json")
