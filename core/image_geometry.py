"""Validate integer crop bounds without decoding images or accessing files."""


def valid_crop(image_width, image_height, x, y, width, height):
    """A crop must be non-empty and fully inside the current image."""
    values = (image_width, image_height, x, y, width, height)
    if any(type(value) is not int for value in values):
        return False
    return (image_width > 0 and image_height > 0 and x >= 0 and y >= 0 and width > 0 and height > 0
            and x + width <= image_width and y + height <= image_height)
