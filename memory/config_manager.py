"""memory/config_manager.py — the ONE module that reads and writes api_keys.json.

WHY THE READ-MODIFY-WRITE HERE IS NOW A LOCKED PRIMITIVE
    Every setter in this file used to open-code the same four steps:

        data = read the whole file
        data[some_key] = value
        write the whole file back

    That is correct when one thread does it. This app writes api_keys.json from
    at least four places at once — the Qt thread (the settings overlays), the
    session thread (a reconnect saving a voice), tool worker threads
    (screen_processor saving the camera index) and the dashboard (a phone
    changing a setting). Two of those interleaving lose whichever value was
    written first; that is exactly how "set MY OWN SETUP, save, reopen, and it
    says Gemini again" happened, and the old save_providers() docstring
    describes the same race from a different angle.

    So the four steps live in `update_config()` and nowhere else. It holds a
    lock across the whole cycle, writes to a temp file in the same directory and
    swaps it in with os.replace(), and only falls back to the old behaviour if
    the directory refuses the rename. A process killed mid-write now leaves the
    previous file intact instead of a half-written one that reads as {} — which
    is the state that made is_configured() False and asked the user for their
    API key again.

THE RULE THIS FILE EXISTS TO ENFORCE
    AGENTS.md says settings and keys live here and must never be written
    directly. This module was one of nine writers, which made the rule untrue
    rather than merely unenforced. `save_setup()` is the door the setup screen
    now uses: it MERGES the API key and the OS into the file instead of
    replacing it, because the old code wrote {"gemini_api_key", "os_system"}
    over everything and took the assistant's name, its voice, the audio device
    choices and every plugin credential with it.
"""
import json
import os
import sys
import tempfile
import threading
from pathlib import Path

# Re-entrant because update_config() may be called from a helper that already
# holds it (save_plugin_config → update_config, and future nesting like it).
_WRITE_LOCK = threading.RLock()

# Last known good contents. When a read fails — a truncated file, a half-written
# one, a JSON syntax error from an editor — returning this beats returning {}
# and making the caller think nothing was ever configured.
_LAST_GOOD: dict = {}


def get_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).resolve().parent.parent

BASE_DIR    = get_base_dir()
CONFIG_DIR  = BASE_DIR / "config"
CONFIG_FILE = CONFIG_DIR / "api_keys.json"

def ensure_config_dir() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)


# ── The primitive every writer below goes through ────────────────────────────

def _read_unlocked() -> dict:
    """The file as a dict. Never raises; never returns None."""
    global _LAST_GOOD
    if not CONFIG_FILE.exists():
        return dict(_LAST_GOOD) if _LAST_GOOD else {}
    try:
        data = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        # One line, not a traceback: a corrupt config is a thing the user can
        # fix by deleting the file, and the app keeps running on the last copy.
        print(f"❌ Failed to load api_keys.json ({e}) — using the last good copy")
        return dict(_LAST_GOOD) if _LAST_GOOD else {}
    if not isinstance(data, dict):
        print("❌ api_keys.json is not a JSON object — using the last good copy")
        return dict(_LAST_GOOD) if _LAST_GOOD else {}
    _LAST_GOOD = dict(data)
    return data


def _atomic_write_unlocked(data: dict) -> bool:
    """Write `data` to the config file so a crash cannot truncate it.

    WHY A TEMP FILE IN THE SAME DIRECTORY
        os.replace() is atomic only within one filesystem, and %TEMP% on Windows
        is frequently a different drive from the project folder. Writing beside
        the target keeps the swap atomic and keeps the file's permission bits
        (a temp file in /tmp would arrive with 0600 and break a shared install).

    WHY THE FALLBACK STILL EXISTS
        A read-only folder, a network share that refuses renames, a filesystem
        without atomic replace: all of them would otherwise lose the setting
        the user just changed. The plain write is what the app did before this
        function existed, so it is a return to the old behaviour, not a new way
        to fail.
    """
    ensure_config_dir()
    text = json.dumps(data, indent=4, ensure_ascii=False)
    tmp_name = None
    try:
        fd, tmp_name = tempfile.mkstemp(
            prefix=".api_keys.", suffix=".tmp", dir=str(CONFIG_DIR))
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())      # the bytes are on disk before the swap
        try:
            os.chmod(tmp_name, 0o600)  # the file holds API keys and OAuth tokens
        except Exception:
            pass                       # Windows: chmod is mostly a no-op
        os.replace(tmp_name, CONFIG_FILE)
        tmp_name = None
        return True
    except Exception as e:
        print(f"⚠️  Atomic config write failed ({e}) — writing directly")
        try:
            CONFIG_FILE.write_text(text, encoding="utf-8")
            return True
        except Exception as e2:
            print(f"❌ Could not save api_keys.json: {e2}")
            return False
    finally:
        if tmp_name:
            try:
                os.unlink(tmp_name)
            except Exception:
                pass


