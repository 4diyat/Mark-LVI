"""Boards 11, 12, 19, 7 and 13 — routines, quick tools, the gesture map, one
permission request, and the writing help page.

THE SPLIT BETWEEN THIS MODULE AND `pages_admin`
    Not importance: SUBJECT. This half is about what the user asks JARVIS to DO
    (what it remembers to do on a schedule, what it puts on the clipboard, what
    its hands can be told). The other half is about how the program is
    configured and what it can be trusted with.

BOARDS THAT DRAW SOMETHING THIS BUILD DOES NOT HAVE
    Board 11's routines: there is no scheduler. `actions/proactive.py` decides
    WHEN to speak, and it has a persisted pause, but nothing stores "Briefing
    pagi, setiap hari 06.30" — so the page lists the one routine that really
    exists (the proactive check, with its real pause state) and says plainly
    that scheduled routines are not built. Board 12's window layout and board
    19's gesture map are drawings of things this build cannot do, and they say
    so on the page as well as in `NOT-IN-MOCKUP.md`.

WHY THE DATA FUNCTIONS ARE SEPARATE FROM THE BUILDERS
    Every `*_rows()` here is importable and testable with no Qt, and the tests
    use them to check the page against its store. The builders below them place
    widgets and decide nothing.
"""
from __future__ import annotations

from ui.tray_pages import GEOMETRY, _at

from ui.page_kit import BODY_TOP, CONTENT_W, MARGIN, ROW_PITCH, at


def _safe(call, default):
    try:
        return call()
    except Exception as e:                       # noqa: BLE001
        print(f"[JARVIS] halaman tidak bisa membaca — {type(e).__name__}: {e}")
        return default


# ── board 11: routines and suggestions ──────────────────────────────────────

def suggestion_paused() -> bool:
    """The persisted pause `actions/proactive.py` keeps in the config file.

    READ THROUGH THE MODULE'S OWN READER, not by loading the config here: the
    key name and its file are that module's business, and a page that read
    `load_api_keys().get("...", False)` with its own copy of the key would go on
    reporting the old answer the day the key moved.
    """
    def read():
        from actions import proactive

        return bool(proactive._read_paused())

    return bool(_safe(read, False))


def routines() -> list[dict]:
    """The routines this build actually runs. Currently one, and it is real.

    THERE IS NO ROUTINE STORE. The artboard draws three scheduled routines with
    times and payloads; nothing in this program stores a schedule. The one thing
    that IS a routine — the proactive check that decides when JARVIS speaks —
    has a real on/off and a real persistence, so it is what the list shows. The
    page states the absence rather than drawing three rows nobody can edit.
    """
    return [{
        "key": "proactive",
        "name": "ui.page.routines.proactive.name",
        "when": "ui.page.routines.proactive.when",
        "what": "ui.page.routines.proactive.what",
        "on": not suggestion_paused(),
    }]


# ── board 12: quick tools ───────────────────────────────────────────────────

_SENSITIVE = (
    # (label key, pattern) — card-like digit groups, an email, or a key shape.
    ("ui.page.tools.kind.card", r"\b(?:\d[ -]?){13,19}\b"),
    ("ui.page.tools.kind.email", r"[\w.+-]+@[\w-]+\.[\w.]+"),
    ("ui.page.tools.kind.key", r"\b(?:sk-|AIza|ghp_)[\w-]{10,}"),
)


def clipboard_text() -> str:
    """What is on the clipboard, or "" when there is none / no module."""
    def read():
        from actions import computer_control

        return str(computer_control.pyperclip.paste() or "")

    return str(_safe(read, ""))


def sensitive_kind(text: str) -> str:
    """The label key for what kind of secret `text` looks like, or "".

    A PATTERN MATCH, NOT A VERDICT. The page says "Terdeteksi: nomor rekening",
    which is what a regex can honestly claim. It never says the number is safe
    or unsafe, and "Tandai aman" only marks it in this session — see
    `mark_safe`.
    """
    import re

    for label_key, pattern in _SENSITIVE:
        if re.search(pattern, str(text or "")):
            return label_key
    return ""


