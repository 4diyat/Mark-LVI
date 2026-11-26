"""Board 6 — the voice overlay, and the camera tile it carries.

WHAT IS BEING TESTED, AND WHY IT IS NOT A SCREENSHOT
    The design (`design/new-ui-proposal/03-voice-mode.png`) makes three promises that a
    picture cannot hold anyone to: the edge glow appears ONLY while the overlay
    is active, Esc closes it, and Ctrl+Alt+G pauses the gestures without taking
    the transcript away. Each of those is a function in `ui/voice_overlay.py`
    returning a number or a bool, and that is deliberate — a rule that lives in
    a `paintEvent` can only be checked by a human looking at a screen.

    The painting itself needs Qt and a display, so the tests here assert the two
    things a headless runner can: that the modules import and the frame does not
    raise with Qt absent or stubbed, and that everything the frame SAYS is
    decided before paint time (`frame_words`).

WHY `tests/qtstub` IS NOT LOADED FOR MOST OF THIS FILE
    It should not need to be. If a rule needs a widget to be true, the rule is
    in the wrong place.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from ui import voice_hand, voice_overlay

ROOT = Path(__file__).resolve().parent.parent


# ── the edge glow: the artboard's footnote is the spec ──────────────────────

def test_the_glow_is_absent_when_the_overlay_is_not_active():
    """The footnote says "hanya saat overlay aktif". Not dimmer — gone."""
    for state in voice_overlay.STATES:
        assert voice_overlay.edge_alpha(False, state) == 0.0, state


def test_the_glow_exists_while_listening_and_is_brighter_while_speaking():
    listening = voice_overlay.edge_alpha(True, "listening")
    speaking = voice_overlay.edge_alpha(True, "speaking")
    assert 0.0 < listening <= voice_overlay.GLOW_MAX_OPACITY
    assert speaking > listening, (
        "the edge is the only cue for which one is using the microphone")


def test_the_glow_never_leaves_its_range():
    for state in voice_overlay.STATES + ("nonsense", ""):
        assert 0.0 <= voice_overlay.edge_alpha(True, state) <= voice_overlay.GLOW_MAX_OPACITY


def test_hiding_the_overlay_really_drops_the_glow_not_just_the_window():
    overlay = voice_overlay.VoiceOverlay(state="listening")
    overlay.show()
    lit = overlay.glow()
    overlay.hide()
    assert lit > 0.0 and overlay.glow() == 0.0


# ── Esc and Ctrl+Alt+G ──────────────────────────────────────────────────────

def test_escape_closes_an_active_overlay_and_tells_its_owner():
    closed = []
    overlay = voice_overlay.VoiceOverlay(on_close=lambda: closed.append(1))
    overlay.show()
    assert overlay.handle_escape() is True
    assert overlay.active is False
    assert closed == [1]


def test_escape_on_a_hidden_overlay_is_not_ours_to_consume():
    """Esc belongs to whatever the user is actually looking at."""
    overlay = voice_overlay.VoiceOverlay()
    assert overlay.handle_escape() is False
    assert voice_overlay.VoiceOverlay(state="listening").handle_escape() is False


def test_pausing_gestures_keeps_the_overlay_and_the_transcript():
    """The user stopped waving, not talking. Taking the words away would be
    answering a question they did not ask."""
    overlay = voice_overlay.VoiceOverlay(state="listening")
    overlay.show()
    overlay.set_transcript("ringkas tabel ini")
    overlay.set_hand((0.3, 0.4, True))

    assert overlay.handle_toggle_gestures() is True
    assert overlay.active is True
    assert overlay.transcript == "ringkas tabel ini"
    assert overlay.hand == voice_hand.Hand(), "the frozen hand must not stay drawn"
    assert overlay.handle_toggle_gestures() is False


def test_the_paused_tile_says_it_is_paused():
    overlay = voice_overlay.VoiceOverlay(state="listening")
    overlay.set_gestures_paused(True)
    assert voice_overlay.frame_words(overlay)["paused"] == "GESTUR DIPENGGU"


# ── what the frame says ─────────────────────────────────────────────────────

def test_the_three_status_words_are_the_artboards():
    assert voice_overlay.status_word("listening") == "MENDENGARKAN"
    assert voice_overlay.status_word("speaking") == "BERBICARA"
    assert voice_overlay.status_word("idle") == "SIAGA"


def test_an_unknown_state_does_not_raise_and_does_not_lie():
    overlay = voice_overlay.VoiceOverlay()
    overlay.set_state("menari")
    assert overlay.state == "idle"
    assert voice_overlay.status_word(overlay.state) == "SIAGA"


def test_the_transcript_and_the_answer_are_both_on_screen():
    overlay = voice_overlay.VoiceOverlay(state="listening")
    overlay.set_transcript("ringkas tabel ini dan tandai baris yang lewat anggaran")
    overlay.set_answer("Baris 7 dan 11 melewati plafon 12% dan 4%.")
    words = voice_overlay.frame_words(overlay)
    assert words["transcript"] and words["answer"]
    assert "plafon" in " ".join(words["answer"])


def test_a_long_transcript_wraps_and_stops_at_three_lines():
    """A sentence that ran off the edge of the screen was the first sketch's
    most obvious failure, and it is arithmetic, not taste."""
    long_text = " ".join(["kata"] * 200)
    lines = voice_overlay.lines_for(long_text, 74)
    assert len(lines) > 3
    assert all(len(line) <= 74 for line in lines)
    overlay = voice_overlay.VoiceOverlay()
    overlay.set_transcript(long_text)
    assert len(voice_overlay.frame_words(overlay)["transcript"]) == 3


def test_lines_for_survives_empty_and_garbage():
    assert voice_overlay.lines_for("", 20) == []
    assert voice_overlay.lines_for(None, 20) == []


def test_the_footnote_is_the_artboards_sentence_verbatim():
    """It is the only place the key bindings are written down on screen."""
    assert voice_overlay.footnote() == (
        "Glow tepi hanya saat overlay aktif · Esc keluar · "
        "Ctrl+Alt+G menjeda gestur saat overlay fokus")


def test_the_camera_tile_admits_when_it_has_no_camera():
    overlay = voice_overlay.VoiceOverlay()
    assert voice_overlay.frame_words(overlay)["camera"] == "KAMERA TIDAK TERSEDIA"
    overlay.set_camera_available(True)
    assert voice_overlay.frame_words(overlay)["camera"] == "LAYANAN GESTUR AKTIF"


# ── the hand on the tile ────────────────────────────────────────────────────

def test_the_hand_is_mirrored_so_it_matches_the_users_own_movement():
    """A camera sees the user as another person does; a tile that did not
    mirror would show their hand going the wrong way."""
    x0, y0, w, h = voice_hand.CAMERA
    left = voice_hand.hand_point(voice_hand.Hand(x=0.1, y=0.5))
    right = voice_hand.hand_point(voice_hand.Hand(x=0.9, y=0.5))
    assert left[0] > right[0], "x is mirrored across the tile"
    assert x0 <= min(left[0], right[0]) and max(left[0], right[0]) <= x0 + w
    assert y0 <= left[1] <= y0 + h


def test_a_sample_becomes_a_hand_and_a_nan_does_not():
    assert voice_hand.hand_from_sample((0.25, 0.75, True)) == \
        voice_hand.Hand(0.25, 0.75, True)
    nan = voice_hand.hand_from_sample((float("nan"), 3.0, False))
    assert nan.x == 0.5 and nan.y == 1.0
    assert voice_hand.hand_from_sample(None) == voice_hand.Hand()
    assert voice_hand.hand_from_sample(("x", None)) == voice_hand.Hand()


def test_pinch_is_the_only_pose_the_overlay_can_know():
    assert voice_hand.pose_of(voice_hand.Hand(pinch=True)) == "pinch"
    assert voice_hand.pose_of(voice_hand.Hand(pinch=False)) == "open"


def test_the_skeleton_has_four_fingers_and_a_pinch_curls_the_index():
    open_hand = voice_hand._finger_joints((640.0, 300.0), 1.0, "open")
    pinch = voice_hand._finger_joints((640.0, 300.0), 1.0, "pinch")
    assert len(open_hand) == 4 == len(pinch)
    # Straight index points up; the pinching one curls toward the thumb.
    assert open_hand[0][1][1] < open_hand[0][0][1]
    assert pinch[0][1][0] < pinch[0][0][0], "the pinching index moves toward the thumb"


# ── the window ──────────────────────────────────────────────────────────────

def test_the_window_flags_are_the_three_that_matter_and_not_click_through():
    class Flags:
        FramelessWindowHint = 1
        Tool = 2
        WindowStaysOnTopHint = 4
        WindowTransparentForInput = 8

    class Qt:
        WindowType = Flags

    flags = voice_overlay.VoiceOverlay.window_flags(Qt)
    assert flags == 1 | 2 | 4
    assert not flags & Flags.WindowTransparentForInput, (
        "a click-through overlay cannot receive the Esc that closes it")


def test_starting_without_qt_fails_survivable_and_says_why():
    """Every surface in this program owes the same contract: a failure to build
    is reported, never raised. There is no display on the machine that runs
    this, so the failure is real rather than simulated."""
    overlay = voice_overlay.VoiceOverlay()
    assert overlay.start() is False or overlay.available is True
    if not overlay.available:
        assert overlay.error, "a surface that did not build must say why"


def test_every_method_is_a_no_op_before_the_window_exists():
    overlay = voice_overlay.VoiceOverlay()
    overlay.set_state("speaking")
    overlay.set_hand((0.1, 0.2, True))
    overlay.set_transcript("x")
    overlay.set_answer("y")
    overlay.set_camera_available(True)
    overlay.show()
    overlay.hide()
    assert overlay.available is False
    overlay.stop()                       # must not raise with no window


# ── the module split ────────────────────────────────────────────────────────

def test_no_ui_module_knows_about_qt_at_import_time():
    """The seam that makes every test above possible.

    `ui/voice_overlay.py` may only touch Qt inside a function. A module-level
    `from PyQt6 import ...` makes the module unimportable on a machine with no
    display — which is every CI runner this repo has.
    """
    for name in ("voice_overlay.py", "voice_paint.py", "voice_hand.py"):
        tree = ast.parse((ROOT / "ui" / name).read_text(encoding="utf-8"))
        for node in tree.body:
            if isinstance(node, ast.ImportFrom) and node.module:
                assert not node.module.startswith("PyQt6"), (name, node.module)
            if isinstance(node, ast.Import):
                assert all(not a.name.startswith("PyQt6") for a in node.names), name


def test_the_painter_never_decides_anything():
    """`ui/voice_paint` asks the overlay. A painter that OWNED a rule would put
    that rule back where no test can reach it — so the rules are looked for as
    definitions, not as calls: calling `status_word` is the painter doing its
    job; defining it would be the painter doing the overlay's.
    """
    source = (ROOT / "ui" / "voice_paint.py").read_text(encoding="utf-8")
    for rule in ("def edge_alpha", "def status_word", "def frame_words",
                 "def lines_for", "def camera_label"):
        assert rule not in source, f"{rule} belongs to ui/voice_overlay"
    assert "overlay.glow()" in source, "the painter must ask, not compute"
    assert "_model.status_word(" in source, "and it must use the overlay's answer"


def test_the_split_is_three_modules_and_each_is_under_the_ceiling():
    sizes = {name: len((ROOT / "ui" / name).read_text(encoding="utf-8").splitlines())
             for name in ("voice_overlay.py", "voice_paint.py", "voice_hand.py")}
    over = {name: n for name, n in sizes.items() if n > 600}
    assert over == {}, f"past the 600-line ceiling: {over}"


@pytest.mark.parametrize("name", ["voice_overlay.py", "voice_paint.py", "voice_hand.py"])
def test_every_module_says_why_in_its_docstring(name):
    """The house rule: a module explains why it exists, not what it does."""
    text = (ROOT / "ui" / name).read_text(encoding="utf-8")
    doc = ast.get_docstring(ast.parse(text)) or ""
    assert len(doc.splitlines()) >= 8, f"{name} has no real docstring"
    assert "WHY" in doc, f"{name} does not say why it exists"


# ── the paint itself, against a painter that records ────────────────────────

def _paint(overlay):
    """Run the real painter code and return what it drew.

    The fake painter is used when `QtGui` cannot import — and on this machine it
    cannot, because `libxkbcommon.so.0` is missing. The point is that the code
    under test is `ui/voice_paint`, not the fake: a `fillRect` with a `str` where
    a gradient belongs, or a `setPen` on a name that does not exist, still fails.
    """
    from tests.fakepainter import RecordingPainter, install_fake_qt_gui, qt_or_fake

    _name, used_fake = qt_or_fake()
    if used_fake:
        install_fake_qt_gui()
    from ui import voice_paint

    painter = RecordingPainter()
    voice_paint.paint_frame(painter, voice_overlay.REFERENCE, overlay)
    return painter


def test_an_inactive_overlay_draws_no_edge_and_no_glow():
    """The footnote's first promise, asserted on the DRAWING and not only on
    the number: an edge drawn at zero alpha would still be an edge."""
    overlay = voice_overlay.VoiceOverlay(state="listening")
    painter = _paint(overlay)
    assert "fillRect" not in painter.names(), "no glow while hidden"
    assert "drawRect" not in painter.names(), "no border while hidden"


def test_an_active_overlay_draws_the_two_pixel_edge_and_the_glow():
    overlay = voice_overlay.VoiceOverlay(state="listening")
    overlay.show()
    painter = _paint(overlay)
    names = painter.names()
    assert "fillRect" in names, "the radial glow is missing"
    assert "drawRect" in names, "the 2 px edge is missing"

    edge_call = next(args for name, args, _ in painter.calls if name == "drawRect")
    rect = edge_call[0]
    width = rect.width() if callable(getattr(rect, "width", None)) else rect.w
    x = rect.x() if callable(getattr(rect, "x", None)) else rect.x
    assert abs(width - (1280 - 2)) < 0.01 and abs(x - 1.0) < 0.01, (
        "the border must sit inside the frame, or half of it is off screen")


def test_the_overlay_does_not_draw_a_fabricated_audio_meter():
    """No audio levels are wired here, so fixed bars would falsely imply input."""
    overlay = voice_overlay.VoiceOverlay(state="listening")
    overlay.show()
    painter = _paint(overlay)
    assert sum(name == "drawRect" for name, _, _ in painter.calls) == 1


def test_the_transcript_pill_is_drawn_behind_the_words():
    """b04() fills a 640x76 rounded rect behind the transcript; the overlay
    drew the words but never the pill, so the transcript had no surface.

    The pill is the transcript's surface, so it is drawn at the artboard's
    geometry — a rounded rect of the panel fill and the accent-line border,
    640 wide and the pill's height tall, at the artboard's radius. The camera
    tile is the only other rounded rect on the frame, and it is smaller, so
    the width and height separate the two.
    """
    overlay = voice_overlay.VoiceOverlay(state="listening")
    overlay.show()
    painter = _paint(overlay)

    pills = [args for name, args, _ in painter.calls
             if name == "drawRoundedRect" and len(args) == 3
             and abs((args[0].width() if callable(getattr(args[0], "width", None)) else args[0].w) - voice_overlay.PILL_W) < 1
             and abs((args[0].height() if callable(getattr(args[0], "height", None)) else args[0].h) - voice_overlay.PILL_H) < 1]
    assert len(pills) == 1, "the transcript pill was not drawn"
    rect = pills[0][0]
    x = rect.x() if callable(getattr(rect, "x", None)) else rect.x
    y = rect.y() if callable(getattr(rect, "y", None)) else rect.y
    assert (x, y) == tuple(voice_overlay.PILL_AT), (
        "the pill is not at the artboard's position")
    assert abs(pills[0][1] - voice_overlay.PILL_RADIUS) < 1, (
        "the pill does not use the artboard's corner radius")


def test_the_paused_tile_says_the_gestures_are_paused_and_draws_no_hand():
    overlay = voice_overlay.VoiceOverlay(state="listening")
    overlay.show()
    overlay.set_gestures_paused(True)
    painter = _paint(overlay)
    assert voice_overlay.PAUSED_WORD in painter.drawn_words()
    # The tile still exists — it is the hand that is gone.
    assert "drawRoundedRect" in painter.names()


def test_the_frame_draws_the_words_the_artboard_draws():
    overlay = voice_overlay.VoiceOverlay(state="listening")
    overlay.show()
    overlay.set_camera_available(True)
    overlay.set_transcript("ringkas tabel ini dan tandai baris yang lewat anggaran")
    overlay.set_answer("Baris 7 dan 11 melewati plafon 12% dan 4%.")
    painter = _paint(overlay)
    words = painter.drawn_words()

    assert "MENDENGARKAN" in words
    assert "LAYANAN GESTUR AKTIF" in words
    assert "ringkas tabel ini" in words
    assert "plafon" in words
    assert "Glow tepi hanya saat overlay aktif" in words
    assert "Esc keluar" in words and "Ctrl+Alt+G" in words


def test_the_orange_never_appears_on_the_overlay():
    """Amber is reserved for warnings and risky actions in this design. Being
    listened to is neither."""
    overlay = voice_overlay.VoiceOverlay(state="speaking")
    overlay.show()
    painter = _paint(overlay)
    colours = [str(c) for c in painter.calls if c[0] in ("setPen", "setBrush", "fillRect")]
    assert all("f5a524" not in c and "amber" not in c.lower() for c in colours)


def test_a_broken_glow_does_not_take_the_window_down():
    """Every entry point swallows: the alternative is an exception in an event
    loop whose only job is to be looked at."""
    from ui import voice_paint

    class Exploding:
        def __getattr__(self, name):
            def boom(*a, **k):
                raise RuntimeError(f"{name} exploded")

            return boom

    overlay = voice_overlay.VoiceOverlay(state="listening")
    overlay.show()
    voice_paint.paint_frame(Exploding(), voice_overlay.REFERENCE, overlay)   # no raise