def update_config(mutate) -> bool:
    """Read → let `mutate(data)` change it → write, under one lock.

    `mutate` may edit the dict in place or return a replacement; returning None
    means "I edited it in place". Returns True when the file was written.

    This is the only function in the codebase that should write api_keys.json.
    """
    with _WRITE_LOCK:
        data = _read_unlocked()
        try:
            out = mutate(data)
        except Exception as e:
            print(f"❌ Config update aborted: {e}")
            return False
        if isinstance(out, dict):
            data = out
        ok = _atomic_write_unlocked(data)
        if ok:
            global _LAST_GOOD
            _LAST_GOOD = dict(data)
        return ok


def set_config_values(**fields) -> bool:
    """Set one or more top-level keys, leaving everything else alone.

    The drop-in replacement for the dozen `data[x] = y; write(data)` blocks this
    file used to contain.
    """
    def _apply(data: dict) -> None:
        data.update(fields)
    return update_config(_apply)


def load_api_keys() -> dict:
    """The whole config. Never raises; returns {} only when nothing is stored."""
    with _WRITE_LOCK:
        return _read_unlocked()


# ── Setup screen ─────────────────────────────────────────────────────────────

def save_api_keys(gemini_api_key: str) -> None:
    """Store the API key, keeping every other setting that is already there.

    THE KEY GOES TO THE KEYCHAIN FIRST, AND THE FILE KEEPS A COPY.
        `core/secrets.py` explains the argument in full. The short version: this
        is the one secret in the file that is actually a key, every desktop OS
        has held one for a decade, and `keyring` is optional — so the keychain
        is tried and the file copy is written either way. That ordering is what
        makes the feature safe to add to an app that must also run headless: a
        machine without a keyring behaves exactly as it did before.

        When the keychain accepts it, the file copy is written with a marker key
        (`gemini_api_key_source`) purely so the settings panel can say where the
        authoritative copy is instead of guessing.
    """
    key = (gemini_api_key or "").strip()
    stored = False
    try:
        from core import secrets
        stored = secrets.set_secret(key) if key else False
    except Exception as e:      # noqa: BLE001 — the file copy is the fallback
        # Reported rather than swallowed: a keyring that fails on every save is
        # a fact the user should be able to see, and this is the only place that
        # knows it happened.
        print(f"⚠ Keychain unavailable, keeping the key in the config file: {e}")
    fields = {"gemini_api_key": key}
    if stored:
        fields["gemini_api_key_source"] = "keychain"
    set_config_values(**fields)


def save_setup(gemini_api_key: str, os_name: str = "") -> bool:
    """What the setup / re-configure screen writes. MERGES — never replaces.

    WHY THIS EXISTS SEPARATELY FROM save_api_keys()
        The screen used to write the JSON itself:
            API_FILE.write_text({"gemini_api_key": key, "os_system": os_name})
        which is correct exactly once, on a machine that has no config yet. The
        same overlay is what appears when an API key is rejected, so the second
        time it ran it deleted the assistant's name, the chosen voice, the
        microphone and speaker choices, the wake-word setting and every plugin
        credential — including OAuth tokens, which then had to be re-authorised.
    """
    return set_config_values(
        gemini_api_key=(gemini_api_key or "").strip(),
        os_system=(os_name or "").strip(),
    )


