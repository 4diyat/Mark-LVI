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

from ui.page_kit import MARGIN, at, text_box


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
    """Board 11, transcribed from `b11()`: 412x84 cards at pitch 96 from y=84.

    THE ARTBOARD DRAWS THREE ROUTINES WITH TIMES AND PAYLOADS. Nothing in this
    build stores a schedule — `actions/proactive` has one on/off and no table —
    so the page draws the ONE real routine in the first card's geometry, and
    says in the space the other two would take that there is no routine store.
    The three suggestion cards at y=406 are drawn at the artboard's pitch with
    the sentence that says the suggestion engine does not exist.
    """
    from PyQt6.QtWidgets import QLabel, QPushButton

    from ui.tray_pages import _at

    page.hide()
    panel._pages["routines"] = page

    # The first card's geometry, read from the drawing: (24, 84, 412, 84).
    panel._labels["rt_card:0"] = _at(page, QLabel, 24, 84, 412, 84, "")
    panel._labels["rt_name:0"] = _at(page, QLabel, 44, 102, 300, 20, "")
    panel._labels["rt_when:0"] = _at(page, QLabel, 44, 124, 300, 16, "")
    panel._labels["rt_what:0"] = _at(page, QLabel, 44, 142, 300, 16, "")
    # The pause is the artboard's toggle at (378, 114) — 40x22.
    panel._buttons["rt_pause"] = QPushButton("", page)
    panel._buttons["rt_pause"].setGeometry(378, 114, 40, 22)
    panel._buttons["rt_pause"].clicked.connect(lambda: panel._call("routines_pause"))

    # Cards 2 and 3 have nothing behind them: one sentence in their band.
    panel._labels["rt_absent"] = _at(page, QLabel, 24, 188, 412, 76, "")

    # SARAN PROAKTIF at 392, three 412x58 cards at y=406, pitch 68.
    panel._labels["rt_suggest_header"] = at(page, QLabel, text_box(24, 392, 10, width=240), "")
    for index in range(3):
        y = 406 + index * 68
        panel._labels[f"rt_suggest_card:{index}"] = _at(page, QLabel, 24, y, 412, 58, "")
    panel._labels["rt_suggest_note"] = _at(page, QLabel, 44, 424, 372, 40, "")

    # The artboard's footnote at 636 is below the panel's own 660 - 12 line,
    # so it moves to the free band under the last card: same copy, same column.
    panel._labels["rt_footnote"] = at(page, QLabel, text_box(24, 632, 10, width=412), "")


def build_tools(panel, page) -> None:
    """Board 12, transcribed from `b12()`: three cards at y=76, 244 and 420.

    THE ARTBOARD IS THREE CARDS AND THE PAGE HAD NONE. Clipboard at (24,76,
    412,150) with a 380x54 preview at 108 and three 32 px pills at 176; search
    at 244 with a 380x40 pill-shaped field at 276 and three hits at 338; layout
    at 420 with three 114x62 thumbnails at 452. Only the first two have
    backends; the third says so inside its own card.
    """
    from PyQt6.QtWidgets import QLabel, QLineEdit, QPushButton

    from ui.tray_pages import _at

    page.hide()
    panel._pages["tools"] = page

    # ── CLIPBOARD CERDAS ───────────────────────────────────────────────────
    panel._labels["tl_clip_card"] = _at(page, QLabel, 24, 76, 412, 150, "")
    panel._labels["tl_clip_header"] = _at(page, QLabel, 42, 88, 300, 18, "")
    panel._labels["tl_clip_box"] = _at(page, QLabel, 40, 108, 380, 54, "")
    panel._labels["tl_clip"] = _at(page, QLabel, 56, 116, 356, 18, "")
    panel._labels["tl_kind"] = _at(page, QLabel, 56, 136, 356, 18, "")
    for name, x, w in (("copy", 40, 110), ("safe", 158, 140), ("clear", 306, 114)):
        button = QPushButton("", page)
        button.setGeometry(x, 176, w, 32)
        button.clicked.connect(
            lambda _checked=False, k=name: panel._call(f"tools_{k}"))
        panel._buttons[f"tl_{name}"] = button

    # ── CARI BERKAS · BAHASA ALAMI ─────────────────────────────────────────
    panel._labels["tl_find_card"] = _at(page, QLabel, 24, 244, 412, 158, "")
    panel._labels["tl_find_header"] = _at(page, QLabel, 42, 256, 300, 18, "")
    panel._fields = getattr(panel, "_fields", {}) or {}
    field = QLineEdit(page)
    field.setGeometry(40, 276, 380, 40)
    field.returnPressed.connect(lambda: panel._call("tools_find", field.text()))
    panel._fields["tl_find"] = field
    for index in range(3):
        panel._labels[f"tl_hit:{index}"] = _at(
            page, QLabel, 60, 328 + index * 22, 356, 18, "")

    # ── SUSUN JENDELA: the card and its three thumbnails, stated absent ────
    panel._labels["tl_snap_card"] = _at(page, QLabel, 24, 420, 412, 176, "")
    panel._labels["tl_snap_header"] = _at(page, QLabel, 42, 432, 300, 18, "")
    for index, x in enumerate((40, 166, 292)):
        panel._labels[f"tl_snap_thumb:{index}"] = _at(page, QLabel, x, 452, 114, 62, "")
    # The sentence occupies the band the three thumbnails sit in (452..514),
    # leaving b12's own caption at 572 alone — the two are different claims and
    # stacking them overlapped one on the other.
    panel._labels["tl_snap_absent"] = _at(page, QLabel, 40, 456, 380, 52, "")


