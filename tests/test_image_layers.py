import pytest

from core.image_layers import make_text_layer, set_visible


def test_text_layers_are_immutable_and_visibility_can_be_changed():
    original = make_text_layer("Hello", 2, 8, 12, 100, 100)
    hidden = set_visible(original, False)
    assert original.visible and not hidden.visible
    assert hidden.text == "Hello" and hidden.x == 2 and hidden.y == 8
    assert set_visible(hidden, True) == original


@pytest.mark.parametrize("text,x,y,size", [("", 0, 0, 12), ("a\nline", 0, 0, 12),
                                         ("x" * 501, 0, 0, 12), ("x", -1, 0, 12),
                                         ("x", 100, 0, 12), ("x", 0, 100, 12),
                                         ("x", 0, 0, 0), ("x", 0, 0, 501)])
def test_invalid_layer_data_is_rejected(text, x, y, size):
    with pytest.raises(ValueError):
        make_text_layer(text, x, y, size, 100, 100)


def test_layer_order_maps_top_row_to_front_without_mutation():
    from core.image_layers import layer_index_from_row, move_layer
    layers = ['bottom', 'middle', 'top']
    assert [layer_index_from_row(3, row) for row in range(3)] == [2, 1, 0]
    assert layer_index_from_row(3, -1) is None
    assert layer_index_from_row(3, True) is None
    assert move_layer(layers, 1, -1) == (['bottom', 'top', 'middle'], 0)
    assert move_layer(layers, 1, 1) == (['middle', 'bottom', 'top'], 2)
    assert move_layer(layers, 0, -1) is None
    assert move_layer(layers, 2, 1) is None
    assert move_layer(layers, -1, 1) is None
    assert move_layer(layers, 1, True) is None
    assert layers == ['bottom', 'middle', 'top']
