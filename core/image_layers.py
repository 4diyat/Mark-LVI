"""Small immutable text-layer model, independent of GUI and image I/O."""
from dataclasses import dataclass, replace


@dataclass(frozen=True)
class TextLayer:
    text: str
    x: int
    y: int
    size: int
    visible: bool = True


def make_text_layer(text, x, y, size, width, height):
    text = str(text).strip()
    if not text or len(text) > 500 or any(ord(c) < 32 for c in text):
        raise ValueError("Text must contain 1–500 printable characters on one line.")
    if (any(type(v) is not int for v in (x, y, size, width, height)) or width <= 0 or height <= 0
            or not 0 <= x < width or not 0 <= y < height or not 1 <= size <= 500):
        raise ValueError("Invalid layer position or font size.")
    return TextLayer(text, x, y, size)


def set_visible(layer, visible):
    return replace(layer, visible=bool(visible))
