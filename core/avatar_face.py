"""
The face's *lighting and surface* maths — Qt-free, numpy only, testable alone.

WHY THIS IS A SEPARATE MODULE
    The head in `core/avatar.py` is drawn with QPainter and that requires a
    display and PyQt6, which no CI runner and no container here can load for a
    unit test. But the part of a face that decides whether it reads as human —
    where the shadows fall, how the skin changes colour, how an eyelid closes —
    is pure arithmetic over the mesh. Keeping it here means the arithmetic can
    be checked on a machine with nothing but numpy, and it means a regression in
    "the cheek is in shadow" is a failing assertion rather than something
    somebody has to notice in a 250-pixel hologram.

WHAT MAKES A FACE READ AS A PERSON (and what was missing)
    `avatar.py` already had the two things that cannot be faked: real measured
    topology (MediaPipe's canonical model) and real motion (visemes, blinks,
    saccades). What it did not have was light and skin. A single ramp of one
    colour, applied per facet, gives a uniform glowing shell: every cavity —
    the eye sockets, under the nose, under the lip — reads as *brighter* than
    the cheek it sits in, because there is no occlusion anywhere in it. Human
    perception reads a face by those cavities; a face without them reads as a
    mask no matter how correct the geometry is.

    So this module supplies three fields, all measured from the mesh rather
    than tuned by eye:

    `cavity`  where light cannot reach — eye sockets, under the brow ridge,
              around the nostrils, the mouth line, under the jaw.
    `warm`    where blood shows — nose, cheeks, lips, ears. A face is never
              one colour, and the difference is small but decisive.
    `lid_up` / `lid_dn`
              which vertices belong to the upper and lower eyelid, so a blink
              can actually *deform the surface* instead of squashing a drawn
              outline over unchanged skin.

    All three are derived from landmark positions and from the frontmost
    vertex, never from hand-picked indices: `_check_landmarks` already proves
    the rings are where they claim to be, and a hardcoded "nostril is vertex
    98" is exactly the kind of guess that silently animates a cheekbone.
"""

from __future__ import annotations

import numpy as np

# Key light: high on the viewer's left, leaning off the camera axis. Weighted
# towards the camera, every front-facing facet returns the same value and the
# face renders as a flat mask — that was the old lighting's second problem.
LIGHT = np.array([-0.55, 0.50, 0.52], dtype=np.float32)
LIGHT /= np.linalg.norm(LIGHT)

# How much of the shading comes from the smooth (vertex) normal rather than the
# facet normal. Both matter and for opposite reasons: the facet normal is what
# preserves anatomy — averaging it away smears the nose and the lips into their
# neighbours — while the vertex normal is what stops 898 triangles reading as
# 898 flat chips of plastic. Mixing them is not a compromise, it is standard
# practice: the facet normal carries the silhouette of a form, the smooth one
# carries the falloff across it.
SMOOTH_MIX = 0.55

# Specular exponent and strength. A tight lobe (28) on the brow ridge, nose and
# chin is the "wet" highlight that reads as skin rather than chalk. Broad and
# weak it becomes a plastic sheen over the whole face, which is why the
# exponent is high and the weight is low.
SPEC_POW = 26.0
SPEC_GAIN = 0.34


def _gauss2(dx, dy, sx, sy, dy2=None, sy2=None):
    """Anisotropic gaussian in the face plane, optionally with a second axis.

    Written out rather than using a scipy/numpy helper because it is called on
    every frame in a form the compiler inlines well, and because `np.exp` over
    three thousand floats is the whole cost of the occlusion field.
    """
    d = (dx / sx) ** 2 + (dy / sy) ** 2
    if dy2 is not None:
        d = d + (dy2 / sy2) ** 2
    return np.exp(-d)


