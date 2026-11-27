"""Calls whose whole risky operation already asks via the trusted UI.

This list is deliberately per call, not per tool. A nested confirmation for
one step of a larger job is not confirmation for the job itself.
"""
from pathlib import Path
from typing import Mapping


def owns_confirmation(name: str, args: Mapping | None = None) -> bool:
    args = args or {}
    action = str(args.get('action') or '').strip().lower()
    if name == 'computer_settings':
        return action in {'shutdown', 'restart', 'toggle_wifi'}
    if name == 'code_helper':
        return action == 'run'
    if name == 'file_processor' and action == 'extract':
        path = str(args.get('file_path') or '')
        return Path(path).suffix.lower() in {'.zip', '.rar', '.tar', '.gz', '.7z', '.bz2', '.xz'}
    return False
