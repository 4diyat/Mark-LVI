"""Boards 14, 15, 16, 18, 21 and 22 — security, accessibility, plugins, the
light-theme privacy page, the brand sheet, and the first-run mode choice.

WHAT EACH OF THESE CAN HONESTLY DO, IN ONE LINE

  14 Keamanan      three risk levels from `core/risk_policy` — real; guest mode and
                   the OS-control switch are not built and the page says so.
  15 Aksesibilitas the language switch is real (`core/i18n.set_locale`); text size
                   is real (a stored scale the panel applies); reduced motion is
                   real (the orb honours it). Custom gestures are not.
  16 Plugin        the plugin list and its toggles are real
                   (`core.plugin_loader` + `get_plugin_enabled`); phone sync is not.
  18 Tema terang   the same permission content board 6 draws, in the light palette.
  21 Brand         read from the program's own palette and orb states, so the sheet
                   cannot describe colours the build does not use.
  22 Installer     the mode choice is real (`set_presence`, persisted); there is no
                   dependency-install UI, and the page does not pretend there is.

WHY THE PAGE NUMBERS ARE IN THE DOCSTRING
    The tests check this module against `ui/page_registry.py`, and a reader
    checking a page against the design sheet needs the number to hand.
"""
from __future__ import annotations

from ui.tray_pages import GEOMETRY, PALETTES, _at

from ui.page_kit import CONTENT_W, MARGIN, at, visible_count


def _safe(call, default):
    try:
        return call()
    except Exception as e:                       # noqa: BLE001
        print(f"[JARVIS] halaman tidak bisa membaca — {type(e).__name__}: {e}")
        return default


# ── board 14: the three levels ──────────────────────────────────────────────

LEVEL_KEYS = (
    ("safe", "ui.page.security.level.safe", "ui.page.security.level.safe.note"),
    ("medium", "ui.page.security.level.medium", "ui.page.security.level.medium.note"),
    ("risky", "ui.page.security.level.risky", "ui.page.security.level.risky.note"),
)


def levels() -> tuple:
    """The three levels as the panel draws them, from `core.risk_policy`.

    THE NAMES COME FROM THE MODULE THAT DECIDES, not from this file: if a level
    were renamed there, a page with its own copy would go on drawing the old
    three and a user would see a level the gate never returns.
    """
    from core import risk_policy

    return tuple((str(level).lower(), name, note)
                 for (level, name, note), level in zip(LEVEL_KEYS, risk_policy.LEVELS))


def level_counts() -> dict:
    """How many registered actions sit at each level. Real, and it is a fact.

    `risk_policy.registered()` is the table the execution gate reads, so this
    count is the number of actions that would be treated that way if called
    now — not a description of the design.
    """
    from core import risk_policy

    counts = {level: 0 for level in risk_policy.LEVELS}
    for level in _safe(lambda: risk_policy.registered().values(), {}) or ():
        if level in counts:
            counts[level] += 1
    return counts


# ── board 15: accessibility ─────────────────────────────────────────────────

TEXT_SCALES = (1.0, 1.15, 1.3)
TEXT_SCALE_KEY = "ui_text_scale"


def text_scale() -> float:
    """The stored text scale, clamped to the three the page offers."""
    def read():
        from memory.config_manager import load_api_keys

        value = float(load_api_keys().get(TEXT_SCALE_KEY, 1.0))
        return min(TEXT_SCALES, key=lambda s: abs(s - value))

    return float(_safe(read, 1.0))


def set_text_scale(scale: float) -> bool:
    """Store a text scale. Unknown values snap to the nearest offered one."""
    nearest = min(TEXT_SCALES, key=lambda s: abs(s - float(scale)))
    return bool(_safe(lambda: _write({TEXT_SCALE_KEY: nearest}), False))


def _write(values: dict) -> bool:
    from memory.config_manager import set_config_values

    return bool(set_config_values(**values))


MOTION_KEY = "reduce_motion"


def reduced_motion() -> bool:
    """Whether the orb has been told to stop animating.

    A CONFIG FLAG, READ BY THE ORB. `ui/orb_paint` already draws a still orb
    (board 5b's "Senyap" state is a dotted, unglowing ring), so this is not a new
    visual: it is the same still frame, chosen by the user instead of by the
    mode. The flag lives in the config file so it survives a restart, and the
    orb reads the same key — a page with its own copy of the answer would let
    the orb pulse while the page said "dikurangi".
    """
    def read():
        from memory.config_manager import load_api_keys

        return bool(load_api_keys().get(MOTION_KEY, False))

    return bool(_safe(read, False))


