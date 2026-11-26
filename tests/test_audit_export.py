"""Audit export reads strictly and never overwrites an existing path."""
import json
import os
import stat

import pytest

from core import audit_export, audit_log


def test_export_writes_all_records_and_refuses_existing_path(tmp_path, monkeypatch):
    monkeypatch.setenv('JARVIS_STATE_DIR', str(tmp_path))
    audit_log.reset_shared()
    try:
        for i in range(55):
            assert audit_log.shared().record(f'tool_{i}', 'safe', 'done', f'detail_{i}')
        output = tmp_path / 'export.json'
        assert audit_export.export_new(output) == 55
        assert len(json.loads(output.read_text(encoding='utf8'))) == 55
        if os.name == 'posix':
            assert stat.S_IMODE(output.stat().st_mode) & 0o077 == 0
        output.write_text('keep me', encoding='utf8')
        with pytest.raises(FileExistsError):
            audit_export.export_new(output)
        assert output.read_text(encoding='utf8') == 'keep me'
        link = tmp_path / 'link.json'
        link.symlink_to(output)
        with pytest.raises(FileExistsError):
            audit_export.export_new(link)
        assert output.read_text(encoding='utf8') == 'keep me'
    finally:
        audit_log.reset_shared()


def test_corrupt_audit_does_not_create_output(tmp_path, monkeypatch):
    monkeypatch.setenv('JARVIS_STATE_DIR', str(tmp_path))
    audit_log.reset_shared()
    try:
        (tmp_path / 'audit.jsonl').write_text('not json\n', encoding='utf8')
        output = tmp_path / 'export.json'
        with pytest.raises(ValueError):
            audit_export.export_new(output)
        assert not output.exists()
    finally:
        audit_log.reset_shared()
