"""A module in this repository must not be named after a stdlib module.

WHY THIS EXISTS: IT ALREADY HAPPENED
    `core/secrets.py` shipped for one push. `core/` is on sys.path in several
    places — tests/conftest.py adds the repo root, the frozen build flattens
    the tree, and the smoke harness inserts `core` itself — so `import secrets`
    resolved to that file. `keyring` (just added) imports `secrets`, and the
    standard library's `uuid` and `random` do too. The result on all six CI
    runners was `ImportError: cannot import name randbits`, from a package
    nobody had touched, with a stack that pointed at the import machinery.

    Locally it did not happen, because the shadowing depends on sys.path order.
    That is the worst property a bug can have, and it is trivially checkable:
    the module names in this repository that are also stdlib top-level modules.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# The directories that end up on sys.path in some configuration of this app.
IMPORT_ROOTS = ("", "core", "memory", "dashboard", "ui", "providers", "actions", "plugins")


def own_modules() -> dict[str, str]:
    found = {}
    for folder in IMPORT_ROOTS:
        base = ROOT / folder
        if not base.is_dir():
            continue
        for path in sorted(base.glob("*.py")):
            if path.stem == "__init__" or path.stem.startswith("__"):
                continue
            found.setdefault(path.stem, path.relative_to(ROOT).as_posix())
    return found


def stdlib_names() -> set[str]:
    names = set(getattr(sys, "stdlib_module_names", set()))
    names |= set(sys.builtin_module_names)
    return names


def test_no_module_shadows_a_stdlib_name():
    clashes = {stem: where for stem, where in own_modules().items()
               if stem in stdlib_names()}
    assert clashes == {}, (
        "these modules are named after a stdlib module and win the import "
        "when their folder is on sys.path:\n  "
        + "\n  ".join(f"{where} -> import {stem}" for stem, where in clashes.items()))


def test_the_import_roots_list_covers_where_modules_actually_live():
    """The check above is only as good as its list. This fails when a new
    package appears that nobody added — a silent gap is the failure mode."""
    # `tests/` and `tools/` run as scripts or are inserted last by conftest, so
    # a name there cannot win an import; everything else is a directory that
    # some configuration of this app puts on sys.path.
    dirs_with_modules = {
        path.parent.name for path in ROOT.glob("*/*.py")
        if path.parent.name not in {"", ".", "tests", "tools"}
        and not path.parent.name.startswith(".")
        and path.stem != "__init__"
    }
    missing = sorted(dirs_with_modules - set(IMPORT_ROOTS))
    assert missing == [], f"add these to IMPORT_ROOTS: {missing}"
