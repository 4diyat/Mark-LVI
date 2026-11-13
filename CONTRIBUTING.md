# Contributing to MARK LVI

The app's own rules — threading, plugins, how to ask a model for something —
live in [AGENTS.md](AGENTS.md) and are not repeated here. This file is about
**working on the code**: how to run the checks, and what a reviewable change
looks like in this repository.

---

## 1. Set up

```bash
git clone <repo> && cd Mark-LVI
python setup.py                 # app dependencies + Playwright browsers
pip install -r requirements-dev.txt
pre-commit install              # optional, runs the same checks as CI
```

Python **3.11 or newer** — the code uses `X | Y` type syntax and `TaskGroup`.
The app is tested on 3.11 and 3.12, on Windows, macOS and Linux; CI proves all
six combinations on every push.

## 2. The three commands

```bash
ruff check .                    # must print "All checks passed!"
python -m pytest -q             # must be green
python -m providers._tests      # the provider engine's own suite
```

**No test needs an API key, a microphone, a display or the network.** If a test
you are writing needs any of those, it belongs in `providers/_tests.py` (which
mocks its own services) or behind a `pytest.mark.skipif` — not in `tests/`.

## 3. What gets enforced, and what deliberately does not

`pyproject.toml` enables **only `F` and `E9`** from ruff. Those are the rules
whose violations are defects rather than preferences:

| Rule | Found in this repo | Why it is a gate |
|---|---|---|
| `F821` undefined-name | 9 | Every one was a Linux firewall branch that could never execute |
| `F401` unused-import | 32 | Suggests a feature that is not there |
| `F841` unused-variable | 6 | Usually a value somebody meant to use |
| `F541` f-string-without-placeholders | 10 | Half-finished edits |

Style families (`E`, `W`, `I`, `UP`, `B`, `SIM`) run in CI **informationally**
so the list stays visible and shrinks by choice. Turning them on over 39,000
lines would produce a wall of findings nobody acts on, and a lint gate that gets
ignored is worse than none. If you touch a file, cleaning up its share is
welcome; a PR that is only reformatting is not.

## 4. Conventions that are not obvious

### Writing to `api_keys.json`
**Never.** `memory/config_manager.py` owns that file. It holds a lock, writes to
a temp file and swaps it in with `os.replace()`, because the file is written
from the Qt thread, the session thread, tool worker threads and the dashboard at
the same time. There is a test that fails if a module bypasses it
(`tests/test_config.py::test_only_the_config_module_writes_the_config_file`) —
add a setter there instead.

> If a setter is missing, add it to `memory/config_manager.py` and call it. Do
> not open the JSON.

### Paths that came from a model
Any path a language model produced is **untrusted input**, exactly like a form
field. It goes through `_safe_rel()` / `_safe_target()` in
`actions/dev_agent.py` before a single byte is written, and the test file
`tests/test_paths.py` lists the shapes that must be refused. New tools that
write files are expected to follow it.

### Threads
- The `ui/` package runs on the Qt main thread. `main.py` runs the session on an asyncio
  loop in a second thread. `actions/` and `plugins/` run on worker threads.
- A widget is **only** created or touched from the Qt thread. To change the
  window from anywhere else, add a `pyqtSignal` to `MainWindow` and a thin
  method on `JarvisUI` — `show_content` / `_content_sig` is the pattern.
- Never block the session thread: `time.sleep` in an `async def` freezes the
  microphone, the avatar and the reply at once. Use `asyncio.to_thread`.

### When something may fail
`core/logbook.get("<area>")` gives you a logger that writes to `logs/jarvis.log`
as well as the console. Use it in `except` blocks:

```python
from core.logbook import get as _log
try:
    optional_thing()
except Exception as e:
    _log("audio").warning("optional_thing failed: %s", e)
```

A silent `pass` is only acceptable for something genuinely cosmetic, and even
then a `debug` line costs nothing. The Linux firewall branch in
`dashboard/server.py` was unreachable for a whole release because its NameError
landed in a bare `except` — the fix was not removing the handler, it was
letting it speak.

### Comments
This codebase explains **why** a line exists, especially when the obvious
version was tried and failed. Keep that. A comment that restates the code
(`# increment i`) adds nothing; a comment that records a bug, a measurement or a
platform quirk is the most valuable thing in the file.

## 5. Adding an action or a plugin

A new `actions/<name>.py` or `plugins/<name>.py` is discovered automatically —
nothing to register, nothing to switch on in the config.

```python
TOOL = {"name": "my_action", "description": "…", "parameters": {...}}

def run(parameters: dict, player=None) -> str:
    try:
        …
        return "one short sentence the assistant can say"
    except Exception as e:
        return f"That failed: {e}"
```

- **Never raise.** Return a sentence saying what went wrong.
- **Return in a few seconds.** Long work goes on a thread and reports through
  `player` when it is done.
- **Never claim an outcome you did not observe.** `core/outcome.py` exists for
  this: `done(...)` for something checked, `unverified(...)` for something that
  went out and could not be confirmed. "Opened Spotify" without watching the
  process table is the bug this rule was written for.

## 6. Pull requests

- One concern per PR. A bug fix plus a refactor plus a reformat is three
  reviews wearing one coat.
- Say **what you observed**, not only what you changed. "The Linux firewall
  branch raised NameError and was unreachable" is reviewable; "fixed firewall"
  is not.
- If you changed behaviour, add the test that would have caught the old
  behaviour. It is worth confirming it fails on the previous commit — a test
  that passes before and after proves nothing.
- No secrets. `config/api_keys.json`, OAuth tokens and the WhatsApp session are
  already git-ignored; keep it that way.

## 7. Where things are

```
main.py          the live session (asyncio, in its own thread)
ui/              the window (Qt main thread): window.py, theme.py, metrics.py
actions/         tools that self-describe with a TOOL dict
plugins/         drop-in tools, one file each
core/            gemini ladder, confirm, undo, outcome, echo, audio, avatar
memory/          config_manager.py (the one config writer) + long-term memory
providers/       optional local engine: STT, LLM, TTS
dashboard/       the phone dashboard (FastAPI, HTTP→HTTPS redirect)
tests/           pytest; offline, no Qt, no key
```

## 8. Known rough edges (fine to fix, not fine to add to)

- `ui/window.py` is still 7,300 lines and `main.py` 2,700. New widgets belong
  in a module of their own under `ui/`, not appended to `window.py`;
  `tests/test_ui_split.py` enforces the ceiling and which file owns `C`.
- 140 `except Exception: pass` blocks. Many are legitimate (optional UI,
  optional hardware). If you touch one, make it say something —
  `except Exception as e: print(f"[Thing] {e}")` — because a silent `except` is
  how the Linux firewall bug hid for a release.
