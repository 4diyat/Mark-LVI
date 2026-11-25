"""Render a design artboard to PNG, with the built page's widgets drawn on top.

WHY THIS EXISTS
    Every check in `tests/test_board_conformance.py` compares NUMBERS: the
    coordinates a page hands to Qt against the coordinates `build.py` draws.
    That closes the drift a review keeps missing, but it cannot show whether
    the two line up on a screen — and the owner's report ("masih banyak yang
    belum sesuai") was made by looking, not by reading a table.

    Qt does not run in this sandbox and Cairo is not installable, so this
    renders the ARTBOARD with Pillow (which is present) and overprints the
    widget rectangles the built page actually places. Matching boxes land on
    matching art; a box that is 44 px high is visible at a glance.

WHAT IT IS NOT
    Not a screenshot of the panel. Text is drawn in a default PIL font at
    roughly the right size, so line lengths differ; the stylesheet, the radius
    and the typeface are all approximations. What it shows exactly is
    ALIGNMENT, which is the thing that was wrong.

USAGE
    ./.venv/bin/python tools/render_board_overlay.py memory
    ./.venv/bin/python tools/render_board_overlay.py b09 --no-widgets

    Writes `docs/verification/board-<name>.png`.
"""
from __future__ import annotations

import importlib.util
import re
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
OUT = ROOT / "docs" / "verification"

