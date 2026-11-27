"""A tool's internal gate is not permission to skip unrelated actions."""
import pytest

from core.self_gated import owns_confirmation


@pytest.mark.parametrize('name,args', [
    ('computer_settings', {'action': 'shutdown'}),
    ('computer_settings', {'action': 'toggle_wifi'}),
    ('code_helper', {'action': 'run'}),
    ('file_processor', {'action': 'extract', 'file_path': '/tmp/archive.zip'}),
])
def test_known_internal_confirmation(name, args):
    assert owns_confirmation(name, args)


@pytest.mark.parametrize('name,args', [
    ('computer_settings', {'action': 'open_run'}),
    ('computer_settings', {'action': 'task_manager'}),
    ('computer_settings', {'action': 'volume_up'}),
    ('code_helper', {'action': 'edit'}),
    ('dev_agent', {'mode': 'build'}),
    ('file_processor', {'action': 'convert', 'file_path': '/tmp/a.png'}),
    ('file_processor', {'action': 'extract', 'file_path': '/tmp/a.pdf'}),
    ('file_processor', {'action': 'extract'}),
])
def test_other_calls_must_not_skip_outer_gate(name, args):
    assert not owns_confirmation(name, args)
