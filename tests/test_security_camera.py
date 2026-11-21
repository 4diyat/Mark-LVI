"""A camera watcher, and the three promises that make it acceptable.

Three properties carry the whole design, and each has a test here because each
is the kind that fails silently:

  1. OFF MEANS THE CAMERA IS NOT OPENED. Not "a camera that discards frames" —
     an operating-system device light is a promise, and a watcher that opens
     the device to decide whether it should be open breaks it out loud.
  2. IT NEVER SPEAKS FIRST. Results go to the log and a banner. The session is
     not touched, so a room is not interrupted by a curtain.
  3. NOTHING IS RECORDED OR UPLOADED. No image reaches the disk; the loop
     never calls the capture at all.
"""
from __future__ import annotations

import ast
import json
import sys
import types
from pathlib import Path

import pytest

from core import security_camera as cam

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture()
def config(tmp_path, monkeypatch):
    """A throw-away `config/api_keys.json` for the module's only reader."""
    from memory import config_manager

    path = tmp_path / "api_keys.json"
    path.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(config_manager, "CONFIG_FILE", path)
    monkeypatch.setattr(config_manager, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(config_manager, "_LAST_GOOD", {})
    cam.reset()
    yield path
    cam.reset()


@pytest.fixture()
def frames(monkeypatch):
    """A camera that returns whatever we say, and counts the openings."""
    calls = {"opened": 0, "images": []}

    def fake_capture():
        calls["opened"] += 1
        image = calls["images"][-1] if calls["images"] else b""
        return image, "image/jpeg"

    from actions import screen_processor

    monkeypatch.setattr(screen_processor, "_capture_camera", fake_capture)
    return calls


# ── 1. off means the camera is not opened ─────────────────────────────────

def test_the_default_is_off(config):
    assert cam.enabled() is False
    assert "OFF" in cam.describe()
    assert "not opened" in cam.describe()


def test_a_tick_with_the_camera_off_does_not_open_it(config, frames, monkeypatch):
    """The load-bearing test. `force` is the tool path; even that must obey."""
    assert cam.tick() is None
    assert frames["opened"] == 0, "the device was opened while the watcher was off"


def test_there_is_no_force_flag_to_get_past_the_switch(config):
    """A caller that can override the setting is a switch that does not mean
    what the drawer says."""
    import inspect

    params = inspect.signature(cam.tick).parameters
    assert list(params) == [], f"tick() grew parameters: {list(params)}"


def test_only_a_literal_true_turns_it_on(config):
    for value in ("true", "yes", 1, [True], {"on": True}, "1"):
        config.write_text(json.dumps({"security_camera": {"enabled": value}}),
                          encoding="utf-8")
        assert cam.enabled() is False, f"{value!r} switched a camera on"


def test_a_broken_settings_file_leaves_it_off(config):
    config.write_text("{not json", encoding="utf-8")
    assert cam.enabled() is False


def test_a_non_dict_section_leaves_it_off(config):
    config.write_text(json.dumps({"security_camera": True}), encoding="utf-8")
    assert cam.enabled() is False


def test_save_off_removes_the_section_rather_than_setting_false(config):
    """A leftover interval is a cadence the next person did not choose."""
    assert cam.save(True, 45) is True
    assert cam.enabled() is True
    assert cam.save(False) is True
    raw = json.loads(config.read_text(encoding="utf-8"))
    assert "security_camera" not in raw


# ── 2. it never speaks first ───────────────────────────────────────────────

def test_the_watcher_loop_never_touches_the_session():
    """A watcher that interrupts the room is a smoke alarm that does not know
    what smoke is. Scanned over the AST: a comment mentioning `session` must
    not fail the test, a call must."""
    tree = ast.parse((ROOT / "core" / "security_camera.py").read_text(encoding="utf-8"))
    offenders = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in {"send_client_content", "send", "generate"}:
                offenders.append(f"line {node.lineno}: {node.func.attr}()")
    assert not offenders, offenders


def test_a_change_is_written_to_the_log_and_not_the_exchange(config, frames, monkeypatch):
    """`watch` reports through `ui.write_log` and the logbook only."""
    seen = []
    sent = []
    monkeypatch.setattr(cam, "enabled", lambda: True)
    monkeypatch.setattr(cam, "interval", lambda: 0.0)
    monkeypatch.setattr(cam, "tick", lambda: cam.Frame(
        image=b"x", mime="image/jpeg", at="2026-11-19T10:00:00",
        changed=True, difference=0.4))

    class UI:
        def write_log(self, text):
            seen.append(text)

        def send_client_content(self, **kwargs):        # pragma: no cover
            sent.append(kwargs)

    async def run_two():
        import asyncio
        task = asyncio.ensure_future(cam.watch(UI()))
        await asyncio.sleep(0.05)
        task.cancel()

    import asyncio
    played = []
    monkeypatch.setattr("core.notify.send_native",
                        lambda title, body: played.append((title, body)))
    try:
        asyncio.run(run_two())
    except asyncio.CancelledError:                       # pragma: no cover
        pass

    assert seen and "Camera check" in seen[0]
    assert sent == [], "the watcher spoke into the session"
    assert played, "the user was never told at all"


# ── 3. nothing is recorded or uploaded ────────────────────────────────────

def test_the_module_never_writes_a_file():
    """No image on disk, no archive, no cache — the record is memory only."""
    tree = ast.parse((ROOT / "core" / "security_camera.py").read_text(encoding="utf-8"))
    banned = {"write_text", "write_bytes", "unlink", "rmtree", "mkdir",
              "rename", "replace", "imwrite", "imencode"}
    offenders = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            if node.func.attr in banned:
                offenders.append(f"line {node.lineno}: {node.func.attr}()")
    assert not offenders, offenders


def test_the_frame_is_returned_and_the_call_is_not_kept_anywhere(config, frames, monkeypatch):
    """`tick` hands back the bytes; the module holds no reference to them."""
    monkeypatch.setattr(cam, "enabled", lambda: True)
    frames["images"].append(b"a-jpeg")

    frame = cam.tick()

    assert frame is not None and frame.image == b"a-jpeg"
    for value in vars(cam).values():
        assert not isinstance(value, cam.Frame), "a frame was retained"


def test_only_changes_are_remembered(config, frames, monkeypatch):
    """A list of "nothing happened" every twenty seconds is a log of absence."""
    monkeypatch.setattr(cam, "enabled", lambda: True)
    frames["images"].append(b"x")
    cam.tick()
    assert cam.recent() == []


def test_the_report_does_not_take_a_picture_when_on_either(config, frames, monkeypatch):
    """Asking "did anything happen" must not itself switch the device on — and
    the off branch returning early is not the test: the ON branch is where a
    report would be tempted to look first."""
    monkeypatch.setattr(cam, "enabled", lambda: True)

    answer = cam.report()

    assert frames["opened"] == 0, "a status question took a picture"
    assert "nothing in view has changed" in answer


def test_the_report_is_off_when_off(config, frames):
    assert "off" in cam.report().lower()
    assert frames["opened"] == 0


# ── the difference detector ───────────────────────────────────────────────

def test_the_same_frames_are_not_a_change():
    a = [10] * 100
    assert cam._difference(a, a) == 0.0


def test_a_bright_frame_is_not_a_change_at_a_dim_one():
    """Mean absolute difference, not a squared error: the number is quoted to
    the user as a share of the frame."""
    assert cam._difference([0] * 100, [255] * 100) == 1.0


def test_frames_of_different_sizes_are_not_silently_compared():
    assert cam._difference([1, 2, 3], [1, 2]) == 1.0


def test_an_unchanged_room_is_not_an_event(config, frames, monkeypatch):
    """The end-to-end claim the module exists to make: two identical looks
    produce one baseline and no report. Testing `_difference` alone would let
    a `changed = True` in `tick` survive."""
    fingerprint = [50] * 100
    monkeypatch.setattr(cam, "enabled", lambda: True)
    monkeypatch.setattr(cam, "_decode_and_fingerprint", lambda image: fingerprint)
    frames["images"].append(b"same")

    cam.tick()                      # establishes the baseline
    frame = cam.tick()              # the same room, a moment later

    assert frame.changed is False
    assert frame.difference == 0.0
    assert cam.recent() == []


def test_a_changed_room_is_one_event(config, frames, monkeypatch):
    """And the other side: one real change is reported once, not once per tick."""
    monkeypatch.setattr(cam, "enabled", lambda: True)
    state = {"value": [0] * 100}
    monkeypatch.setattr(cam, "_decode_and_fingerprint", lambda image: state["value"])
    frames["images"].append(b"x")
    cam.tick()                      # baseline: dark
    state["value"] = [255] * 100    # a lamp comes on

    first = cam.tick()
    second = cam.tick()

    assert first.changed is True
    assert second.changed is False, "the same change was reported twice"
    assert len(cam.recent()) == 1


def test_a_second_change_within_the_hold_off_is_not_reported(config, frames, monkeypatch):
    """Somebody moving around the room changes the frame every tick. The
    hold-off is what turns that into one line instead of a notification every
    twenty seconds — and it is the only thing that does, because a reported
    change also moves the baseline."""
    monkeypatch.setattr(cam, "enabled", lambda: True)
    state = {"value": [0] * 100}
    monkeypatch.setattr(cam, "_decode_and_fingerprint", lambda image: state["value"])
    frames["images"].append(b"x")
    cam.tick()                          # baseline

    state["value"] = [255] * 100
    assert cam.tick().changed is True   # the lamp comes on — reported

    state["value"] = [255] * 50 + [0] * 50
    assert cam.tick().changed is False, "a second change was reported in silence"

    assert len(cam.recent()) == 1


def test_a_fingerprint_failure_does_not_report_a_change(config, frames, monkeypatch):
    """Without numpy/cv2 there is nothing to compare, and claiming otherwise
    would be worse than saying nothing."""
    monkeypatch.setattr(cam, "enabled", lambda: True)
    monkeypatch.setattr(cam, "_decode_and_fingerprint", lambda image: None)
    frames["images"].append(b"x")

    frame = cam.tick()

    assert frame is not None and frame.changed is False


def test_the_interval_has_a_floor(config):
    """1 second is a video stream, which is a different feature with a
    different consent conversation."""
    config.write_text(json.dumps({"security_camera": {
        "enabled": True, "interval_seconds": 1}}), encoding="utf-8")
    assert cam.interval() >= 10.0


def test_a_junk_interval_falls_back_to_the_default(config):
    config.write_text(json.dumps({"security_camera": {
        "enabled": True, "interval_seconds": "soon"}}), encoding="utf-8")
    assert cam.interval() == cam.TICK_SECONDS


# ── the switch nobody but a person may press ───────────────────────────────

def test_no_tool_or_plugin_can_switch_the_camera_on():
    """Same rule as `core/file_access.py`: a permission the model could grant
    itself is a permission a prompt injection can grant.

    Scanned over the AST and following aliases, because the plain name is the
    obvious way past a test that only looks for `import core.security_camera`.
    """
    forbidden = {"save", "reset"}
    offenders = []
    for folder in ("actions", "plugins"):
        for path in (ROOT / folder).rglob("*.py"):
            tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
            aliases = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    if node.module == "core.security_camera":
                        if {a.name for a in node.names} & forbidden:
                            offenders.append(f"{path}:{node.lineno} imports {sorted(forbidden)}")
                        aliases |= {a.asname or a.name for a in node.names
                                    if a.name == "security_camera"}
                    elif node.module == "core":
                        aliases |= {a.asname or a.name for a in node.names
                                    if a.name == "security_camera"}
                elif isinstance(node, ast.Import):
                    for a in node.names:
                        if a.name == "core.security_camera":
                            aliases.add(a.asname or "core")
            for node in ast.walk(tree):
                if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                        and node.func.attr in forbidden
                        and _rooted_at(node.func.value, aliases)):
                    offenders.append(f"{path}:{node.lineno} calls {node.func.attr}()")
    assert not offenders, offenders


