"""The Qt half of floating widgets — re-parenting, and putting it back.

WHY THIS IS SO THIN
    Everything that can be decided without a display is decided in
    `core/floating.py`: which widgets may float, what that means on this
    platform, and where the window goes. This file only does the two things
    that genuinely need Qt — change a widget's window flags, and move it — so
    that the rules are testable on a machine with no display and this file has
    almost nothing in it that could be wrong on its own.

THE ONE-PARENT PROBLEM, AND WHY `Dock` EXISTS
    A `QWidget` has exactly one parent. Taking the speech caption out of the
    layout is not "hiding it": the layout it came from will close the gap, and
    when the widget comes back it reappears wherever the layout decides, not
    where it was. `ui/face_bubble.py` already hit this and solved it by
    building a second widget; that is not available for a live caption, whose
    whole job is to follow the audio.

    So the window keeps a `Dock` — a record of the parent, the layout and the
    index — and takes the widget back to the same index. The layout closes the
    gap while the widget is away, which is the correct thing for it to do: a
    floating caption should not leave a hole in the window behind it.

WHAT THIS FILE DOES NOT DO
    It does not decide. `attach()` is handed a `Fit` it did not compute, and a
    `Placement` it did not work out; a refusal has already happened upstream.
"""
from __future__ import annotations

from core import logbook


def _soft(action, what: str) -> None:
    """Run one Qt call that is allowed to fail, and say so in the log.

    Every call wrapped by this is one whose failure is survivable: a Qt stub in
    a test that has no `setAttribute`, a widget that was already deleted by the
    time we asked, a compositor that refuses translucency. Logged rather than
    swallowed — this repository's ruff config bans `except: pass` (`S110`) and
    it is right to: a silent failure here would be a widget that never appears
    and no way to find out why.
    """
    try:
        action()
    except Exception as e:              # noqa: BLE001 — Qt, at its edges
        logbook.get(__name__).debug("%s failed: %s", what, e)


class Dock:
    """Where a widget came from, so it can be put back exactly there."""

    __slots__ = ("parent", "layout", "index")

    def __init__(self, parent=None, layout=None, index: int = -1):
        self.parent = parent
        self.layout = layout
        self.index = index

    def describe(self) -> str:
        where = type(self.layout).__name__ if self.layout is not None else "its parent"
        return f"{where} at index {self.index}"


def take(widget) -> Dock | None:
    """Work out where a widget lives, before it is moved.

    Returns None when there is nothing to remember — an already-floating widget
    has no layout, and re-docking it "at index -1" would silently append it.
    """
    parent = widget.parentWidget()
    layout = parent.layout() if parent is not None else None
    if layout is None:
        return None
    try:
        index = layout.indexOf(widget)
    except Exception as e:               # noqa: BLE001 — a stub in a test
        logbook.get(__name__).debug("indexOf failed: %s", e)
        index = -1
    return Dock(parent=parent, layout=layout, index=index)


def window_flags(Qt, fit) -> int:
    """Frameless, off the taskbar, and on top only where `fit` says so.

    `Tool` keeps it out of the taskbar: a second entry for a caption is
    confusing, and the window it belongs to is already there. The always-on-top
    flag is added ONLY when the platform note says it will be honoured — asking
    for it on Wayland is a request the compositor accepts and ignores, and an
    ignored request is a lie the user will discover by covering the widget.
    """
    flags = Qt.WindowType
    value = getattr(flags, "FramelessWindowHint") | getattr(flags, "Tool")
    if fit.always_on_top:
        value = value | getattr(flags, "WindowStaysOnTopHint")
    return value


def attach(widget, Qt, fit, placement) -> Dock | None:
    """Move a docked widget out onto the desktop. Returns where it came from.

    The order matters: remember the dock BEFORE the widget is re-parented,
    because after `setParent(None)` there is no layout left to ask.
    """
    if not fit.allowed:
        raise ValueError(fit.reason or "this widget may not float")

    dock = take(widget)
    _soft(lambda: widget.setParent(None), "setParent")
    widget.setWindowFlags(window_flags(Qt, fit))
    _translucent(widget, Qt)
    widget.setGeometry(placement.x, placement.y, placement.width, placement.height)
    widget.show()
    _soft(widget.raise_, "raise_")
    return dock


def detach(widget, Qt, dock: Dock | None) -> None:
    """Put a floating widget back where it was docked.

    `WA_DeleteOnClose` is NOT set anywhere here on purpose: closing a floating
    caption must dock it again, not destroy a widget the window still owns and
    still reads. `ui/desktop_workspace.py` needs the delete-on-close behaviour
    for documents; a caption is the opposite case.
    """
    if dock is None or dock.layout is None:
        return
    _soft(lambda: widget.setWindowFlags(Qt.WindowType.Widget), "setWindowFlags")
    _soft(lambda: widget.setParent(dock.parent), "setParent")
    index = dock.index if dock.index >= 0 else -1
    # `insertWidget(-1, w)` appends, which is what an unknown index should do:
    # at the end of the panel, not in the middle of it.
    _soft(lambda: dock.layout.insertWidget(index, widget), "insertWidget")
    _soft(widget.show, "show")


def _translucent(widget, Qt) -> None:
    """Frameless without translucency is a black rectangle on some compositors.

    Best effort: a Qt build without the attribute simply keeps an opaque
    background, which is ugly but not broken.
    """
    _soft(lambda: widget.setAttribute(
        Qt.WidgetAttribute.WA_TranslucentBackground, True), "WA_TranslucentBackground")


__all__ = ["Dock", "attach", "detach", "take", "window_flags"]
