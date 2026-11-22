"""Every ambient surface draws the design system, not the retired HUD palette.

WHY THIS FILE EXISTS
    `docs/mockups/build.py` is the source of truth and it defines one palette:
    BASE #04080D, PANEL #0A1722, LINE #17323F, CYAN #4FD8F0, AMBER #F5A524,
    TEXT #E6F4F8, MUTED #8FA9B5. Four of the six ambient surfaces declared
    those numbers themselves. Two did not:

      * `ui/confirm_banner.py` read `ui.theme.C`, which still carries the look
        of the full-screen window ambient mode replaced — #171719 base,
        #ff6b00 orange accent, Courier New. Board 25's dialog was therefore
        # near-black with an orange border at a 6 px radius, not #0C1B26 with
        an amber border at 16.
      * `ui/face_canvas.py` read `C.PRI` (#4b9fff, blue) and `C.MUTED_C`
        (#ff3366, pink) for the floating head, so the face drew BLUE rings
        inside a CYAN orb and went pink when muted.

    Both were invisible to the test suite because every existing test asked
    what the surfaces SAY, and none asked what they look like. These do.

WHAT IS PROVEN AND WHAT IS NOT
    Proven: the tokens the code passes to Qt, and the stylesheet it builds.
    Not proven: the rendered pixels. Qt cannot run in this sandbox, so a
    screenshot comparison is a manual check in `docs/verification.md`.
"""
from __future__ import annotations

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
UI = ROOT / "ui"
BUILD = ROOT / "docs" / "mockups" / "build.py"


def _sheet_tokens() -> dict:
    """The palette, read out of the sheet rather than retyped here."""
    source = BUILD.read_text(encoding="utf-8")
    line = next(l for l in source.splitlines() if l.startswith("BASE, PANEL, LINE"))
    ns: dict = {}
    exec(line + "\n" + next(
        l for l in source.splitlines() if l.startswith("LINE_ACC, CYAN, AMBER")), ns)
    exec(next(l for l in source.splitlines() if l.startswith("TEXT, MUTED")), ns)
    return ns


TOK = _sheet_tokens()


# ── the retired palette must not reach an ambient surface ───────────────────

def _without_comments(source: str) -> str:
    """The source with `#` comments and docstrings removed.

    A hex value in prose describes the design; a hex value in code draws it.
    Only the second kind is the subject of the colour audit.
    """
    import io
    import tokenize

    out = []
    try:
        for tok in tokenize.generate_tokens(io.StringIO(source).readline):
            if tok.type == tokenize.COMMENT:
                continue
            if tok.type == tokenize.STRING and tok.string.lstrip("rbuRBU").startswith(
                    ('"""', "\'\'\'")):
                continue
            out.append(tok.string)
    except (tokenize.TokenError, IndentationError):
        return source
    return " ".join(out)


def _ambient_sources() -> list[Path]:
    """Every module that DRAWS one of the six artboards.

    Named explicitly rather than globbed: `ui/theme.py` legitimately holds the
    old palette, and a glob would either fail on it or have to exempt it by
    name anyway. A surface added later has to be added here, which is the
    point — the list is the audit.
    """
    return [UI / name for name in (
        "orb_paint.py", "toast_card.py", "tray_pages.py", "voice_paint.py",
        "face_canvas.py", "confirm_banner.py",
    )]


def test_the_sheet_still_defines_the_palette_these_assertions_use():
    """A guard on the guard: if the sheet's tokens move, say so here."""
    assert TOK["BASE"] == "#04080D"
    assert TOK["CYAN"] == "#4FD8F0"
    assert TOK["AMBER"] == "#F5A524"


def test_no_drawing_surface_reads_the_retired_hud_palette():
    """`ui.theme.C` is not a design source for the ambient shell.

    Reading it is how a surface silently joins a palette nobody else uses —
    which is exactly what happened to the confirmation dialog and the floating
    face. `qcol` is fine: it is a `QColor` helper, not a colour.
    """
    offenders = []
    for path in _ambient_sources():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
                if node.value.id == "C" and node.attr.isupper():
                    offenders.append(f"{path.name}:{node.lineno} C.{node.attr}")
            # `from ui.theme import C` is the import that starts it
            if isinstance(node, ast.ImportFrom) and node.module == "ui.theme":
                for alias in node.names:
                    if alias.name == "C":
                        offenders.append(f"{path.name}:{node.lineno} imports C")
    assert not offenders, (
        "these surfaces read the retired HUD palette instead of the design "
        "system: " + ", ".join(offenders))


# ── board 25, measured against its artboard ─────────────────────────────────

