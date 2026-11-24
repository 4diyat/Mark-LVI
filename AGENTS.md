# Rules for coding agents working on JARVIS

The built-in coding agent (`actions/dev_agent.py`) reads this file before every
change it makes to this project, and so should any other agent or contributor.
Each rule below exists because breaking it produced code that looked right,
passed a syntax check and did nothing when used.

## How the app runs

- `main.py` holds the voice session on an asyncio event loop in a background
  thread. The `ui/` package holds the window on the **Qt main thread**.
- Tools — `actions/*.py` and `plugins/*.py` — run on **worker threads**, never
  on the Qt main thread.
- There is exactly **one** `QApplication`, created in the `ui/` package (`ui/window.py`).

## Threading: the rule that breaks most generated code

Code in `actions/` and `plugins/` must **never create or touch a Qt widget**.
That means no `QApplication`, `QWidget`, `QMainWindow`, `QDialog`, `QThread` or
anything else from `PyQt6.QtWidgets` or `PyQt6.QtGui`. Creating a widget from a
worker thread prints `QObject::setParent: Cannot set parent, new parent is in a
different thread` and nothing appears on screen.

To show something, call the **thread-safe methods on `player`** (the `JarvisUI`
object passed to every tool). They hand the work to the Qt thread for you. The
current list, with signatures, is appended below this file by the coding agent
automatically. The ones plugins usually need:

| Need | Call |
|---|---|
| A line in the activity log | `player.write_log("text")` |
| Text in the panel under the head | `player.show_content(title, text)` |
| A quiz the user answers on screen | `player.show_quiz(topic, questions, grade=None)` |
| A structured review | `player.show_review(title, summary, findings)` |
| Play a video in the HUD | `player.show_video(path_or_url, title)` |

`show_quiz` takes `questions` as a list of dicts:
`{"question": str, "options": [str, ...] (empty list for a typed answer),
"answer": str, "note": str (shown after answering, optional)}`.
`grade(question, given) -> True | False | None` is optional; `None` means
"let the assistant judge this answer". The user answers at their own pace and
the result comes back to the conversation by itself — `run()` returns at once.

Do **not** start a separate GUI program (`subprocess` running a PyQt script)
to work around this rule. It hides every error from the user, and the app
already has a screen for it.

## Plugins

A plugin is one file `plugins/<name>.py` (no leading underscore) with:

- `PLUGIN = {"name": ..., "description": ..., "parameters": {"type": "OBJECT", ...}}`
- `def run(parameters: dict, player=None, session_memory=None) -> str`

`run()` must:

- return a **short string** — the assistant turns it into speech;
- **never raise** — catch errors and return a sentence saying what went wrong;
- return **within a few seconds** — put slow work on a `threading.Thread`
  and show its result through `player` when it is done;
- treat `player` as possibly `None` (tests and the phone dashboard).

Helper modules may live beside it with a leading underscore
(`plugins/_helper.py`); the loader skips those. See `plugins/_template.py`.

Settings are optional. A plugin that needs configuring declares
`PLUGIN_SETTINGS = {"namespace": ..., "title": ..., "fields": [...]}` and the
settings panel renders a form for it; a plugin without one still appears in
that panel, saying it needs no settings. Read the values with
`get_plugin_config(namespace)` — never from `config/api_keys.json` yourself.

A new plugin is **enabled automatically** the moment its file exists — nothing
needs to be registered or switched on. Never edit `config/api_keys.json` to
"enable" one; that file holds the user's API keys and settings.

## Asking a model for something

Always go through `core.gemini` — it has deadlines, a fallback ladder and the
user's chosen provider:

```python
from core import gemini
text = gemini.text(prompt, tier=gemini.FAST)       # short answers
data = gemini.as_json(prompt, tier=gemini.SMART)    # structured, may return None
```

Every call can fail or return `None`. Code must handle that — for example with
a small built-in fallback — instead of crashing.

## Changing the window (`ui/`)

- The package is split by ownership: `ui/theme.py` owns the palette (`C`) and is
  the only module that may assign to it; `ui/metrics.py` owns the sampler
  thread; `ui/window.py` owns the widgets. `ui/__init__.py` re-exports all of
  it, so `ui.C`, `ui.qcol` and `ui.JarvisUI` are still the names to use.
- Do not recreate `ui.py`: it would shadow the package (Python resolves the
  directory first) and every import inside it would fail.

- Widgets are created and changed only on the Qt thread.
- To let other threads trigger a change: add a `pyqtSignal` to `MainWindow`,
  connect it to a slot in `__init__`, and add a thin public method on
  `JarvisUI` that only emits the signal. `show_content` / `_content_sig` /
  `_show_content` is the pattern to copy.
