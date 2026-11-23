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

from ui.board_geometry import BOARDS
from ui.tray_pages import GEOMETRY, PALETTES, _at

from ui.page_kit import MARGIN, at, text_box


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


def set_text_scale(scale) -> bool:
    """Store a text scale. Unknown values snap to the nearest offered one.

    `"next"` CYCLES, because the artboard draws a SLIDER and this panel has no
    drag handling: pressing the track is the one gesture available, and a
    control that always set the same value would be a slider that only ever
    slides one way. The knob and the "Sedang · 14 px" line show where it
    landed, which is what a slider is for.
    """
    if str(scale).strip().lower() == "next":
        current = text_scale()
        index = min(range(len(TEXT_SCALES)),
                    key=lambda i: abs(TEXT_SCALES[i] - current))
        scale = TEXT_SCALES[(index + 1) % len(TEXT_SCALES)]
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

def _plugin_label(name: str) -> str:
    """The catalogue key for a plugin id. See `ui/plugin_labels.py`.

    The table moved out of this file when it took the page past its 600-line
    ceiling — a lookup is not page logic.
    """
    from ui.plugin_labels import label_for

    return label_for(name)


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
                # THE ROW SHOWS A NAME AND A VERSION PAIR, as board 16 does
                # ("Penjadwal" over "1.4.0 · resmi"). A manifest carries the
                # module id, the version and whether it declared permissions —
                # NOT a display name and NOT whether it is "resmi". So the pair
                # is built from those three facts: the catalogue's name for the
                # id where one exists (and the id where it does not, so nothing
                # is invented), the real version, and "resmi" only when the
                # plugin declares no permissions — the loader's own distinction
                # between a sandboxed plugin and one that asks for the machine.
                "label": _plugin_label(name),
                "version": str(data.get("version") or ""),
                # THE SECOND LINE IS THE VERSION AND THE SECURITY LEVEL, both
                # of which the manifest states. It is NOT "resmi · pihak
                # ketiga": this build has no notion of an official plugin —
                # all fifteen carry `author: MARK-LVI` and all fifteen declare
                # permissions, so a rule of "official when it declares none"
                # would print "third party" on every row, a claim about
                # provenance the manifest cannot support. `level` (safe /
                # medium / risky) is what `plugins/*.json` actually says about
                # how much a plugin is trusted, and it is what the loader acts
                # on. The artboard's layout holds; the word in it is real.
                "level": ("ui.page.plugins.level." + str(data.get("level") or "medium")
                          if str(data.get("level") or "medium")
                          in ("safe", "medium", "risky") else ""),
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
    """Board 14, transcribed from `b14()`.

    THE NUMBERS ARE THE DRAWING'S, AND THE FIRST VERSION'S WERE NOT. It used a
    66 px pitch where the artboard draws 76 — three rows of 64 px cards at
    y=302, 378, 454 — so the third level sat 30 px high and the OS-control card
    overlapped it. `tests/test_board_conformance.py` compares this page with the
    generated table.

    THE TWO ABSENCES STAY AND ARE NAMED IN PLACE. b14 draws "MODE TAMU" with a
    toggle and a "Kontrol OS dinonaktifkan" card. 06a's guest mode is deleted by
    ruling and no OS control exists, so the page draws the section header and
    one sentence saying both are absent — in the same band the artboard gives
    them, not dropped and not faked.
    """
    from PyQt6.QtWidgets import QLabel

    from ui.tray_pages import _at

    page.hide()
    panel._pages["security"] = page
    geo = BOARDS["security"]

    # The three risk cards, read from the drawing: 412x64 at pitch 76.
    cards = [r for r in geo["rects"] if r[2] == 412 and r[3] == 64]
    panel._labels["sec_levels_header"] = at(page, QLabel, text_box(24, 288, 10, width=240), "")
    for index, (x, y, w, h, _r) in enumerate(cards):
        panel._labels[f"sec_card:{index}"] = _at(page, QLabel, x, y, w, h, "")
        panel._labels[f"sec_name:{index}"] = _at(page, QLabel, x + 20, y + 12, 200, 20, "")
        panel._labels[f"sec_note:{index}"] = _at(page, QLabel, x + 20, y + 34, 280, 18, "")
        panel._labels[f"sec_count:{index}"] = _at(page, QLabel, x + 300, y + 22, 90, 20, "")

    # MODE TAMU / KONTROL OS: the header stays where b14 puts it, the card the
    # artboard draws under it becomes the sentence naming both absences.
    panel._labels["sec_os_header"] = at(page, QLabel, text_box(24, 176, 10, width=240), "")
    panel._labels["sec_os"] = _at(page, QLabel, 24, 190, 412, 66, "")
    # The artboard's amber-bordered card at (24,540,412,76). It is the second
    # of the two absences and it keeps the drawing's geometry: the card exists,
    # the control it describes does not.
    panel._labels["sec_os_card"] = _at(page, QLabel, 24, 540, 412, 76, "")


