"""What the tray panel DRAWS, given a snapshot. No state, no decisions.

WHY THIS IS A THIRD FILE ABOUT ONE PANEL
    `ui/tray_panel.py` is lifecycle and dispatch, `ui/tray_pages.py` is geometry
    and palettes, and this is the step between them: take one immutable
    `Snapshot` and write it onto widgets that already exist. The split is not
    taste. The panel crossed the 600-line ceiling twice — once when the theme
    control was added, once before — and both times the right answer was that
    "draw" and "open/close/dispatch" are different jobs sharing a file.

WHAT MAKES THIS SAFE TO MOVE
    Every function takes `panel` and touches only `panel._labels`,
    `panel._buttons`, `panel._theme`, `panel._requested` and `panel._page`.
    Nothing here reads the world: `snapshot()` in the model module does that,
    once, before any of this runs. So the panel cannot half-paint itself from
    live state — the failure mode where the mode has changed but the label has
    not.

WHAT A CALLER MUST HAVE
    `labels` and `buttons` filled by the builders in `ui/tray_pages.py`. These
    functions assume the keys exist and let a KeyError through: a missing key is
    a bug in the builder, and a painter that silently skipped it would leave a
    widget saying whatever it said at build time — which is the exact class of
    lie this panel was built to avoid.
"""
from __future__ import annotations

from ui.tray_pages import PALETTES
from ui.tray_theme import _rgba
from ui.tray_panel_model import MODE_ORDER, PERMISSIONS, _t


def paint(panel, snap) -> None:
    """Put one snapshot on the widgets. Never raises."""
    labels = panel._labels

    labels["title"].setText(snap.title)
    labels["subtitle"].setText(snap.subtitle)
    labels["quota"].setText(snap.quota_line)
    paint_theme(panel)
    labels["suggestion"].setText(
        snap.suggestion or _t("ui.panel.suggestion.empty"))

    for mode in MODE_ORDER:
        panel._buttons[f"mode:{mode}"].setChecked(mode == snap.mode)
    mark_segments(panel, snap)

    # Board 23's strip: only in Fokus, because only Fokus holds anything.
    held = labels["held"]
    if snap.mode == "focus":
        held.setText("\n".join((_t("ui.panel.focus.active_until", time="17.00"),
                                 _t("ui.panel.focus.held"),
                                 snap.held_line)))
        held.show()
    else:
        held.hide()

    for key, _name, _sub in PERMISSIONS[:3]:
        button = panel._buttons[f"perm:{key}"]
        state = snap.permissions.get(key, {})
        button.setChecked(bool(state.get("on")))
        button.setEnabled(not bool(state.get("fixed")))
        _paint_dot(panel, key, state)

    paint_history(panel, snap)
    paint_privacy(panel, snap)



def _paint_dot(panel, key: str, state: dict) -> None:
    """The 40x22 track at x=396: cyan with the knob to the right when on.

    IT IS A READOUT, NOT A CONTROL — the row's label is the click target, and
    a second control for one boolean would be two places to disagree. But an
    unlit dot that never moves would be a lie of a worse kind: it would show
    "off" for a permission that is on, which is the exact failure the panel
    was built to avoid. `fixed` (a Microphone that does not exist) draws
    muted, because there is nothing behind the switch to permit.
    """
    dot = panel._labels.get(f"perm_dot:{key}")
    if dot is None:
        return
    pal = PALETTES[panel._theme]
    if state.get("fixed"):
        track, border = pal["card"], pal["line"]
    elif state.get("on"):
        track, border = pal["accent"], pal["accent"]
    else:
        track, border = pal["card"], pal["line"]
    try:
        dot.setStyleSheet(
            f"background:{track};border:1px solid {border};border-radius:11px;")
    except Exception as e:                       # noqa: BLE001
        panel._note(f"permission dot {key!r} refused — {type(e).__name__}: {e}")


def paint_theme(panel) -> None:
    """The header control says which SETTING is on, never which palette.

    "auto" on the button is the truth the user set; the palette it resolved
    to is what they see. A button reading "light" because `auto` happened to
    resolve light is a button that cannot be set back to auto.
    """
    button = panel._buttons.get("theme")
    if button is None:
        return
    mark = {"auto": "A", "dark": "D", "light": "L"}.get(panel._requested, "A")
    try:
        button.setText(mark)
        button.setStyleSheet(
            f"background:transparent;color:{PALETTES[panel._theme]['muted']};"
            f"border:1px solid {PALETTES[panel._theme]['line']};"
            f"border-radius:6px;padding:0;")
    except Exception as e:                       # noqa: BLE001
        panel._note(f"theme control not painted — {type(e).__name__}: {e}")