class FaceFrames:
    """The handful of measured positions everything else is placed against.

    Named and stored once instead of recomputed per field, and derived from the
    landmark rings the mesh builder has already verified — see
    `avatar_mesh._check_landmarks`.
    """

    __slots__ = ("eye_l", "eye_r", "eye_mid", "brow", "mouth", "nose",
                 "chin_y", "n_head", "face_w")

    def __init__(self, verts: np.ndarray, landmarks: dict, n_head: int) -> None:
        head = verts[:n_head]
        self.n_head = n_head
        self.eye_l = head[landmarks["eye_l"]].mean(axis=0)
        self.eye_r = head[landmarks["eye_r"]].mean(axis=0)
        self.eye_mid = (self.eye_l + self.eye_r) * 0.5
        self.brow = head[np.concatenate([landmarks["brow_l"],
                                         landmarks["brow_r"]])].mean(axis=0)
        self.mouth = head[landmarks["lips_out"]].mean(axis=0)
        # The nose TIP is the frontmost vertex of the head. The canonical model
        # has no nose landmark, and picking an index from memory is how you end
        # up animating something that turns out to be a cheekbone.
        self.nose = head[int(np.argmax(head[:, 2]))]
        self.chin_y = float(head[:, 1].min())
        # Head width at eye level, used to scale every radius below: the
        # weights are then proportions of *this* head rather than magic
        # numbers that only work at one scale.
        self.face_w = float(np.ptp(head[:, 0]))


def cavity(verts: np.ndarray, frames: FaceFrames) -> np.ndarray:
    """0..1, where light cannot reach. The field human vision reads a face by.

    Five sources, each placed on measured geometry:

      * the eye sockets — deepest at the two eye centres, and biased *below*
        the lid line because an eyebrow ridge casts a shadow onto the upper
        lid, not the other way round;
      * the brow ridge's own underside;
      * the nostril shadow, just under and behind the nose tip;
      * the mouth line, where the lips part and the corners tuck in;
      * under the jaw, where the chin's shadow ends the face.

    Everything is gated to the front of the face (z > 0), because a "cavity"
    painted on the back of the head is a hole.
    """
    x, y, z = verts[:, 0], verts[:, 1], verts[:, 2]
    w = frames.face_w
    out = np.zeros(len(verts), dtype=np.float32)

    # Eye sockets. Radii are fractions of the face's own width so the field is
    # scale-free; the vertical bias (+0.055 downward) is the lid shadow.
    for c in (frames.eye_l, frames.eye_r):
        out += 0.90 * _gauss2(x - c[0], y - (c[1] + 0.030 * w),
                              0.105 * w, 0.082 * w, z - c[2], 0.28)

    # Underside of the brow ridge: a horizontal band, not a point.
    out += 0.34 * _gauss2(x - frames.eye_mid[0],
                          y - (frames.brow[1] - 0.038 * w),
                          0.30 * w, 0.030 * w, z - frames.brow[2], 0.26)

    # Nostrils: just under the tip, either side of the septum. Placed on the
    # measured tip rather than a remembered vertex index, and only slightly
    # back — the underside of a nose is where the shadow is, not the inside of
    # the skull.
    for sx in (-1.0, 1.0):
        out += 0.58 * _gauss2(x - (frames.nose[0] + sx * 0.036 * w),
                              y - (frames.nose[1] - 0.045 * w),
                              0.040 * w, 0.030 * w,
                              z - (frames.nose[2] - 0.10), 0.26)

    # The mouth: the seam between the lips plus the corners, which tuck in and
    # go dark in every human face.
    out += 0.62 * _gauss2(x - frames.mouth[0], y - frames.mouth[1],
                          0.115 * w, 0.026 * w, z - frames.mouth[2], 0.22)
    for sx in (-1.0, 1.0):
        out += 0.30 * _gauss2(x - (frames.mouth[0] + sx * 0.105 * w),
                              y - frames.mouth[1],
                              0.030 * w, 0.030 * w, z - frames.mouth[2], 0.22)

    # Under the jaw. A softer, wider value: this is the face ending, not a hole.
    out += 0.42 * _gauss2(x, y - (frames.chin_y + 0.055 * w),
                          0.26 * w, 0.050 * w)

    # Front of the head only, and never on the neck stub (which fades anyway).
    front = np.clip(z / 0.30, 0.0, 1.0)
    out *= front
    out[frames.n_head:] = 0.0
    return np.clip(out, 0.0, 1.0).astype(np.float32)


