"""Built-in vision controls are scoped and never claim OS enforcement."""
import pytest

from actions import screen_processor
from core import tool_permissions, vision_access, vision_gate


@pytest.fixture(autouse=True)
def reset_switches(monkeypatch):
    monkeypatch.setattr('core.action_gate._audit', lambda *args: None)
    tool_permissions.reset(); vision_access.reset()
    yield
    tool_permissions.reset(); vision_access.reset()


def test_disabled_capture_is_checked_before_any_device(monkeypatch):
    vision_access.set_allowed('screen', False)
    vision_access.set_allowed('camera', False)
    monkeypatch.setattr(screen_processor, '_MSS', False)
    monkeypatch.setattr(screen_processor, '_capture_camera_owned', lambda: pytest.fail('camera opened'))
    with pytest.raises(PermissionError, match='Screen vision'):
        screen_processor._capture_screen()
    with pytest.raises(PermissionError, match='Camera vision'):
        screen_processor._capture_camera()


def test_safe_tool_switch_prevents_vision_capture():
    tool_permissions.set_allowed('safe', False)
    image, message = vision_gate.capture({'angle': 'screen'}, lambda: pytest.fail('capture ran'))
    assert image is None and 'disabled' in message


def test_vision_capture_failure_and_success_never_leak_image_to_message():
    image, message = vision_gate.capture({'angle': 'camera'}, lambda: (b'secret', 'image/jpeg'))
    assert image == (b'secret', 'image/jpeg') and 'secret' not in message
    def denied(): raise PermissionError('camera disabled')
    image, message = vision_gate.capture({'angle': 'camera'}, denied)
    assert image is None and 'camera disabled' in message
