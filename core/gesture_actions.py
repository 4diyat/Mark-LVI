"""Restricted Windows actions for the hand menu, with an explicit target.

Never send a close command unless the UI has separately obtained confirmation.
Targets are checked against handle reuse, changing title and our own process.
"""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class WindowTarget:
    handle: int
    pid: int
    title: str


class WindowsActions:
    def __init__(self, user32=None, input_module=None):
        if user32 is None:
            import ctypes
            from ctypes import wintypes
            user32 = ctypes.WinDLL("user32", use_last_error=True)
            user32.GetForegroundWindow.restype = wintypes.HWND
            user32.GetShellWindow.restype = wintypes.HWND
            user32.GetDesktopWindow.restype = wintypes.HWND
            user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
            user32.IsWindow.argtypes = [wintypes.HWND]
            user32.IsWindowVisible.argtypes = [wintypes.HWND]
            user32.GetWindowTextLengthW.argtypes = [wintypes.HWND]
            user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
            user32.SetForegroundWindow.argtypes = [wintypes.HWND]
            user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
            user32.IsIconic.argtypes = [wintypes.HWND]
            user32.IsZoomed.argtypes = [wintypes.HWND]
            user32.PostMessageW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
        self.user32 = user32
        if input_module is None:
            import pyautogui as input_module
        self.input = input_module

    def capture(self):
        import ctypes
        from ctypes import wintypes
        handle = self.user32.GetForegroundWindow()
        if (not handle or handle in (self.user32.GetShellWindow(), self.user32.GetDesktopWindow())
                or not self.user32.IsWindowVisible(handle)):
            return None
        pid = wintypes.DWORD()
        self.user32.GetWindowThreadProcessId(handle, ctypes.byref(pid))
        size = self.user32.GetWindowTextLengthW(handle)
        buf = ctypes.create_unicode_buffer(size + 1)
        self.user32.GetWindowTextW(handle, buf, len(buf))
        if not pid.value or pid.value == os.getpid() or not buf.value:
            return None
        return WindowTarget(int(handle), pid.value, buf.value)

    def valid(self, target):
        import ctypes
        from ctypes import wintypes
        if not isinstance(target, WindowTarget) or target.pid == os.getpid():
            return False
        if target.handle in (self.user32.GetShellWindow(), self.user32.GetDesktopWindow()):
            return False
        if not self.user32.IsWindow(target.handle) or not self.user32.IsWindowVisible(target.handle):
            return False
        pid = wintypes.DWORD()
        self.user32.GetWindowThreadProcessId(target.handle, ctypes.byref(pid))
        size = self.user32.GetWindowTextLengthW(target.handle)
        buf = ctypes.create_unicode_buffer(size + 1)
        self.user32.GetWindowTextW(target.handle, buf, len(buf))
        return pid.value == target.pid and buf.value == target.title

    def run(self, action, target=None):
        # Only explicitly whitelisted operations; no free-form command execution.
        global_keys = {"task_view": ("win", "tab"), "desktop": ("win", "d"),
                       "start": ("win",), "volume_up": ("volumeup",),
                       "volume_down": ("volumedown",), "volume_mute": ("volumemute",),
                       "media_play": ("playpause",)}
        if action in global_keys:
            self.input.hotkey(*global_keys[action])
            return True
        if action not in {"switch", "minimize", "maximize", "close"} or not self.valid(target):
            return False
        if action == "close":
            # WM_CLOSE asks the application to close normally, so its own save
            # dialog still applies. Never force-kill or bypass UAC.
            return bool(self.user32.PostMessageW(target.handle, 0x0010, 0, 0))
        if action in {"minimize", "maximize"}:
            self.user32.ShowWindow(target.handle, 6 if action == "minimize" else 3)
            return bool(self.user32.IsIconic(target.handle) if action == "minimize" else
                        self.user32.IsZoomed(target.handle))
        if not self.user32.SetForegroundWindow(target.handle):
            return False
        if int(self.user32.GetForegroundWindow() or 0) != target.handle:
            return False
        self.input.hotkey("alt", "tab")
        return True


def close_with_confirmation(controller, backend, target, confirm):
    """Disarm gesture input before asking; re-check the target after the answer."""
    controller.stop()
    if not backend.valid(target):
        return "invalid"
    if not confirm(target):
        return "cancelled"
    return "done" if backend.run("close", target) else "invalid"