- Colours come from the `C` palette class; fonts are `QFont("Courier New", size)`.

## Writing a path that came from a model

A path inside a model's JSON is **untrusted input**, not a name. It can climb
(`../`), ignore the left side entirely (an absolute path), or name another drive
(`C:\\...`). `dev_agent` used to do `project_dir / file_path` and write it, which
is how a "new project" could place a `.py` outside the project and then run it.

- Take every model-supplied path through `_safe_rel()` / `_safe_target()` in
  `actions/dev_agent.py` before reading or writing anything.
- `tests/test_paths.py` is the list of shapes that must be refused. Add to it
  when you find a new one.
- `_safe_rel` must resolve BOTH sides (`folder.resolve()` too). Comparing a
  resolved left side against an unresolved root rejected every path under a
  symlinked or relative root; see the comment there and the symlink test.

## Doing something the user cannot take back

Anything that is irreversible, or that leaves the app's own folders, goes behind
`core/confirm.request()` — the on-screen token is issued by the UI, never by the
model.

- Currently gated: shutdown/restart (`actions/computer_settings.py`), running a
  file (`actions/code_helper.py`), pip installs from a plan or from a
  `ModuleNotFoundError` (`actions/dev_agent.py`), and archive extraction
  (`actions/file_processor.py`).
- `confirm.request` returns the sentence to hand the model. Do not perform the
  work first and ask afterwards: put the real work in `run=`, and let the
  caller's AI turn end with "I need you to confirm that".
- If the gated work is a step *inside* a longer job (the build → install → test
  loop in `dev_agent`), the job must stop there and say so, not carry on and
  report the project as working. See `_gated_install` in `_build_project`.
- What is checked BEFORE the gate still matters: the banner must describe
  exactly what the work will do. `_install_with_confirmation` computes the
  accepted list once and passes it down, so the two cannot disagree.

**File operations are NOT gated — they use `core/undo.py` instead.** That is a
deliberate design (see its docstring: "act immediately, make it reversible"). The
rule that follows from it:

- If an operation has no reliable inverse, it must **decline** rather than run.
  `shutil.move` and `shutil.copy2` silently replace an existing destination, and
  the replaced file is unrecoverable — so `move_file`/`copy_file` refuse to
  overwrite instead.
- The inverse must not itself be destructive. Undoing a copy sends it to the
  Trash (`_safe_trash`), never `rmtree`.
- A name that came from a model is checked as a *name* (`_is_plain_name`), not
  only as a path: `Path("/a/b") / "/etc/passwd"` is `/etc/passwd`, with the left
  side discarded silently.

## Running something a model chose

- `run_command` is split with `shlex.split`, never `.split()`: a quoted path is
  one argument.
- A `pip install` argument must pass `_safe_requirement()` in
  `actions/dev_agent.py`: a plain name, optional extras and specifier, nothing
  beginning with `-`, no URL, no path. pip reads `--index-url` as an option.
- A file to execute is executed by absolute interpreter path (`sys.executable`
  for Python), and `-`-prefixed "arguments" are not forwarded — they are
  interpreter options, not program arguments.
- **Anything read here goes to the model.** `actions/code_helper._read_file`
  takes any path the user names and pastes it into a prompt, so it asks
  `core.code_checks.is_secret_path()` first. Add that check to any new
  read-into-a-prompt path; `Protection` only covers the project folder, and a
  tool handed an absolute path has no project to ask.

## Testing and lint before you hand work back

- `ruff check .` must print "All checks passed!" — the enabled rules are `F`,
  `E9` and `B006` only (undefined names, unused imports and variables, syntax,
  mutable default arguments). An
  undefined name is not a style issue here: it is a branch that can never run,
  and the Linux firewall path in `dashboard/server.py` was nine of them.
- `python -m pytest -q` must be green. No test may need an API key, a
  microphone, a display or the network.
- If you fix a bug, add the test that fails without the fix. Check it against
  the previous commit — a test that passes before and after proves nothing.
- Rejected actions are easy to miss because the loader survives them. If you
  touched an action, run the loader and read the rejections:
  `python -c "from pathlib import Path; from core.action_loader import discover_actions; discover_actions(Path('actions'), set(), print)"`

## General

- Never send a child process's output to `DEVNULL` without logging it, and
  never report success without checking that the thing actually happened.
- Settings live in `config/api_keys.json` through
  `memory/config_manager.py`; never write that file directly. Use
  `set_config_values()` / `update_config()` — they hold a lock and write
  atomically, because four threads write this file at the same time.
  `tests/test_config.py` fails if a module bypasses them.