def get_gemini_key() -> str | None:
    """The Gemini key: the keychain if it has one, else the file.

    Keychain FIRST and not "whichever is non-empty": a key that was rotated in
    the panel is written to both, but a key the user pasted into the file by
    hand and then saved once has a keychain copy that is now the newer of the
    two. Reading the file first would silently keep using the old one.
    """
    try:
        from core import secrets
        key = secrets.get_secret()
        if key:
            return key
    except Exception as e:      # noqa: BLE001 — fall through to the file
        print(f"⚠ Keychain read failed, using the config file: {e}")
    return load_api_keys().get("gemini_api_key")

def is_configured() -> bool:
    key = get_gemini_key()
    return bool(key and len(key) > 15)


def get_assistant_name() -> str:
    """Return the configured assistant name, or 'JARVIS' if not set."""
    return load_api_keys().get("assistant_name", "JARVIS") or "JARVIS"


def get_user_name() -> str:
    """Return the configured user name for addressing."""
    return load_api_keys().get("user_name", "")


def save_assistant_config(assistant_name: str, user_name: str) -> None:
    """Persist assistant name and user name to config."""
    set_config_values(
        assistant_name=(assistant_name or "").strip() or "JARVIS",
        user_name=(user_name or "").strip(),
    )


# ── Assistant voice ──────────────────────────────────────────────────────────
# Gemini Live prebuilt voices. Names are proper nouns — identical in every
# language, so this list is safe to show verbatim in any locale.
AVAILABLE_VOICES = ["Charon", "Puck", "Kore", "Fenrir", "Aoede"]
DEFAULT_VOICE    = "Charon"


def get_voice() -> str:
    """Return the configured Live voice, falling back to the default if unset
    or if the stored value is not a voice we recognise."""
    v = load_api_keys().get("voice_name", DEFAULT_VOICE) or DEFAULT_VOICE
    return v if v in AVAILABLE_VOICES else DEFAULT_VOICE


def save_voice(voice_name: str) -> None:
    """Persist the chosen Live voice. Unknown names collapse to the default so a
    bad value can never reach the API and break the session."""
    v = (voice_name or "").strip()
    set_config_values(voice_name=v if v in AVAILABLE_VOICES else DEFAULT_VOICE)


def get_wake_word_enabled() -> bool:
    """Whether local wake-word gating is on (assistant sleeps until 'Hey Jarvis')."""
    return load_api_keys().get("wake_word_enabled", False)


def save_wake_word_enabled(enabled: bool) -> None:
    set_config_values(wake_word_enabled=bool(enabled))


def get_push_to_talk_enabled() -> bool:
    """Hold-a-key-to-speak. When on, the mic is closed unless the chord is held."""
    return load_api_keys().get("push_to_talk_enabled", False)


def save_push_to_talk_enabled(enabled: bool) -> None:
    _save_flag("push_to_talk_enabled", enabled)

HUD_STYLES = ("face", "core")


def get_hud_style() -> str:
    """Which centrepiece the HUD draws: the animated head, or the reactor core.

    Taste, not capability — both render in the same software painter and cost
    about the same. Defaults to the head because that is what MARK LIV shipped
    with; anyone who preferred the older look can switch back in ⚙ and the
    choice survives a restart.
    """
    v = str(load_api_keys().get("hud_style", "face")).strip().lower()
    return v if v in HUD_STYLES else "face"


def save_hud_style(style: str) -> None:
    s = str(style or "").strip().lower()
    _save_flag("hud_style", s if s in HUD_STYLES else "face")


def get_ui_scale() -> float:
    """How much larger than designed the whole interface is drawn, or 0 for
    'work it out from the screen'.

    Read once, before the window exists — Qt only takes a scale factor at
    start-up, so a change here applies on the next launch."""
    try:
        v = float(load_api_keys().get("ui_scale", 0) or 0)
    except (TypeError, ValueError):
        return 0.0
    return min(v, 3.0) if v >= 0.5 else 0.0


def save_ui_scale(scale: float) -> None:
    _save_flag("ui_scale", float(scale or 0))


# ── Live-session tuning ──────────────────────────────────────────────────────
# Everything here is optional and has a working default, so an untouched
# config behaves exactly like a configured one. Each value is also a way out:
# the setting exists because a real microphone, network or quota needed it.