def build_plugins(panel, page) -> None:
    """Board 16, transcribed from `b16()`.

    THREE 412x60 PLUGIN CARDS AT PITCH 70 FROM y=106, a 40x22 dot at x=378 on
    each, then the phone card the artboard draws at 360. The built page had the
    rows as bare text with a 76 px "ON/OFF" rectangle — no cards, and a control
    that read as a button rather than the switch b16 draws.

    THE PHONE CARD IS DRAWN AND SAYS THERE IS NO DEVICE. `b16()` fills it with
    "Pixel 8 · terhubung" and a pairing code; no pairing backend exists, so the
    card keeps the artboard's geometry and its sentences say so. The pairing
    code is not typed: a "4 7 9 2 1 5" drawn as a literal is a code nobody
    issued.
    """
    from PyQt6.QtWidgets import QLabel, QPushButton

    page.hide()
    panel._pages["plugins"] = page

    panel._labels["pl_section"] = at(page, QLabel, text_box(24, 92, 10, width=240), "")
    # THREE ROWS, THE ARTBOARD'S NUMBER, and a sentence for the rest: b16 draws
    # three cards at pitch 70 and puts the phone card at 360, so a fourth row
    # would land on it. The header's count is of the STORE, not of these rows.
    panel._labels["pl_more"] = at(page, QLabel, text_box(24, 316, 10, width=412), "")
    for index in range(3):
        y = 106 + index * 70
        panel._labels[f"pl_card:{index}"] = _at(page, QLabel, 24, y, 412, 60, "")
        # THE TWO BASELINES ARE `b16()`'s: the name at y+26 in 12.5 px and the
        # version line at y+45 in 10 px. `text_box` converts baseline to a Qt
        # top (baseline - 0.72*size) — the conversion every other page uses and
        # `tests/test_tray_geometry.py` already pins for `n05`. The first
        # version used hand-typed tops of y+12 and y+32, which sat the words 5
        # and 6 px above the drawing: close enough to look right in a box
        # overlay, and wrong.
        panel._labels[f"pl_name:{index}"] = at(
            page, QLabel, text_box(44, y + 26, 12.5, width=300), "")
        panel._labels[f"pl_desc:{index}"] = at(
            page, QLabel, text_box(44, y + 45, 10, width=300), "")
        button = QPushButton("", page)
        button.setGeometry(378, y + 19, 40, 22)
        button.clicked.connect(
            lambda _checked=False, i=index: panel._call("plugin_toggle", i))
        panel._buttons[f"pl_toggle:{index}"] = button

    # SINKRON PONSEL at 346, the 412x130 card at 360, the phone silhouette at
    # (44,380) and (50,390), the "Putuskan" pill at (120,458).
    panel._labels["pl_phone_header"] = at(page, QLabel, text_box(24, 346, 10, width=300), "")
    panel._labels["pl_phone_card"] = _at(page, QLabel, 24, 360, 412, 130, "")
    panel._labels["pl_phone_shape"] = _at(page, QLabel, 44, 380, 56, 90, "")
    panel._labels["pl_phone"] = _at(page, QLabel, 120, 390, 300, 20, "")
    panel._labels["pl_phone2"] = _at(page, QLabel, 120, 408, 300, 40, "")

    # The divider and the pairing-code box: the box is drawn, the code is not.
    rule = QLabel(page)
    rule.setGeometry(24, 506, 412, 1)
    rule.setStyleSheet(f"background:{PALETTES['dark']['line']};")
    panel._labels["pl_rule"] = rule
    panel._labels["pl_code_header"] = at(page, QLabel, text_box(24, 536, 10, width=300), "")
    # THE BOX IS DRAWN AND THE CODE IS NOT. `b16()` prints "4 7 9 2 1 5" —
    # characters at 30 px intervals across the whole strip — plus "berlaku 5
    # menit" at x=300. No pairing backend exists, so that code is a number this
    # program never issued: exactly the plausible fake the owner's ruling
    # forbids. The box keeps the artboard's 412x46 rectangle and its size; its
    # text starts at the SAME left edge as the digits and is the sentence
    # instead. Drawing the six characters and the sentence together would put
    # two strings in one 46 px strip.
    panel._labels["pl_code_box"] = _at(page, QLabel, 24, 550, 412, 46, "")


