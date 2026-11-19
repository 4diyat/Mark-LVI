"""Small immutable text-layer model, independent of GUI and image I/O."""
from dataclasses import dataclass, replace
import re


@dataclass(frozen=True)
class TextLayer:
    text: str
    x: int
    y: int
    size: int
    visible: bool = True
    color: str = "#ffffff"


def make_text_layer(text, x, y, size, width, height, color="#ffffff"):
    text = str(text).strip()
    if not text or len(text) > 500 or any(ord(c) < 32 for c in text):
        raise ValueError("Text must contain 1–500 printable characters on one line.")
    if (any(type(v) is not int for v in (x, y, size, width, height)) or width <= 0 or height <= 0
            or not 0 <= x < width or not 0 <= y < height or not 1 <= size <= 500):
        raise ValueError("Invalid layer position or font size.")
    if not isinstance(color, str) or re.fullmatch(r"#[0-9a-fA-F]{6}", color) is None:
        raise ValueError("Color must be an RGB hex string.")
    return TextLayer(text, x, y, size, color=color.lower())


def set_visible(layer, visible):
    return replace(layer, visible=bool(visible))


def layer_index_from_row(count, row):
    """The top row is the last layer painted; invalid rows select nothing."""
    if type(count) is not int or type(row) is not int or count < 0 or not 0 <= row < count:
        return None
    return count - row - 1


def move_layer(layers, row, direction):
    """Return reordered bottom-to-top layers and the new row, or None.

    Direction is -1 for up in the UI (toward the front), +1 for down.
    The input is not mutated. Identical layer values still retain their slots.
    """
    count = len(layers)
    index = layer_index_from_row(count, row)
    if index is None or type(direction) is not int or direction not in (-1, 1):
        return None
    destination = index - direction
    if not 0 <= destination < count:
        return None
    result = list(layers)
    result[index], result[destination] = result[destination], result[index]
    return result, row + direction
