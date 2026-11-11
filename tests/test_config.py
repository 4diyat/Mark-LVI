"""The config file: one writer, no lost settings, no half-written file.

Every test here exists because a specific thing went wrong in the field:

  * two writers interleaving lost a setting           → test_no_lost_updates
  * a save from the setup screen deleted everything   → test_setup_merges
  * a crash left a truncated file that read as {}     → test_corrupt_file
  * nine modules wrote this file directly             → test_only_one_writer
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import threading
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent


# ── the primitive ────────────────────────────────────────────────────────────

def test_set_value_keeps_everything_else(isolated_config):
    cm = isolated_config
    cm.save_api_keys("key-aaaaaaaaaaaaaaaa")
    cm.save_assistant_config("JARVIS", "Fatih")
    cm.save_voice("Puck")
    cm.save_input_device("Blue Yeti")
    cm.save_plugin_config("whatsapp", {"token": "t0ken"})

    cm.save_media_resolution("high")          # one more setting

    data = cm.load_api_keys()
    assert data["gemini_api_key"] == "key-aaaaaaaaaaaaaaaa"
    assert data["assistant_name"] == "JARVIS"
    assert data["user_name"] == "Fatih"
    assert data["voice_name"] == "Puck"
    assert data["input_device"] == "Blue Yeti"
    assert data["plugin_config"]["whatsapp"]["token"] == "t0ken"
    assert data["media_resolution"] == "high"


def test_setup_merges_and_never_replaces(isolated_config):
    """The re-configure screen used to write two keys over the whole file.

    That screen appears when an API key is rejected, so the second time it ran
    it deleted the assistant's name, the voice, the devices and every plugin
    credential — OAuth tokens included, which then needed re-authorising.
    """
    cm = isolated_config
    cm.save_api_keys("old-key-1234567890")
    cm.save_assistant_config("FRIDAY", "Fatih")
    cm.save_voice("Kore")
    cm.save_plugin_config("gmail", {"token": "oauth-token"})

    assert cm.save_setup("new-key-0987654321", "linux") is True

    data = cm.load_api_keys()
    assert data["gemini_api_key"] == "new-key-0987654321"
    assert data["os_system"] == "linux"
    # everything the old implementation would have destroyed
    assert data["assistant_name"] == "FRIDAY"
    assert data["voice_name"] == "Kore"
    assert data["plugin_config"]["gmail"]["token"] == "oauth-token"


def test_no_lost_updates_under_concurrency(isolated_config):
    """Twelve threads, twelve keys, all twelve present at the end.

    The old read-modify-write in each setter lost writes as soon as two of
    them overlapped — which is the real reason "set MY OWN SETUP, save, reopen,
    and it says Gemini again" happened: the mode was written, then overwritten
    by a write that had started before it.
    """
    cm = isolated_config

    def writer(i: int) -> None:
        cm.set_config_values(**{f"k{i}": i})

    threads = [threading.Thread(target=writer, args=(i,)) for i in range(12)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    data = cm.load_api_keys()
    written = {k for k in data if k.startswith("k") and k[1:].isdigit()}
    assert written == {f"k{i}" for i in range(12)}, f"lost writes: {sorted(written)}"


def test_corrupt_file_keeps_the_last_good_copy(isolated_config):
    """A truncated file must not read as "nothing was ever configured".

    Reading {} made is_configured() False, which put the setup screen in front
    of a user who had a perfectly good key one line above the damage.
    """
    cm = isolated_config
    cm.save_api_keys("key-abcdefghijklmnop")
    cm.save_voice("Aoede")

    cm.CONFIG_FILE.write_text('{"gemini_api_key": "trunc', encoding="utf-8")

    assert cm.get_gemini_key() == "key-abcdefghijklmnop"
    assert cm.get_voice() == "Aoede"

    # and the next write repairs the file rather than building on the wreckage
    cm.set_config_values(os_system="linux")
    on_disk = json.loads(cm.CONFIG_FILE.read_text(encoding="utf-8"))
    assert on_disk["gemini_api_key"] == "key-abcdefghijklmnop"
    assert on_disk["os_system"] == "linux"


def test_write_is_atomic_no_temp_files_left(isolated_config):
    cm = isolated_config
    cm.save_api_keys("key-abcdefghijklmnop")
    leftovers = [p.name for p in cm.CONFIG_DIR.iterdir() if p.name != "api_keys.json"]
    assert leftovers == [], f"temp files left behind: {leftovers}"


def test_config_file_is_not_world_readable(isolated_config):
    """It holds API keys and OAuth tokens."""
    if os.name == "nt":
        pytest.skip("POSIX permission bits do not apply on Windows")
    cm = isolated_config
    cm.save_api_keys("key-abcdefghijklmnop")
    mode = cm.CONFIG_FILE.stat().st_mode & 0o777
    assert mode == 0o600, oct(mode)


def test_update_that_raises_does_not_write(isolated_config):
    cm = isolated_config
    cm.save_api_keys("key-abcdefghijklmnop")

    def boom(_data):
        raise RuntimeError("nope")

    assert cm.update_config(boom) is False
    assert cm.get_gemini_key() == "key-abcdefghijklmnop"


# ── validation that must never reach the API ─────────────────────────────────

@pytest.mark.parametrize("given,expected", [
    ("Puck", "Puck"),
    ("charon", "Charon"),        # unknown, not merely lowercase
    ("", "Charon"),
    ("../etc/passwd", "Charon"),
])
def test_voice_names_are_validated(isolated_config, given, expected):
    isolated_config.save_voice(given)
    assert isolated_config.get_voice() == expected


@pytest.mark.parametrize("given", ["default", "low", "medium", "high"])
def test_media_resolution_roundtrips(isolated_config, given):
    isolated_config.save_media_resolution(given)
    assert isolated_config.get_media_resolution() == given


def test_turn_tuning_is_clamped(isolated_config):
    isolated_config.save_turn_tuning({"silence_ms": 99_999, "prefix_ms": -5})
    tuning = isolated_config.get_turn_tuning()
    assert tuning["silence_ms"] == 3000
    assert tuning["prefix_ms"] == 0


def test_providers_block_defaults_to_gemini(isolated_config):
    assert isolated_config.get_provider_mode() == "gemini"
    assert isolated_config.get_pipeline() == {}
    isolated_config.save_provider_mode("nonsense")
    assert isolated_config.get_provider_mode() == "gemini"


def test_provider_credentials_merge_per_service(isolated_config):
    cm = isolated_config
    cm.save_provider_config("openai_compat@minimax", {"key": "a", "model": "m1"})
    cm.save_provider_config("openai_compat@minimax", {"model": "m2"})
    cm.save_provider_config("openai_compat@openai", {"key": "b"})

    assert cm.get_provider_config("openai_compat@minimax") == {"key": "a", "model": "m2"}
    assert cm.get_provider_config("openai_compat@openai") == {"key": "b"}


def test_legacy_provider_id_is_migrated_on_read(isolated_config):
    """Old configs shared one "openai_compat" block; it moves to the service its
    catalog key names, and pipeline references follow it."""
    cm = isolated_config
    cm.set_config_values(providers={
        "mode": "pipeline",
        "creds": {"openai_compat": {"catalog": "minimax", "key": "k"}},
        "pipeline": {"stt": "", "llm": "openai_compat", "tts": ""},
        "sidecar": "openai_compat",
    })
    providers = cm.get_providers()
    assert "openai_compat" not in providers["creds"]
    assert providers["creds"]["openai_compat@minimax"]["key"] == "k"
    assert providers["pipeline"]["llm"] == "openai_compat@minimax"
    assert providers["sidecar"] == "openai_compat@minimax"


# ── the architectural rule ───────────────────────────────────────────────────

def test_only_the_config_module_writes_the_config_file():
    """AGENTS.md: "never write that file directly" — now actually true.

    This reads the source rather than grepping in the head, because the rule
    was violated by nine modules before and would be again by the next one
    written in a hurry.
    """
    offenders = []
    write_markers = re.compile(r"""write_text|json\.dump\(|["'](?:w|a|r\+)["']""")
    for path in ROOT.rglob("*.py"):
        if any(part in {".git", "__pycache__", "tests", ".venv"} for part in path.parts):
            continue
        if path.name == "config_manager.py":
            continue
        # providers/_tests.py materialises a config in a TEMP directory to
        # measure a cold start; it never touches the user's file.
        if path.parts[-2:] == ("providers", "_tests.py"):
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for match in re.finditer(r"api_keys\.json", text):
            # A writer names the file and reaches for a write API nearby; a
            # reader opens it "r". The window is wide enough for the call to
            # span lines (open(...) then .write(...)) and narrow enough not to
            # catch an unrelated write elsewhere in a 7,000-line file.
            window = text[max(0, match.start() - 260): match.start() + 320]
            marker = write_markers.search(window)
            if marker is None:
                continue
            line_no = text.count("\n", 0, match.start()) + 1
            offenders.append(f"{path.relative_to(ROOT)}:{line_no} ({marker.group(0)})")
    assert offenders == [], "these write api_keys.json directly:\n" + "\n".join(offenders)


def test_config_module_imports_without_the_app_running():
    """`memory.config_manager` must not import Qt, sounddevice or genai.

    It is imported by the setup screen before the session exists, by the
    dashboard in its own thread, and by tests. Any heavy import here becomes a
    startup cost for all three.
    """
    code = (
        "import sys; import memory.config_manager;"
        "bad=[m for m in ('PyQt6','sounddevice','google.genai','numpy') if m in sys.modules];"
        "print(','.join(bad))"
    )
    out = subprocess.run([sys.executable, "-c", code], cwd=str(ROOT),
                         capture_output=True, text=True, timeout=60)
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "", f"unexpected heavy imports: {out.stdout.strip()}"

# ── the two APIs that answer the same question ───────────────────────────────

def test_config_module_reads_the_same_file_as_the_writer(isolated_config, monkeypatch):
    """`config.is_windows()` used to look in a folder of its own.

    The package built its path from `Path(__file__).parent`, which is right in
    a checkout and wrong in a bundle: frozen with PyInstaller, `__file__` lives
    in the temporary extraction folder, so the app read a config file that did
    not exist — and its bare `except` turned that into "no OS configured",
    silently answering Linux on a Windows machine. It now asks
    memory.config_manager where the file is, which already handles `frozen`.
    """
    isolated_config.save_setup("key-aaaaaaaaaaaaaaaa", "windows")

    import config

    monkeypatch.setattr(config, "_CONFIG_PATH", isolated_config.CONFIG_FILE)
    assert config.get_os() == "windows"
    assert config.is_windows() and not config.is_linux()


def test_config_module_still_answers_when_there_is_no_file(tmp_path, monkeypatch):
    """No config file is a normal first run, not an error: detect the OS."""
    import config

    monkeypatch.setattr(config, "_CONFIG_PATH", tmp_path / "absent.json")
    assert config.get_config() == {}
    assert config.get_os() in {"windows", "mac", "linux"}
