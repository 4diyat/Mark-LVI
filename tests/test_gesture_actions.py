"""Exercise Win32 targeting without touching a desktop or sending input."""
import ctypes
from ctypes import wintypes

from core.gesture_actions import WindowTarget, WindowsActions


class FakeWin:
    def __init__(self):
        self.handle, self.pid, self.title = 125, 1234567, "Document"
        self.visible = True
        self.posts, self.shows = [], []
        self.foreground_allowed = True
    def GetForegroundWindow(self):
        return self.handle
    def GetShellWindow(self):
        return 999
    def GetDesktopWindow(self):
        return 998
    def IsWindow(self, handle):
        return handle == self.handle
    def IsWindowVisible(self, handle):
        return self.visible and handle == self.handle
    def GetWindowThreadProcessId(self, handle, ptr):
        ctypes.cast(ptr, ctypes.POINTER(wintypes.DWORD))[0] = self.pid
        return 1
    def GetWindowTextLengthW(self, handle):
        return len(self.title)
    def GetWindowTextW(self, handle, buf, size):
        buf.value = self.title
        return len(self.title)
    def SetForegroundWindow(self, handle):
        return self.foreground_allowed
    def PostMessageW(self, *args):
        self.posts.append(args)
        return 1
    def ShowWindow(self, *args):
        self.shows.append(args)
    def IsIconic(self, _handle):
        return 1
    def IsZoomed(self, _handle):
        return 1


class FakeInput:
    def __init__(self):
        self.keys = []
    def hotkey(self, *args):
        self.keys.append(args)


def test_target_identity_is_checked_before_close_or_window_action():
    win, keys = FakeWin(), FakeInput()
    actions = WindowsActions(win, keys)
    target = actions.capture()
    assert target == WindowTarget(win.handle, win.pid, win.title)
    assert actions.run("close", target)
    assert win.posts == [(125, 0x10, 0, 0)]
    win.title = "Different document"
    assert not actions.run("close", target)
    assert not actions.run("minimize", target)
    assert len(win.posts) == 1
    assert not win.shows
    win.title = "Document"
    win.pid += 1
    assert not actions.run("close", target)
    assert not actions.run("unknown", target)


def test_switch_refuses_when_windows_does_not_restore_target():
    win, keys = FakeWin(), FakeInput()
    actions = WindowsActions(win, keys)
    target = actions.capture()
    win.foreground_allowed = False
    assert not actions.run("switch", target)
    assert not keys.keys
    win.foreground_allowed = True
    assert actions.run("switch", target)
    assert keys.keys == [("alt", "tab")]


def test_global_actions_are_explicitly_whitelisted():
    win, keys = FakeWin(), FakeInput()
    actions = WindowsActions(win, keys)
    assert actions.run("volume_up")
    assert keys.keys == [("volumeup",)]
    assert not actions.run("shutdown")
    assert not actions.run("close", None)
    assert not win.posts


def test_close_disarms_before_confirmation_and_revalidates():
    from core.gesture_actions import close_with_confirmation
    win, mouse = FakeWin(), FakeInput()
    actions = WindowsActions(win, mouse)
    target = actions.capture()

    class Controller:
        stopped = False
        def stop(self):
            self.stopped = True

    ctl = Controller()
    def cancel(t):
        assert ctl.stopped and t == target
        return False
    assert close_with_confirmation(ctl, actions, target, cancel) == "cancelled"
    assert not win.posts
    def change_target(t):
        assert ctl.stopped
        win.title = "Different"
        return True
    assert close_with_confirmation(ctl, actions, target, change_target) == "invalid"
    assert not win.posts
    win.title = "Document"
    assert close_with_confirmation(ctl, actions, target, lambda t: True) == "done"
    assert len(win.posts) == 1


def test_shell_and_own_process_are_not_targets(monkeypatch):
    win = FakeWin()
    actions = WindowsActions(win, FakeInput())
    monkeypatch.setattr("core.gesture_actions.os.getpid", lambda: win.pid)
    assert actions.capture() is None
    monkeypatch.setattr("core.gesture_actions.os.getpid", lambda: 50)
    target = actions.capture()
    win.handle = 999
    assert actions.capture() is None
    assert not actions.valid(WindowTarget(999, win.pid, win.title))
    assert not actions.valid(target)
