"""Explicit, non-overwriting export of the audit store."""
import json
import os
from pathlib import Path


def export_new(path):
    """Read the whole valid audit log, then create a new JSON file exclusively.

    A failed read creates no output. Existing destinations, including symlinks,
    are never overwritten; a write error can leave a partial new file.
    """
    from core import audit_log

    records = audit_log.shared().entries(strict=True)
    payload = json.dumps(records, ensure_ascii=False, indent=2) + '\n'
    fd = os.open(Path(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as target:
        target.write(payload)
    return len(records)