# The sheet's own tokens, read from `build.py` rather than retyped.
def _sheet():
    spec = importlib.util.spec_from_file_location(
        "_sheet_render", ROOT / "docs" / "mockups" / "build.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["_sheet_render"] = module
    spec.loader.exec_module(module)
    return module


def _colour(value: str, default=(255, 255, 255)):
    """An SVG paint value as an RGB tuple, or None for "no paint".

    `fill="none"` MEANS NO FILL. The first version of this function folded it
    into the default and drew the artboard's unfilled pills as solid white
    blocks — which would have read as "the built page fills buttons the design
    leaves empty", a difference that does not exist.
    """
    value = (value or "").strip().lower()
    if value in ("none", "transparent", ""):
        return None
    if "url(" in value:
        return (79, 216, 240)              # the orb's gradient, flattened
    if value.startswith("#") and len(value) == 7:
        return tuple(int(value[i:i + 2], 16) for i in (1, 3, 5))
    return {"white": (255, 255, 255), "black": (0, 0, 0)}.get(value, default)


def _font(size: float):
    try:
        return ImageFont.truetype("DejaVuSans.ttf", max(6, int(size)))
    except Exception:                                    # noqa: BLE001
        return ImageFont.load_default()


def render_svg(svg: str, scale: int = 2) -> Image.Image:
    """A rasteriser for the subset `build.py` emits: rect, circle, path, text."""
    frame = re.search(r'viewBox="0 0 (\d+) (\d+)"', svg)
    w, h = int(frame.group(1)), int(frame.group(2))
    # GRADIENTS ARE NOT DRAWN. `<defs>` holds the orb's radial gradients; the
    # orb itself is drawn as a flat cyan disc below, which is enough to see
    # WHERE it is — and stripping the block keeps its `<stop offset=...>` tags
    # out of the primitive matcher.
    svg = re.sub(r"<defs>.*?</defs>", "", svg, flags=re.S)
    img = Image.new("RGB", (w * scale, h * scale), (4, 8, 13))
    draw = ImageDraw.Draw(img, "RGBA")

    for m in re.finditer(
            r"<rect\b([^>]*?)/>|<circle\b([^>]*?)/>|<path\b([^>]*?)/>|"
            r"<text\b([^>]*)>(.*?)</text>", svg, re.S):
        # Group indices: 1=rect 2=circle 3=path 4=text-attrs 5=text-body.
        # FOR A TEXT ELEMENT THE ATTRIBUTES ARE GROUP 4 AND THE WORDS ARE GROUP
        # 5 — reading the body as attributes left every label without an x, and
        # the first render drew the artboard with all of its type missing.
        tag = {1: "rect", 2: "circle", 3: "path", 4: "text", 5: "text"}[m.lastindex]
        attrs = m.group(4) if tag == "text" else m.group(m.lastindex)
        a = dict(re.findall(r'([\w-]+)="([^"]*)"', attrs))
        if tag == "text":
            a["_body"] = m.group(5)

        if tag == "rect":
            # The sheet's full-bleed background rect omits x/y; SVG defaults
            # them to 0, so the renderer must too.
            x = float(a.get("x", 0)) * scale
            y = float(a.get("y", 0)) * scale
            ww = float(a.get("width", 0)) * scale
            hh = float(a.get("height", 0)) * scale
            fill = _colour(a.get("fill", ""))
            stroke = _colour(a.get("stroke", ""))
            if ww <= 0 or hh <= 0 or (fill is None and stroke is None):
                continue
            draw.rounded_rectangle(
                [x, y, x + ww, y + hh],
                radius=float(a.get("rx", 0)) * scale,
                fill=fill,
                outline=stroke,
                width=max(1, int(float(a.get("stroke-width", 1)) * scale)),
            )
        elif tag == "circle":
            cx, cy = float(a["cx"]) * scale, float(a["cy"]) * scale
            r = float(a["r"]) * scale
            raw = a.get("fill", "")
            # THE GLOW IS A RADIAL GRADIENT, and flattening it to a solid disc
            # drew a 68 px cyan blob where the artboard has a soft halo — the
            # single most misleading thing in the first render. `glow` fills
            # are skipped; the orb's own `orb` gradient is drawn as a disc.
            if "glow" in raw:
                continue
            fill = _colour(raw, (79, 216, 240)) if raw else (79, 216, 240)
            if fill is None:
                continue
            draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=fill)
        elif tag == "text":
            if "x" not in a or "y" not in a:
                continue
            x, y = float(a["x"]) * scale, float(a["y"]) * scale
            size = float(a.get("font-size", 12)) * scale
            body = a.get("_body", "")
            body = (body.replace("&amp;", "&").replace("&lt;", "<")
                    .replace("&gt;", ">").replace("&quot;", '"'))
            anchor = a.get("text-anchor", "start")
            fill = _colour(a.get("fill", ""), (230, 244, 248))
            font = _font(size)
            if anchor == "middle":
                x -= draw.textlength(body, font=font) / 2
            elif anchor == "end":
                x -= draw.textlength(body, font=font)
            draw.text((x, y - size), body, font=font, fill=fill)
        elif tag == "path":
            # The sheet's paths are tick marks, chevrons and arrows: straight
            # segments with occasional small arcs. Absolute M/L is enough to
            # see them; arcs are approximated by their endpoints.
            stroke = a.get("stroke")
            if not stroke:
                continue
            ink = _colour(stroke, (230, 244, 248))
            width = max(1, int(float(a.get("stroke-width", 1)) * scale))
            d = a.get("d", "")
            points = [(float(px), float(py)) for px, py in
                      re.findall(r"[ML](-?[\d.]+) (-?[\d.]+)", d)]
            if len(points) >= 2:
                draw.line([(px * scale, py * scale) for px, py in points],
                          fill=ink, width=width)
            for cx, cy, r in re.findall(r"circle cx=\"?([\d.]+)\"? cy=\"?([\d.]+)\"? r=\"?([\d.]+)", d):
                pass
    return img


def _inside(widget, page) -> bool:
    """Whether `page` is `widget` or one of its ancestors."""
    node = widget
    for _ in range(12):                          # a page is never this deep
        if node is None:
            return False
        if node is page:
            return True
        node = getattr(node, "_parent", None)
    return False


