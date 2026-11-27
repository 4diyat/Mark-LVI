"""The one list of board pages, and the builder for each. Qt, no state.

WHY THE LIST IS HERE AND NOT IN `tray_panel`
    The panel has a 600-line ceiling and fourteen `_page(...)` pairs put it at
    exactly 600 — a number a ceiling cannot police, because the next line anyone
    adds is the one that breaks it. The builders are also the only thing in the
    panel that must import five other modules, and an import list is not
    lifecycle.

WHY THE NAMES ARE STRINGS AND NOT CONSTANTS
    `ui/pages_more.py` builds its buttons from `ui/page_registry.py` and calls
    `panel._call("page", key)`. The keys in `_BUILDERS` below are the same
    strings; a test walks the registry and asserts every key has a builder here
    and a painter in `pages_paint`, so the three lists cannot drift apart
    silently.
"""
from __future__ import annotations


def _builders() -> tuple:
    """(page key, builder) pairs, imported lazily.

    LAZY BECAUSE OF QT. These modules import `PyQt6.QtWidgets` at function scope
    for the same reason every other builder in this package does; importing them
    at module scope from a module `tray_panel` imports at ITS module scope would
    make `import ui.tray_panel` need Qt, and the headless tests import it.
    """
    from ui import pages_access, pages_admin, pages_memory, pages_more, pages_people

    return (
        ("more", pages_more.build_more),
        ("memory", pages_memory.build_memory),
        ("memory_one", pages_memory.build_memory_one),
        ("routines", pages_people.build_routines),
        ("tools", pages_people.build_tools),
        ("security", pages_admin.build_security),
        ("access", pages_access.build_access),
        ("plugins", pages_admin.build_plugins),
        ("light", pages_admin.build_light),
        ("gestures", pages_people.build_gestures),
        ("brand", pages_admin.build_brand),
        ("installer", pages_admin.build_installer),
        ("consent", pages_people.build_consent),
        ("help", pages_people.build_help),
    )


def page_keys() -> tuple:
    """Every page this module can build, without importing Qt."""
    # "more" FIRST, because it is the list that reaches the others: a page
    # whose only route in is the list cannot be the last thing built.
    return ("more", "memory", "memory_one", "routines", "tools", "security",
            "access", "plugins", "light", "gestures", "brand", "installer",
            "consent", "help")


PANEL_W, PANEL_H = 460, 660


def make_page(window, widget_class, name: str):
    """A hidden child page, ready to be filled. Hidden: board 5 is what opens.

    THIS USED TO BE `_page()` IN `tray_panel`. It moved because every page needs
    it and the panel had reached exactly 600 lines: a factory that takes a
    window and answers a widget is not lifecycle, and the panel is the thing
    with a ceiling.
    """
    page = widget_class(window)
    page.setGeometry(0, 0, PANEL_W, PANEL_H)
    page.setObjectName(name)
    page.hide()
    return page


def build_board_pages(panel, window) -> None:
    """Create and fill every board page. Hidden until `show_page` picks one."""
    from PyQt6.QtWidgets import QWidget

    for name, builder in _builders():
        builder(panel, make_page(window, QWidget, name))


__all__ = ["build_board_pages", "make_page", "page_keys"]


def build_panel_controls(panel, window) -> None:
    """Controls above the page stack, so every page has a way back."""
    from PyQt6.QtWidgets import QPushButton
    from ui.tray_panel_model import _t

    back = QPushButton("‹", window)
    back.setGeometry(374, 22, 28, 24)
    back.setToolTip(_t("ui.panel.chat.back"))
    back.clicked.connect(lambda _checked=False: panel.go_back())
    panel._buttons["panel_back"] = back
    close = QPushButton("×", window)
    close.setGeometry(408, 22, 28, 24)
    close.setToolTip(_t("ui.panel.chat.close"))
    close.clicked.connect(lambda _checked=False: panel.close())
    panel._buttons["panel_close"] = close
    # The theme selector retains its own place in the main header.
    panel._buttons["theme"].setGeometry(374, 22, 28, 24)
