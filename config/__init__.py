# config/__init__.py
"""The OS this copy of the app was configured for.

WHY `_MEIPASS` MATTERED HERE AND DOES NOT ANY MORE
    `_CONFIG_PATH` used to be built from `Path(__file__).parent`. Frozen with
    PyInstaller, `__file__` points inside the temporary extraction folder, so
    once the app was bundled this module read a config file that did not exist
    — and quietly returned {} from its bare `except`, which made every caller
    see "no OS configured" instead of an error. `memory/config_manager.py`
    already resolves the base directory correctly (next to the executable when
    frozen), so the file is looked for there. Where the user configured Windows
    is not a property of where the Python files happen to be sitting.
"""
import json
import platform
from pathlib import Path

try:
    # One definition of "where is the project", not two that disagree when
    # frozen. Imported lazily enough that a plain `import config` still works
    # from a checkout with no config/ folder at all.
    from memory.config_manager import CONFIG_FILE as _CONFIG_PATH
except Exception:  # pragma: no cover — only if memory/ is missing entirely
    _CONFIG_PATH = Path(__file__).resolve().parent.parent / "config" / "api_keys.json"


def _platform_os() -> str:
    """Auto-detect OS when config file is absent."""
    return {"Windows": "windows", "Darwin": "mac", "Linux": "linux"}.get(
        platform.system(), "linux"
    )


def get_config() -> dict:
    try:
        with open(_CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def get_os() -> str:
    """Returns: 'windows' | 'mac' | 'linux'"""
    return get_config().get("os_system", _platform_os()).lower()


def is_windows() -> bool: return get_os() == "windows"
def is_mac()     -> bool: return get_os() == "mac"
def is_linux()   -> bool: return get_os() == "linux"
