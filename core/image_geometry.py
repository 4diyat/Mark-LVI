"""Validate integer crop bounds without decoding images or accessing files."""


def valid_crop(image_width, image_height, x, y, width, height):
    """A crop must be non-empty and fully inside the current image."""
    values = (image_width, image_height, x, y, width, height)
    if any(type(value) is not int for value in values):
        return False
    return (image_width > 0 and image_height > 0 and x >= 0 and y >= 0 and width > 0 and height > 0
            and x + width <= image_width and y + height <= image_height)


def preview_size(image_width, image_height, viewport_width, viewport_height, zoom):
    """Size a fit-relative preview, bounded to 16 megapixels and 8192 per side.

    Zoom is a percentage of the fit-to-viewport size, not original pixels.
    Bounds keep an unusually large window from allocating an enormous pixmap.
    """
    from math import sqrt

    if min(image_width, image_height, viewport_width, viewport_height, zoom) <= 0:
        return 1, 1
    scale = min(viewport_width / image_width, viewport_height / image_height) * zoom / 100
    width, height = image_width * scale, image_height * scale
    limit = min(1.0, 8192 / width, 8192 / height, sqrt(16_000_000 / (width * height)))
    return max(1, int(width * limit)), max(1, int(height * limit))


def selection_from_points(image_width, image_height, left, top, display_width, display_height, start, end):
    """Map a dragged preview rectangle to bounded image pixels (half-open)."""
    from math import ceil, floor

    if min(image_width, image_height, display_width, display_height) <= 0:
        return None
    x1, x2 = sorted((start[0], end[0]))
    y1, y2 = sorted((start[1], end[1]))
    x1, x2 = max(left, x1), min(left + display_width, x2)
    y1, y2 = max(top, y1), min(top + display_height, y2)
    if x2 <= x1 or y2 <= y1:
        return None
    x = max(0, floor((x1 - left) * image_width / display_width))
    y = max(0, floor((y1 - top) * image_height / display_height))
    right = min(image_width, ceil((x2 - left) * image_width / display_width))
    bottom = min(image_height, ceil((y2 - top) * image_height / display_height))
    return x, y, right - x, bottom - y
