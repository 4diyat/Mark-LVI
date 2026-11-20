"""Bounded snapshots for explicit, review-before-send visual follow-ups.

Only the user's chosen item plus lightweight surrounding context is included.
All supplied text remains untrusted. No hidden shared selection state exists.
"""
from __future__ import annotations

import json

from core import outcome
from core.narrative_content import validate as validate_narrative
from core.visual_content import validate as validate_chart


def _neighbors(items, index, project):
    return {
        'previous': project(items[index - 1]) if index > 0 else None,
        'next': project(items[index + 1]) if index + 1 < len(items) else None,
    }


def _check_index(index, items):
    if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < len(items):
        raise ValueError('Invalid selection.')


def narrative_snapshot(payload, index):
    data = validate_narrative(payload)
    items = data['items']
    _check_index(index, items)
    return {
        'type': data['kind'], 'title': data['title'], 'summary': data['summary'],
        'source': data['source'], 'observed': data['observed'],
        'position': index + 1, 'total': len(items), 'selected': items[index],
        **_neighbors(items, index, lambda item: {'label': item['label'], 'when': item['when']}),
    }


def chart_snapshot(payload, index):
    data = validate_chart(payload)
    items = data['points']
    _check_index(index, items)
    return {
        'title': data['title'], 'source': data['source'], 'observed': data['observed'],
        'unit': data['unit'], 'chart_type': data['chart_type'], 'position': index + 1, 'total': len(items),
        'selected': items[index], **_neighbors(items, index, dict),
    }


def question(prefix, source, snapshot):
    """A plain-text draft, with the complete JSON inside the untrusted boundary."""
    content = json.dumps(snapshot, ensure_ascii=False, allow_nan=False)
    return prefix + ' ' + outcome.untrusted(source, content).replace('\n', ' ')


def fits_qlineedit(text, max_length):
    """Qt's QLineEdit limit is in UTF-16 code units, not Python code points."""
    return len(text.encode('utf-16-le', errors='surrogatepass')) // 2 <= max_length
