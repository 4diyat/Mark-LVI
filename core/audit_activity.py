"""Summarise recorded requests, not inferred or verified system activity."""


def request_counts(records):
    """Count gate request records by risk; callers define the time/window scope.

    Each gate request contributes once, rather than counting its subsequent
    awaiting and outcome records as additional actions. Missing audit entries
    and actions outside the gate cannot be inferred from this log.
    """
    counts = {'safe': 0, 'medium': 0, 'risky': 0}
    for record in records:
        level = record.get('level')
        if record.get('outcome') == 'requested' and level in counts:
            counts[level] += 1
    return counts
