"""Render a scrolling list as it would look: columns measured from the tokens.

WHY A SECOND RENDERER
    `render_board_overlay.py` draws widgets at the coordinates they were GIVEN.
    After the memory page moved onto `components.scroll_list`, its rows are laid
    out by a QVBoxLayout and have no `setGeometry` — which is correct, and means
    the overlay can only see the three widgets the page still places absolutely.
    A tool that cannot show the page it is auditing is not auditing it.

    So this measures the COLUMN: card heights from `components.card_height`, the
    gap from `tokens.S3`, and draws the same text the page puts in them. It is a
    reconstruction, not a screenshot — Qt's real layout engine is not here — but
    it answers the question the overlay exists for: what will the user see, and
    is anything colliding.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PIL import Image, ImageDraw  # noqa: E402

from tests.qtstub import fresh_ui, restore_ui  # noqa: E402


def _font(size: int, bold: bool = False):
    from PIL import ImageFont

    candidates = (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold
        else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    )
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def rows_for(page: str):
    """The card text the page would draw, read from its own populate function.

    Goes through the page's real `populate_memory` on a stub panel so the WORDS
    come from the same code the app runs, not from a copy in this script.
    """
    saved = fresh_ui()
    try:
        from ui import tray_pages, tray_paint, tray_panel
        from ui.tray_panel_model import snapshot

        panel = tray_panel.TrayPanel({})
        panel.open()
        panel.set_page(page)
        tray_paint.paint(panel, snapshot(page))

        column = getattr(panel, "_memory_column", None)
        if column is None:
            return [], {}
        out = []
        for i in range(column.count()):
            item = column.itemAt(i)
            card = item.widget() if item is not None else None
            if card is None:
                continue
            texts = []
            stack = [card]
            while stack:
                node = stack.pop()
                if hasattr(node, "text") and not hasattr(node, "clicked"):
                    value = node.text()
                    if value:
                        texts.append(value)
                layout = getattr(node, "_layout", None)
                for child in list(getattr(layout, "_items", []) or []):
                    stack.append(child)
            if texts:
                out.append(texts)
        paint = tray_pages.PALETTES["dark"]
        return out, paint
    finally:
        restore_ui(saved)


def render(page: str = "memory") -> Path:
    from ui import components, tokens

    cards, palette = rows_for(page)
    scale = 2
    width, height = tokens.PANEL_W, tokens.PANEL_H
    image = Image.new("RGB", (width * scale, height * scale), palette["base"])
    draw = ImageDraw.Draw(image)

    def box(x, y, w, h, fill, radius):
        draw.rounded_rectangle([x * scale, y * scale, (x + w) * scale, (y + h) * scale],
                               radius=radius * scale, fill=fill)

    # the head, as the panel draws it
    draw.ellipse([24 * scale, 27 * scale, 50 * scale, 53 * scale], fill=palette["accent"])
    draw.text((62 * scale, 22 * scale), "JARVIS",
              font=_font(int(tokens.WORDMARK * scale * 0.95), bold=True),
              fill=palette["text"])
    draw.text((62 * scale, 42 * scale), "Personal memory",
              font=_font(int(10.5 * scale * 0.95)), fill=palette["muted"])

    # section marker
    draw.text((tokens.S5 * scale, tokens.HEAD_H * scale), "FACTS ABOUT YOU",
              font=_font(int(tokens.LABEL * scale * 0.95)), fill=palette["muted"])

    top = tokens.HEAD_H + tokens.S6
    pitch = components.card_height(2) + tokens.S3
    limit = tokens.PANEL_H - tokens.ACTION_H

    drawn = 0
    for texts in cards:
        y = top + drawn * pitch
        if y + components.card_height(2) > limit:
            break
        box(tokens.S5, y, tokens.CONTENT_W, components.card_height(2),
            palette["card"], tokens.R_CARD)
        key = texts[0] if texts else ""
        value = texts[1] if len(texts) > 1 else ""
        draw.text(((tokens.S5 + tokens.CARD_PAD) * scale,
                   (y + tokens.S4) * scale), key,
                  font=_font(int(tokens.META * scale * 0.95)), fill=palette["muted"])
        draw.text(((tokens.S5 + tokens.CARD_PAD) * scale,
                   (y + tokens.S4 + tokens.META + tokens.S1) * scale), value,
                  font=_font(int(tokens.CARD_TITLE * scale * 0.95), bold=True),
                  fill=palette["text"])
        drawn += 1

    hidden = len(cards) - drawn

    # the action band
    draw.rectangle([tokens.S5 * scale, limit * scale,
                    (tokens.S5 + tokens.CONTENT_W) * scale, limit * scale + 1],
                   fill=palette["line"])
    pill_w = (tokens.CONTENT_W - tokens.S3) // 2
    for index, label in enumerate(("Add memory", "Delete all")):
        x = tokens.S5 + index * (pill_w + tokens.S3)
        draw.rounded_rectangle(
            [x * scale, (limit + tokens.S2) * scale,
             (x + pill_w) * scale, (limit + tokens.S2 + tokens.PILL_H_SMALL) * scale],
            radius=(tokens.PILL_H_SMALL // 2) * scale,
            outline=palette["line_accent"], width=2)
        draw.text((x * scale + 20 * scale, (limit + tokens.S2 + 12) * scale), label,
                  font=_font(int(tokens.BODY * scale * 0.95)), fill=palette["text"])

    if hidden > 0:
        # AN ANNOTATION OF THIS TOOL, NOT APPLICATION UI. The app shows no such
        # line: it scrolls. The note exists so a reader of the PNG can tell
        # "these are all the rows" from "these are the rows that fit", which is
        # the exact confusion the old `dan N lagi` label created in the product.
        draw.text((tokens.S5 * scale, (limit - tokens.S5) * scale),
                  f"[render] {hidden} more below the fold — the app scrolls",
                  font=_font(int(tokens.META * scale * 0.95)), fill=palette["muted"])

    out = ROOT / "docs" / "verification" / f"list-{page}.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    image.save(out)
    print(f"wrote {out.relative_to(ROOT)}  ({drawn} cards drawn, {hidden} below the fold)")
    return out


if __name__ == "__main__":
    render(sys.argv[1] if len(sys.argv) > 1 else "memory")
