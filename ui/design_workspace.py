"""Compatibility entrance for the shared desktop memory page.

The memory implementation lives in desktop_memory. Both tray and home routes
now open the same workspace rather than constructing a second desktop window.
"""
from ui.desktop_memory import MemoryCard as MemoryCard


class DesignWorkspace:
    def __init__(self, shell):
        from ui.desktop_navigation import DesktopWorkspace
        from ui.qt_thread import init_dispatcher
        init_dispatcher()
        self.shell = shell
        workspace = getattr(shell, '_desktop_workspace', None)
        if workspace is None:
            workspace = DesktopWorkspace(shell)
            shell._desktop_workspace = workspace
        self.workspace = workspace
        self.window = workspace.window

    def __getattr__(self, name):
        return getattr(self.workspace.memory, name)

    def show(self):
        from ui.desktop_navigation import open_desktop
        open_desktop(self.shell, 'memory')


def open_workspace(shell) -> bool:
    from ui.desktop_navigation import open_desktop
    return open_desktop(shell, 'memory')
