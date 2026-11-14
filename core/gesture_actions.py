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


# Keyboard shortcuts are allowlisted, never executed as shell commands. A
# foreground window is needed for all document/browser keys.
GLOBAL_KEYS = {
    "task_view": ("win", "tab"), "desktop": ("win", "d"), "start": ("win",),
    "explorer": ("win", "e"), "settings": ("win", "i"), "search": ("win", "s"),
    "quick_settings": ("win", "a"), "lock_screen": ("win", "l"),
    "volume_up": ("volumeup",), "volume_down": ("volumedown",),
    "volume_mute": ("volumemute",), "media_play": ("playpause",),
    "media_next": ("nexttrack",), "media_previous": ("prevtrack",),
}
TARGET_KEYS = {
    "switch": ("alt", "tab"), "snap_left": ("win", "left"), "snap_right": ("win", "right"),
    "key_up": ("up",), "key_down": ("down",), "key_left": ("left",), "key_right": ("right",),
    "key_tab": ("tab",), "key_shift_tab": ("shift", "tab"), "key_escape": ("esc",),
    "key_home": ("home",), "key_end": ("end",), "key_page_up": ("pageup",), "key_page_down": ("pagedown",),
    "key_enter": ("enter",), "copy": ("ctrl", "c"), "select_all": ("ctrl", "a"),
    "cut": ("ctrl", "x"), "paste": ("ctrl", "v"), "undo": ("ctrl", "z"), "redo": ("ctrl", "y"),
    "save": ("ctrl", "s"), "find": ("ctrl", "f"),
    "new_tab": ("ctrl", "t"), "close_tab": ("ctrl", "w"),
    "next_tab": ("ctrl", "tab"), "previous_tab": ("ctrl", "shift", "tab"),
    "back": ("alt", "left"), "forward": ("alt", "right"), "refresh": ("ctrl", "r"),
    "zoom_in": ("ctrl", "+"), "zoom_out": ("ctrl", "-"), "zoom_reset": ("ctrl", "0"),
}
RISKY_ACTIONS = frozenset({"close", "close_tab", "cut", "paste", "undo", "redo", "save",
                           "key_enter", "back", "forward", "refresh", "lock_screen"})
TARGET_ACTIONS = frozenset(TARGET_KEYS) | {"minimize", "maximize", "restore", "close"}
ACTION_GROUPS = {
    "window": ("switch", "task_view", "desktop", "minimize", "maximize", "restore", "snap_left", "snap_right", "close"),
    "system": ("start", "explorer", "settings", "search", "quick_settings", "lock_screen"),
    "navigation": ("key_up", "key_down", "key_left", "key_right", "key_tab", "key_shift_tab", "key_escape", "key_home", "key_end", "key_page_up", "key_page_down", "key_enter"),
    "editing": ("copy", "select_all", "cut", "paste", "undo", "redo", "save", "find"),
    "browser": ("new_tab", "close_tab", "next_tab", "previous_tab", "back", "forward", "refresh", "zoom_in", "zoom_out", "zoom_reset"),
    "media": ("volume_up", "volume_down", "volume_mute", "media_play", "media_next", "media_previous"),
}


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

    def run(self, action, target=None, *, confirmed=False):
        # Confirmation comes from the UI only, never from a model parameter.
        if action in RISKY_ACTIONS and confirmed is not True:
            return False
        if action in GLOBAL_KEYS:
            self.input.hotkey(*GLOBAL_KEYS[action])
            return True
        if action not in TARGET_ACTIONS or not self.valid(target):
            return False
        if action == "close":
            # WM_CLOSE asks the app to close normally, preserving save dialogs.
            return bool(self.user32.PostMessageW(target.handle, 0x0010, 0, 0))
        if action in {"minimize", "maximize", "restore"}:
            self.user32.ShowWindow(target.handle, {"minimize": 6, "maximize": 3, "restore": 9}[action])
            if action == "restore":
                return not self.user32.IsIconic(target.handle) and not self.user32.IsZoomed(target.handle)
            return bool(self.user32.IsIconic(target.handle) if action == "minimize" else
                        self.user32.IsZoomed(target.handle))
        # QMenu took focus; restore and check the original target rather than
        # sending keys to whichever window happened to receive focus instead.
        if int(self.user32.GetForegroundWindow() or 0) != target.handle:
            if not self.user32.SetForegroundWindow(target.handle):
                return False
        if int(self.user32.GetForegroundWindow() or 0) != target.handle or not self.valid(target):
            return False
        self.input.hotkey(*TARGET_KEYS[action])
        return True


def action_with_confirmation(controller, backend, action, target, confirm):
    """Disarm gesture input before asking, and re-check target after the answer."""
    if action not in RISKY_ACTIONS:
        return "invalid"
    controller.stop()
    if action in TARGET_ACTIONS and not backend.valid(target):
        return "invalid"
    if not confirm(target):
        return "cancelled"
    return "done" if backend.run(action, target, confirmed=True) else "invalid"


def close_with_confirmation(controller, backend, target, confirm):
    return action_with_confirmation(controller, backend, "close", target, confirm)