def get_thinking_enabled() -> bool:
    """Whether background requests may use a thinking model.

    Off by default: it is slower and costs more tokens, and the workloads that
    benefit are the planning tools, which run on a separate non-Live model.
    """
    return bool(load_api_keys().get("thinking_enabled", False))


def save_thinking_enabled(enabled: bool) -> None:
    _save_flag("thinking_enabled", enabled)


def get_turn_tuning() -> dict:
    """How eagerly the server decides you have stopped speaking.

    OFF by default, and that default was earned. Cutting turns shorter looks
    like a free speed win and is not: proactive audio has to judge whether an
    utterance was even addressed to the assistant, and a turn clipped early
    gives it less to judge, so it stays quiet — and the reply to your first
    sentence only arrives once your second one has given it enough context.
    That reads as the assistant being a turn behind, which is far worse than
    the fraction of a second the tuning saves.

    Turn it on with "turn_tuning": {"enabled": true} if your own microphone and
    speaking pace suit it. `silence_ms` is the one that is felt: the pause the
    server sits through before accepting your turn is over.
    """
    cfg = load_api_keys().get("turn_tuning")
    cfg = cfg if isinstance(cfg, dict) else {}

    def _int(key, default, lo, hi):
        try:
            return max(lo, min(hi, int(cfg.get(key, default))))
        except (TypeError, ValueError):
            return default

    return {
        "enabled":    bool(cfg.get("enabled", False)),
        "silence_ms": _int("silence_ms", 550, 200, 3000),
        "prefix_ms":  _int("prefix_ms", 150, 0, 1000),
        # "high" = quicker to decide speech has ended.
        "end_sensitivity":   str(cfg.get("end_sensitivity", "high")).lower(),
        "start_sensitivity": str(cfg.get("start_sensitivity", "default")).lower(),
    }


def save_turn_tuning(values: dict) -> None:
    def _apply(data: dict) -> None:
        cur = data.get("turn_tuning")
        cur = dict(cur) if isinstance(cur, dict) else {}
        cur.update(values or {})
        data["turn_tuning"] = cur
    update_config(_apply)


def get_proactive_audio_enabled() -> bool:
    """Whether the model gets to decide an utterance was not aimed at it and
    stay quiet.

    On by default — it is what stops the assistant answering the room. But it
    is also the first thing to switch off if replies ever seem to arrive a turn
    late: what looks like lag is usually the model having judged your previous
    sentence as not addressed to it, and only changing its mind once the next
    one arrives.
    """
    return bool(load_api_keys().get("proactive_audio", True))


def save_proactive_audio_enabled(enabled: bool) -> None:
    _save_flag("proactive_audio", enabled)


MEDIA_RESOLUTIONS = ("default", "low", "medium", "high")


def get_media_resolution() -> str:
    """How finely the model tokenises the screenshots and camera frames it is
    sent. 'medium' keeps on-screen text readable at a fraction of the tokens a
    full-resolution image costs."""
    v = str(load_api_keys().get("media_resolution", "medium")).strip().lower()
    return v if v in MEDIA_RESOLUTIONS else "medium"


def save_media_resolution(value: str) -> None:
    v = str(value or "").strip().lower()
    _save_flag("media_resolution", v if v in MEDIA_RESOLUTIONS else "medium")


def _save_flag(key: str, value) -> None:
    """Read-modify-write one key without disturbing the rest of the config."""
    set_config_values(**{key: value})


def get_brief_enabled() -> bool:
    return load_api_keys().get("morning_brief_enabled", True)


def save_brief_enabled(enabled: bool) -> None:
    set_config_values(morning_brief_enabled=bool(enabled))


# ── Audio devices ────────────────────────────────────────────────────────────
# Stored as device NAMES, not sounddevice indices. Indices shift every time a
# USB device is plugged in or removed, so a saved index silently starts pointing
# at a different microphone. The empty string means "system default", which is
# both the factory setting and what an unresolvable saved device falls back to —
# so unplugging a headset degrades to the built-in speakers instead of crashing.

def _patch_config(**fields) -> None:
    """Set one or more keys in one locked write.

    Every setter in this file open-coded this. Collapsing it here means a new
    setting is one line, and there is one place where a concurrent write is
    handled instead of nine. Kept as a name because other modules call it.
    """
    set_config_values(**fields)


