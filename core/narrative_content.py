"""Validate bounded, non-executable interactive explanatory content."""

KINDS = frozenset({'cards', 'steps', 'timeline'})
MAX_ITEMS = 16


def _text(value, field, limit, *, multiline=False, optional=False):
    if not isinstance(value, str) or len(value) > limit:
        raise ValueError(f'Invalid {field}.')
    if any(ord(c) < 32 and not (multiline and c in '\n\t') for c in value):
        raise ValueError(f'Invalid {field}.')
    value = value.strip()
    if not value and not optional:
        raise ValueError(f'{field} is required.')
    return value


def validate(payload):
    """Return a detached snapshot; content and attribution are not verified."""
    if not isinstance(payload, dict):
        raise ValueError('Expected a content object.')
    kind = payload.get('kind')
    if not isinstance(kind, str) or kind not in KINDS:
        raise ValueError('Use cards, steps or timeline.')
    title = _text(payload.get('title'), 'title', 100)
    source = _text(payload.get('source'), 'source', 160)
    observed = _text(payload.get('observed', ''), 'time', 80, optional=True)
    summary = _text(payload.get('summary', ''), 'summary', 500, multiline=True, optional=True)
    items = payload.get('items')
    if not isinstance(items, list) or not 1 <= len(items) <= MAX_ITEMS:
        raise ValueError(f'Provide 1 to {MAX_ITEMS} items.')
    result = []
    for item in items:
        if not isinstance(item, dict):
            raise ValueError('Invalid content item.')
        result.append({
            'label': _text(item.get('label'), 'item label', 100),
            'detail': _text(item.get('detail'), 'item detail', 1200, multiline=True),
            'when': _text(item.get('when', ''), 'item time', 80, optional=True),
        })
    return {'kind': kind, 'title': title, 'source': source, 'observed': observed,
            'summary': summary, 'items': result}
