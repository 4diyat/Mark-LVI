"""A silent `except: pass` may not be ADDED, and the list may only shrink.

core/logbook.py makes the case: this codebase had ~140 of them, and several
"hid a real bug — the Linux firewall branch in dashboard/server.py was
unreachable for a release because its NameError fell into one".

So `S110` (try-except-pass) is enforced by ruff, with an explicit per-file
exemption list for the files that still carry the pre-existing ones. These tests
keep that list honest, which `ruff check` alone cannot do:

  * a file on the list that no longer needs it is a claim that has gone stale;
  * a file NOT on the list that grows a new one is caught by ruff, not here.

Both directions are checked so neither an unnoticed new `pass` nor a
permanently-frozen exemption list survives by being forgotten.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PYPROJECT = ROOT / "pyproject.toml"


def exempted_files() -> set[str]:
    """The per-file-ignores entries that grant S110."""
    text = PYPROJECT.read_text(encoding="utf-8")
    return set(re.findall(r'^"([^"]+)"\s*=\s*\[[^\]]*"S110"', text, re.MULTILINE))


def silent_handlers(path: Path) -> list[int]:
    """Line numbers of `except <broad>: pass`.

    ONLY the broad cases, because those are what S110 is about and what the
    exemption list exists for. A narrow handler that swallows one expected
    condition is a different thing and needs no exemption:

        except queue.Full:      pass   # the queue being full is the design
        except FileNotFoundError: pass  # the file being absent is the answer

    Counting those as findings is how a check becomes noise and then gets
    turned off — which is the history this project already has with lint.
    """
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError:
        return []

    def is_broad(handler: ast.ExceptHandler) -> bool:
        if handler.type is None:
            return True                        # bare `except:`
        names = ast.unparse(handler.type)
        return any(word in names for word in ("Exception", "BaseException"))

    return [node.lineno for node in ast.walk(tree)
            if isinstance(node, ast.ExceptHandler)
            and is_broad(node)
            and len(node.body) == 1
            and isinstance(node.body[0], ast.Pass)]


def files_with_silent_handlers() -> dict[str, list[int]]:
    found = {}
    for path in ROOT.rglob("*.py"):
        if any(part in {".git", "__pycache__", ".venv", "build", "dist"}
               for part in path.parts):
            continue
        lineno = silent_handlers(path)
        if lineno:
            found[path.relative_to(ROOT).as_posix()] = lineno
    return found


def test_every_file_with_a_silent_handler_is_exempted():
    """Ruff enforces this too — this states the rule where a reader looks."""
    missing = sorted(set(files_with_silent_handlers()) - exempted_files())
    assert missing == [], (
        "these files have an `except: pass` but are not on the S110 list; either "
        "log the failure or add the file deliberately:\n  " + "\n  ".join(missing))


def test_no_file_is_exempted_without_a_silent_handler_left():
    """An exemption that outlives its cause is a rule nobody re-reads.

    When the last `pass` in a file is turned into a log line, delete the file
    from the list in pyproject.toml. actions/open_app.py was done that way.
    """
    stale = sorted(exempted_files() - set(files_with_silent_handlers()))
    assert stale == [], (
        "these files are exempted from S110 but no longer have a silent "
        "handler — remove them from pyproject.toml:\n  " + "\n  ".join(stale))


def test_the_rule_is_actually_enabled():
    text = PYPROJECT.read_text(encoding="utf-8")
    assert '"S110"' in text.split("per-file-ignores")[0], (
        "S110 must stay in the enforced select list")
