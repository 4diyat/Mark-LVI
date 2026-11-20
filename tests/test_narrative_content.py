import pytest

from core.narrative_content import validate
from plugins.present_content import run


def sample(kind='cards'):
    return {'kind': kind, 'title': 'Photosynthesis', 'source': 'AI-generated, unverified',
            'summary': 'How it works', 'items': [
                {'label': 'Light', 'detail': 'Plants absorb light.'},
                {'label': 'Sugar', 'detail': 'Energy is stored in sugar.', 'when': ''}]}


@pytest.mark.parametrize('kind', ['cards', 'steps', 'timeline'])
def test_supported_forms_preserve_information_and_never_invent_time(kind):
    data = sample(kind)
    output = validate(data)
    data['items'][0]['detail'] = 'changed'
    assert output['items'][0]['detail'] == 'Plants absorb light.'
    assert output['items'][0]['when'] == '' and output['observed'] == ''
    assert output['kind'] == kind


@pytest.mark.parametrize('change', [
    {'kind': 'execute'}, {'kind': []}, {'source': ''}, {'title': 'x\nBad'},
    {'items': []}, {'items': [None]}, {'items': [{'label': 'x', 'detail': ''}]},
    {'items': [{'label': 'x', 'detail': 'y'}] * 17},
    {'items': [{'label': 'x', 'detail': 'y' * 1201}]},
])
def test_bad_input_is_rejected(change):
    with pytest.raises(ValueError):
        validate({**sample(), **change})


def test_plugin_uses_ui_and_does_not_claim_unavailable_display():
    class Player:
        def show_narrative_content(self, payload):
            self.payload = payload
            return {'ok': True, 'message': 'Opened'}
    p = Player()
    assert run(sample(), p) == 'Opened'
    assert p.payload == validate(sample())
    assert 'requires the JARVIS desktop' in run(sample())
    assert 'Nothing was opened' in run({**sample(), 'items': []}, p)


def _bridge_without_qt():
    import importlib.util
    from pathlib import Path
    path = Path(__file__).resolve().parents[1] / 'ui' / 'visual_bridge.py'
    spec = importlib.util.spec_from_file_location('visual_bridge_test', path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_unclaimed_expired_visual_request_never_opens(monkeypatch):
    from core.workspace_control import WorkspaceRequest
    visual_bridge = _bridge_without_qt()
    request = WorkspaceRequest(validate(sample()))
    assert not request.wait(0)['ok']
    monkeypatch.setattr(visual_bridge, '_parts', lambda _: pytest.fail('cancelled request was opened'))
    visual_bridge.open_content(None, 'narrative', request)


def test_ui_thread_refuses_blocking_visual_request():
    import threading
    from types import SimpleNamespace
    result = _bridge_without_qt().request(SimpleNamespace(_ui_thread_id=threading.get_ident()), 'narrative', sample())
    assert not result['ok'] and 'worker' in result['message']
