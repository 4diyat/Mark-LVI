"""The face's lighting, skin and eyelids — checked without a display.

WHY THESE TESTS EXIST AND WHY THEY CAN RUN HERE
    The avatar is drawn with QPainter, so the picture itself needs PyQt6 and a
    display, and no CI runner has one. That is exactly how a renderer rots: the
    only thing that ever looked at it was a pair of eyes, and those are not in
    the pipeline.

    So everything that decides whether the face reads as human was moved into
    `core/avatar_face` — Qt-free, numpy only — and asserted here on the real
    mesh. Each test names a property of a human face rather than a number the
    code happens to produce:

      * a socket is darker than the cheek beside it (occlusion exists at all);
      * a nose is warmer than a forehead (skin has a colour temperature);
      * a blink closes the eye completely and leaves everything else alone;
      * light comes from one side, so the two cheeks are not the same shade;
      * none of it depends on the accent colour being blue.

    A test that asserted "brightness at vertex 91 is 0.4127" would pin the code
    without pinning the picture, and would have to be rewritten by every
    deliberate change. These survive retuning.
"""
from __future__ import annotations

import numpy as np
import pytest

from core import avatar_face as af
from core.avatar_mesh import get_head_mesh


@pytest.fixture(scope="module")
def head():
    """The real head: MediaPipe's canonical face plus the cranium and neck."""
    mesh = get_head_mesh()
    frames = af.FaceFrames(mesh["verts"], mesh["landmarks"], mesh["n_head"])
    return mesh, frames


@pytest.fixture(scope="module")
def fields(head):
    mesh, frames = head
    return {
        "cavity": af.cavity(mesh["verts"], frames),
        "warm": af.warm(mesh["verts"], frames),
    }


def _nearest(verts, point) -> int:
    return int(np.argmin(np.linalg.norm(verts - np.asarray(point, dtype=np.float32),
                                        axis=1)))


# ── occlusion ────────────────────────────────────────────────────────────────

def test_the_eye_socket_is_darker_than_the_cheek(head, fields):
    """The single property that was missing from the old renderer.

    Every cavity read as *brighter* than the skin around it, because a
    single-colour ramp has no notion of occlusion at all. Human vision reads a
    face by those dark recesses; without them the correctness of the geometry
    does not matter.
    """
    mesh, frames = head
    cav = fields["cavity"]
    socket = cav[_nearest(mesh["verts"], frames.eye_l)]
    cheek = cav[_nearest(mesh["verts"],
                         [frames.eye_l[0] * 0.72,
                          frames.eye_l[1] - 0.17 * frames.face_w,
                          0.52])]
    assert socket > 0.35, f"the socket is not occluded at all ({socket:.3f})"
    assert socket > cheek + 0.25, f"socket {socket:.3f} vs cheek {cheek:.3f}"


def test_the_mouth_line_and_the_nostrils_are_occluded_too(head, fields):
    """A face has more cavities than the eyes, and they are what the eye uses
    to place the mouth and the nose on the surface."""
    mesh, frames = head
    cav = fields["cavity"]
    at_mouth = cav[_nearest(mesh["verts"], frames.mouth)]
    at_nose = cav[_nearest(mesh["verts"],
                           [frames.nose[0] + 0.036 * frames.face_w,
                            frames.nose[1] - 0.045 * frames.face_w,
                            frames.nose[2] - 0.10])]
    assert at_mouth > 0.25, f"no occlusion at the mouth ({at_mouth:.3f})"
    assert at_nose > 0.25, f"no occlusion under the nose ({at_nose:.3f})"


def test_occlusion_never_reaches_the_back_of_the_head(head, fields):
    """"Dark inside a cavity" is a face; "dark on the occiput" is a hole.

    The field is gated to the front, and to the head — the neck fades out on its
    own and must not be given a second, competing treatment.
    """
    mesh, frames = head
    cav = fields["cavity"]
    back = mesh["verts"][:, 2] < -0.3
    assert cav[back].max() == pytest.approx(0.0, abs=1e-6)
    assert cav[frames.n_head:].max() == pytest.approx(0.0, abs=1e-6)


def test_occlusion_is_a_smooth_field_not_a_patch(head, fields):
    """A hard-edged blob would read as dirt on the lens. Neighbouring vertices
    on a mesh this dense must differ by little."""
    mesh, frames = head
    cav = fields["cavity"]
    faces = mesh["faces"]
    d = np.abs(cav[faces[:, 0]] - cav[faces[:, 1]]).max()
    assert d < 0.55, f"occlusion jumps by {d:.3f} across a single edge"


# ── skin colour ──────────────────────────────────────────────────────────────

def test_the_nose_and_lips_are_warmer_than_the_forehead(head, fields):
    """A real face is not one colour: the nose, cheeks and lips run warmer than
    the forehead and the jaw. On a hologram this is the difference between "a
    glowing head" and "a person made of light"."""
    mesh, frames = head
    warm = fields["warm"]
    nose = warm[_nearest(mesh["verts"], frames.nose)]
    lips = warm[_nearest(mesh["verts"], frames.mouth)]
    forehead = warm[_nearest(mesh["verts"], [0.0, frames.brow[1] + 0.30, 0.45])]
    assert nose > forehead + 0.2, f"nose {nose:.3f} vs forehead {forehead:.3f}"
    assert lips > forehead + 0.2, f"lips {lips:.3f} vs forehead {forehead:.3f}"


