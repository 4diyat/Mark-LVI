import base64
import json
import struct

import pytest

from core.image_layers import make_text_layer, set_visible
from core.image_project import MAX_LAYERS, decode_project, encode_project, png_dimensions

# The format validator checks the header; Qt's image reader validates the rest.
def header(width=40, height=20):
    return b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR' + struct.pack('>II', width, height) + b'\0' * 9


def test_roundtrip_preserves_layer_order_visibility_and_color():
    layers = [make_text_layer('front', 3, 4, 20, 40, 20, '#aabbcc'),
              set_visible(make_text_layer('hidden', 5, 9, 10, 40, 20), False)]
    assert decode_project(encode_project(header(), layers)) == (header(), layers)


@pytest.mark.parametrize('data', [b'', b'no', header(0, 1), header(10000, 10000)])
def test_png_header_limits(data):
    with pytest.raises(ValueError):
        png_dimensions(data)


def test_invalid_projects_and_layers_rejected():
    valid = json.loads(encode_project(header(), [make_text_layer('test', 0, 1, 2, 40, 20)]))
    variants = []
    for key, value in [('version', 2), ('version', True), ('background_png', '!!!!'), ('layers', [None]),
                       ('layers', valid['layers'] * (MAX_LAYERS + 1))]:
        variants.append({**valid, key: value})
    for key, value in [('x', 40), ('x', True), ('visible', 1), ('color', 'red'), ('text', '  test ')]:
        variants.append({**valid, 'layers': [{**valid['layers'][0], key: value}]})
    variants.append({**valid, 'background_png': base64.b64encode(header(0, 1)).decode()})
    for value in variants:
        with pytest.raises(ValueError):
            decode_project(json.dumps(value).encode())
    for value in (b'\xff', b'{', b'[]'):
        with pytest.raises(ValueError):
            decode_project(value)
