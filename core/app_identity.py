"""What the operating system thinks this program is called.

WHY THIS MODULE EXISTS
    A Python program is, to the OS, an interpreter. Windows groups taskbar
    buttons and decides which icon a pin uses by the *AppUserModelID*, and a
    process that never sets one gets `python.exe`'s — so JARVIS pins as
    python, shows python's icon, and sits in a group with every other Python
    script the user runs. Qt has the same problem from the other side: an app
    that never names itself presents `python3` as the name in the dock, and a
    Linux `.desktop` file only matches an icon to a window when
    `StartupWMClass` names the class the window actually uses.

    None of that is visible from inside the app, which is why it has been
    missing: everything worked, it just worked under somebody else's name.

THREE FACTS, ONE PLACE
    APP_ID      the stable identifier. Quoted verbatim as the Windows
                AppUserModelID and as the macOS bundle identifier, and used as
                `StartupWMClass` on Linux — the same string everywhere, so the
                launcher entry, the tray icon and the taskbar button can be
                recognised as one application rather than three.

    APP_NAME    what a person reads. Not translated: it is an identity, and a
                shortcut whose name changes with the interface language is a
                shortcut the user cannot find twice.

    apply_qt    the Qt half, set the moment the `QApplication` exists and never
                mutated afterwards.

WHAT IS DELIBERATELY NOT HERE
    No file writes, and no registry writes beyond the Windows identity call
    itself. The `.desktop` entries belong to `core.autostart` and
    `core.deeplink`; this module only tells them what to put in them. Two
    writers to one file is how a settings panel starts disagreeing with itself.
"""
from __future__ import annotations

import platform
from pathlib import Path

# Reverse-DNS, lower case, no version number. Appears in the Windows
# AppUserModelID, in the macOS bundle, and in `StartupWMClass`.
APP_ID = "com.jarvis.assistant"

# The name on the taskbar, in the dock, and in the window manager's list.
APP_NAME = "J.A.R.V.I.S"

# The icon both Qt and the `.desktop` entries point at, relative to the
# program's own directory. `ui/icons.py` draws it; `config/` is where it has
# always been written (`ui.tray.icon_path`), so nothing moves.
ICON_RELATIVE = ("config", "jarvis.ico")


def app_user_model_id() -> str:
    """The Windows AppUserModelID.

    Windows parses the value as `CompanyName.ProductName.SubProduct.Version`.
    The reverse-DNS identifier is used as-is: it is already the shape Windows
    expects, and deriving a second spelling from it is how the pin and the
    running process end up in different groups.
    """
    return APP_ID


def startup_wm_class() -> str:
    """What a `.desktop` file must put in `StartupWMClass` to claim our windows.

    GNOME and KDE match a running window to a launcher by WM_CLASS, and Qt
    sets WM_CLASS from the application name. So this must be the SAME string
    `apply_qt` gives Qt — the identifier, not the display name, whose dots and
    spaces window managers mangle.
    """
    return APP_ID


def apply_qt(app) -> bool:
    """Name the `QApplication`. True when it was set.

    Order matters and is the whole point: the desktop file name and the
    application name are read by Qt when windows are created and by the
    desktop when it groups them, so they are set as soon as the app object
    exists — before the first window. A failure here is cosmetic, so it is
    reported rather than raised: an app that will not start because it could
    not rename itself is worse than one called python3.
    """
    try:
        app.setApplicationName(APP_NAME)
        app.setApplicationDisplayName(APP_NAME)
        app.setOrganizationName("JARVIS")
        app.setOrganizationDomain(APP_ID)
        # Qt uses this verbatim as WM_CLASS on X11 and as the bundle hint on
        # macOS. Must equal what `startup_wm_class()` tells the `.desktop`.
        app.setDesktopFileName(APP_ID)
        return True
    except Exception:                     # noqa: BLE001 — cosmetics only
        return False


def _set_windows_app_id(identifier: str) -> bool:
    """`SetCurrentProcessExplicitAppUserModelID` via ctypes.

    Imported inside the call because `ctypes.windll` does not exist off
    Windows, and this module is imported at startup everywhere.
    """
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            ctypes.c_wchar_p(identifier))
        return True
    except Exception:                     # noqa: BLE001
        return False


def apply_os(os_name: str | None = None) -> bool:
    """Give the process an OS-level identity. True when the platform has one.

    Called BEFORE the first window exists, because Windows decides the taskbar
    group when the window is created, not when it is shown. On Linux and macOS
    there is nothing process-wide to set — the identity lives in the launcher
    entry and the bundle — so this is a no-op that returns True.
    """
    os_name = os_name or platform.system()
    if os_name == "Windows":
        return _set_windows_app_id(app_user_model_id())
    return True


def icon_path(program_dir) -> Path:
    """`<program dir>/config/jarvis.ico` — the one icon, from one place.

    `ui.tray.icon_path` and the desktop shortcut already agree on this file;
    routing the OS registration through the same path is what keeps the
    taskbar icon, the tray icon and the scheme handler from drifting apart.
    """
    return Path(program_dir).joinpath(*ICON_RELATIVE)