def warm(verts: np.ndarray, frames: FaceFrames) -> np.ndarray:
    """0..1, where the skin shows blood: nose, cheeks, lips, ears.

    The whole head is one accent colour, and a real face never is: the nose and
    cheeks run several shades warmer than the forehead and jaw. In a hologram
    this is the difference between "a glowing head" and "a person rendered as
    light", and it costs one multiply per vertex because the tint itself comes
    from the theme's own accent colour.
    """
    x, y, z = verts[:, 0], verts[:, 1], verts[:, 2]
    w = frames.face_w
    out = np.zeros(len(verts), dtype=np.float32)

    # Cheeks: below and outside each eye.
    for c in (frames.eye_l, frames.eye_r):
        out += 0.70 * _gauss2(x - (c[0] + np.sign(c[0]) * 0.02 * w),
                              y - (c[1] - 0.135 * w),
                              0.13 * w, 0.11 * w, z - c[2], 0.30)

    # Nose and its bridge — the warmest part of most faces.
    out += 0.55 * _gauss2(x - frames.nose[0], y - frames.nose[1],
                          0.075 * w, 0.10 * w, z - frames.nose[2], 0.26)

    # Lips.
    out += 0.75 * _gauss2(x - frames.mouth[0], y - frames.mouth[1],
                          0.11 * w, 0.055 * w, z - frames.mouth[2], 0.24)

    # Ears: at the widest point, at eye height, on the sides.
    for sx in (-1.0, 1.0):
        out += 0.80 * _gauss2(x - sx * 0.47 * w, y - (frames.eye_mid[1] - 0.02 * w),
                              0.06 * w, 0.13 * w)

    front = np.clip(z / 0.25, 0.0, 1.0)
    out *= front
    out[frames.n_head:] = 0.0
    return np.clip(out, 0.0, 1.0).astype(np.float32)


def lid_weights(verts: np.ndarray, landmarks: dict,
                frames: FaceFrames) -> dict[str, tuple[np.ndarray, np.ndarray]]:
    """Per eye, which vertices are the upper and the lower lid (0..1 each).

    ONE DICT PER EYE, AND THAT IS A FIX, NOT A STYLE CHOICE
        The first version returned two arrays covering both eyes at once, taking
        the maximum of each. `blink()` then walked both eyes' mid-heights over
        the same combined arrays, so a vertex under the left eye that also had a
        little weight from the right eye's skirt was pulled towards the left lid
        line and then towards the right one — a two-step move whose size depends
        on the *distance between the eyes*, which is how a blink ended up moving
        skin by more than the lid travels. Per-eye weights make that impossible
        rather than unlikely.

    Upper and lower are decided by which side of the ring's own mean each ring
    vertex lies on. That sounds fragile and is not: the ring is an eye-shaped
    loop, so its mean sits between the lids by construction, and the two halves
    are exactly what the anatomy calls upper and lower.
    """
    out: dict[str, tuple[np.ndarray, np.ndarray]] = {}
    x, y, z = verts[:, 0], verts[:, 1], verts[:, 2]

    for key in ("eye_l", "eye_r"):
        idx = landmarks[key]
        ring = verts[idx]
        c = ring.mean(axis=0)
        mid = float(c[1])
        upper = ring[:, 1] > mid

        up = np.zeros(len(verts), dtype=np.float32)
        dn = np.zeros(len(verts), dtype=np.float32)

        # A soft skirt around the socket so the surrounding skin follows the lid
        # a little. Without it the ring closes and the skin around it stays
        # rigid, which pinches the corners.
        g = _gauss2(x - c[0], y - c[1], 0.075, 0.062, z - c[2], 0.13)
        np.maximum(up, g * (y > mid), out=up)
        np.maximum(dn, g * (y <= mid), out=dn)

        # The ring itself leads: those vertices must reach the lid line when the
        # weight is 1, or the "closed" eye is a hole with a bar across it.
        up[idx[upper]] = 1.0
        dn[idx[~upper]] = 1.0

        up[frames.n_head:] = 0.0
        dn[frames.n_head:] = 0.0
        out[key] = (up, dn)
    return out