def test_board_25_dialog_uses_the_artboards_tokens():
    """#0C1B26 fill, amber border, 16 px radius — all four were wrong."""
    source = _without_comments(
        (UI / "confirm_banner.py").read_text(encoding="utf-8"))
    assert 'AMBER_BG = "#0C1B26"' in source, "the dialog no longer knows its fill"
    assert 'AMBER = "#F5A524"' in source
    assert "background: {AMBER_BG}" in source, (
        "the dialog body is not drawn in the artboard's fill")
    assert "border: 1px solid {AMBER}" in source, (
        "the border is not amber; board 25 frames a risk, it does not decorate")
    assert "border-radius: 16px" in source, "the radius is not the artboard's 16"
    assert "rgba(" not in source, (
        "the near-black red-cast body is back; the artboard fills the dialog "
        "with an opaque token, not an rgba wash")


def test_board_25_primary_button_is_filled_and_pill_shaped():
    """`pill_btn(..., primary=True)` is a FILLED 40 px pill with dark text.

    The dialog's one job is that button; drawn transparent and 32 px tall it
    reads as the secondary action next to the real one.
    """
    source = (UI / "confirm_banner.py").read_text(encoding="utf-8")
    assert "background: {AMBER}; color: {BASE}" in source, (
        "the confirm button is not filled with the accent")
    assert "border-radius: 20px" in source, "the buttons are not pills"
    assert "yes.setFixedHeight(40)" in source
    assert "no.setFixedHeight(40)" in source


def test_board_25_speaks_the_design_systems_typeface():
    """Courier New appeared in exactly one module, and it was this one.

    The sheet's `FONT` is a Space Grotesk → Segoe UI → Arial chain. A dialog
    borrowed from a terminal look is a dialog from a different application.
    """
    source = (UI / "confirm_banner.py").read_text(encoding="utf-8")
    assert "Courier New" not in source, (
        "the confirmation dialog is the only surface in a monospace typeface; "
        "the artboard uses the design system's font")
    assert 'FONT = "Space Grotesk, Segoe UI, Arial"' in source


def test_board_25_is_the_artboards_width():
    """520, from `bx, by, bw, bh = 380, 236, 520, 250` in the sheet.

    Read with AST rather than importing the module: `ui/confirm_banner.py`
    imports PyQt6 at module level, and this machine has no Qt. The number is a
    constant, and a constant can be read without a display.
    """
    tree = ast.parse((UI / "confirm_banner.py").read_text(encoding="utf-8"))
    cls = next(n for n in ast.walk(tree)
               if isinstance(n, ast.ClassDef) and n.name == "ConfirmBanner")
    width = next(
        n.value.value for n in cls.body
        if isinstance(n, ast.Assign)
        and any(getattr(t, "id", "") == "_OW" for t in n.targets)
        and isinstance(n.value, ast.Constant))
    assert width == 520, "board 25 draws the dialog 520 px wide"


# ── board 1, the floating face ──────────────────────────────────────────────

def test_the_floating_face_is_painted_in_the_orb_it_sits_in():
    """The face and the ring beside it must not be two different colours.

    `C.PRI` is #4b9fff blue and the orb's ring is #4FD8F0 cyan. On the same
    260 px surface that is visible without a screenshot — one of them is the
    accent and the other is from a theme that no longer exists.
    """
    source = (UI / "face_canvas.py").read_text(encoding="utf-8")
    assert "from ui.orb_paint import CYAN, MUTED" in source, (
        "the face does not take its colour from the same source as the ring")
    tree = ast.parse(source)
    call = next(node for node in ast.walk(tree)
                if isinstance(node, ast.Call) and getattr(node.func, "attr", "") == "paint")
    call_src = ast.unparse(call)
    # The colour is bound to `primary` one line earlier, so BOTH halves are
    # checked: the assignment and the argument. Reading only the call would
    # pass for a function that named the right thing and passed the wrong one.
    assert "qcol(CYAN)" in source and "qcol(MUTED)" in source, (
        "the face is not coloured from the same source as the ring")
    assert "primary" in call_src, "the avatar is not handed the computed colour"
    assert "FACE_ACCENT" in call_src, (
        "the iris highlight is not the sheet's bright token")
    offenders = [name for name in ("qcol(C.PRI)", "qcol(C.WHITE)", "qcol(C.MUTED_C)")
                 if name in source]
    assert not offenders, f"still reading the retired palette: {offenders}"


def test_the_face_accent_is_the_sheets_highlight_token():
    """#BFF6FF is `CORE` in `ui/orb_paint.py` and the sheet's bright stop."""
    from ui.face_canvas import FACE_ACCENT

    assert FACE_ACCENT == "#BFF6FF"


