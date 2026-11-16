"""Bounded Wavefront OBJ geometry for the native in-session wireframe viewer.

Only vertex positions and polygon faces are accepted. Materials, textures,
external references, normals, animation and executable content are ignored.
"""
from __future__ import annotations

import math

MAX_OBJ_BYTES = 2 * 1024 * 1024
MAX_VERTICES = 5000
MAX_FACES = 10000
MAX_FACE_VERTICES = 64
MAX_EDGES = 20000


def parse_obj(data: bytes):
    """Return normalized vertices and unique face edges; reject invalid input."""
    if not isinstance(data, bytes) or len(data) > MAX_OBJ_BYTES:
        raise ValueError('OBJ exceeds the size limit')
    try:
        text = data.decode('utf-8-sig')
    except UnicodeDecodeError as exc:
        raise ValueError('OBJ must be UTF-8') from exc
    vertices = []
    edges = set()
    face_count = 0
    for line in text.splitlines():
        parts = line.split('#', 1)[0].split()
        if not parts:
            continue
        if parts[0] == 'v':
            if len(parts) < 4 or len(vertices) >= MAX_VERTICES:
                raise ValueError('Invalid vertex or too many vertices')
            try:
                coords = tuple(float(v) for v in parts[1:4])
            except ValueError as exc:
                raise ValueError('Invalid vertex') from exc
            if not all(math.isfinite(v) and abs(v) <= 1e12 for v in coords):
                raise ValueError('Invalid vertex coordinate')
            vertices.append(coords)
        elif parts[0] == 'f':
            face_count += 1
            if face_count > MAX_FACES or not 3 <= len(parts) - 1 <= MAX_FACE_VERTICES:
                raise ValueError('Invalid face or too many faces')
            indices = []
            for component in parts[1:]:
                try:
                    number = int(component.split('/', 1)[0])
                except ValueError as exc:
                    raise ValueError('Invalid face index') from exc
                # OBJ negative indices refer to vertices already read.
                index = number - 1 if number > 0 else len(vertices) + number
                if number == 0 or index < 0 or index >= len(vertices):
                    raise ValueError('Face index outside vertices')
                indices.append(index)
            for i, start in enumerate(indices):
                end = indices[(i + 1) % len(indices)]
                if start != end:
                    edges.add(tuple(sorted((start, end))))
                    if len(edges) > MAX_EDGES:
                        raise ValueError('Too many model edges')
    if len(vertices) < 3 or not edges:
        raise ValueError('OBJ must contain vertices and faces')
    minimum = [min(v[i] for v in vertices) for i in range(3)]
    maximum = [max(v[i] for v in vertices) for i in range(3)]
    center = [(minimum[i] + maximum[i]) / 2 for i in range(3)]
    size = max(maximum[i] - minimum[i] for i in range(3))
    if size <= 1e-12:
        raise ValueError('OBJ has no visible geometry')
    normalized = tuple(tuple((v[i] - center[i]) / size for i in range(3)) for v in vertices)
    return normalized, tuple(sorted(edges))


def component_directions(vertices, edges):
    """Return per-vertex outward directions and count of disconnected mesh parts.

    Parts are determined only by shared OBJ vertex indices, not semantic CAD
    parts. A single connected mesh intentionally cannot be exploded.
    """
    parent = list(range(len(vertices)))

    def root(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    used = set()
    for a, b in edges:
        used.update((a, b))
        x, y = root(a), root(b)
        if x != y:
            parent[y] = x
    groups = {}
    for i in sorted(used):
        groups.setdefault(root(i), []).append(i)
    offsets = [(0., 0., 0.) for _ in vertices]
    if len(groups) < 2:
        return tuple(offsets), len(groups)
    for n, indices in enumerate(groups.values()):
        center = [sum(vertices[i][axis] for i in indices) / len(indices) for axis in range(3)]
        length = math.sqrt(sum(v * v for v in center))
        # Parts can share a centre; spread those deterministically instead of
        # pretending the file describes meaningful physical assembly axes.
        if length < 1e-9:
            angle = 2 * math.pi * n / len(groups)
            direction = (math.cos(angle), math.sin(angle), 0.)
        else:
            direction = tuple(v / length for v in center)
        for i in indices:
            offsets[i] = direction
    return tuple(offsets), len(groups)
