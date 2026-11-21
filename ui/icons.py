"""The generated application icon: a JARVIS arc reactor, drawn with Pillow.

WHY THIS IS A MODULE AND NOT A STATICMETHOD ON THE WINDOW
It is 98 lines of geometry and it needs nothing from `MainWindow` — it is a
`staticmethod` that takes an output path and returns whether it worked. A
function with no `self` in it does not belong on a 2,900-line class: it
cannot be read without scrolling past the class, and it cannot be called
from anywhere else without borrowing the whole window.

WHY IT IS DRAWN RATHER THAN SHIPPED
A multi-resolution .ico is a binary in the repository that nobody can review
or change, and the palette is a setting. Drawing it means the accent colour
in the file is the accent colour in the app.

WHY PILLOW IS IMPORTED INSIDE
It is an optional dependency for the desktop shortcut only. Importing it at
module level would make `ui.icons` fail to import on a machine that never
creates a shortcut — and this module is imported through `ui`, which
main.py imports at startup.
"""
from __future__ import annotations

from pathlib import Path

CYAN = (0, 220, 255)
WHITE = (235, 250, 255)
GLOW = (0, 140, 200)
DARK = (2, 18, 30)
DIM = (0, 90, 130)


def build_jarvis_icon(out_path: Path) -> bool:
    """
    Render a JARVIS arc-reactor icon at 4× resolution and downsample
    for crisp results at all sizes. Saves a multi-res .ico to out_path.
    Returns True on success.
    """
    try:
        import math
        import PIL.Image
        import PIL.ImageDraw
        import PIL.ImageFilter
    except ImportError:
        return False

    CYAN   = (0, 212, 255)
    DIM    = (0, 100, 140)
    DARK   = (0, 6, 10)
    GLOW   = (0, 160, 200)
    WHITE  = (220, 240, 255)

    def _render(sz: int) -> PIL.Image.Image:
        S  = sz * 4                     # draw at 4× then downscale
        img = PIL.Image.new("RGBA", (S, S), (0, 0, 0, 0))
        d   = PIL.ImageDraw.Draw(img)
        cx = cy = S // 2

        # ── filled background circle ──────────────────────────────────
        R = S // 2 - 2
        d.ellipse([cx-R, cy-R, cx+R, cy+R], fill=(*DARK, 255))

        # ── outer border ring ─────────────────────────────────────────
        lw = max(2, S // 40)
        d.ellipse([cx-R, cy-R, cx+R, cy+R],
                  outline=(*CYAN, 220), width=lw)

        # ── mid decorative ring ───────────────────────────────────────
        R2 = int(R * 0.72)
        d.ellipse([cx-R2, cy-R2, cx+R2, cy+R2],
                  outline=(*DIM, 180), width=max(1, lw // 2))

        # ── 6 radial spokes (hex bolt) ────────────────────────────────
        R_inner = int(R * 0.30)
        R_outer = int(R * 0.62)
        spoke_w = max(1, S // 80)
        for i in range(6):
            angle = math.radians(i * 60 - 30)
            x1 = cx + int(R_inner * math.cos(angle))
            y1 = cy + int(R_inner * math.sin(angle))
            x2 = cx + int(R_outer * math.cos(angle))
            y2 = cy + int(R_outer * math.sin(angle))
            d.line([x1, y1, x2, y2], fill=(*GLOW, 200), width=spoke_w)

        # ── 6 tick marks on outer ring ────────────────────────────────
        for i in range(6):
            angle = math.radians(i * 60)
            for dr in range(lw * 2):
                rx = (R - lw - dr)
                d.point(
                    [cx + int(rx * math.cos(angle)),
                     cy + int(rx * math.sin(angle))],
                    fill=(*WHITE, 220),
                )

        # ── inner glowing ring ────────────────────────────────────────
        Ri = int(R * 0.26)
        d.ellipse([cx-Ri, cy-Ri, cx+Ri, cy+Ri],
                  outline=(*CYAN, 255), width=max(2, lw))

        # ── bright glow soft blur applied before core ─────────────────
        # (draw a slightly larger cyan circle on a separate layer)
        glow_layer = PIL.Image.new("RGBA", (S, S), (0, 0, 0, 0))
        gd = PIL.ImageDraw.Draw(glow_layer)
        Rc = int(R * 0.13)
        gd.ellipse([cx-Rc*2, cy-Rc*2, cx+Rc*2, cy+Rc*2],
                   fill=(*CYAN, 110))
        glow_layer = glow_layer.filter(PIL.ImageFilter.GaussianBlur(S // 14))
        img = PIL.Image.alpha_composite(img, glow_layer)
        d   = PIL.ImageDraw.Draw(img)

        # ── core dot ──────────────────────────────────────────────────
        d.ellipse([cx-Rc, cy-Rc, cx+Rc, cy+Rc], fill=(*WHITE, 255))

        # ── downscale to target size ──────────────────────────────────
        return img.resize((sz, sz), PIL.Image.LANCZOS)

    try:
        sizes  = [256, 128, 64, 48, 32, 16]
        frames = [_render(s) for s in sizes]
        frames[0].save(
            out_path,
            format="ICO",
            append_images=frames[1:],
            sizes=[(s, s) for s in sizes],
        )
        return True
    except Exception as e:
        print(f"[Shortcut] ⚠️  Icon generation failed: {e}")
        return False