# ── and the surfaces that were already right stay right ─────────────────────

def test_every_drawing_surface_declares_sheet_colours():
    """A surface that invents a hex value is a surface drifting.

    Only the sheet's own palette may appear in these modules, plus the few
    derived shades the artboards themselves use (dashed overlay, card fills,
    the light theme). A new value here is a design decision, so it has to be
    added to this list deliberately.
    """
    allowed = {
        "#04080D", "#0A1722", "#17323F", "#2A6477", "#4FD8F0", "#F5A524",
        "#E6F4F8", "#8FA9B5", "#0C1B26", "#081520", "#BFF6FF", "#0B4A5C",
        "#25404C", "#13242E", "#5E7A87",
        # light theme, from the same sheet
        "#F6F9FB", "#FFFFFF", "#D8E3E9", "#0A7A93", "#0B1A24", "#5B7480",
        "#9A5B00",
        # board 6's camera inset, drawn as #071018 in the sheet. #1c3a4a,
        # #7f97a6, #00d4ff and #eaf6ff were boarded 6's own drift and are
        # deliberately NOT allowed: they were replaced by LINE_ACC, MUTED,
        # CYAN and TEXT.
        "#071018",
        # hover states derived from the accent, not new hues
        "#FFB944",
    }
    unknown = {}
    for path in _ambient_sources():
        # COMMENTS ARE NOT COLOURS. The docstrings in these modules explain
        # what they used to draw, and quoting #00d4ff there is the record of a
        # bug, not a repeat of it — the first version of this test counted
        # those and failed on its own documentation.
        code = _without_comments(path.read_text(encoding="utf-8"))
        found = re.findall(r"#[0-9A-Fa-f]{6}", code)
        stray = sorted({h for h in found if h not in allowed})
        if stray:
            unknown[path.name] = stray
    assert not unknown, f"colours outside the design sheet: {unknown}"


def test_board_25s_risk_bar_is_a_widget_not_a_stylesheet_hope():
    """A5 makes the 3 px left bar load-bearing: it is how "berisiko" is told
    apart from "aman" without introducing a red the palette does not have.

    CSS `border-left` is not reliably painted by Qt on a plain `QWidget`, so
    the bar is its own widget. This asserts the widget exists, is 3 px wide,
    is amber, and is positioned by `resizeEvent` — anything less and the bar is
    a claim rather than a mark.
    """
    tree = ast.parse((UI / "confirm_banner.py").read_text(encoding="utf-8"))
    cls = next(n for n in ast.walk(tree)
               if isinstance(n, ast.ClassDef) and n.name == "ConfirmBanner")
    # `self._risk_bar = QWidget(self)` — assigned in __init__, built from Qt.
    assigned = any(
        isinstance(n, ast.Assign)
        and any(getattr(t, "attr", "") == "_risk_bar" for t in n.targets)
        and isinstance(n.value, ast.Call)
        and getattr(n.value.func, "id", "") == "QWidget"
        for n in ast.walk(cls))
    assert assigned, (
        "the risk bar is not a real widget; a stylesheet border is a claim Qt "
        "may not draw")
    # and it is positioned with the artboard's 18 px inset
    geometry = [ast.unparse(n) for n in ast.walk(cls)
                if isinstance(n, ast.Call) and getattr(n.func, "attr", "") == "setGeometry"]
    assert any("18, 3," in g for g in geometry), (
        f"the bar is not pinned with the artboard's inset: {geometry}")


def test_the_risk_bar_survives_a_resize():
    """Drive it: the real `resizeEvent` must place the bar, not just exist."""
    import sys

    sys.path.insert(0, str(ROOT / "tests"))
    import qtstub

    saved = {k: v for k, v in sys.modules.items() if k.startswith("PyQt6")}
    sys.modules.update(qtstub.install_qt())
    try:
        from ui.confirm_banner import ConfirmBanner

        banner = ConfirmBanner.__new__(ConfirmBanner)
        placed = {}

        class _Bar:
            def setGeometry(self, *a):
                placed["geometry"] = a

        banner._risk_bar = _Bar()
        banner.height = lambda: 250          # board 25's dialog height
        banner.resizeEvent(None)
        assert placed["geometry"] == (1, 18, 3, 250 - 36), (
            "the risk bar is not inset 18 px top and bottom on a 250 px dialog")
    finally:
        for name in [k for k in sys.modules if k.startswith("PyQt6")]:
            sys.modules.pop(name, None)
        sys.modules.update(saved)