def find_files(query: str, limit: int = 3) -> list[str]:
    """Board 12's plain-language file search, answered by name matching.

    WHAT THIS IS NOT: it does not understand "faktur bulan lalu yang belum
    dibayar" — nothing in this build turns that sentence into a query. It
    matches the words the user typed against file names, which is honest and
    useful and is exactly what the page says it does.
    """
    from pathlib import Path

    words = [w for w in str(query or "").lower().split() if len(w) > 2]
    if not words:
        return []

    def scan():
        roots = [Path.home() / "Documents", Path.home() / "Downloads",
                 Path.home() / "Desktop"]
        hits = []
        for root in roots:
            if not root.is_dir():
                continue
            for path in root.rglob("*"):
                if len(hits) >= limit:
                    return hits
                if not path.is_file():
                    continue
                name = path.name.lower()
                if all(word in name for word in words):
                    hits.append(str(path))
        return hits

    return list(_safe(scan, []))


# ── board 19: the gesture map ───────────────────────────────────────────────

GESTURES = (
    ("ui.page.gestures.g1", "ui.page.gestures.g1.note"),
    ("ui.page.gestures.g2", "ui.page.gestures.g2.note"),
    ("ui.page.gestures.g3", "ui.page.gestures.g3.note"),
    ("ui.page.gestures.g4", "ui.page.gestures.g4.note"),
    ("ui.page.gestures.g5", "ui.page.gestures.g5.note"),
    ("ui.page.gestures.g6", "ui.page.gestures.g6.note"),
)


def gesture_rows() -> tuple:
    """The six gestures, as (name key, meaning key) pairs."""
    return GESTURES


# ── board 7: one permission, asked once ─────────────────────────────────────

CONSENT_KEY = "microphone_consent"


def consent_given() -> bool:
    """Whether the user has answered the microphone question.

    THE ANSWER IS STORED, THE QUESTION IS NOT REPEATED. An unanswered question
    is not a refusal — `findings` in the config file distinguishes the two, and
    the panel's own microphone switch reads the DEVICE, not this. This is the
    consent record, which is what board 7 is about.
    """
    def read():
        from memory.config_manager import load_api_keys

        return bool(load_api_keys().get(CONSENT_KEY, False))

    return bool(_safe(read, False))


def record_consent(allowed: bool) -> bool:
    """Store the answer. Returns whether it reached the file.

    `set_config_values` REPORTS a read-only config by returning False, and a page
    that ignored that would say "izin tercatat" about a write that did not
    happen — the exact class of lie this build keeps removing.
    """
    def write():
        from memory.config_manager import set_config_values

        return bool(set_config_values(**{CONSENT_KEY: bool(allowed)}))

    return bool(_safe(write, False))


# ── Qt ───────────────────────────────────────────────────────────────────────

def build_routines(panel, page) -> None:
    """Board 11: the routine list and the pause that is real."""
    from PyQt6.QtWidgets import QLabel, QPushButton

    from ui.tray_pages import _at

    page.hide()
    panel._pages["routines"] = page
    g = GEOMETRY
    panel._labels["rt_head"] = at(page, QLabel, g["rt_head"], "")
    panel._labels["rt_count"] = at(page, QLabel, g["rt_count"], "")
    panel._labels["rt_section"] = at(page, QLabel, g["rt_section"], "")

    for index, row in enumerate(routines()):
        y = BODY_TOP + index * ROW_PITCH
        panel._labels[f"rt_name:{index}"] = _at(page, QLabel, MARGIN + 18, y + 10,
                                                260, 18, "")
        panel._labels[f"rt_when:{index}"] = _at(page, QLabel, MARGIN + 18, y + 30,
                                                260, 16, "")
        panel._labels[f"rt_what:{index}"] = _at(page, QLabel, MARGIN + 18, y + 46,
                                                260, 16, "")

    panel._labels["rt_absent"] = at(page, QLabel, g["rt_absent"], "")
    panel._labels["rt_suggest_header"] = at(page, QLabel, g["rt_suggest"], "")
    panel._labels["rt_suggest_note"] = at(page, QLabel, g["rt_suggest_note"], "")
    panel._buttons["rt_pause"] = QPushButton("", page)
    panel._buttons["rt_pause"].setGeometry(*g["rt_pause"])
    panel._buttons["rt_pause"].clicked.connect(lambda: panel._call("routines_pause"))


