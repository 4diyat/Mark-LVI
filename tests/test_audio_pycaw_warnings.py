"""Windows endpoint enumeration: noisy optional properties are not fatal."""
import sys
import types
import warnings

from core import audio_devices


def install_pycaw(monkeypatch, get_devices):
    package = types.ModuleType("pycaw")
    module = types.ModuleType("pycaw.pycaw")
    module.AudioUtilities = types.SimpleNamespace(GetAllDevices=get_devices)
    monkeypatch.setitem(sys.modules, "pycaw", package)
    monkeypatch.setitem(sys.modules, "pycaw.pycaw", module)
    monkeypatch.setattr(audio_devices, "_platform_is", lambda: "Windows")


def test_optional_pycaw_property_warning_suppressed_but_others_remain(monkeypatch):
    endpoint = object()
    dev = types.SimpleNamespace(state="AudioDeviceState.Active", FriendlyName="Speakers", EndpointVolume=endpoint)
    def get_devices():
        warnings.warn_explicit("COMError attempting to get property 24 from device <pointer>: COMError(...)"
                               , UserWarning, "utils.py", 289, module="pycaw.utils")
        warnings.warn_explicit("Different pycaw problem", UserWarning, "utils.py", 290, module="pycaw.utils")
        warnings.warn_explicit("COMError attempting to get property 24 from device other", UserWarning,
                               "other.py", 1, module="other")
        return [dev]
    install_pycaw(monkeypatch, get_devices)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        assert audio_devices._endpoint_for("Speakers") is endpoint
    assert [str(w.message) for w in caught] == ["Different pycaw problem", "COMError attempting to get property 24 from device other"]


def test_endpoint_matching_still_prefers_active_exact_name(monkeypatch):
    exact = object()
    devices = [types.SimpleNamespace(state="AudioDeviceState.NotPresent", FriendlyName="Speakers", EndpointVolume=object()),
               types.SimpleNamespace(state="AudioDeviceState.Active", FriendlyName="Speakers extra", EndpointVolume=object()),
               types.SimpleNamespace(state="AudioDeviceState.Active", FriendlyName="Speakers", EndpointVolume=exact)]
    install_pycaw(monkeypatch, lambda: devices)
    assert audio_devices._endpoint_for("Speakers") is exact


def test_enumeration_failure_remains_visible(monkeypatch, capsys):
    def fail():
        raise RuntimeError("device enumeration failed")
    install_pycaw(monkeypatch, fail)
    assert audio_devices._endpoint_for("Speakers") is None
    assert "device enumeration failed" in capsys.readouterr().out
