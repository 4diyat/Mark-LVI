"""Bounded, versioned local image-project format; never executes project data.

The background is a PNG and text layers are stored bottom-to-top. This module
validates the container and model; the caller must validate and decode the PNG
with a trusted image reader before replacing the current document.
"""
import base64
import binascii
import json
import struct

from core.image_layers import make_text_layer, set_visible

MAX_PROJECT_BYTES = 96 * 1024 * 1024
MAX_PNG_BYTES = 64 * 1024 * 1024
MAX_LAYERS = 1000
MAX_PIXELS = 40_000_000
PNG_SIGNATURE = b'\x89PNG\r\n\x1a\n'


def png_dimensions(data):
    if (not isinstance(data, bytes) or len(data) < 33 or len(data) > MAX_PNG_BYTES
            or data[:8] != PNG_SIGNATURE or data[8:16] != b'\x00\x00\x00\rIHDR'):
        raise ValueError('Invalid PNG header')
    width, height = struct.unpack('>II', data[16:24])
    if not width or not height or width * height > MAX_PIXELS:
        raise ValueError('Invalid image dimensions')
    return width, height


def encode_project(png, layers):
    width, height = png_dimensions(png)
    records = [dict(text=l.text, x=l.x, y=l.y, size=l.size,
                    visible=l.visible, color=l.color) for l in layers]
    document = {'format': 'jarvis-image-project', 'version': 1,
                'background_png': base64.b64encode(png).decode('ascii'), 'layers': records}
    # Validate before saving, including layer count and bounds.
    _parse_layers(records, width, height)
    data = json.dumps(document, ensure_ascii=True, separators=(',', ':')).encode('utf-8')
    if len(data) > MAX_PROJECT_BYTES:
        raise ValueError('Project is too large')
    return data


def _parse_layers(records, width, height):
    if not isinstance(records, list) or len(records) > MAX_LAYERS:
        raise ValueError('Invalid layers')
    layers = []
    for record in records:
        if (not isinstance(record, dict) or set(record) != {'text', 'x', 'y', 'size', 'visible', 'color'}
                or not isinstance(record['text'], str) or type(record['visible']) is not bool):
            raise ValueError('Invalid layer')
        layer = make_text_layer(record['text'], record['x'], record['y'], record['size'],
                                width, height, record['color'])
        if layer.text != record['text']:
            raise ValueError('Invalid layer text')
        layers.append(set_visible(layer, record['visible']))
    return layers


def decode_project(data):
    if not isinstance(data, bytes) or len(data) > MAX_PROJECT_BYTES:
        raise ValueError('Project is too large')
    try:
        document = json.loads(data.decode('utf-8'))
        if (not isinstance(document, dict) or set(document) != {'format', 'version', 'background_png', 'layers'}
                or document['format'] != 'jarvis-image-project' or type(document['version']) is not int
                or document['version'] != 1 or not isinstance(document['background_png'], str)
                or len(document['background_png']) > (MAX_PNG_BYTES + 2) // 3 * 4):
            raise ValueError('Invalid project header')
        png = base64.b64decode(document['background_png'], validate=True)
        width, height = png_dimensions(png)
        return png, _parse_layers(document['layers'], width, height)
    except (UnicodeError, json.JSONDecodeError, binascii.Error, RecursionError) as exc:
        raise ValueError('Invalid project') from exc