- **The Gemini key is stored in that file and nowhere else.** It was in the OS
  keychain until 2026-11-22; that was removed so the user can see and edit what
  the app reads. Read it with `config_manager.get_gemini_key()` and write it
  with `save_api_keys()`. `core.gemini.api_key()` is the only other reader and
  it asks the config manager rather than reading the file, because a second
  reader is a second opinion about which copy is current.
  If you add a credential that is a *key* rather than a token for a service
  the user can revoke in a browser, give it the same treatment; plugin tokens
  stay in the file deliberately (see the docstring).
- **A missing key is a screen, not a log line.** `config_manager.is_configured()`
  is false → `ui/setup_window.py` asks, verifies with `core/key_check.py`
  (one real `models.get`), and saves only a key the service did not reject.
  `AmbientShell.mark_ready()` is what ends `wait_for_api_key()`, and
  `prompt_reconfig()` is the only thing that clears it again. A change that
  makes either loop wait on something nothing sets is the bug both loops were
  written about — `tests/test_shell_setup.py` drives both to a return with a
  timeout, so a hang is a failure instead of a hung runner.
- **No skip on setup.** The owner's decision (2026-11-22): no key, no start.
  Not a disabled button either — `tests/test_setup_window.py` refuses the word
  in the module's literals and refuses a close before a save.
- **Text a user reads goes through `core/i18n.py`**, never a literal in a Qt
  call. `label("key")` with `assets/i18n/{en,id}.json`; `tests/test_i18n.py`
  fails on a hardcoded `setText("...")` and on a key the catalogue lacks.
  The assistant's name, combo-box values and paste-ready commands are the only
  things exempt, and each exemption is listed in that test with a reason.
- Keep to the libraries already in `requirements.txt`.

## Voice verification (the owner's voiceprint gate)

The owner asked for their **voice** to verify them before JARVIS speaks back,
so the gate is a biometric control, not a preference. Three rules keep it safe:

- **The policy is pure.** `core/voice_auth.py` decides (`Decision`, `decide`,
  `next_attempt`, `is_locked`, `should_verify`, `timeout_state`) and holds no
  I/O. `tests/test_voice_auth.py` drives it with no Qt, no mic, no network.
- **The voiceprint is private, local and gitignored.** `memory/voiceprint.json`
  is written by exactly one module — `memory/voiceprint_store.py`. No tool or
  plugin may import the engine, the store, or mention the path; `tests/test_
  voice_auth_ast.py` enforces this over the AST.
- **Enabling is owner-only, through the UI.** `config_manager`
  (`get_voice_auth_enabled`/`save_voice_auth_enabled`) is the only place the
  setting is read or written, and the board 14 security card is the only
  surface that calls it. A plugin that could flip the gate would be a hole the
  size of the plugin system — that is what the AST test is watching for.

The gate is **off by default**. `tests/test_config.py` proves the default and
that the round-trip through `save/get` is honest.

## Scheduled routines (board 11)

A routine is the owner telling JARVIS to do something at a time, on a repeat
pattern. Three rules keep it honest and safe:

- **The policy is pure.** `core/routines.py` parses a schedule phrase, validates
  it, and decides `is_due` / `next_fire` against an injectable clock. No I/O, no
  thread, so the whole decision is testable without a session.
- **The store is the only writer.** `memory/routine_store.py` owns
  `memory/routines.json` (gitignored, user data). No tool or plugin may reach
  the store, the scheduler, or the policy; `tests/test_routines_ast.py` enforces
  this over the AST, and the scheduler does no filesystem or network I/O.
- **The scheduler owns the clock and the thread.** `core/routine_scheduler.py`
  polls the store and hands a due routine to `main.py`'s `_fire_routine`, which
  sends the payload to the session exactly like a user turn. A routine that
  fires wrong is worse than no routine, so the parser is conservative: an
  unreadable phrase is refused, not guessed at.

## Form filling, review-first (board 13)

Board 13 fills a form, but only after the owner has reviewed what will be sent.
Three rules:

- **The policy is pure.** `core/form_fill.py` validates a target page (only
  `https://` origins are fillable, reusing the browser URL rule), builds a
  selector→value plan, sanitises values to bounded text, and enforces the
  "review before apply" gate: an unreviewed `FormFillPlan` refuses to apply.
  No browser, no network — fully testable with a fake driver.
- **The adapter is the only I/O edge.** `actions/browser_form.py` drives an
  approved plan into the existing `_BrowserSession.fill_form` (which owns
  Playwright and the per-browser event loop). Its pure part,
  `parse_fill_results`, turns the session's textual report back into per-field
  `FieldResult`s; the no-session path reports every field failed.
- **The UI states the status.** Board 13's three field rows are editable
  inputs; the preview strip reports review/applied/failed. The apply button
  (`pages_actions.form_fill_apply`) reads the inputs, builds and reviews the
  plan, then calls the adapter — never applying an unreviewed plan.