class _Colour:
    """The duck type a QColor satisfies for the palette code: three channels.

    Using this instead of importing PyQt6 is what lets the colour maths be
    tested on a headless machine — and it also proves the palette code has no
    hidden dependency on Qt beyond those three methods.
    """

    def __init__(self, r: int, g: int, b: int) -> None:
        self._rgb = (r, g, b)

    def red(self) -> int:
        return self._rgb[0]

    def green(self) -> int:
        return self._rgb[1]

    def blue(self) -> int:
        return self._rgb[2]


@pytest.mark.parametrize("accent", [(255, 107, 0), (0, 212, 255), (120, 255, 180)])
def test_warm_skin_is_redder_and_darker_skin_is_darker(accent):
    """"Warmer" has to mean warmer in a way that survives the theme.

    The palette is derived from the accent colour so the avatar retints for
    free, which means the warm column cannot be a fixed skin tone — but a blue
    theme must still have blood under the skin, so the shift carries a small
    fixed red bias on top of the accent.
    """
    bg = _Colour(0, 6, 10)
    primary = _Colour(0, 212, 255)
    lo, deep, mid, hi, warm = af.skin_columns(bg, primary, _Colour(*accent))

    # Warm is red-shifted relative to ordinary skin.
    assert warm[0] - mid[0] > warm[2] - mid[2]
    # A crevice is darker than the skin at the same light level.
    assert deep.mean() < lo.mean()
    # And the highlight is brighter than ordinary skin, or the head has no form.
    assert hi.mean() > mid.mean()


def test_ordinary_skin_sits_between_the_shadow_and_the_highlight():
    bg, primary = _Colour(0, 6, 10), _Colour(0, 212, 255)
    lo, deep, mid, hi, warm = af.skin_columns(bg, primary, _Colour(255, 107, 0))
    assert deep.mean() <= mid.mean() <= hi.mean()
    assert lo.mean() <= mid.mean()


# ── blink ────────────────────────────────────────────────────────────────────

def test_the_blink_weight_is_the_ring_the_geometry_and_nothing_else(head):
    """The lid rig must be the landmark ring (which `_check_landmarks` already
    proves is an eye) plus a skirt — not a set of hand-picked vertices that
    might turn out to be a cheekbone."""
    mesh, frames = head
    lids = af.lid_weights(mesh["verts"], mesh["landmarks"], frames)
    for key in ("eye_l", "eye_r"):
        idx = mesh["landmarks"][key]
        up, dn = lids[key]
        assert up[idx].max() == pytest.approx(1.0)
        assert dn[idx].max() == pytest.approx(1.0)
        # Some ring vertices are upper and some are lower: a rig that put them
        # all on one side would close the eye by moving it bodily upwards.
        assert (up[idx] > 0.9).any() and (dn[idx] > 0.9).any()
    for up, dn in lids.values():
        assert up[frames.n_head:].max() == pytest.approx(0.0)
        assert dn[frames.n_head:].max() == pytest.approx(0.0)


def test_a_closed_eye_is_exactly_closed(head):
    """A blink that leaves a 2-pixel gap is a blink that looks like a squint.

    The target is the ring's own mid-height, so "fully closed" is true by
    construction rather than by a tuned constant that can drift away from the
    geometry it was tuned on.
    """
    mesh, frames = head
    lids = af.lid_weights(mesh["verts"], mesh["landmarks"], frames)
    shut = af.blink(mesh["verts"], lids, 1.0, mesh["landmarks"])
    for key in ("eye_l", "eye_r"):
        idx = mesh["landmarks"][key]
        height = float(np.ptp(shut[idx, 1]))
        assert height < 1e-5, f"{key} is still {height:.5f} open"


def test_a_blink_leaves_the_rest_of_the_face_alone(head):
    """The skirt around the socket may follow a little; the mouth may not.

    A rig that leaked past the eye would have the blink pull the cheek down,
    and at HUD size that reads as a twitch rather than a blink.
    """
    mesh, frames = head
    lids = af.lid_weights(mesh["verts"], mesh["landmarks"], frames)
    shut = af.blink(mesh["verts"], lids, 1.0, mesh["landmarks"])

    mouth = mesh["landmarks"]["lips_out"]
    assert np.allclose(shut[mouth], mesh["verts"][mouth], atol=1e-6)
    brow = mesh["landmarks"]["brow_l"]
    assert np.allclose(shut[brow], mesh["verts"][brow], atol=1e-6)