def get_input_device() -> str:
    """Microphone device name, or '' for the system default."""
    return (load_api_keys().get("input_device", "") or "").strip()


def save_input_device(name: str) -> None:
    _patch_config(input_device=(name or "").strip())


def get_output_device() -> str:
    """Speaker device name, or '' for the system default."""
    return (load_api_keys().get("output_device", "") or "").strip()


def save_output_device(name: str) -> None:
    _patch_config(output_device=(name or "").strip())


def get_plugin_enabled(plugin_name: str) -> bool:
    """Plugins are enabled by default the moment they're discovered (opt-out model)."""
    return load_api_keys().get("plugins_enabled", {}).get(plugin_name, True)


# ── Per-plugin settings ("tokens" / connection details) ───────────────────────
# Generic store so a plugin can declare its own config fields (PLUGIN_SETTINGS)
# and the settings UI renders + persists them WITHOUT any core edit — keeping the
# drop-in model intact. Values live under plugin_config[<namespace>][<key>].
# A namespace defaults to the plugin name, but a suite of plugins (e.g. the
# several printer plugins) can share ONE namespace.
def get_plugin_config(namespace: str) -> dict:
    """All stored values for a namespace (empty dict if none set yet)."""
    cfg = load_api_keys().get("plugin_config")
    val = cfg.get(namespace) if isinstance(cfg, dict) else None
    return dict(val) if isinstance(val, dict) else {}


def get_plugin_setting(namespace: str, key: str, default=None):
    """A single value from a namespace, or `default` if unset."""
    return get_plugin_config(namespace).get(key, default)


def save_plugin_config(namespace: str, values: dict) -> None:
    """Merge `values` into a namespace's stored config (read-modify-write, like
    every other helper here). Only the provided keys are touched."""
    def _apply(data: dict) -> None:
        pc = data.get("plugin_config")
        if not isinstance(pc, dict):
            pc = {}
        cur = pc.get(namespace)
        if not isinstance(cur, dict):
            cur = {}
        cur.update(values)
        pc[namespace] = cur
        data["plugin_config"] = pc
    update_config(_apply)


def save_plugin_enabled(plugin_name: str, enabled: bool) -> None:
    def _apply(data: dict) -> None:
        cfg = data.get("plugins_enabled")
        if not isinstance(cfg, dict):
            cfg = {}
        cfg[plugin_name] = bool(enabled)
        data["plugins_enabled"] = cfg
    update_config(_apply)

# ── Providers: local STT/LLM/TTS and non-Gemini APIs ─────────────────────────
# Stored here rather than in a file of their own, for the same reason plugin
# settings are: one config to back up, one already in .gitignore, one place a
# user knows to look.
#
# The important property is what happens when nobody has configured anything.
# `get_provider_mode()` returns "gemini" on a config that has never heard of
# providers, and every caller checks that BEFORE importing the providers
# package — so an ordinary install never executes a line of it. This is the
# whole basis of the claim that the folder costs nothing when unused.
PROVIDER_MODE_GEMINI = "gemini"      # the conversation runs on the Live API
PROVIDER_MODE_PIPELINE = "pipeline"  # STT -> LLM -> TTS, assembled from providers


def _upgrade_ids(block: dict) -> dict:
    """Give every catalog service its own id and its own stored settings.

    One provider serves Ollama, OpenAI, MiniMax and a dozen more, and they used
    to share ONE block of settings under "openai_compat" — so the fallback and
    ② THINKING could not be two different services, picking one overwrote the
    other's address, and an API key typed for MiniMax was sent to OpenAI after
    a switch. Each service is now "<provider>@<entry>", e.g.
    "openai_compat@minimax", with settings of its own.

    An older config is converted as it is read, not by a migration step: the
    shared block moves to the service its "catalog" key names (its key belonged
    to that service and nothing else), and every reference to it follows.
    Writing the providers block back persists it; until then nothing on disk
    changes."""
    creds = block.get("creds")
    if not isinstance(creds, dict):
        return block
    creds = dict(creds)
    moved: dict = {}
    for pid, cfg in list(creds.items()):
        if "@" in pid or not isinstance(cfg, dict):
            continue
        eid = str(cfg.get("catalog") or "").strip()
        if not eid:
            continue
        new = f"{pid}@{eid}"
        creds.setdefault(new, dict(cfg))
        del creds[pid]
        moved[pid] = new
    if not moved:
        return block
    block = dict(block)
    block["creds"] = creds
    pipe = block.get("pipeline")
    if isinstance(pipe, dict):
        block["pipeline"] = {k: moved.get(v, v) for k, v in pipe.items()}
    for key in ("sidecar", "coding"):
        if block.get(key) in moved:
            block[key] = moved[block[key]]
    return block


