import math

import pytest

from core.visual_content import positions, validate
from plugins import visualize_data


def sample():
    return {"title": "Trend", "source": "User-provided", "unit": "kg",
            "points": [{"label": "A", "value": -2}, {"label": "B", "value": 4}]}


def test_validation_copies_and_preserves_real_data_without_inventing_time():
    data = sample()
    result = validate(data)
    data["points"][0]["value"] = 100
    assert result["points"][0]["value"] == -2
    assert result["observed"] == "" and result["source"] == "User-provided"


@pytest.mark.parametrize('value', [math.nan, math.inf, -math.inf, True, '5', 1e13, 10**1000, None])
def test_bad_numeric_values_are_rejected(value):
    data = sample()
    data['points'][0]['value'] = value
    with pytest.raises(ValueError):
        validate(data)


def test_bad_payloads_are_rejected():
    for change in ({'source': ''}, {'title': 'x\nfoo'}, {'points': []},
                   {'points': [{'label': 'a', 'value': 1}] * 49}):
        with pytest.raises(ValueError):
            validate({**sample(), **change})


def test_plot_geometry_includes_zero_and_handles_constant_data():
    assert positions(validate(sample())['points'], 0, 0, 100, 60) == [(0, 60), (100, 0)]
    assert all(math.isfinite(x) and math.isfinite(y) for x, y in positions(
        [{'value': 0}, {'value': 0}], 0, 0, 100, 60))
    assert positions([], 0, 0, 1, 1) == []


def test_plugin_refuses_bad_data_and_reports_actual_ui_result():
    class Player:
        def show_visual_content(self, data):
            self.data = data
            return {'ok': True, 'message': 'Opened'}
    player = Player()
    assert visualize_data.run(sample(), player) == 'Opened'
    assert player.data == validate(sample())
    assert 'requires the JARVIS desktop' in visualize_data.run(sample())
    assert 'No chart was opened' in visualize_data.run({**sample(), 'source': ''}, player)
