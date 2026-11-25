"""What the tray panel SHOWS, decided without Qt.

WHY THIS IS SEPARATE FROM THE WIDGET
    Boards 5, 23, 26, 27 and 28 draw one panel in five states. Five states of
    one surface means the risk is not in drawing it, it is in the panel and the
    rest of the program disagreeing about what is true: the panel saying "Fokus
    aktif" after the mode was changed from elsewhere, a count of held toasts
    that stops at 3 because it was captured when the widget was built, an Undo
    button for something already undone.

    So every value the panel renders is computed HERE, from the modules that
    already own it (`core.presence_mode`, `core.suggestion_quota`, `core.undo`,
    `core.audit_log`, `core.mic_status`), by a function that takes no widget.
    The widget's only job is to paint the result. That is also what makes the
    panel testable on a machine with no display, which is every CI runner.

WHAT IT DELIBERATELY DOES NOT DO
    It never mutates. `snapshot()` reads; the `act()` map on the shell writes.
    A panel that both decided and applied would be a second place where the
    presence mode lives, and the first thing to drift.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# The three modes, in the order the segmented control draws them (board 5).
MODE_ORDER = ("active", "focus", "quiet")

# The segment labels are catalogue keys, not text: the panel is the one place
# where three words sit side by side and a truncated translation is obvious.
MODE_LABELS = {"active": "Aktif", "focus": "Fokus", "quiet": "Senyap"}


def _t(key: str, **fields) -> str:
    """`core.i18n.label`, falling back to the key itself.

    A panel that raises because a catalogue is missing is a tray icon that opens
    nothing. The fallback is the marker i18n itself uses for a missing key, so a
    broken locale is still visible rather than silently English.
    """
    try:
        from core.i18n import label

        return str(label(key, **fields))
    except Exception:                                # noqa: BLE001
        return f"⟪{key}⟫"

# The sentence under the title, per mode. Board 5 draws the Aktif one; board 05a
# draws the Fokus one, which is the only mode with something to say beyond its
# own name — notifications are HELD, not dropped, and a panel that stays silent
# about that is a panel whose toast count later looks like a bug.
# BOARD 27 (and 26) GIVE EACH PAGE ITS OWN TWO LINES.
#
# Every page used to draw "JARVIS / Panel baki · mengikuti posisi taskbar",
# which is the identity of the APPLICATION, not of the page. Board 06a's first
# two lines are "Izin & Privasi / Semua data diproses lokal secara default";
# board 08a's are its own. `ui.panel.privacy.title` was already in the catalogue
# in both languages and called by nothing — a key nobody reads is a translation
# nobody notices is missing.
#
# The main page keeps the assistant's name: it IS the assistant, and the mode
# subtitle under it is what changes with Aktif/Fokus/Senyap.
PAGE_TITLES = {
    "main": ("ui.panel.title", None),                       # None: the mode subtitle
    "history": ("ui.panel.history.title", "ui.panel.history.subtitle"),
    "privacy": ("ui.panel.privacy.title", "ui.panel.privacy.subtitle"),
}

# EVERY OTHER PAGE KEEPS ITS OWN TITLE, and this is where it is declared. The
# panel has one `title` label shared by all pages, so a page missing from this
# map falls back to "JARVIS" — which is how seventeen pages came to be labelled
# with the assistant's name, the exact bug the "each page keeps its own title"
# ruling exists to prevent. Built from the registry rather than written out:
# a page added there cannot forget to name itself here.
def _board_titles() -> dict:
    """`(title key, subtitle key)` for every board page.

    THE SUBTITLE IS THE ARTBOARD'S OWN, and the first version of this table got
    that wrong in the opposite direction: it put `None` under every board page,
    on the reasoning that the page drew its own second line. The artboards put
    the second line in the HEADER — `b09()` passes "12 hal yang JARVIS ingat" to
    `panel_head`, and the panel artboards `n10`/`n11` draw it at (24, 54) under
    the title. So the header is where it belongs, and a page that also drew its
    own copy drew it twice.

    A LINE THAT COUNTS IS FORMATTED IN `Snapshot.subtitle`, not here: a literal
    "12 hal" is a lie the first time the user adds a memory.
    """
    try:
        from ui.page_registry import PAGES
    except Exception:                                    # noqa: BLE001
        return {}
    # `more` is not in the registry's PAGES (it is the list itself).
    out = {"more": ("ui.page.more.title", "ui.page.more.subtitle")}
    for key, _label_key, title_key, _board in PAGES:
        out[key] = (title_key, SUBTITLE_KEYS.get(key))
    return out


# The subtitle each artboard passes to `panel_head()`, or the sentence that
# stands in its place where the artboard's line would be a claim about data this
# build does not store.
SUBTITLE_KEYS = {
    "memory": "ui.page.memory.subtitle",          # "12 hal yang JARVIS ingat"
    "routines": "ui.page.routines.subtitle",      # "3 rutinitas aktif"
    "plugins": "ui.page.plugins.subtitle",        # "2 dari 5 plugin aktif"
    "tools": "ui.page.tools.subtitle",
    "access": "ui.page.access.subtitle",          # "Bahasa & gestur"
    "security": "ui.page.security.subtitle",      # "Tiga tingkat risiko"
    "light": "ui.page.light.subtitle",
    "help": "ui.page.help.subtitle",
    "consent": "ui.page.consent.subtitle",
    "memory_one": "ui.page.memory_one.subtitle",
    "gestures": "ui.page.gestures.subtitle",
    "brand": "ui.page.brand.subtitle",
    "installer": "ui.page.installer.subtitle",
}


PAGE_TITLES.update(_board_titles())


def _memory_count() -> dict:
    """Board 9's "N hal yang JARVIS ingat" — the store's count, not the rows'.

    THROUGH THE PAGE'S OWN READER, not a second query against
    `memory_manager`. Two paths to one store is two places for the header and
    the list under it to disagree, and the page's reader is also the one that
    answers `[]` instead of raising when the store is mid-write.
    """
    try:
        from ui import pages_memory

        return {"count": pages_memory.count()}
    except Exception:                                    # noqa: BLE001
        return {"count": 0}


def _routine_count() -> dict:
    """Board 11's "N rutinitas aktif" — the same list the page draws.

    It goes through `pages_people.routines()` and not a second query, so the
    header cannot count anything the list below it does not show. There is no
    routine STORE in this build; that function returns the one real routine
    (the proactive check) and the page states that the artboard's three are not
    stored.
    """
    try:
        from ui import pages_people

        return {"count": len(pages_people.routines() or [])}
    except Exception:                                    # noqa: BLE001
        return {"count": 0}


def _plugin_count() -> dict:
    """Board 16's "N dari M plugin aktif", through the page's own manifest reader.

    NOT `discover_plugins()`. That function IMPORTS every plugin module to
    validate it — one of the forbidden things on this path, and the reason the
    count read "0 of 0" while the page listed fifteen: the import blew up and
    the bare `except` turned a real failure into a plausible zero. The page's
    reader parses the manifests instead, and it is the same list the rows are
    drawn from, so the header cannot count something the list does not show.
    """
    try:
        from ui import pages_admin

        rows = pages_admin.plugin_rows()
        return {"on": sum(1 for r in rows if r["on"]), "total": len(rows)}
    except Exception as e:                               # noqa: BLE001
        print(f"[JARVIS] Plugin count tidak terbaca — {type(e).__name__}: {e}")
        return {"on": 0, "total": 0}


# A SUBTITLE WITH A NUMBER IN IT IS FORMATTED AT PAINT TIME. Written as a
# literal it is wrong the moment the store changes, and board 9's header is the
# most visible example: "12 hal" over a list of three is a page contradicting
# itself in its first two lines.
_COUNTED_SUBTITLES = {
    "ui.page.memory.subtitle": _memory_count,
    "ui.page.routines.subtitle": _routine_count,
    "ui.page.plugins.subtitle": _plugin_count,
}

MODE_SUBTITLES = {
    "active": "ui.panel.subtitle.active",
    "focus": "ui.panel.subtitle.focus",
    "quiet": "ui.panel.subtitle.quiet",
}

# Board 5's four quick actions. The chord is part of the row, not a tooltip,
# because a quick action whose chord is invisible is one the user retypes.
#
# THE CHORDS ARE THE ARTBOARD'S, AND TWO OF THEM ARE NOT BOUND IN THIS BUILD.
# That is stated rather than quietly relabelled: "Susun jendela" has no snap
# behaviour behind it on any platform this project has run on, and "Cari
# berkas" has a search function but no chord. The panel still lists them —
# they are what the mockup asks for and they do something useful when pressed —
# but `design/new-ui-proposal-ANALISIS.md` does not claim the chords exist, and a
# chord printed on a row is not a promise that the OS owns it.
# (key, label-key, chord). The label is a catalogue key — see `PERMISSIONS`.
QUICK_ACTIONS = (
    ("screenshot", "ui.panel.quick.screenshot", "Ctrl+Shift+S"),
    ("dictate", "ui.panel.quick.dictate", "Ctrl+Win"),
    ("find_file", "ui.panel.quick.find_file", "Ctrl+Shift+F"),
    ("tidy_windows", "ui.panel.quick.tidy_windows", "Ctrl+Shift+J"),
)

# BOARD 23 DRAWS THREE DIFFERENT ROWS IN FOKUS, and until this tuple existed the
# panel showed board 5's four in every mode — so a user who had just asked for
# quiet was offered "Tangkap layar".
#
# "Ubah durasi (45 mnt)" is OMITTED ON PURPOSE. There is no focus duration in
# this build: no deadline, no timer, nothing that ends Fokus on its own. A row
# that opens a dialog for a setting which does not exist is worse than a row that
# is not drawn, and the panel's honest sentence says what happens instead. The
# owner chose this over inventing a timer to justify the row.
#
# The chord column is where a shortcut goes, and in Fokus it carries the count
# for the first row, exactly as the artboard draws "3" right-aligned there.
FOCUS_ACTIONS = (
    ("held", "ui.panel.focus.quick.held", "{count}"),
    ("end_focus", "ui.panel.focus.quick.end", ""),
    ("pause_scheduling", "ui.panel.focus.quick.pause", ""),
)


# Every action key the panel can press, in the order a row appears: board 5's
# four first, then Fokus's own. The page builds one widget per entry.
ALL_QUICK_KEYS = tuple(dict.fromkeys(
    [key for key, _n, _c in QUICK_ACTIONS] + [key for key, _n, _c in FOCUS_ACTIONS]))


def quick_actions_for(mode: str) -> tuple:
    """Which rows the panel shows. One function, because two lists plus an `if`
    in two places is how the panel draws Fokus's rows while acting on board 5's.
    """
    return FOCUS_ACTIONS if str(mode or "").strip().lower() == "focus" else QUICK_ACTIONS

# Board 06a's explicit list. `key` is what `act()` receives; `label` and `sub` are
# what the user reads. Kept here rather than in the widget so the test asserts
# the same four rows the artboard draws.
PERMISSIONS = (
    ("screen", "ui.panel.permission.screen", "ui.panel.permission.screen.sub"),
    ("microphone", "ui.panel.permission.microphone",
     "ui.panel.permission.microphone.sub"),
    ("files", "ui.panel.permission.files", "ui.panel.permission.files.sub"),
    ("apps", "ui.panel.permission.apps", "ui.panel.permission.apps.sub"),
)


@dataclass(frozen=True)
class Snapshot:
    """Everything the panel draws in one state. Immutable on purpose.

    A frozen dataclass because the panel is rebuilt from this on every open and
    on every change: a mutable one invites a widget to keep a reference and
    paint yesterday's truth, which is the class of bug this module exists to
    prevent.
    """

    mode: str = "active"
    page: str = "main"
    held: int = 0
    quota_used: int = 0
    quota_limit: int = 3
    suggestion: str = ""
    undo_label: str = ""
    can_undo: bool = False
    can_hear: bool = True
    permissions: dict = field(default_factory=dict)
    history: tuple = ()
    audit: tuple = ()
    voice_auth: str = "off"

    @property
    def mode_index(self) -> int:
        """Which segment is lit. -1 for a mode this build does not know."""
        try:
            return MODE_ORDER.index(self.mode)
        except ValueError:
            return -1

    @property
    def title(self) -> str:
        """The page's own first line, or the assistant's name on the main page.

        `page` is a field on the snapshot rather than an argument to `title`
        because the panel repaints from the snapshot after every press: a title
        that takes an argument is a title someone will forget to pass.
        """
        key, _sub = PAGE_TITLES.get(self.page, PAGE_TITLES["main"])
        return _t(key)

    @property
    def subtitle(self) -> str:
        """The page's own second line; on the main page, the presence mode.

        The HISTORY subtitle carries a count, which is why it is formatted
        here rather than looked up: `ui.panel.history.subtitle` is
        "Hari ini · {count} bisa diurungkan", and a literal would be a lie the
        first time the user undoes something.
        """
        _title, sub = PAGE_TITLES.get(self.page, PAGE_TITLES["main"])
        if sub == "ui.panel.history.subtitle":
            return _t(sub, count=self.undoable)
        if sub in _COUNTED_SUBTITLES:
            return _t(sub, **_COUNTED_SUBTITLES[sub]())
        if sub is not None:
            return _t(sub)
        return _t(MODE_SUBTITLES.get(self.mode, MODE_SUBTITLES["active"]))

    @property
    def undoable(self) -> int:
        return sum(1 for row in self.history if row.get("undoable"))

    @property
    def held_line(self) -> str:
        """Board 05a's count, spelled out. Never hidden when it is zero —
        "0 tertahan" is a fact, a missing line is a question."""
        return _t("ui.panel.focus.held_count", count=self.held)

    def quick_chord(self, chord: str) -> str:
        """A row's right-hand text, with `{count}` filled from the held queue.

        The count comes from the queue, never from a literal: "3 tertahan" with
        3 hardcoded is the same class of bug as "Fokus aktif sampai 17.00".
        """
        text = str(chord or "")
        if "{count}" not in text:
            return text
        return text.replace("{count}", str(int(self.held)))

    @property
    def quota_line(self) -> str:
        return _t("ui.panel.quota", used=self.quota_used, limit=self.quota_limit)

    @property
    def history_subtitle(self) -> str:
        undoable = sum(1 for row in self.history if row.get("undoable"))
        return _t("ui.panel.history.subtitle", count=undoable)


def _safe(call, default):
    """Call `call`, or return `default`. Never raises.

    Each of these reads a module that owns its own state; a panel that dies
    because one of them is mid-write is a tray icon that opens nothing, which
    is worse than a panel with one stale line.
    """
    try:
        return call()
    except Exception:                                # noqa: BLE001
        return default


def _mode() -> str:
    from core import presence_mode

    mode = str(_safe(presence_mode.current, "active") or "active").strip().lower()
    return mode if mode in MODE_ORDER else "active"


def _permissions() -> dict:
    """The four switches of board 06a, from the only place each is decided.

    TWO KINDS OF SWITCH, AND THE PANEL MUST NOT PRETEND THEY ARE ONE.

      * `microphone` is a FACT ABOUT THE MACHINE — a device exists or it does
        not (`core.audio_devices.input_available`). Drawing it as a switch the
        user can turn on would be a promise no click can keep, so it renders
        `fixed` and says why.
      * `files` and `apps` are PLUGIN ENABLEMENT. They are real toggles because
        turning one off is what stops the tool from being offered to the model.
      * `screen` is neither: screenshots are a built-in action, not a plugin, so
        the honest answer is "always on when asked" rather than a switch that
        would have nothing behind it.
    """
    from core import audio_devices
    from memory import config_manager

    can_hear = bool(_safe(lambda: audio_devices.input_available(), True))
    return {
        "screen": {"on": True, "fixed": True, "note": ""},
        "microphone": {"on": can_hear, "fixed": not can_hear,
                       "note": ""},
        "files": {"on": bool(_safe(
            lambda: config_manager.get_plugin_enabled("file_controller", False), False)),
                  "fixed": False, "note": ""},
        "apps": {"on": bool(_safe(
            lambda: config_manager.get_plugin_enabled("computer_control", False), False)),
                 "fixed": False, "note": ""},
    }


def _history() -> tuple:
    """The undoable work, newest first, in board 08a's shape.

    `core.undo.history()` is already newest-first — it returns
    `reversed(_stack)` — so this must not reverse it again. (Reversing twice is
    the harmless-looking bug that puts the row the user just created at the
    bottom of a list they scroll from the top.)
    """
    from core import undo

    return tuple({"label": str(label), "undoable": True}
                 for label in (_safe(undo.history, []) or []))


def _audit() -> tuple:
    """The last three audit lines, oldest first, as board 08a draws them.

    `entries()` returns dicts, newest last. The board puts the newest at the
    TOP of its little table, so the order is reversed here once, deliberately.
    """
    from core import audit_log

    entries = _safe(lambda: audit_log.shared().entries(3), ()) or ()
    lines = []
    for item in entries:
        when = str(item.get("at") or item.get("time") or "")[11:19]
        tool = str(item.get("tool") or "?")
        outcome = str(item.get("outcome") or "")
        detail = str(item.get("detail") or "")
        text = " · ".join(part for part in (tool, outcome, detail) if part)
        lines.append(f"{when}  {text}".strip())
    return tuple(reversed(lines))


def _quota() -> tuple[int, int]:
    from core import suggestion_quota

    quota = _safe(suggestion_quota.shared, None)
    if quota is None:
        return 0, 3
    return int(_safe(quota.used, 0)), int(_safe(quota.limit, 3))


def quota_note() -> str:
    """The second quota sentence: board 05a's "Dua sisanya ditahan sampai fokus
    berakhir". Empty outside Fokus.

    WHY IT EXISTS ONLY IN FOKUS. Outside Fokus nothing is being held — the
    remainder is simply unused, and the line above already says "1 dari 3".
    Printing the sentence in Aktif would teach the user that their suggestion is
    being withheld when it is only unspent. So this is not decoration on the
    quota line: it is the one place the panel says what Fokus DOES to the
    suggestions.

    THE NUMBER IS DERIVED, NOT WRITTEN. It is `limit - used` from the same quota
    the line above reads. A literal "2" would drift the first time the limit
    changed, and a sentence that outlives its own arithmetic is exactly the
    "17.00" failure with more words.
    """
    if _mode() != "focus":
        return ""
    used, limit = _quota()
    remaining = max(0, int(limit) - int(used))
    if remaining == 0:
        # Nothing is being held, so there is no remainder to describe. Saying
        # "0 held" over a quota that is fully spent is a promise about a queue
        # that does not exist.
        return ""
    return _t("ui.panel.quota.held", remaining=remaining)


def _suggestion() -> str:
    """The one line under SARAN HARI INI, or "" when there is nothing today.

    Board 5 draws a real suggestion with an amber rule on it. The section is
    drawn either way — an empty section that says so keeps the panel from
    changing height between opens, which is the one thing a tray panel must not
    do, because it is anchored to the taskbar.

    There is no suggestion engine in this build yet: `core.suggestion_quota`
    counts what was offered, it does not produce one. Saying nothing is correct;
    inventing a line to fill the artboard would be worse than an empty row.
    """
    return ""


def snapshot(page: str = "main") -> Snapshot:
    """Read every value the panel needs, in one pass.

    Called on open and after every action, so it has to be cheap: these are
    dictionary reads and one small file read, not a scan.
    """
    from core import presence_mode, undo, voice_auth

    used, limit = _quota()
    perms = _permissions()
    return Snapshot(
        mode=_mode(),
        page=str(page or "main"),
        held=int(_safe(presence_mode.held_count, 0)),
        quota_used=used,
        quota_limit=limit,
        suggestion=_suggestion(),
        undo_label=str(_safe(undo.peek, "") or ""),
        can_undo=bool(_safe(undo.can_undo, False)),
        can_hear=bool(perms["microphone"]["on"]),
        permissions=perms,
        history=_history(),
        audit=_audit(),
        voice_auth=str(_safe(voice_auth.status, "off") or "off"),
    )


__all__ = [
    "ALL_QUICK_KEYS", "FOCUS_ACTIONS", "quota_note", "MODE_LABELS", "MODE_ORDER", "MODE_SUBTITLES", "PAGE_TITLES", "PERMISSIONS", "QUICK_ACTIONS",
    "Snapshot", "snapshot",
]
