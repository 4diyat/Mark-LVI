"""Boards 11, 12, 19, 7 and 13 — routines, quick tools, the gesture map, one
permission request, and the writing help page.

THE SPLIT BETWEEN THIS MODULE AND `pages_admin`
    Not importance: SUBJECT. This half is about what the user asks JARVIS to DO
    (what it remembers to do on a schedule, what it puts on the clipboard, what
    its hands can be told). The other half is about how the program is
    configured and what it can be trusted with.

BOARD 11 stores scheduled routines; its form accepts daily local time and a
command, and pagination reaches every saved row. Board 12's window-layout
preference does not arrange desktop windows.

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


def routines() -> list[dict] | None:
    """The scheduled routines this build stores and runs.

    THE STORE IS REAL NOW. `memory/routine_store.py` keeps the list and
    `core/routine_scheduler.py` fires what is due. Each row is a routine the
    owner created: a name, when it runs, and the command text it sends. The
    page draws as many cards as the store holds (up to the artboard's three)
    and says in the empty band when there are none yet.
    """
    def read():
        from memory.routine_store import default_store
        from core.routines import humanize_when

        rows = default_store().all()
        return [{
            "key": r.id,
            "name": r.name,
            "when": humanize_when(r.schedule),
            "what": r.payload,
            "on": r.enabled,
        } for r in rows]

    return _safe(read, None)



# ── board 12: quick tools ───────────────────────────────────────────────────

_SENSITIVE = (
    # (label key, pattern) — card-like digit groups, an email, or a key shape.
    ("ui.page.tools.kind.card", r"\b(?:\d[ -]?){13,19}\b"),
    ("ui.page.tools.kind.email", r"[\w.+-]+@[\w-]+\.[\w.]+"),
    ("ui.page.tools.kind.key", r"\b(?:sk-|AIza|ghp_)[\w-]{10,}"),
)


def clipboard_text() -> str | None:
    """Clipboard text, empty string for no text, or None if it cannot be read."""
    try:
        from actions import computer_control
        return str(computer_control.pyperclip.paste() or "")
    except Exception:  # unavailable clipboard is not an empty clipboard
        return None


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


def find_files(query: str, limit: int = 3, *, cancel=None) -> list[str]:
    """Match names in Documents, Downloads and Desktop; propagate scan errors.

    Called on a worker. Cancellation is cooperative between filesystem calls;
    an OS call that is already blocked cannot be interrupted here.
    """
    import os
    from pathlib import Path
    import stat

    words = [w for w in str(query or "").lower().split() if len(w) > 2]
    if not words or limit <= 0:
        return []
    cancelled = cancel or (lambda: False)
    def on_error(error):
        raise error

    hits = []
    for root in (Path.home() / "Documents", Path.home() / "Downloads", Path.home() / "Desktop"):
        if cancelled():
            return hits
        try:
            mode = root.stat().st_mode
        except (FileNotFoundError, NotADirectoryError):
            continue
        if not stat.S_ISDIR(mode):
            continue
        for directory, _dirs, files in os.walk(root, onerror=on_error):
            if cancelled():
                return hits
            for name in files:
                if cancelled():
                    return hits
                if all(word in name.lower() for word in words):
                    path = Path(directory) / name
                    try:
                        mode = path.stat().st_mode
                    except FileNotFoundError:
                        continue  # changed while walking
                    if stat.S_ISREG(mode):
                        hits.append(str(path))
                        if len(hits) >= limit:
                            return hits
    return hits


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
    """Board 11, transcribed from `b11()`: three 412x84 routine cards.

    THE STORE IS REAL NOW, so the page draws up to three routine cards from
    `memory/routine_store.py` — each with its name, when, payload, a pause
    toggle and a delete button. The builder stores an explicit daily time and
    command; pagination reaches additional rows. Suggestions are unavailable.
    """
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QLabel, QLineEdit, QPushButton

    from ui.tray_pages import _at

    page.hide()
    panel._pages["routines"] = page

    def routine_action(action, index, *args):
        ids = getattr(panel, "_routine_ids", ())
        if index < len(ids) and ids[index]:
            panel._call(action, ids[index], *args)
        panel.refresh()  # also undo a checked state if the action failed

    # Three routine cards at pitch 96 from y=84, each 412x84. Toggle at
    # (378, y+30); a delete button sits left of it at (320, y+30).
    for index in range(3):
        y = 84 + index * 96
        panel._labels[f"rt_card:{index}"] = _at(page, QLabel, 24, y, 412, 84, "")
        panel._labels[f"rt_name:{index}"] = _at(page, QLabel, 44, y + 18, 260, 20, "")
        panel._labels[f"rt_when:{index}"] = _at(page, QLabel, 44, y + 40, 260, 16, "")
        panel._labels[f"rt_what:{index}"] = _at(page, QLabel, 44, y + 58, 260, 16, "")
        for part in ("name", "when", "what"):
            panel._labels[f"rt_{part}:{index}"].setTextFormat(Qt.TextFormat.PlainText)
        toggle = QPushButton("", page)
        toggle.setGeometry(378, y + 30, 40, 22)
        toggle.setObjectName(f"rt_toggle:{index}")
        toggle.clicked.connect(lambda checked=False, i=index:
                               routine_action("routine_toggle", i, checked))
        panel._buttons[f"rt_toggle:{index}"] = toggle
        delete = QPushButton("", page)
        delete.setGeometry(320, y + 30, 40, 22)
        delete.setObjectName(f"rt_delete:{index}")
        delete.clicked.connect(lambda _c=False, i=index: routine_action("routine_delete", i))
        panel._buttons[f"rt_delete:{index}"] = delete

    # A deliberately narrow schedule: local HH:MM every day, plus the
    # actual command. No natural-language interpretation or guessed weekdays.
    panel._labels["rt_builder_label"] = _at(page, QLabel, 24, 366, 412, 18, "")
    edit = QLineEdit(page)
    edit.setGeometry(24, 388, 106, 30)
    edit.setObjectName("rt_builder_edit")
    panel._inputs["rt_builder_edit"] = edit
    command = QLineEdit(page)
    command.setGeometry(138, 388, 208, 30)
    command.setObjectName("rt_builder_command")
    panel._inputs["rt_builder_command"] = command
    create = QPushButton("", page)
    create.setGeometry(354, 388, 82, 30)
    create.setObjectName("rt_builder_create")
    create.clicked.connect(lambda _c=False: panel._call("routine_create"))
    panel._buttons["rt_builder_create"] = create
    note = _at(page, QLabel, 24, 420, 412, 32, "")
    note.setWordWrap(True)
    panel._labels["rt_builder_note"] = note

    status = _at(page, QLabel, 24, 452, 412, 18, "")
    status.setTextFormat(Qt.TextFormat.PlainText)
    panel._labels["rt_builder_status"] = status
    edit.textChanged.connect(lambda _text: status.setText(""))
    command.textChanged.connect(lambda _text: status.setText(""))
    panel._labels["rt_suggest_header"] = _at(page, QLabel, 24, 478, 412, 18, "")
    panel._labels["rt_suggest_note"] = _at(page, QLabel, 24, 498, 412, 30, "")
    panel._labels["rt_suggest_note"].setWordWrap(True)
    panel._labels["rt_more"] = _at(page, QLabel, 112, 575, 230, 18, "")
    def move_page(delta):
        panel._routine_page = getattr(panel, "_routine_page", 0) + delta
        panel.refresh()
    for key, x, delta in (("prev", 24, -1), ("next", 352, 1)):
        button = QPushButton("", page)
        button.setGeometry(x, 568, 84, 32)
        button.clicked.connect(lambda _c=False, d=delta: move_page(d))
        panel._buttons[f"rt_{key}"] = button
    panel._labels["rt_footnote"] = at(page, QLabel, text_box(24, 632, 10, width=412), "")


def build_tools(panel, page) -> None:
    """Board 12, transcribed from `b12()`: three cards at y=76, 244 and 420.

    THE ARTBOARD IS THREE CARDS AND THE PAGE HAD NONE. Clipboard at (24,76,
    412,150) with a 380x54 preview at 108 and three 32 px pills at 176; search
    at 244 with a 380x40 pill-shaped field at 276 and three hits at 338; layout
    at 420 with three 114x62 thumbnails at 452. Only the first two have
    backends; the third says so inside its own card.
    """
    from PyQt6.QtCore import Qt, QTimer
    from PyQt6.QtWidgets import QLabel, QLineEdit, QPushButton

    from ui.tray_pages import _at

    page.hide()
    panel._pages["tools"] = page

    # ── CLIPBOARD CERDAS ───────────────────────────────────────────────────
    panel._labels["tl_clip_card"] = _at(page, QLabel, 24, 76, 412, 150, "")
    panel._labels["tl_clip_header"] = _at(page, QLabel, 42, 88, 300, 18, "")
    panel._labels["tl_clip_box"] = _at(page, QLabel, 40, 108, 380, 54, "")
    panel._labels["tl_clip"] = _at(page, QLabel, 56, 116, 356, 18, "")
    panel._labels["tl_clip"].setTextFormat(Qt.TextFormat.PlainText)
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
    field.textChanged.connect(lambda _text: panel.invalidate_search())
    timer = QTimer(page)
    timer.setInterval(100)
    timer.timeout.connect(panel.poll_search)
    panel._search_timer = timer
    panel._fields["tl_find"] = field
    for index in range(3):
        panel._labels[f"tl_hit:{index}"] = _at(
            page, QLabel, 60, 328 + index * 22, 356, 18, "")

    # ── SUSUN JENDELA: the card and its three clickable thumbnails ────────
    # The artboard draws three thumbnails (2 kolom / 3 kolom / Fokus). Each is
    # a real button: picking one asks the layout policy to record the choice.
    panel._labels["tl_snap_card"] = _at(page, QLabel, 24, 420, 412, 176, "")
    panel._labels["tl_snap_header"] = _at(page, QLabel, 42, 432, 300, 18, "")
    for index, x in enumerate((40, 166, 292)):
        thumb = QPushButton("", page)
        thumb.setGeometry(x, 452, 114, 62)
        thumb.setObjectName(f"tl_snap_thumb:{index}")
        thumb.clicked.connect(
            lambda _checked=False, i=index: panel._call("tools_layout", i))
        panel._buttons[f"tl_snap_thumb:{index}"] = thumb
    panel._labels["tl_snap_note"] = _at(page, QLabel, 40, 528, 380, 46, "")
    panel._labels["tl_snap_note"].setWordWrap(True)
    for index, key in enumerate(("screenshot", "dictate")):
        button = QPushButton("", page)
        button.setGeometry(24 + 210 * index, 610, 202, 36)
        button.clicked.connect(lambda _checked=False, k=key: panel.press_quick(k))
        panel._buttons[f"tl_quick:{key}"] = button


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
    """Board 7: the four-step onboarding ladder, transcribed from `b07()`.

    FOUR 97x4 SEGMENTS AT y=74. The artboard draws a four-step onboarding
    ("Langkah 2 dari 4") — welcome, microphone consent, presence mode, and a
    summary. Each step has its own content in the card and its own controls
    at the bottom; the step indicator shows where the flow is.

    The three bottom controls are reused across the steps rather than drawn
    fresh per step, because the artboard's geometry is fixed: the deny button
    becomes "Back / Skip", the toggle becomes the presence-mode selector on
    the presence step, and the allow button is the step's primary action.
    """
    from PyQt6.QtWidgets import QLabel, QPushButton

    from ui.tray_pages import _at

    page.hide()
    panel._pages["consent"] = page

    # The four-step progress track, the step name, and the shared card.
    for index in range(4):
        panel._labels[f"cn_step:{index}"] = _at(
            page, QLabel, 24 + index * 105, 74, 97, 4, "")

    panel._labels["cn_name"] = _at(page, QLabel, 24, 110, 412, 30, "")
    panel._labels["cn_body"] = at(page, QLabel, text_box(24, 154, 12, width=412), "")
    panel._labels["cn_card"] = _at(page, QLabel, 24, 174, 412, 190, "")
    panel._labels["cn_when"] = _at(page, QLabel, 44, 330, 372, 20, "")
    panel._labels["cn_what_header"] = at(page, QLabel, text_box(24, 400, 10, width=240), "")
    for index in range(3):
        panel._labels[f"cn_point:{index}"] = _at(
            page, QLabel, 50, 408 + index * 28, 372, 18, "")

    # The consent toggle is the artboard's own (24, 520) 40x22 control. On the
    # presence step it is repurposed as the mode selector's readout; on the
    # other steps it mirrors the mic consent.
    panel._labels["cn_ack"] = _at(page, QLabel, 76, 522, 340, 20, "")
    panel._buttons["cn_toggle"] = QPushButton("", page)
    panel._buttons["cn_toggle"].setGeometry(24, 520, 40, 22)
    panel._buttons["cn_toggle"].setCheckable(True)
    panel._buttons["cn_toggle"].clicked.connect(lambda: panel._call("onboard_toggle"))
    panel._buttons["cn_deny"] = QPushButton("", page)
    panel._buttons["cn_deny"].setGeometry(24, 566, 196, 44)
    panel._buttons["cn_deny"].clicked.connect(lambda: panel._call("onboard_back"))
    panel._buttons["cn_allow"] = QPushButton("", page)
    panel._buttons["cn_allow"].setGeometry(236, 566, 200, 44)
    panel._buttons["cn_allow"].clicked.connect(lambda: panel._call("onboard_next"))


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
    from PyQt6.QtWidgets import QLabel, QLineEdit, QPushButton

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
        # The field row is an editable QLineEdit, not a label: the value the
        # plan will send is typed here, then reviewed in the strip before the
        # apply button sends it to the browser. (A QLineEdit is an input, so
        # the conformance audit's ALLOWED_GAPS carries the three row coords.)
        field = QLineEdit(page)
        field.setGeometry(24, y, 412, 32)
        field.setObjectName(f"hp_form_input:{index}")
        panel._inputs[f"hp_form_input:{index}"] = field

    # The preview strip: cyan at 12% opacity in the artboard. It starts by
    # saying nothing has been applied, and flips to the review/applied status
    # once the builder below is used.
    panel._labels["hp_preview"] = _at(page, QLabel, 24, 578, 412, 34, "")

    # THE BUILDER: a page URL field and a review-and-apply button, sitting in
    # the band under the preview strip. Board 13's form filling is review-first:
    # the plan is built, reviewed, and only then applied into the browser.
    panel._labels["hp_form_url_label"] = at(page, QLabel, text_box(24, 616, 10, width=200), "")
    url_edit = QLineEdit(page)
    url_edit.setGeometry(24, 630, 300, 24)
    url_edit.setObjectName("hp_form_url")
    panel._inputs["hp_form_url"] = url_edit
    apply_button = QPushButton("", page)
    apply_button.setGeometry(328, 630, 108, 24)
    apply_button.setObjectName("hp_form_apply")
    apply_button.clicked.connect(lambda: panel._call("form_fill_apply"))
    panel._buttons["hp_form_apply"] = apply_button


__all__ = ["GESTURES", "build_consent", "build_gestures", "build_help",
           "build_routines", "build_tools", "clipboard_text", "consent_given",
           "find_files", "gesture_rows", "record_consent", "routines",
           "sensitive_kind", "suggestion_paused"]