def build_gestures(panel, page) -> None:
    """Board 19: six gestures, drawn and not clickable — the page says so."""
    from PyQt6.QtWidgets import QLabel


    page.hide()
    panel._pages["gestures"] = page
    g = GEOMETRY
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
    """Board 7, transcribed from `b07()`.

    FOUR 97x4 SEGMENTS AT y=74, AND ONLY THE FIRST IS FILLED. The artboard
    draws a four-step onboarding ("Langkah 2 dari 4") and shows two segments
    lit. This build has ONE consent question — the microphone — so the first
    segment is lit, the other three are the unfilled track, and the header says
    "Langkah 1 dari 1". Drawing two lit segments would claim a second step
    nobody will ever be shown.
    """
    from PyQt6.QtWidgets import QLabel, QPushButton

    from ui.tray_pages import _at

    page.hide()
    panel._pages["consent"] = page

    for index in range(4):
        panel._labels[f"cn_step:{index}"] = _at(
            page, QLabel, 24 + index * 105, 74, 97, 4, "")

    panel._labels["cn_name"] = _at(page, QLabel, 24, 110, 412, 30, "")
    panel._labels["cn_why"] = at(page, QLabel, text_box(24, 154, 12, width=412), "")
    panel._labels["cn_card"] = _at(page, QLabel, 24, 174, 412, 190, "")
    panel._labels["cn_when"] = _at(page, QLabel, 44, 330, 372, 20, "")
    panel._labels["cn_what_header"] = at(page, QLabel, text_box(24, 400, 10, width=240), "")
    for index in range(3):
        panel._labels[f"cn_point:{index}"] = _at(
            page, QLabel, 50, 408 + index * 28, 372, 18, "")

    # The consent toggle is the artboard's own (24, 520) 40x22 control, and
    # the allow button is the 200x44 pill at (236, 566).
    panel._labels["cn_ack"] = _at(page, QLabel, 76, 522, 340, 20, "")
    # b07 draws BOTH a 40x22 toggle at (24,520) AND a 200x44 "Lanjut" pill at
    # (236,566). They are one decision — consent to the microphone — so they
    # share one handler and the page keeps them in the same state. Two controls
    # that could disagree about a permission is how a user ends up not knowing
    # whether they consented.
    panel._buttons["cn_toggle"] = QPushButton("", page)
    panel._buttons["cn_toggle"].setGeometry(24, 520, 40, 22)
    panel._buttons["cn_toggle"].clicked.connect(lambda: panel._call("consent"))
    panel._buttons["cn_deny"] = QPushButton("", page)
    panel._buttons["cn_deny"].setGeometry(24, 566, 196, 44)
    panel._buttons["cn_allow"] = QPushButton("", page)
    panel._buttons["cn_allow"].setGeometry(236, 566, 200, 44)
    panel._buttons["cn_allow"].clicked.connect(lambda: panel._call("consent"))


def build_help(panel, page) -> None:
    """Board 13, transcribed from `b13()`.

    THREE PANELS AND A PREVIEW STRIP. The artboard draws DIKTE (412x88 at 106),
    PEMBACA LAYAR (412x116 at 246 with a "Bacakan" pill at (44,330)), and ISI
    FORM (three 412x32 field rows at 432/488/544) over a cyan preview strip at
    578. Dictation and screen reading are real chords this build binds; form
    filling has no backend, so the three field rows are drawn at the artboard's
    coordinates and the strip says the preview is not applied to anything.

    THE FORM ROWS CARRY NO INVENTED VALUES. The artboard fills them with "PT
    Sinar Abadi", "FB-2026-0912", "Rp 12.400.000" — example data for a feature
    that does not exist. Each row shows its label and says the value would be
    proposed, never applied, because there is nothing to propose from.
    """
    from PyQt6.QtWidgets import QLabel, QPushButton

    from ui.tray_pages import _at

    page.hide()
    panel._pages["help"] = page

    panel._labels["hp_dictate_header"] = at(page, QLabel, text_box(24, 92, 10, width=300), "")
    panel._labels["hp_dictate_card"] = _at(page, QLabel, 24, 106, 412, 88, "")
    panel._labels["hp_dictate"] = _at(page, QLabel, 44, 128, 372, 44, "")

    panel._labels["hp_read_header"] = at(page, QLabel, text_box(24, 232, 10, width=300), "")
    panel._labels["hp_read_card"] = _at(page, QLabel, 24, 246, 412, 116, "")
    panel._labels["hp_read"] = _at(page, QLabel, 44, 262, 372, 60, "")
    # "Bacakan" is the screen reader the artboard draws. This build has the
    # screenshot chord and no speech synthesiser, so the pill names the chord
    # it can actually trigger rather than promising a voice it does not have.
    panel._buttons["hp_read"] = QPushButton("", page)
    panel._buttons["hp_read"].setGeometry(44, 330, 120, 26)
    panel._buttons["hp_read"].clicked.connect(lambda: panel._call("quick", "screenshot"))

    panel._labels["hp_form_header"] = at(page, QLabel, text_box(24, 396, 10, width=300), "")
    for index in range(3):
        y = 432 + index * 56
        panel._labels[f"hp_form_label:{index}"] = _at(
            page, QLabel, 24, y - 12, 300, 16, "")
        panel._labels[f"hp_form_field:{index}"] = _at(page, QLabel, 24, y, 412, 32, "")

    # The preview strip: cyan at 12% opacity in the artboard, and the sentence
    # inside it is why it exists — nothing here is applied to a form.
    panel._labels["hp_preview"] = _at(page, QLabel, 24, 578, 412, 34, "")


__all__ = ["GESTURES", "build_consent", "build_gestures", "build_help",
           "build_routines", "build_tools", "clipboard_text", "consent_given",
           "find_files", "gesture_rows", "record_consent", "routines",
           "sensitive_kind", "suggestion_paused"]
