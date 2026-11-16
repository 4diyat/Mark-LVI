import pytest
from core.obj_wireframe import MAX_OBJ_BYTES, parse_obj


def test_obj_wireframe_normalizes_and_deduplicates_edges():
    data = b'v 0 0 0\nv 2 0 0\nv 0 2 0\nf 1 2 3\nf -3 -2 -1\n'
    vertices, edges = parse_obj(data)
    assert vertices == ((-.5, -.5, 0), (.5, -.5, 0), (-.5, .5, 0))
    assert edges == ((0, 1), (0, 2), (1, 2))


@pytest.mark.parametrize('data', [b'', b'\xff', b'v nan 1 1', b'v 0 0 0\nf 0 1 1',
                                  b'v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 4',
                                  b'v 0 0 0\nv 0 0 0\nv 0 0 0\nf 1 2 3'])
def test_invalid_geometry_is_rejected(data):
    with pytest.raises(ValueError):
        parse_obj(data)


def test_size_limit_prevents_large_model():
    with pytest.raises(ValueError):
        parse_obj(b' ' * (MAX_OBJ_BYTES + 1))


def test_explode_parts_only_separate_disconnected_meshes():
    from core.obj_wireframe import component_directions
    single = parse_obj(b'v 0 0 0\nv 1 0 0\nv 0 1 0\nf 1 2 3\n')
    offsets, count = component_directions(*single)
    assert count == 1 and set(offsets) == {(0., 0., 0.)}
    two = parse_obj(b'v -2 0 0\nv -1 0 0\nv -1 1 0\nv 1 0 0\nv 2 0 0\nv 1 1 0\nf 1 2 3\nf 4 5 6\n')
    offsets, count = component_directions(*two)
    assert count == 2
    assert offsets[0] == offsets[1] == offsets[2]
    assert offsets[3] == offsets[4] == offsets[5]
    assert offsets[0][0] < 0 < offsets[3][0]
