# Security

MARK LVI is a desktop assistant that holds credentials, drives the file system,
runs generated code and can place trades. That makes the security surface larger
than a normal desktop app's, and this file says what to do about it.

## Reporting a vulnerability

**Please do not open a public issue for a security problem.**

Use GitHub's private reporting channel: **Security → Report a vulnerability** on
the repository page. That opens a draft advisory only you and the maintainers can
see.

If private reporting is unavailable, open an issue that says only *"I have a
security report, please contact me"* — no details, no proof-of-concept — and the
maintainers will move the conversation somewhere private.

Please include:

* what you did, what happened, and what you expected;
* the version (`APP_VERSION` in `ui/window.py`) and your OS and Python version;
* whether the Gemini API key, the phone dashboard, a plugin, or the MT5 bridge
  was involved.

This is a single-maintainer project, so expect a first reply within about a
week rather than within hours. There is no bug bounty.

## What counts as a vulnerability here

Worth reporting:

* a way to reach `config/api_keys.json`, the OAuth tokens, or the dashboard
  pairing key from outside the user's own account;
* a path out of the folders an action is supposed to stay inside
  (`actions/file_controller.py`, `code_helper.py`, `dev_agent.py`,
  `file_processor.py`);
* a way to make the phone dashboard accept a command without a paired token, or
  to reuse an expired one;
* a way to get code executed that the user did not ask for — including through a
  prompt-injected file the assistant reads;
* anything that lets a plugin escape the consent shown before it loads.

**Not** vulnerabilities, by design — the reasoning is in `readme.md` and the
docstring of the module named:

* the dashboard being reachable over plain HTTP: HTTPS is opt-in because
  mandatory TLS produced an unusable interstitial on Android. Plaintext mode
  logs a warning. Use HTTPS on any network you do not control.
* a plugin being able to read anything the app can: plugins run in-process by
  design, and `core/plugin_manifest.py` argues that the goal is informed consent,
  not a sandbox.
* `api_keys.json` being readable by the user's own account: it is written `0600`
  and is the only store for the Gemini key. It was also written to the OS
  keychain until 2026-11-22; storing it in one file the user can edit was chosen
  deliberately, and `.gitignore` plus `tests/test_gitignore.py` are what keep it
  from leaving the machine.

## What the project already does

| Area | Where |
|---|---|
| No `shell=True` anywhere — enforced by an AST test | `tests/test_shell_true.py` |
| Dashboard: PBKDF2 pairing key, expiring scoped tokens, login throttling | `dashboard/server.py` |
| Config: atomic write, `0600`, one file for the key | `memory/config_manager.py`, `tests/test_gitignore.py` |
| Irreversible actions behind an on-screen token the model cannot issue | `core/confirm.py` |
| Model-supplied paths confined to a folder | `tests/test_paths.py`, `actions/file_controller.py` |
| Trades gated by account mode, review expiry and an emergency stop | `core/trade_gate.py`, `core/trade_guard.py` |
| Archive extraction refuses escaping paths and caps expansion | `tests/test_archive_extract.py` |
| Pip installs from a model plan accept plain package names only | `tests/test_dev_agent_deps.py` |
