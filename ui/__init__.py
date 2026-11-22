"""ui — the ambient shell, split by what each surface owns.

WHAT THIS PACKAGE IS NOW
    It used to be a full-screen window with a desktop workspace inside it. The
    design sheet (`docs/mockups/jarvis-design-system.html`) draws twelve
    artboards and not one of them is a window: an orb, a toast, a command bar,
    a tray panel, a risk confirmation, a history list, a permissions page and a
    light theme. So the window is gone and this package is those surfaces.

    | module            | what it is                                        |
    |-------------------|---------------------------------------------------|
    | `theme.py`        | the palette (`C`) and the accent code — the only writer |
    | `orb_paint.py`    | the ONE orb painter, at any size                  |
    | `orb_overlay.py`  | the 96 px desktop ring and its hit test           |
    | `face_bubble.py`  | the 260 px floating face (kept by owner request)  |
    | `command_bar.py`  | Ctrl+Space, one line, Esc gives focus back        |
    | `toast_queue.py`  | three at a time, the rest queued and counted      |
    | `confirm_banner.py`| the trusted-UI gate in front of risky actions    |
    | `tray.py`         | the notification-area icon and its menu           |
    | `shell.py`        | `AmbientShell` — the object main.py talks to      |
    | `lifecycle.py`    | start, summon, dismiss, quit, autostart           |
    | `ambient_shell.py`| the orb / bar / presence wiring                   |

    `ui.C`, `ui.qcol`, `ui.AmbientShell` keep working: `main.py` and plugins
    written against the old module must not have to care that it changed shape.

IMPORTING THIS NEEDS QT. Anything that only needs to know ABOUT the surfaces —
their structure, their rules, which file owns what — reads the AST instead;
`tests/test_ui_split.py` does exactly that, and CI installs no PyQt6.
"""
from ui.theme import (          # noqa: F401 — the public face of the package
    C,
    DEFAULT_UI_COLOR,
    apply_ui_accent,
    current_palette,
    qcol,
    retheme_all_widgets,
)
from ui.shell import AmbientShell   # noqa: F401 — what main.py constructs

__all__ = ["AmbientShell", "C", "DEFAULT_UI_COLOR", "apply_ui_accent",
           "current_palette", "qcol", "retheme_all_widgets"]