def widget_boxes(page: str) -> list[tuple[float, float, float, float, str, str, bool]]:
    """Every visible widget the built page places, in artboard coordinates."""
    from tests.qtstub import fresh_ui, restore_ui

    saved = fresh_ui()
    try:
        from ui import tray_paint, tray_panel

        panel = tray_panel.TrayPanel({})
        panel.open()
        panel.set_page(page)
        tray_paint.paint(panel, panel.snapshot)
        out = []
        for kind, bucket in (("label", panel._labels), ("button", panel._buttons)):
            for key, widget in bucket.items():
                if not widget.isVisible():
                    continue
                # WIDGETS INSIDE A SCROLLING COLUMN ARE STILL ON THE PAGE.
                # The first version required a widget's parent to be the page
                # itself, which was true when every label was placed absolutely.
                # After the memory page moved onto `components.scroll_list`, its
                # rows became children of a viewport's inner widget and the tool
                # went blind — it printed the ARTBOARD's six example cards and
                # looked like the page was unchanged. A widget is on the page if
                # the page is somewhere above it in the parent chain.
                if not _inside(widget, panel._pages.get(page)):
                    continue
                text = widget.text() if hasattr(widget, "text") else ""
                # ALIGNMENT AND TYPE SIZE ARE PART OF THE PLACEMENT. Qt centres
                # a label's text vertically in its box and honours
                # `setAlignment`; drawing at the box's top-left corner showed
                # the words 6 px above where they land on screen and made every
                # 416-anchored "fixed" look left-aligned. A rendering tool that
                # misplaces the text it is auditing is worse than no tool.
                align = widget._align if hasattr(widget, "_align") else None
                out.append((widget.x(), widget.y(), widget.width(),
                            widget.height(), f"{kind}:{key}", str(text or ""),
                            kind == "button", int(align or 0)))
        return out
    finally:
        restore_ui(saved)


BOARD_OF = {"memory": "b09", "memory_one": "b10", "routines": "b11",
            "tools": "b12", "help": "b13", "security": "b14", "access": "b15",
            "plugins": "b16", "light": "b18", "consent": "b07"}


def main(argv: list[str]) -> int:
    if not argv:
        print("usage: render_board_overlay.py <page|bNN> "
              "[--no-widgets | --text-only]")
        return 2
    target = argv[0]
    with_widgets = "--no-widgets" not in argv
    # `--text-only` DRAWS WHAT THE PAGE SAYS IN THE SPACE THE ARTBOARD GIVES IT,
    # and nothing else: no boxes, no fills. The boxed view answers "is the
    # geometry right"; it cannot answer "does the page put the artboard's words
    # where the artboard puts them", because a filled box hides the sheet's own
    # type underneath and a text that overflows its box gets clipped by the
    # next box drawn over it. This mode is the one for auditing CONTENT.
    text_only = "--text-only" in argv
    sheet = _sheet()
    board = BOARD_OF.get(target, target)

    svg = getattr(sheet, board)()
    img = render_svg(svg)
    scale = 2
    draw = ImageDraw.Draw(img, "RGBA")

    if with_widgets and target in BOARD_OF:
        # THE WIDGETS ARE DRAWN ON TOP OF THE ARTBOARD, WITH THEIR TEXT.
        # Boxes alone show alignment and hide the thing a reader actually
        # compares: what the page SAYS where the drawing says something else.
        # Board 16's pairing code is the example — the sheet prints
        # "4 7 9 2 1 5" and the page must not, and only the words can show that.
        for x, y, w, h, name, text, is_button, align in widget_boxes(target):
            if not text_only:
                draw.rectangle([x * scale, y * scale,
                                (x + w) * scale, (y + h) * scale],
                               fill=(10, 23, 34) if text else None,
                               outline=(255, 64, 160, 230), width=2)
            if text:
                size = 10 if is_button else 9.5
                font = _font(size * scale * 0.95)
                ink = (255, 140, 210) if is_button else (255, 210, 235)
                # VERTICALLY CENTRED, as Qt draws it, so the words sit where
                # they will on screen. A 14 px box with 9.5 px type centres to
                # about 2 px from the top; adding a fixed +2 put everything low.
                shown = text[:60]
                left, top, right, bottom = draw.textbbox((0, 0), shown, font=font)
                ty = y * scale + ((h * scale) - (bottom - top)) / 2 - top
                # ALIGNMENT: bit 1 is right, bit 2 is centre (Qt.AlignRight == 2,
                # AlignHCenter == 4 in PyQt6). Right-aligned cells end at the
                # box's right edge, which is how "ubah" is drawn at x=416.
                if align & 2:
                    tx = (x + w) * scale - (right - left) - 6
                elif align & 4:
                    tx = x * scale + ((w * scale) - (right - left)) / 2
                else:
                    tx = x * scale + 6
                draw.text((tx, ty), shown, font=font, fill=ink)

    OUT.mkdir(parents=True, exist_ok=True)
    suffix = ("-text" if text_only else "") if with_widgets else "-artboard"
    path = OUT / f"board-{target}{suffix}.png"
    img.save(path)
    print(f"wrote {path.relative_to(ROOT)}  ({img.width}x{img.height})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
