import pytest

from core.image_geometry import valid_crop


@pytest.mark.parametrize("rect", [(0, 0, 100, 80), (99, 79, 1, 1), (10, 20, 50, 30)])
def test_valid_crop_within_image(rect):
    assert valid_crop(100, 80, *rect)


@pytest.mark.parametrize("rect", [(-1, 0, 1, 1), (0, 0, 0, 1), (99, 0, 2, 1),
                                  (0, 79, 1, 2), (0, 0, 1.5, 1), (True, 0, 1, 1)])
def test_invalid_crop_fails_closed(rect):
    assert not valid_crop(100, 80, *rect)


def test_preview_size_fit_zoom_and_allocation_limits():
    from core.image_geometry import preview_size

    assert preview_size(400, 200, 300, 300, 100) == (300, 150)
    assert preview_size(400, 200, 300, 300, 200) == (600, 300)
    assert preview_size(400, 200, 300, 300, 25) == (75, 37)
    assert preview_size(0, 20, 100, 100, 100) == (1, 1)
    width, height = preview_size(400, 200, 50000, 50000, 200)
    assert width <= 8192 and height <= 8192 and width * height <= 16_000_000
    assert abs(width / height - 2) < .01