def _rooted_at(node, aliases: set[str]) -> bool:
    while isinstance(node, ast.Attribute):
        node = node.value
    return isinstance(node, ast.Name) and node.id in aliases


def test_the_plugin_asks_a_person_instead_of_refusing_silently():
    """A refusal the model cannot explain is a dead end for the user."""
    answer = _plugin_module().run({"action": "on"})
    assert "CONTROLS" in answer and "cannot switch" in answer


def _plugin_module():
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "security_camera_plugin", ROOT / "plugins" / "security_camera.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


# ── the row ───────────────────────────────────────────────────────────────

class _FakeButton:
    def __init__(self):
        self.text = ""
        self.tooltip = ""
        self.style = ""

    def setText(self, value):
        self.text = value

    def setToolTip(self, value):
        self.tooltip = value

    def setStyleSheet(self, value):
        self.style = value

    def setFont(self, value):
        pass


@pytest.fixture()
def row(monkeypatch):
    import importlib.util

    gui = types.ModuleType("PyQt6.QtGui")
    gui.QFont = lambda *a, **k: None
    widgets = types.ModuleType("PyQt6.QtWidgets")
    widgets.QPushButton = _FakeButton
    theme = types.ModuleType("ui.theme")
    theme.C = types.SimpleNamespace(RED="#f00", TEXT="", TEXT_DIM="", WHITE="",
                                    BORDER="", BORDER_B="")
    saved = {n: sys.modules.get(n) for n in
             ("PyQt6", "PyQt6.QtGui", "PyQt6.QtWidgets", "ui.theme")}
    sys.modules.update({"PyQt6": types.ModuleType("PyQt6"), "PyQt6.QtGui": gui,
                        "PyQt6.QtWidgets": widgets, "ui.theme": theme})
    spec = importlib.util.spec_from_file_location(
        "camera_row", ROOT / "ui" / "camera_row.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    try:
        yield module
    finally:
        for name, value in saved.items():
            if value is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = value


def test_the_row_turns_the_watcher_on_and_off(row, config):
    button = _FakeButton()
    assert row.toggle(button) is True
    assert cam.enabled() is True
    assert "ON" in button.text
    assert row.toggle(button) is False
    assert cam.enabled() is False
    assert "OFF" in button.text


def test_the_row_does_not_open_the_camera(row, config, frames):
    """Pressing the switch writes a setting; the first look is the loop's job.
    A button that lights the device indicator while the label is still being
    read is a button that surprises people."""
    row.toggle(_FakeButton())
    row.toggle(_FakeButton())
    assert frames["opened"] == 0


def test_the_row_reports_the_setting_not_the_optimism(row, config, monkeypatch):
    monkeypatch.setattr(cam, "save", lambda *a, **k: True)     # lies about writing
    button = _FakeButton()
    assert row.toggle(button) is False
    assert "OFF" in button.text


def test_the_two_permission_rows_are_built_together():
    """Adjacent in the drawer on purpose: two questions of the same kind."""
    source = (ROOT / "ui" / "permission_rows.py").read_text(encoding="utf-8")
    assert "build_file_access_button" in source
    assert "build_camera_button" in source
