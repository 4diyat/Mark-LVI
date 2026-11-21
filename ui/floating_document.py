"""A plugin's document window, out of the MDI area and onto the desktop.

WHY THIS IS NOT `ui/floating_window.py`
    That module re-parents a plain WIDGET out of a layout and back. A document
    is not a plain widget: it lives inside a `QMdiSubWindow`, and the MDI area
    owns that subwindow's lifecycle — it is added with `addSubWindow`, it is
    tracked in `window._workspace_documents`, and it is destroyed on close
    because `show_document` sets `WA_DeleteOnClose`.

    So floating a document is a different operation with the same shape:
    detach the subwindow from the MDI area so the MDI area stops managing it,
    give it real window flags, put it where it was asked to go, and on the way
    back do the exact reverse and RE-ADD it, because a subwindow that is simply
    parented back is a child widget drawn at 0,0 with no title bar.

THE THREE THINGS THIS FILE REFUSES TO DO
    * It does not set `WA_DeleteOnClose` anywhere. That attribute belongs to
      whoever created the subwindow, and closing a floating document must go
      back to that same decision, not to a new one made here.
    * It does not close anything on its own. `recall()` asks; the document's
      own `closeEvent` — and with it the "you have unsaved work" veto — answers.
    * It does not decide whether a kind may float. `fit_document` in
      `core/floating.py` did that before this file was called.

WHAT GOES WRONG WITHOUT `EXIT_RETURN`
    A `QMdiSubWindow` whose window state is left as it was comes back into the
    MDI area maximised, or minimised, or still wearing the geometry it had on
    the desktop. `recall()` returns the state explicitly, and `float()` stores
    which state it was in so it can be given back.
"""
from __future__ import annotations

from core import logbook


def _soft(action, what: str) -> None:
    """Run one Qt call that is allowed to fail, and say so in the log.

    Same contract as `ui/floating_window.py::_soft`: every wrapped call is one
    whose failure is survivable (a compositor refusing a hint, a window already
    deleted), and this repository bans `except: pass` because a silent failure
    here is a document that vanishes with no way to find out why.
    """
    try:
        action()
    except Exception as e:              # noqa: BLE001 — Qt, at its edges
        logbook.get(__name__).debug("%s failed: %s", what, e)


class Detached:
    """Where a subwindow came from, so it can be put back exactly there."""

    __slots__ = ("mdi", "was_maximized", "was_minimized", "geometry")

    def __init__(self, mdi=None, was_maximized: bool = False,
                 was_minimized: bool = False, geometry=None):
        self.mdi = mdi
        self.was_maximized = was_maximized
        self.was_minimized = was_minimized
        self.geometry = geometry

    def describe(self) -> str:
        if self.was_maximized:
            return "maximised in the workspace"
        if self.was_minimized:
            return "minimised in the workspace"
        return "docked in the workspace"


def detach(sub, Qt, fit, placement) -> Detached:
    """Take a `QMdiSubWindow` out of the MDI area and onto the desktop."""
    if not fit.allowed:
        raise ValueError(fit.reason or "this document may not float")

    mdi = sub.mdiArea()
    was_maximized = bool(_soft_bool(sub.isMaximized))
    was_minimized = bool(_soft_bool(sub.isMinimized))
    geometry = None
    try:
        geometry = sub.geometry()
    except Exception as e:                        # noqa: BLE001
        logbook.get(__name__).debug("could not read the geometry: %s", e)

    if mdi is not None:
        # Leaves the MDI area WITHOUT closing: `removeSubWindow` only drops the
        # containment, so the document's own close veto is untouched.
        _soft(lambda: mdi.removeSubWindow(sub), "removeSubWindow")

    flags = Qt.WindowType
    value = getattr(flags, "FramelessWindowHint")
    if fit.always_on_top:
        value = value | getattr(flags, "WindowStaysOnTopHint")
    _soft(lambda: sub.setWindowFlags(value), "setWindowFlags")
    # The MDI area maximises its subwindows; on the desktop that is a full
    # screen with no title bar and no obvious way back.
    _soft(lambda: sub.setWindowState(Qt.WindowState.WindowNoState), "setWindowState")
    sub.setGeometry(placement.x, placement.y, placement.width, placement.height)
    sub.show()
    _soft(sub.raise_, "raise_")
    return Detached(mdi, was_maximized, was_minimized, geometry)


def recall(sub, Qt, dock: Detached | None) -> None:
    """Put the subwindow back into the MDI area, in the state it left in.

    `EXIT_RETURN` is not set on purpose. `EXIT_MAXIMIZE`/`EXIT_MINIMIZE` would
    mean that closing a floating document returns to a maximised area even if
    the user left it tiled — the layout would be quietly rewritten by an
    unrelated gesture.
    """
    if dock is None:
        return
    _soft(lambda: sub.setWindowFlags(Qt.WindowType.SubWindow), "setWindowFlags")

    def _readd():
        if dock.mdi is not None:
            dock.mdi.addSubWindow(sub)

    _soft(_readd, "addSubWindow")
    if dock.geometry is not None:
        # Restored BEFORE the state: a maximised area would otherwise take the
        # geometry back to the full viewport and the stored one is lost.
        _soft(lambda: sub.setGeometry(dock.geometry), "setGeometry")
    _soft(sub.show, "show")
    if dock.was_minimized:
        _soft(sub.showMinimized, "showMinimized")
    elif dock.was_maximized:
        _soft(sub.showMaximized, "showMaximized")
    else:
        _soft(sub.showNormal, "showNormal")


def _soft_bool(predicate):
    try:
        return bool(predicate())
    except Exception as e:                        # noqa: BLE001
        logbook.get(__name__).debug("could not read the window state: %s", e)
        return False


__all__ = ["Detached", "detach", "recall"]
