import pytest

from core.image_geometry import valid_crop


@pytest.mark.parametrize("rect", [(0, 0, 100, 80), (99, 79, 1, 1), (10, 20, 50, 30)])
def test_valid_crop_within_image(rect):
    assert valid_crop(100, 80, *rect)


@pytest.mark.parametrize("rect", [(-1, 0, 1, 1), (0, 0, 0, 1), (99, 0, 2, 1),
                                  (0, 79, 1, 2), (0, 0, 1.5, 1), (True, 0, 1, 1)])
def test_invalid_crop_fails_closed(rect):
    assert not valid_crop(100, 80, *rect)