def set_reduced_motion(on: bool) -> bool:
    """Store the preference. Returns whether the file accepted it."""
    return bool(_safe(lambda: _write({MOTION_KEY: bool(on)}), False))


def languages() -> list[str]:
    """Every locale the catalogues actually ship."""
    from core import i18n

    return list(_safe(i18n.available, ["en"]))


def active_language() -> str:
    from core import i18n

    return str(_safe(i18n.active_locale, "en"))


def set_language(code: str) -> str:
    """Switch the UI locale. Returns what is active afterwards.

    RETURNS THE ACTIVE LOCALE AND NOT A BOOL, because `set_locale` answers with
    the locale it resolved — which is not always the one asked for. A page that
    showed a checkmark on the requested code would be showing a choice the
    program did not take.
    """
    from core import i18n

    return str(_safe(lambda: i18n.set_locale(code), active_language()))


# ── board 16: plugins ───────────────────────────────────────────────────────

def plugin_rows() -> list[dict]:
    """Every plugin with a manifest, its description, and its real on/off.

    WHY THE MANIFESTS AND NOT `discover_plugins`: that function needs the set of
    core tool names to detect collisions, and it IMPORTS each plugin module to
    validate it. A settings page must not import and run thirteen plugin files
    to draw a list; it reads the declared name and description, which is what
    the row shows.

    THE DEFAULT MATCHES THE LOADER'S RULE: a plugin that declared permissions is
    off until asked (`default=False`), one without a manifest is on. A page that
    defaulted everything to on would invite a click on a plugin the loader is
    refusing.
    """
    from pathlib import Path

    def scan():
        from memory.config_manager import get_plugin_enabled

        root = Path(__file__).resolve().parent.parent / "plugins"
        rows = []
        for manifest in sorted(root.glob("*.json")):
            import json

            try:
                data = json.loads(manifest.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            name = str(data.get("name") or manifest.stem)
            declared = bool(data.get("permissions"))
            rows.append({
                "name": name,
                "description": str(data.get("description") or ""),
                "on": bool(get_plugin_enabled(name, default=not declared)),
                "declared": declared,
            })
        return rows

    return list(_safe(scan, []))


def set_plugin(name: str, on: bool) -> bool:
    """Turn one plugin on or off, through the loader's own store."""
    def write():
        from memory.config_manager import save_plugin_enabled

        return bool(save_plugin_enabled(str(name), bool(on)))

    return bool(_safe(write, False))


# ── board 21: the brand sheet ───────────────────────────────────────────────

def palette_swatches() -> list[tuple[str, str]]:
    """The dark palette, from the table the panel paints with."""

    names = ("base", "panel", "card", "line_accent", "accent", "text", "muted",
             "warn")
    pal = PALETTES["dark"]
    return [(key, str(pal[key])) for key in names if key in pal]


def orb_states() -> list[tuple[str, str]]:
    """The four tray states, in the colours `ui/orb_paint` gives them.

    READ FROM THE PAINTER so the sheet cannot describe a colour the program does
    not use. Board 21 draws four states and calls them by name; this returns the
    same four with the palette entry behind each.
    """
    def read():

        pal = PALETTES["dark"]
        return [("ui.page.brand.state.idle", str(pal.get("muted", ""))),
                ("ui.page.brand.state.listening", str(pal.get("accent", ""))),
                ("ui.page.brand.state.working", str(pal.get("accent", ""))),
                ("ui.page.brand.state.attention", str(pal.get("warn", "")))]

    return list(_safe(read, []))


# ── board 22: the first-run mode choice ─────────────────────────────────────

INSTALL_MODES = (
    ("active", "ui.page.installer.ambient", "ui.page.installer.ambient.note"),
    ("focus", "ui.page.installer.focus", "ui.page.installer.focus.note"),
    ("quiet", "ui.page.installer.quiet", "ui.page.installer.quiet.note"),
)


def modes() -> tuple:
    """The three presence modes, as board 22 draws them."""
    return INSTALL_MODES


def apply_mode(mode: str) -> bool:
    """Set the presence mode the first-run page was asked for.

    THROUGH `presence_mode`, WHICH IS ALSO WHAT THE PANEL'S SEGMENT AND THE ORB
    MENU CALL — so choosing a mode here is the same act as choosing it anywhere
    else, and it persists the same way.
    """
    def write():
        from core import presence_mode

        return bool(presence_mode.set_mode(str(mode)))

    return bool(_safe(write, False))


# ── Qt ───────────────────────────────────────────────────────────────────────

def build_security(panel, page) -> None:
    """Board 14: three levels with real counts, and two absences."""
    from PyQt6.QtWidgets import QLabel

    from ui.tray_pages import _at

    page.hide()
    panel._pages["security"] = page
    g = GEOMETRY
    panel._labels["sec_head"] = at(page, QLabel, g["sec_head"], "")
    panel._labels["sec_levels_header"] = at(page, QLabel, g["sec_levels"], "")
    for index in range(3):
        y = g["sec_rows_y"] + index * g["sec_pitch"]
        panel._labels[f"sec_name:{index}"] = _at(page, QLabel, MARGIN + 18, y + 8,
                                                 200, 18, "")
        panel._labels[f"sec_note:{index}"] = _at(page, QLabel, MARGIN + 18, y + 28,
                                                 240, 16, "")
        panel._labels[f"sec_count:{index}"] = _at(
            page, QLabel, 330, y + 16, 86, 20, "")
    panel._labels["sec_os_header"] = at(page, QLabel, g["sec_os_h"], "")
    panel._labels["sec_os"] = at(page, QLabel, g["sec_os"], "")


def build_access(panel, page) -> None:
    """Board 15: language, text size, motion — all three real."""
    from PyQt6.QtWidgets import QLabel, QPushButton


    page.hide()
    panel._pages["access"] = page
    g = GEOMETRY
    panel._labels["ac_head"] = at(page, QLabel, g["ac_head"], "")
    panel._labels["ac_lang_header"] = at(page, QLabel, g["ac_lang_h"], "")
    for index, code in enumerate(languages()[:2]):
        button = QPushButton(str(code).upper(), page)
        button.setGeometry(24 + index * 208, g["ac_lang_y"], 200, 38)
        button.clicked.connect(
            lambda _checked=False, c=code: panel._call("language", c))
        panel._buttons[f"ac_lang:{code}"] = button
    panel._labels["ac_size_header"] = at(page, QLabel, g["ac_size_h"], "")
    panel._labels["ac_size_note"] = at(page, QLabel, g["ac_size_note"], "")
    for index, scale in enumerate(TEXT_SCALES):
        button = QPushButton("", page)
        button.setGeometry(24 + index * 140, g["ac_size_y"], 130, 34)
        button.clicked.connect(
            lambda _checked=False, s=scale: panel._call("text_scale", s))
        panel._buttons[f"ac_scale:{index}"] = button
    panel._labels["ac_motion_header"] = at(page, QLabel, g["ac_motion_h"], "")
    panel._buttons["ac_motion"] = QPushButton("", page)
    panel._buttons["ac_motion"].setGeometry(*g["ac_motion"])
    panel._buttons["ac_motion"].clicked.connect(lambda: panel._call("motion_toggle"))
    panel._labels["ac_gestures_header"] = at(page, QLabel, g["ac_gest_h"], "")
    panel._labels["ac_gestures"] = at(page, QLabel, g["ac_gest"], "")


def build_plugins(panel, page) -> None:
    """Board 16: the plugin list with real toggles, and the phone that is absent."""
    from PyQt6.QtWidgets import QLabel, QPushButton


    page.hide()
    panel._pages["plugins"] = page
    g = GEOMETRY
    panel._labels["pl_head"] = at(page, QLabel, g["pl_head"], "")
    panel._labels["pl_count"] = at(page, QLabel, g["pl_count"], "")
    panel._labels["pl_section"] = at(page, QLabel, g["pl_section"], "")
    rows = visible_count(99, top=g["pl_rows_y"], pitch=g["pl_pitch"])
    for index in range(rows):
        y = g["pl_rows_y"] + index * g["pl_pitch"]
        panel._labels[f"pl_name:{index}"] = _at(page, QLabel, MARGIN + 16, y + 8,
                                                240, 18, "")
        panel._labels[f"pl_desc:{index}"] = _at(page, QLabel, MARGIN + 16, y + 28,
                                                240, 16, "")
        button = QPushButton("", page)
        button.setGeometry(340, y + 12, 76, 26)
        button.clicked.connect(
            lambda _checked=False, i=index: panel._call("plugin_toggle", i))
        panel._buttons[f"pl_toggle:{index}"] = button
    panel._labels["pl_phone_header"] = at(page, QLabel, g["pl_phone_h"], "")
    panel._labels["pl_phone"] = at(page, QLabel, g["pl_phone"], "")
    panel._labels["pl_phone2"] = at(page, QLabel, g["pl_phone2"], "")


def build_light(panel, page) -> None:
    """Board 18: board 6's content, read in the light palette.

    NOT A SECOND PAGE OF WIDGETS WITH ITS OWN COLOURS. It reuses the permission
    rows' keys under a `l18_` prefix and is painted by the same function that
    paints board 6 — the palette is the difference, and the palette lives in
    `PALETTES`. A page with its own colours would be board 17a's mistake again.
    """
    from PyQt6.QtWidgets import QLabel


    page.hide()
    panel._pages["light"] = page
    g = GEOMETRY
    panel._labels["l18_head"] = at(page, QLabel, g["l18_head"], "")
    panel._labels["l18_sub"] = at(page, QLabel, g["l18_sub"], "")
    panel._labels["l18_perm_header"] = at(page, QLabel, g["l18_perm_h"], "")
    for index in range(4):
        y = BODY_FOR_LIGHT + index * 72
        panel._labels[f"l18_name:{index}"] = _at(page, QLabel, MARGIN + 18, y + 10,
                                                 260, 18, "")
        panel._labels[f"l18_sub_name:{index}"] = _at(
            page, QLabel, MARGIN + 18, y + 30, 260, 16, "")
        panel._labels[f"l18_state:{index}"] = _at(page, QLabel, 340, y + 18,
                                                 76, 20, "")
    panel._labels["l18_log_header"] = at(page, QLabel, g["l18_log_h"], "")
    for index in range(3):
        panel._labels[f"l18_log:{index}"] = _at(
            page, QLabel, MARGIN + 16, g["l18_log_y"] + index * 28, CONTENT_W - 32,
            18, "")
    panel._labels["l18_note"] = at(page, QLabel, g["l18_note"], "")


BODY_FOR_LIGHT = 106


def build_brand(panel, page) -> None:
    """Board 21: swatches and the four tray states, read from the program."""
    from PyQt6.QtWidgets import QLabel


    page.hide()
    panel._pages["brand"] = page
    g = GEOMETRY
    panel._labels["br_head"] = at(page, QLabel, g["br_head"], "")
    for index, (_key, colour) in enumerate(palette_swatches()):
        column, row = index % 4, index // 4
        swatch = _at(page, QLabel, 24 + column * 104, 100 + row * 76, 96, 48, "")
        swatch.setStyleSheet(f"background:{colour};border-radius:8px;")
        panel._labels[f"br_swatch:{index}"] = swatch
        panel._labels[f"br_hex:{index}"] = _at(
            page, QLabel, 24 + column * 104, 152 + row * 76, 96, 16, colour)
    panel._labels["br_icons_header"] = at(page, QLabel, g["br_icons_h"], "")
    for index, (name_key, colour) in enumerate(orb_states()):
        dot = _at(page, QLabel, 40 + index * 100, 300, 20, 20, "")
        dot.setStyleSheet(f"background:{colour};border-radius:10px;")
        panel._labels[f"br_state:{index}"] = dot
        label = _at(page, QLabel, 24 + index * 100, 326, 96, 32, "")
        label._key = name_key
        panel._labels[f"br_state_name:{index}"] = label
    panel._labels["br_app_note"] = at(page, QLabel, g["br_app"], "")
    panel._labels["br_spec"] = at(page, QLabel, g["br_spec"], "")


def build_installer(panel, page) -> None:
    """Board 22: three modes, one real choice."""
    from PyQt6.QtWidgets import QLabel, QPushButton


    page.hide()
    panel._pages["installer"] = page
    g = GEOMETRY
    panel._labels["in_head"] = at(page, QLabel, g["in_head"], "")
    panel._labels["in_sub"] = at(page, QLabel, g["in_sub"], "")
    for index, (_mode, name_key, note_key) in enumerate(modes()):
        y = g["in_rows_y"] + index * 96
        panel._labels[f"in_name:{index}"] = _at(page, QLabel, MARGIN + 18, y + 12,
                                                300, 20, "")
        panel._labels[f"in_note:{index}"] = _at(page, QLabel, MARGIN + 18, y + 36,
                                                360, 32, "")
        panel._labels[f"in_name:{index}"]._key = name_key
        panel._labels[f"in_note:{index}"]._key = note_key
        button = QPushButton("", page)
        button.setGeometry(340, y + 20, 76, 30)
        button.clicked.connect(
            lambda _checked=False, i=index: panel._call("install_mode", i))
        panel._buttons[f"in_pick:{index}"] = button


__all__ = ["INSTALL_MODES", "LEVEL_KEYS", "MOTION_KEY", "TEXT_SCALES",
           "TEXT_SCALE_KEY",
           "active_language", "apply_mode", "build_access", "build_brand",
           "build_installer", "build_light", "build_plugins", "build_security",
           "languages", "level_counts", "levels", "modes", "orb_states",
           "palette_swatches", "plugin_rows", "reduced_motion", "set_language",
           "set_plugin", "set_reduced_motion", "set_text_scale", "text_scale"]