def build_light(panel, page) -> None:
    """Board 18, transcribed from `b18()`: board 6's layout in light tokens.

    NOT A SECOND PAGE OF WIDGETS WITH ITS OWN COLOURS. `b18()` draws exactly
    the permission page — four 412x62 cards at 106, a 412x118 log box at 426,
    two 200x40 pills at 574, the same words — and differs only in the palette.
    So this page is board 6 with the `l18_` prefix and the palette comes from
    `PALETTES[panel._theme]`. A page carrying its own colours would be board
    17a's mistake again.
    """
    from PyQt6.QtWidgets import QLabel, QPushButton

    page.hide()
    panel._pages["light"] = page

    panel._labels["l18_perm_header"] = at(page, QLabel, text_box(24, 92, 10, width=300), "")
    for index in range(4):
        y = 106 + index * 72
        # The card, the name, the subtitle and the 40x22 dot at x=378 — the
        # four things b18 draws per row, at b18's own coordinates.
        panel._labels[f"l18_card:{index}"] = _at(page, QLabel, 24, y, 412, 62, "")
        panel._labels[f"l18_name:{index}"] = _at(page, QLabel, 44, y + 16, 300, 18, "")
        panel._labels[f"l18_sub_name:{index}"] = _at(
            page, QLabel, 44, y + 35, 300, 16, "")
        panel._labels[f"l18_state:{index}"] = _at(page, QLabel, 378, y + 20, 40, 22, "")

    panel._labels["l18_log_header"] = at(page, QLabel, text_box(24, 412, 10, width=300), "")
    panel._labels["l18_log_box"] = _at(page, QLabel, 24, 426, 412, 118, "")
    for index in range(3):
        panel._labels[f"l18_log:{index}"] = _at(
            page, QLabel, 40, 438 + index * 32, 380, 20, "")

    panel._buttons["l18_clear"] = QPushButton("", page)
    panel._buttons["l18_clear"].setGeometry(24, 574, 200, 40)
    panel._buttons["l18_clear"].clicked.connect(lambda: panel._call("history_clear"))
    panel._buttons["l18_export"] = QPushButton("", page)
    panel._buttons["l18_export"].setGeometry(236, 574, 200, 40)
    panel._buttons["l18_export"].clicked.connect(
        lambda: panel._call("history_export"))


def build_brand(panel, page) -> None:
    """Board 21: swatches and the four tray states, read from the program."""
    from PyQt6.QtWidgets import QLabel


    page.hide()
    panel._pages["brand"] = page
    g = GEOMETRY
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
           "active_language", "apply_mode", "build_brand",
           "build_installer", "build_light", "build_plugins", "build_security",
           "languages", "level_counts", "levels", "modes", "orb_states",
           "palette_swatches", "plugin_rows", "reduced_motion", "set_language",
           "set_plugin", "set_reduced_motion", "set_text_scale", "text_scale"]