def blink(verts: np.ndarray, lids: dict[str, tuple[np.ndarray, np.ndarray]],
          amount: float, landmarks: dict) -> np.ndarray:
    """Close the eyes by `amount` (0 open .. 1 shut), returning new positions.

    The whole trick is that the target is *the lid line itself*: every lid
    vertex is interpolated toward its own eye ring's mid-height, so at amount=1
    they meet exactly and the outline becomes a line. No second set of magic
    offsets, no "how far down is a blink" constant to get wrong — a fully
    closed eye closes by definition.

    Upper and lower weights are summed into ONE weight per vertex before the
    move. Applying them as two moves — which the first version did — pulls a
    vertex halfway, then halfway again, so half a blink travels three quarters
    of the way and the eyelid moves like it is on a rubber band.
    """
    amount = float(min(1.0, max(0.0, amount)))
    out = verts.copy()
    if amount <= 0.0:
        return out

    for key, (up, dn) in lids.items():
        idx = landmarks[key]
        mid = float(verts[idx, 1].mean())

        w = np.minimum(1.0, (up + dn) * amount)
        out[:, 1] -= (out[:, 1] - mid) * w

        # The lid bulges very slightly forward as it closes — a closed eye is
        # convex, not flat, and this is what keeps it from looking like a cut.
        out[:, 2] += w * 0.004
    return out