def test_half_a_blink_is_half_way(head):
    """Linear in the amount, because the eye animation feeds a number that is
    already eased — a second curve here would make the motion read as elastic."""
    mesh, frames = head
    lids = af.lid_weights(mesh["verts"], mesh["landmarks"], frames)
    v = mesh["verts"]
    half = af.blink(v, lids, 0.5, mesh["landmarks"])
    full = af.blink(v, lids, 1.0, mesh["landmarks"])
    # Compared vertex by vertex, not as two maxima: the vertex that travels
    # furthest when fully shut is not necessarily the one that travels furthest
    # at half. The ratio has to hold for every vertex, which is what "linear in
    # the amount" means.
    travel_full = np.abs(full[:, 1] - v[:, 1])
    # "Every vertex that actually moves." A vertex whose whole travel is one
    # float32 ulp has no ratio worth asserting: it is cancellation noise, not
    # motion, and demanding linearity there is demanding the impossible.
    moved = travel_full > travel_full.max() * 1e-2
    assert moved.sum() > 10
    ratio = np.abs(half[:, 1] - v[:, 1])[moved] / travel_full[moved]
    # 1e-3 of a head-half-height is a tenth of a pixel at HUD size; the spread
    # that remains is float32 cancellation where a vertex sits on the lid line.
    assert np.allclose(ratio, 0.5, atol=1e-3), f"half a blink is {ratio.min():.3f}"


def test_a_blink_of_zero_changes_nothing(head):
    mesh, frames = head
    lids = af.lid_weights(mesh["verts"], mesh["landmarks"], frames)
    same = af.blink(mesh["verts"], lids, 0.0, mesh["landmarks"])
    assert np.array_equal(same, mesh["verts"])


# ── lighting ─────────────────────────────────────────────────────────────────

def test_the_light_comes_from_one_side(head, fields):
    """A face lit from straight ahead is a mask: every front-facing facet
    returns the same value. The key light leans off-axis on purpose, and the
    test asserts the consequence — the two cheeks are not the same shade."""
    mesh, frames = head
    sh = af.shade_facets(mesh["verts"], mesh["normals"], mesh["faces"], frames,
                         fields["cavity"], fields["warm"], mesh["fade"], 0.0)
    verts, faces, bright = mesh["verts"], mesh["faces"], sh["bright"]
    cent = verts[faces].mean(axis=1)
    front = (sh["nz"] > 0.35) & (cent[:, 2] > 0.35)

    def mean_bright(x_sign: float) -> float:
        sel = front & (np.sign(cent[:, 0]) == x_sign)
        sel &= np.abs(cent[:, 0]) > 0.18
        sel &= np.abs(cent[:, 1] - frames.eye_mid[1]) < 0.32
        assert sel.sum() > 20, "not enough facets to compare"
        return float(bright[sel].mean())

    left, right = mean_bright(-1.0), mean_bright(1.0)
    assert abs(left - right) > 0.02, f"cheeks are equally lit ({left:.3f}/{right:.3f})"


def test_the_socket_is_darker_than_the_cheek_in_the_rendered_shading(head, fields):
    """The occlusion field is only worth having if it reaches the pixels. The
    old renderer computed a light value per facet and never consulted anything
    like this."""
    mesh, frames = head
    sh = af.shade_facets(mesh["verts"], mesh["normals"], mesh["faces"], frames,
                         fields["cavity"], fields["warm"], mesh["fade"], 0.0)
    verts, faces, bright = mesh["verts"], mesh["faces"], sh["bright"]
    cent = verts[faces].mean(axis=1)
    visible = sh["nz"] > 0.1

    def at(point) -> float:
        d = np.linalg.norm(cent - np.asarray(point, dtype=np.float32), axis=1)
        d[~visible] = 1e9
        return float(bright[int(np.argmin(d))])

    socket = at([frames.eye_l[0] * 0.92, frames.eye_l[1] + 0.02, 0.62])
    cheek = at([frames.eye_l[0] * 0.72, frames.eye_l[1] - 0.17 * frames.face_w, 0.52])
    assert socket < cheek - 0.10, f"socket {socket:.3f} vs cheek {cheek:.3f}"


def test_brightness_stays_inside_the_palette(head, fields):
    """The painter indexes a table with these numbers; one above 1.0 or below
    0.0 is an out-of-range index, i.e. a crash rather than a wrong colour."""
    mesh, frames = head
    sh = af.shade_facets(mesh["verts"], mesh["normals"], mesh["faces"], frames,
                         fields["cavity"], fields["warm"], mesh["fade"], 1.0)
    assert sh["bright"].min() >= 0.0
    assert sh["bright"].max() <= 1.0
    assert np.isfinite(sh["bright"]).all()
    assert sh["heat"].min() >= 0.0 and sh["heat"].max() <= 1.0
    assert sh["dark"].min() >= 0.0 and sh["dark"].max() <= 1.0


def test_speaking_brightens_the_face(head, fields):
    """`amp` is the audio level. The head lights up with its own voice — that
    was true before this change and must stay true."""
    mesh, frames = head
    args = (mesh["verts"], mesh["normals"], mesh["faces"], frames,
            fields["cavity"], fields["warm"], mesh["fade"])
    quiet = af.shade_facets(*args, 0.0)["bright"].mean()
    loud = af.shade_facets(*args, 1.0)["bright"].mean()
    assert loud > quiet