def build_tools(panel, page) -> None:
    """Board 12: clipboard, file search, and the layout tool that is absent."""
    from PyQt6.QtWidgets import QLabel, QLineEdit, QPushButton


    page.hide()
    panel._pages["tools"] = page
    g = GEOMETRY
    panel._labels["tl_head"] = at(page, QLabel, g["tl_head"], "")
    panel._labels["tl_clip_header"] = at(page, QLabel, g["tl_clip_header"], "")
    panel._labels["tl_clip"] = at(page, QLabel, g["tl_clip"], "")
    panel._labels["tl_kind"] = at(page, QLabel, g["tl_kind"], "")

    for index, (name, x) in enumerate((("copy", 24), ("safe", 150), ("clear", 276))):
        button = QPushButton("", page)
        button.setGeometry(x, g["tl_btns_y"], 110, 30)
        button.clicked.connect(
            lambda _checked=False, k=name: panel._call(f"tools_{k}"))
        panel._buttons[f"tl_{name}"] = button

    panel._labels["tl_find_header"] = at(page, QLabel, g["tl_find_header"], "")
    panel._fields = getattr(panel, "_fields", {}) or {}
    field = QLineEdit(page)
    field.setGeometry(*g["tl_find_field"])
    field.returnPressed.connect(lambda: panel._call("tools_find", field.text()))
    panel._fields["tl_find"] = field
    for index in range(3):
        panel._labels[f"tl_hit:{index}"] = _at(
            page, QLabel, MARGIN, g["tl_hits_y"] + index * 22, CONTENT_W, 18, "")

    panel._labels["tl_snap_header"] = at(page, QLabel, g["tl_snap_header"], "")
    panel._labels["tl_snap_absent"] = at(page, QLabel, g["tl_snap_absent"], "")


def build_gestures(panel, page) -> None:
    """Board 19: six gestures, drawn and not clickable — the page says so."""
    from PyQt6.QtWidgets import QLabel


    page.hide()
    panel._pages["gestures"] = page
    g = GEOMETRY
    panel._labels["gs_head"] = at(page, QLabel, g["gs_head"], "")
    for index, (name_key, note_key) in enumerate(gesture_rows()):
        column, row = index % 2, index // 2
        x = MARGIN + column * 208
        y = 92 + row * 96
        panel._labels[f"gs_name:{index}"] = _at(page, QLabel, x, y, 190, 20, "")
        panel._labels[f"gs_note:{index}"] = _at(page, QLabel, x, y + 22, 190, 18, "")
        panel._labels[f"gs_name:{index}"]._key = name_key
        panel._labels[f"gs_note:{index}"]._key = note_key
    panel._labels["gs_absent"] = at(page, QLabel, g["gs_absent"], "")
    panel._labels["gs_note"] = at(page, QLabel, g["gs_note"], "")


def build_consent(panel, page) -> None:
    """Board 7: one permission, its reason, and the honest step count."""
    from PyQt6.QtWidgets import QLabel, QPushButton


    page.hide()
    panel._pages["consent"] = page
    g = GEOMETRY
    panel._labels["cn_head"] = at(page, QLabel, g["cn_head"], "")
    panel._labels["cn_step"] = at(page, QLabel, g["cn_step"], "")
    panel._labels["cn_name"] = at(page, QLabel, g["cn_name"], "")
    panel._labels["cn_why"] = at(page, QLabel, g["cn_why"], "")
    panel._labels["cn_when"] = at(page, QLabel, g["cn_when"], "")
    panel._labels["cn_done"] = at(page, QLabel, g["cn_done"], "")
    panel._buttons["cn_allow"] = QPushButton("", page)
    panel._buttons["cn_allow"].setGeometry(*g["cn_allow"])
    panel._buttons["cn_allow"].clicked.connect(
        lambda: panel._call("consent", True))
    panel._buttons["cn_deny"] = QPushButton("", page)
    panel._buttons["cn_deny"].setGeometry(*g["cn_deny"])
    panel._buttons["cn_deny"].clicked.connect(lambda: panel._call("page", "more"))


def build_help(panel, page) -> None:
    """Board 13: dictation and screen reading that exist; form filling that does not."""
    from PyQt6.QtWidgets import QLabel


    page.hide()
    panel._pages["help"] = page
    g = GEOMETRY
    panel._labels["hp_head"] = at(page, QLabel, g["hp_head"], "")
    panel._labels["hp_dictate_header"] = at(page, QLabel, g["hp_dictate_h"], "")
    panel._labels["hp_dictate"] = at(page, QLabel, g["hp_dictate"], "")
    panel._labels["hp_read_header"] = at(page, QLabel, g["hp_read_h"], "")
    panel._labels["hp_read"] = at(page, QLabel, g["hp_read"], "")
    panel._labels["hp_form_header"] = at(page, QLabel, g["hp_form_h"], "")
    panel._labels["hp_form_absent"] = at(page, QLabel, g["hp_form_absent"], "")


__all__ = ["GESTURES", "build_consent", "build_gestures", "build_help",
           "build_routines", "build_tools", "clipboard_text", "consent_given",
           "find_files", "gesture_rows", "record_consent", "routines",
           "sensitive_kind", "suggestion_paused"]