def get_providers() -> dict:
    """The whole providers block, or an empty dict."""
    val = load_api_keys().get("providers")
    return _upgrade_ids(dict(val)) if isinstance(val, dict) else {}


def get_provider_mode() -> str:
    """Which engine holds the conversation. Defaults to Gemini Live."""
    mode = str(get_providers().get("mode", "") or "").strip().lower()
    return mode if mode in (PROVIDER_MODE_GEMINI, PROVIDER_MODE_PIPELINE) \
        else PROVIDER_MODE_GEMINI


def get_provider_config(provider_id: str) -> dict:
    """Stored settings for one provider — address, model, key, limits."""
    creds = get_providers().get("creds")
    val = creds.get(provider_id) if isinstance(creds, dict) else None
    return dict(val) if isinstance(val, dict) else {}


def get_pipeline() -> dict:
    """Which provider fills each slot of the pipeline engine."""
    val = get_providers().get("pipeline")
    return dict(val) if isinstance(val, dict) else {}


def get_sidecar_provider() -> str:
    """The provider id used for one-shot calls when Gemini cannot answer them,
    or '' for none.

    Separate from the conversation on purpose: these are different jobs with
    different failure modes. Gemini's Live quota and its text quota are separate
    pools, and on the free tier it is the text pool that runs out first — which
    kills document reading, screen reasoning and code generation while the
    conversation carries on. Being able to point only those at another model,
    without changing the voice at all, is the cheapest useful thing this whole
    folder does.
    """
    return str(get_providers().get("sidecar", "") or "").strip()


def _patch_providers(**fields) -> None:
    def _apply(data: dict) -> None:
        p = data.get("providers")
        p = _upgrade_ids(dict(p)) if isinstance(p, dict) else {}
        p.update(fields)
        data["providers"] = p
    update_config(_apply)


def save_provider_mode(mode: str) -> None:
    mode = (mode or "").strip().lower()
    _patch_providers(mode=mode if mode in (PROVIDER_MODE_GEMINI,
                                           PROVIDER_MODE_PIPELINE)
                     else PROVIDER_MODE_GEMINI)


def save_provider_config(provider_id: str, values: dict) -> None:
    """Merge settings for one provider. Only the given keys are touched, so the
    panel can save one field without reading and rewriting the rest."""
    def _apply(data: dict) -> None:
        p = data.get("providers")
        p = _upgrade_ids(dict(p)) if isinstance(p, dict) else {}
        creds = p.get("creds")
        if not isinstance(creds, dict):
            creds = {}
        cur = creds.get(provider_id)
        cur = dict(cur) if isinstance(cur, dict) else {}
        cur.update(values or {})
        creds[provider_id] = cur
        p["creds"] = creds
        data["providers"] = p
    update_config(_apply)


def save_pipeline(stt: str = None, llm: str = None, tts: str = None) -> None:
    """Set one or more pipeline slots. `None` leaves a slot alone; '' clears it."""
    def _apply(data: dict) -> None:
        p = data.get("providers")
        p = _upgrade_ids(dict(p)) if isinstance(p, dict) else {}
        pipe = p.get("pipeline")
        pipe = dict(pipe) if isinstance(pipe, dict) else {}
        for slot, value in (("stt", stt), ("llm", llm), ("tts", tts)):
            if value is not None:
                pipe[slot] = str(value).strip()
        p["pipeline"] = pipe
        data["providers"] = p
    update_config(_apply)


def save_sidecar_provider(provider_id: str) -> None:
    _patch_providers(sidecar=(provider_id or "").strip())