def light(verts: np.ndarray, normals: np.ndarray, faces: np.ndarray,
          frames: FaceFrames, cav: np.ndarray, fade: np.ndarray,
          amp: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Per-facet brightness, warmth and darkness — the whole lighting model.

    Returns three arrays, one per visible facet:
        bright  the palette index fraction, 0 (background) .. 1 (highlight)
        heat    how warm that facet is, 0 .. 1
        dark    how deeply occluded it is, 0 .. 1

    `dark` is returned separately instead of being folded into `bright` because
    a shadow is not the same thing as a dim light: an occluded crevice keeps its
    colour and loses its intensity, and mixing the two into one number is what
    makes cheap 3-D faces look like grey plastic.

    Flat facet normals are kept for the form (they are what makes the cheekbone
    a ridge rather than a smear) and mixed with the smooth vertex normals for
    the falloff. Culling stays on the facet normal, which is the only one that
    can honestly say a triangle faces away.
    """
    a, b, c = faces[:, 0], faces[:, 1], faces[:, 2]
    va, vb, vc = verts[a], verts[b], verts[c]

    fn = np.cross(vb - va, vc - va)
    fn /= np.maximum(np.linalg.norm(fn, axis=1, keepdims=True), 1e-9)

    # Orient outwards by agreeing with the built-time vertex normals. Flipping
    # on the sign of n_z instead would negate x and y too and scramble the
    # lighting into moiré.
    ref = normals[a] + normals[b] + normals[c]
    fn *= np.sign((fn * ref).sum(1))[:, None]

    sn = normals[a] + normals[b] + normals[c]
    sn /= np.maximum(np.linalg.norm(sn, axis=1, keepdims=True), 1e-9)

    n = fn * (1.0 - SMOOTH_MIX) + sn * SMOOTH_MIX
    n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-9)

    nz = fn[:, 2]

    # Lambert, with a wrap so the terminator is not a hard line: skin scatters,
    # and the "glow" of a hologram is exactly a wide wrap term.
    lam = np.clip(n @ LIGHT, 0.0, 1.0)
    wrap = np.clip((n @ LIGHT + 0.28) / 1.28, 0.0, 1.0)

    # Fresnel rim: the glass edge of the head, which stays part of the look.
    fres = np.clip(1.0 - np.abs(nz), 0.0, 2.0) ** 1.7

    # Specular from the halfway vector against a camera on +z.
    half = LIGHT + np.array([0.0, 0.0, 1.0], dtype=np.float32)
    half /= np.linalg.norm(half)
    spec = np.clip(n @ half, 0.0, 1.0) ** SPEC_POW * SPEC_GAIN

    cav_f = (cav[a] + cav[b] + cav[c]) / 3.0
    fade_f = (fade[a] + fade[b] + fade[c]) / 3.0

    bright = 0.20 + 0.20 * fres + 0.58 * wrap + 0.16 * lam + spec
    # Occlusion removes light, and it does so most in the deepest cavities.
    bright *= (1.0 - 0.52 * cav_f ** 0.85)
    bright *= fade_f
    bright *= 0.90 + 0.22 * float(amp)

    return (np.clip(bright, 0.0, 1.0).astype(np.float32),
            nz, np.clip(cav_f, 0.0, 1.0).astype(np.float32))


def shade_facets(verts: np.ndarray, normals: np.ndarray, faces: np.ndarray,
                 frames: FaceFrames, cav: np.ndarray, heat_w: np.ndarray,
                 fade: np.ndarray, amp: float) -> dict:
    """`light()` plus the per-facet warmth, in the form the painter wants.

    Kept apart from the painter so the numbers can be asserted: a test can say
    "the eye socket is darker than the cheek" without a display.
    """
    bright, nz, dark = light(verts, normals, faces, frames, cav, fade, amp)
    heat = ((heat_w[faces[:, 0]] + heat_w[faces[:, 1]] + heat_w[faces[:, 2]])
            / 3.0).astype(np.float32)
    return {"bright": bright, "nz": nz, "dark": dark, "heat": heat}


# ── palette ─────────────────────────────────────────────────────────────────
#
# WHY THE COLUMNS ARE BUILT FROM THE THEME'S OWN COLOURS
#   The avatar must retint instantly when the user picks a new accent — that is
#   the whole reason `paint()` takes its colours as arguments. So the three skin
#   axes are not fixed skin tones; they are DERIVED from the accent, and the
#   relationship between them is what a real face has:
#
#     base    the accent as given             — the lit skin
#     warm    the accent rotated towards red  — nose, cheeks, lips, ears
#     deep    the accent pushed down and in   — crevices, where light stops
#
#   Interpolating the middle column between the shadow and the highlight
#   instead would make a "warmer" skin that is merely brighter, which is the
#   exact failure the single ramp already had.

# How far the warm column turns towards red, and how far the deep column sinks.
# The numbers are deliberately small: a face that is obviously two colours reads
# as a mask with blush painted on, while a 15% shift is what skin actually does.
WARM_SHIFT = 0.16
DEEP_SINK = 0.70


def _rgb(col) -> tuple[float, float, float]:
    return float(col.red()), float(col.green()), float(col.blue())


def skin_columns(bg, primary, accent):
    """The three palette endpoints, as row vectors of 0..1 floats.

    Returns `(lo, mid, hi, warm_mid)` — the columns the surface is mixed
    between. `lo` is the shadow end, `hi` the highlight end, `mid` the ordinary
    skin, and `warm_mid` the same with the warm axis applied, so the painter can
    pick per facet without recomputing anything.
    """
    b = np.array(_rgb(bg), dtype=np.float32) / 255.0
    p = np.array(_rgb(primary), dtype=np.float32) / 255.0
    a = np.array(_rgb(accent), dtype=np.float32) / 255.0

    # Ordinary skin sits close to the background, because this is a hologram in
    # shadow rather than a photograph lit from inside. The old ramp's `mid`
    # point was far too bright and the head read as a lampshade.
    mid = b + (p - b) * 0.46
    hi = p * 0.92 + a * 0.08
    lo = b + (p - b) * 0.10

    # Warmth: pull towards the accent (which is the theme's own warm end) and
    # add a small fixed red bias so the shift survives an accent that is itself
    # blue — a blue theme still has blood under the skin.
    warm_mid = mid + (a - mid) * WARM_SHIFT
    # The fixed bias is what makes this true of ANY theme. Pulling towards the
    # accent alone fails exactly when the accent equals the primary — a cyan
    # theme on a cyan head has nowhere warm to reach for — and a blue face with
    # no blood in it is the thing this whole column exists to avoid.
    warm_mid = warm_mid + np.array([0.080, 0.015, -0.035], dtype=np.float32)
    warm_mid = np.clip(warm_mid, 0.0, 1.0)

    # Crevices: darker AND less saturated, which is what a shadow in skin does,
    # as opposed to a shadow on a plastic model.
    deep = lo * DEEP_SINK
    return lo, deep, mid, hi, warm_mid