def mark_segments(panel, snap) -> None:
    """The lit segment is filled; the others are outlines.

    Colour alone is not enough — the active segment also carries the
    heavier weight, so the difference survives a grey-scale screenshot and
    the checked state survives a reader who cannot see the fill.
    """
    pal = PALETTES[panel._theme]
    for mode in MODE_ORDER:
        button = panel._buttons[f"mode:{mode}"]
        if mode == snap.mode:
            button.setStyleSheet(
                f"background:{pal['accent']};color:{pal['on_accent']};"
                f"border:none;border-radius:9px;font-weight:600;")
        else:
            button.setStyleSheet(
                f"background:transparent;color:{pal['muted']};"
                f"border:1px solid {pal['line']};border-radius:9px;")



def paint_history(panel, snap) -> None:
    labels = panel._labels
    labels["history_count"].setText(snap.history_subtitle)
    rows = list(snap.history)[:4]
    for index in range(4):
        row = rows[index] if index < len(rows) else None
        labels[f"history:{index}"].setText(str(row["label"]) if row else "")
        labels[f"history_meta:{index}"].setText(
            _t("ui.panel.history.state.undoable") if row else "")
        button = panel._buttons[f"undo:{index}"]
        # Only the OLDEST row may carry the button, because undo is a
        # stack and `undo_last()` reverses the oldest entry. Two buttons
        # for one operation would be two buttons that always do the same
        # thing, in the two places a user would least expect it.
        show = bool(row) and index == len(rows) - 1 and snap.can_undo
        button.setVisible(show)
    labels["audit"].setText(
        "\n".join(snap.audit) or _t("ui.panel.audit.empty"))



def paint_privacy(panel, snap) -> None:
    labels = panel._labels
    for key, _name, _sub in PERMISSIONS[:3]:
        state = snap.permissions.get(key, {})
        on = bool(state.get("on"))
        note = str(state.get("note") or "")
        labels[f"indicator_state:{key}"].setText(
            note or _t("ui.panel.indicator.on" if on else "ui.panel.indicator.off"))
    for key, _name, _sub in PERMISSIONS:
        button = panel._buttons[f"permx:{key}"]
        state = snap.permissions.get(key, {})
        button.setChecked(bool(state.get("on")))
        # A fixed switch is DISABLED, not merely refused on click: drawing
        # a live switch over something no click can change is a control
        # that teaches the user not to trust the panel.
        button.setEnabled(not bool(state.get("fixed")))



def show_page(panel) -> None:
    for name, page in panel._pages.items():
        try:
            page.show() if name == panel._page else page.hide()
        except Exception as e:                   # noqa: BLE001
            panel._note(f"page {name!r} would not switch — {type(e).__name__}: {e}")



def apply_style(panel) -> None:
    """One stylesheet for the whole panel, rebuilt when the palette changes.

    Set on the window rather than per widget, so board 28 is a palette swap
    and not a second set of colours in twelve places.
    """
    window = panel._window
    if window is None:
        return
    pal = PALETTES[panel._theme]
    try:
        window.setStyleSheet(f"""
            QWidget {{ background:{pal['panel']};color:{pal['text']}; }}
            QLabel {{ background:transparent;color:{pal['text']}; }}
            QPushButton {{ background:{pal['card']};color:{pal['text']};
                          border:1px solid {pal['line']};border-radius:10px;
                          text-align:left;padding-left:14px; }}
            QPushButton:checked {{ border:1px solid {pal['accent']};
                                  background:{_rgba(pal['accent'], 0.12)}; }}
            QPushButton:disabled {{ color:{pal['muted']}; }}
            QLineEdit {{ background:{pal['card']};color:{pal['text']};
                        border:1px solid {pal['line']};border-radius:20px;
                        padding-left:18px; }}
        """)
    except Exception as e:                       # noqa: BLE001
        panel._note(f"stylesheet refused — {type(e).__name__}: {e}")
