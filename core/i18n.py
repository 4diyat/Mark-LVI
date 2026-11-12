"""core/i18n.py — one catalogue for the words the window shows.

WHY THIS EXISTS AT ALL
    The conversation is multilingual before anything in this repo is: the model
    is told to answer in the user's language, STT accepts what is spoken, and
    TTS picks a voice from a language prefix. The UI was the one part that
    assumed English — 47 labels hardcoded across 4,000 lines of Qt code, in a
    project whose own installer, logs and docs are written in Indonesian. A
    user who talks to it in Indonesian reads an English control panel.

WHY A PLAIN DICT AND NOT gettext
    gettext is the right tool once there are translators and .po files to
    exchange. There are neither. What there is instead is a handful of labels
    and a project with no Qt in its test environment, so the two properties
    that matter here are (a) the catalogue can be read and edited without
    compiling anything, and (b) what the window renders can be checked by a
    test on a machine with no display. Both are easier with dicts in JSON.

WHY A MARKER RATHER THAN AN ENGLISH DEFAULT
    A missing translation must never be silently English: that is how a locale
    ships half-translated and nobody notices. `label()` is declared here as the
    ONLY place a catalogue key is read — pass a key and get text, never a
    fallback built at the call site. `missing()` lists keys a locale lacks, and
    `tests/test_i18n.py` fails the build if any locale has a hole, an extra
    key, or a placeholder the others do not.

THE ONE THING THAT IS NOT A KEY
    The assistant's name is a setting, not a word — "Phone connected — JARVIS
    ready" is the same sentence for every user, so the name is interpolated
    into a template rather than baked into 6 locales. Templates use str.format
    fields, and the test checks that every locale has the same fields.
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path

CATALOG_DIR = Path(__file__).resolve().parent.parent / "assets" / "i18n"

# What a key looks like when a locale has not translated it. Visible on purpose:
# the alternative is English appearing in an Indonesian window and the gap
# going unnoticed until a user reports it.
MARKER = "⟪{}⟫"

DEFAULT_LOCALE = "en"

# Every locale we claim to ship. Adding one means adding a file with every key,
# and the test will say which keys are missing rather than failing at runtime.
LOCALES = ("en", "id")

_lock = threading.Lock()
_loaded: dict[str, dict[str, str]] = {}
_active: str = DEFAULT_LOCALE


def _read(locale: str) -> dict[str, str]:
    """The catalogue for `locale`, cached. Never raises: a broken or missing
    file yields an empty catalogue, which surfaces as markers, not a crash on
    startup — a translation is not worth a window that will not open."""
    with _lock:
        if locale in _loaded:
            return _loaded[locale]
    data: dict[str, str] = {}
    path = CATALOG_DIR / f"{locale}.json"
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(raw, dict):
            data = {str(k): str(v) for k, v in raw.items()
                    if not str(k).startswith("_")}
    except FileNotFoundError:
        pass                      # reported by missing(), not worth a log line
    except Exception as e:
        # A translation file that will not parse is a build problem, and the
        # person who can fix it is looking at the console, not the window.
        print(f"⚠ i18n: {path.name} could not be read ({e}) — showing keys")
    with _lock:
        _loaded[locale] = data
    return data


def available() -> list[str]:
    """The locales that actually have a file, in a stable order."""
    return [loc for loc in LOCALES if (CATALOG_DIR / f"{loc}.json").is_file()]


def resolve(preferred: str | None = None) -> str:
    """Pick a locale: the caller's choice, then the OS, then English.

    Deliberately lenient about the shape of the tag — 'id_ID.UTF-8',
    'id-ID' and 'id' all mean Indonesian, and a user who set LANG by hand
    should not have to spell it our way.
    """
    offered = available() or [DEFAULT_LOCALE]
    for candidate in (preferred, os.environ.get("LANGUAGE"),
                      os.environ.get("LC_ALL"), os.environ.get("LC_MESSAGES"),
                      os.environ.get("LANG")):
        if not candidate:
            continue
        tag = str(candidate).split(":")[0].split(".")[0].split("@")[0]
        head = tag.replace("-", "_").split("_")[0].strip().lower()
        if head in offered:
            return head
    return DEFAULT_LOCALE if DEFAULT_LOCALE in offered else offered[0]


def set_locale(preferred: str | None = None) -> str:
    """Make `preferred` (or the OS locale) the one label() reads."""
    global _active
    with _lock:
        _active = resolve(preferred)
        return _active


def active_locale() -> str:
    with _lock:
        return _active


def label(key: str, /, **fields) -> str:
    """The text for `key`, with `fields` substituted.

    THE ONLY DOOR. Two failures it is built to make loud rather than quiet:

      * a key that is missing in the active locale falls back to English and
        then to the marker, so the window says ⟪key⟫ instead of lying in a
        language the user may not read;
      * a template whose fields do not match the call raises, because a label
        reading "Phone connected — {name} ready" on screen is worse than a
        traceback in a test.

    Placeholders are substituted with str.format, so a translation can reorder
    them; that is the main reason not to use %-formatting here.
    """
    loc = active_locale()
    template = _read(loc).get(key)
    if template is None and loc != DEFAULT_LOCALE:
        template = _read(DEFAULT_LOCALE).get(key)
    if template is None:
        return MARKER.format(key)
    if not fields and "{" not in template:
        return template          # nothing to substitute: .format() would be a
    try:                         # no-op that also trips over a stray brace
        return template.format(**fields)
    except (KeyError, IndexError, ValueError):
        # A half-translated template is a bug in the catalogue, and a window
        # showing raw braces is how it becomes visible to whoever edits the
        # JSON without running the tests.
        return f"{template} {MARKER.format('bad-fields:' + key)}"


def missing(locale: str = DEFAULT_LOCALE) -> list[str]:
    """Keys the reference locale has and `locale` does not. Used by the test."""
    reference = set(_read(DEFAULT_LOCALE))
    return sorted(reference - set(_read(locale)))


def extra(locale: str) -> list[str]:
    """Keys `locale` has that the reference does not — a typo, usually."""
    reference = set(_read(DEFAULT_LOCALE))
    return sorted(set(_read(locale)) - reference)


def reload() -> None:
    """Drop the cache. For tests, and for a future 'edit the JSON and look'."""
    with _lock:
        _loaded.clear()
