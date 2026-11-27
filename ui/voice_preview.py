"""Privacy-scoped in-memory camera preview for the voice gesture tile.

Camera encoding happens in the tracking worker; only the Qt thread converts
its bounded latest JPEG to an image. Hiding the view clears and unsubscribes.
"""


def clear(overlay):
    feed = getattr(overlay, '_gesture_feed', None)
    controller = getattr(feed, '_controller', None)
    callback = getattr(controller, 'set_preview_enabled', None)
    if callable(callback):
        callback(False)
    overlay._camera_preview_image = None


def update(overlay, controller, available):
    visible = bool(getattr(overlay, 'active', False) and available)
    callback = getattr(controller, 'set_preview_enabled', None)
    if callable(callback):
        callback(visible)
    if not visible:
        overlay._camera_preview_image = None
        return
    reader = getattr(controller, 'preview', None)
    data = reader() if callable(reader) else b''
    if not data:
        overlay._camera_preview_image = None
        return
    from PyQt6.QtGui import QImage
    image = QImage.fromData(data, 'JPG')
    overlay._camera_preview_image = None if image.isNull() else image