def get_coding_provider() -> str:
    """The service dev_agent writes code with, or '' to use whatever answers
    background requests.

    Its own setting because coding is the one background job where the model
    matters most and the request is longest — somebody may well want a strong
    coding model there and something cheap and fast for reading the screen."""
    return str(get_providers().get("coding", "") or "").strip()


def save_coding_provider(provider_id: str) -> None:
    _patch_providers(coding=(provider_id or "").strip())


def get_sidecar_first() -> bool:
    """Whether the side-call provider is tried BEFORE Gemini rather than after.

    Off by default: measured in core/gemini.py, the Gemini rungs answer a short
    request in well under a second, and a local model on ordinary hardware does
    not. On means something specific — 'I would rather this stayed on my
    machine, and I accept it being slower' — so it is a choice someone makes,
    never a default they inherit.
    """
    return bool(get_providers().get("sidecar_first", False))


def save_sidecar_first(enabled: bool) -> None:
    _patch_providers(sidecar_first=bool(enabled))


def save_providers(mode: str = None, pipeline: dict = None, creds: dict = None,
                   sidecar: str = None, sidecar_first: bool = None,
                   coding: str = None) -> None:
    """Write the whole providers block in ONE file write.

    The settings panel used to call five setters in a row — one per provider's
    credentials, then the mode, then the pipeline, then the two side-call
    keys — and every one of them was a separate read-modify-write of
    api_keys.json. Five reads and five writes of the same file, in sequence,
    while the panel's own APPLY was already triggering a reconnect that makes
    main.py write to it too. Any interleaving loses whichever key was written
    first, and the one people noticed was the mode: set MY OWN SETUP, save,
    reopen, and it says Gemini again.

    `None` leaves a section alone; `creds` is merged per provider so a panel
    that only edited one does not have to send the others.
    """
    def _apply(data: dict) -> None:
        block = data.get("providers")
        block = _upgrade_ids(dict(block)) if isinstance(block, dict) else {}

        if mode is not None:
            m = str(mode).strip().lower()
            block["mode"] = m if m in (PROVIDER_MODE_GEMINI,
                                       PROVIDER_MODE_PIPELINE) else PROVIDER_MODE_GEMINI
        if pipeline is not None:
            current = block.get("pipeline")
            current = dict(current) if isinstance(current, dict) else {}
            current.update({k: str(v or "").strip() for k, v in pipeline.items()})
            block["pipeline"] = current
        if creds is not None:
            store = block.get("creds")
            store = dict(store) if isinstance(store, dict) else {}
            for pid, values in (creds or {}).items():
                one = store.get(pid)
                one = dict(one) if isinstance(one, dict) else {}
                one.update(values or {})
                store[pid] = one
            block["creds"] = store
        if sidecar is not None:
            block["sidecar"] = str(sidecar or "").strip()
        if sidecar_first is not None:
            block["sidecar_first"] = bool(sidecar_first)
        if coding is not None:
            block["coding"] = str(coding or "").strip()

        data["providers"] = block
    update_config(_apply)


# ── Language ─────────────────────────────────────────────────────────────────
# A setting with three states and one rule: "auto" means "ask the operating
# system", which is what a user who has already set their language in one place
# expects. It is stored as a string rather than a bool so a third locale needs
# no migration, and it is validated HERE rather than at the point of use —
# config_manager is the only module allowed to decide what a stored value means
# (see AGENTS.md), and a config file edited by hand must not be able to put an
# unknown locale into the window.

def get_ui_language() -> str:
    """The configured UI language: 'auto', or a locale we ship."""
    from core.i18n import LOCALES
    value = str(load_api_keys().get("ui_language", "auto") or "auto").lower()
    return value if value == "auto" or value in LOCALES else "auto"


def save_ui_language(language: str) -> None:
    """Persist the UI language, collapsing anything unknown to 'auto'.

    Unknown values become 'auto' rather than being rejected: a config written by
    a newer version, or edited by hand, must degrade to the OS language instead
    of leaving the window in a locale that has no catalogue.
    """
    from core.i18n import LOCALES
    value = (language or "auto").strip().lower()
    set_config_values(ui_language=value if value == "auto" or value in LOCALES
                      else "auto")
