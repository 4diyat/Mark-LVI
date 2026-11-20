import math

import pytest

from core.workspace_avatar_layout import avatar_layout


@pytest.mark.parametrize('width,height,span', [(320, 350, 2.5), (240, 238, 2.6), (450, 500, 3), (110, 112, 2)])
def test_avatar_and_three_caption_rows_are_bounded(width, height, span):
    cx, cy, radius, name, tagline, state = avatar_layout(width, height, span)
    assert cx == width / 2 and 0 < radius <= width * .33
    assert cy - radius >= 0
    assert cy + (span - 1) * radius < name
    assert name + 27 == tagline and tagline + 22 == state
    assert state + 24 <= height


@pytest.mark.parametrize('values', [(0, 300, 2), (200, 111, 2), (200, 200, 1),
                                    (200, 200, math.nan), (True, 200, 2), (200, math.inf, 2)])
def test_invalid_dimensions_fail_closed(values):
    assert avatar_layout(*values) is None
