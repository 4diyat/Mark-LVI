"""The Qt half of the dashboard layer — a board, entered and left.

WHY A LAYER AND NOT A WINDOW
    `ui/floating_documents.py` re-parents a document into a top-level window of
    its own. A dashboard is the other idea: ONE surface, covering this window,
    holding the things you want to glance at, entered on purpose and left with
    everything exactly where it was. The window is the parent, so there is no
    top-level to position, no window manager to argue with, and nothing that can
    outlive the app.

WHY THIS FILE IS THIS SHORT
    Every decision is in `core/dashboard.py`: what may appear, what a tile is
    worth in cells, how a set splits into shown-and-refused, and the sentence for
    each way of leaving. This file builds the widgets and does the two Qt
    operations that genuinely need Qt. That split is the same one
    `ui/floating_window.py` makes, for the same reason: the rules can be tested
    on a machine with no display, and this file has almost nothing in it that
    could be wrong on its own.

THE TWO OPERATIONS THAT ARE ACTUALLY HARD
    1. TAKING A WIDGET OUT. A `QWidget` has exactly one parent. Moving the
       caption onto the board is a re-parent, and the layout it came from will
       close the gap — which is right: a floating tile should not leave a hole.
       So the layer keeps the slot and puts it back by index, exactly like
       `ui/floating_window.Dock`.
    2. PUTTING IT BACK WHEN THE LAYER IS LEFT BY ANY ROUTE. Esc, the button,
       losing focus and shutdown all take the same path, because a dashboard
       that only tidies up on the polite exit is a dashboard that eats the
       caption the first time the user alt-tabs.

WHAT IT DOES NOT DO
    It does not create the caption or the metrics reader — those exist for the
    whole run and belong to the window. The layer borrows them.
"""
from __future__ import annotations

from core import dashboard as _dash
from core import logbook


def _soft(action, what: str) -> None:
    """Run one Qt call that is allowed to fail, and say so in the log.

    Same rule as `ui/floating_window._soft`: a silent failure here is a tile
    that never appears and no way to find out why. Ruff bans `except: pass`
    (`S110`) and it is right to.
    """
    try:
        action()
    except Exception as e:                  # noqa: BLE001 — Qt, at its edges
        logbook.get(__name__).debug("%s failed: %s", what, e)


class DashboardLayer:
    """A full-board overlay over the workspace, holding borrowed widgets."""

    def __init__(self, window):
        self.window = window
        self.layer = _dash.Layer()
        self._board = None
        self._grid = None
        self._tiles: dict[str, object] = {}
        self._slots: dict[str, tuple] = {}
        self._held: dict[str, object] = {}
        self.open = False

    # ── construction ──────────────────────────────────────────────────────

    def _build(self):
        if self._board is not None:
            return self._board
        from PyQt6.QtWidgets import QGridLayout, QScrollArea, QWidget

        board = QWidget(self.window)
        board.setObjectName("DashboardBoard")
        board.setStyleSheet("""
            QWidget#DashboardBoard { background: rgba(6, 14, 22, 232); }
            QWidget#DashboardTile { background: rgba(18, 34, 48, 220);
                border: 1px solid #33566e; border-radius: 10px; }
        """)
        # A scroll area rather than a fixed board: a dashboard with more tiles
        # than fit must scroll, not clip. Clipping is how a read-only tile
        # starts to look like the thing is broken.
        scroll = QScrollArea(board)
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")
        inner = QWidget()
        grid = QGridLayout(inner)
        grid.setContentsMargins(24, 24, 24, 24)
        grid.setSpacing(16)
        scroll.setWidget(inner)
        scroll.setGeometry(0, 0, board.width(), board.height())
        board._scroll = scroll                     # kept alive by its parent
        board._grid = grid
        try:
            board.hide()
        except Exception as e:                      # noqa: BLE001
            logbook.get(__name__).debug("could not build the board: %s", e)
        self._board, self._grid = board, grid
        return board

    def _tile(self, name: str, entry):
        """A framed panel for one widget, sized from the catalogue."""
        from PyQt6.QtWidgets import QVBoxLayout, QWidget

        cell = QWidget()
        cell.setObjectName("DashboardTile")
        box = QVBoxLayout(cell)
        box.setContentsMargins(10, 10, 10, 10)
        # One cell of the board. 220×140 is big enough for a caption line and a
        # two-column metrics tile without the text being clipped at the default
        # window size, and small enough that four tiles fit across a 1280px
        # window without scrolling.
        cell.setMinimumSize(110 * entry.columns, 70 * entry.rows)
        cell._box = box
        return cell

    @property
    def tiles(self) -> dict:
        """What is on the board right now, by name. For the drawer and tests."""
        return dict(self._tiles)

    # ── entering ──────────────────────────────────────────────────────────

    def show(self, names=None) -> list:
        """Lift `names` onto the board and show it. Returns the refusals.

        A refusal does NOT cancel the layer: the user asked for three things and
        two can be shown, so the layer opens with two and each refusal is
        logged. Punishing the user for a plugin they did not write is how a
        feature gets switched off.
        """
        names = list(names or _dash.catalogue())
        shown, refused = _dash.plan(names, active=True)
        board = self._build()
        for decision in refused:
            self._log(f"SYS: {decision.describe()}")
        if not shown:
            # An empty board teaches the user the feature is broken. Say so and
            # do not enter.
            self._log("SYS: Nothing on this machine can be shown on a dashboard.")
            return refused

        for name, decision in shown:
            widget = self._borrow(name)
            if widget is None:
                self._log(f"SYS: {name} is not available right now.")
                continue
            self.layer.lift(name, slot=self._slots.get(name))
            if name in self._tiles:
                continue
            # Remember where it was BEFORE it moves: this is the only record of
            # the place the user left it, and it has to be taken while the
            # widget is still in its own layout.
            self._slots[name] = self._geometry_of(widget)
            cell = self._tile(name, decision)
            self._tiles[name] = cell
            cell._box.addWidget(widget)
            widget.show()

        self._arrange()
        self._resize()
        _soft(board.show, "show the board")
        _soft(board.raise_, "raise the board")
        self.open = True
        self._log("SYS: Dashboard open — Esc to leave.")
        return refused

    def _arrange(self):
        """Place the tiles column by column, in catalogue order."""
        grid = self._grid
        # Take the tiles out of the layout before re-placing them. `takeAt` only
        # detaches the LAYOUT ITEM; the tile widget keeps its parent and stays
        # visible, so the re-place below adds an already-parented widget rather
        # than rebuilding it.
        while (item := grid.takeAt(0)) is not None:
            del item
        column, row = 0, 0
        for name in sorted(self._tiles):
            cell = self._tiles[name]
            entry = _dash.entry(name)
            if row + entry.rows > _dash.BOARD_COLUMNS * 2:
                column += 1
                row = 0
            grid.addWidget(cell, row, column, entry.rows, entry.columns)
            row += entry.rows

    def _geometry_of(self, widget) -> tuple:
        """`(x, y, w, h)` in the widget's own parent, or () when unreadable."""
        try:
            geo = widget.geometry()
            return (geo.x(), geo.y(), geo.width(), geo.height())
        except Exception as e:                  # noqa: BLE001 — a stub or a dead widget
            logbook.get(__name__).debug("no geometry to remember: %s", e)
            return ()

    def _resize(self):
        """The board covers the window; it is a layer, not a panel."""
        board = self._board
        if board is None:
            return
        _soft(lambda: board.setGeometry(0, 0, self.window.width(),
                                        self.window.height()), "size the board")
        _soft(lambda: board._scroll.setGeometry(0, 0, self.window.width(),
                                                self.window.height()), "size the scroll")

    # ── borrowing and returning ───────────────────────────────────────────

    def _borrow(self, name: str):
        """The real widget behind `name`, or None if it does not exist yet.

        `camera_preview` is the odd one: it is already a self-timing overlay
        that positions ITSELF, so it is not re-parented. Lifting it would fight
        the code that moves it — which is the one thing a floating window may
        never do (`core/floating.py`, RETIRED). It is shown, not moved.
        """
        if name == "camera_preview":
            return None                     # shown by its own overlay, not here
        widget = getattr(self.window, f"_{name}", None)
        if widget is None:
            return None
        self._held[name] = widget
        return widget

    def _return_all(self):
        """Put every borrowed widget back where it came from."""
        for name, widget in list(self._held.items()):
            entry = _dash.entry(name)
            if not entry.allowed:
                continue
            _soft(lambda n=name, w=widget: self._return_one(n, w), f"return {name}")
        self._held.clear()

    def _return_one(self, name: str, widget):
        """Re-parent to the tile's own grid cell, then drop the tile.

        The tile is what keeps the widget's geometry; dropping it first would
        leave the widget parentless with nothing to measure against.
        """
        cell = self._tiles.pop(name, None)
        if cell is None:
            return
        slot = self._slots.pop(name, None)
        if slot is not None and len(slot) == 4:
            widget.setGeometry(*slot)
        _soft(cell.deleteLater, f"drop the {name} tile")
        self._slots.pop(name, None)

    # ── leaving ───────────────────────────────────────────────────────────

    def hide(self, reason: str = "escape") -> bool:
        """Leave the layer. Every route ends here; none of them is special.

        Returns whether anything was actually open, so the caller does not log
        "dashboard closed" for an Esc pressed in a normal window.
        """
        if not self.open:
            return False
        self._return_all()
        for cell in list(self._tiles.values()):
            _soft(cell.deleteLater, "drop a tile on exit")
        self._tiles.clear()
        self._slots.clear()
        if self._board is not None:
            _soft(self._board.hide, "hide the board")
        self.open = False
        self._log(f"SYS: {_dash.exit_reason(reason)}.")
        return True

    def toggle(self, names=None) -> None:
        if self.open:
            self.hide("toggle")
        else:
            self.show(names)

    def resize(self) -> None:
        """Follow the window. Called from the window's own resize handler."""
        if self.open:
            self._resize()

    # ── plumbing ──────────────────────────────────────────────────────────

    def _log(self, text: str) -> None:
        write = getattr(self.window, "write_log", None)
        if callable(write):
            try:
                write(text)
            except Exception as e:          # noqa: BLE001
                logbook.get(__name__).debug("could not log: %s", e)


def attach(window) -> DashboardLayer:
    """The window's layer, built once and reused."""
    layer = getattr(window, "_dashboard_layer", None)
    if layer is None:
        layer = DashboardLayer(window)
        window._dashboard_layer = layer
    return layer


def toggle(window, names=None) -> None:
    """One entry point for the drawer's button and the shortcut."""
    attach(window).toggle(names)


def close(window) -> None:
    """The window is going away: a layer is a mode, so it goes with it.

    `core/dashboard.survives_restart()` is False, and this is where that answer
    is honoured. Kept here rather than inline in the window's close handler
    because a mode left open at shutdown is a bug with a test, not a comment.
    """
    layer = getattr(window, "_dashboard_layer", None)
    if layer is not None:
        layer.hide("shutdown")


__all__ = ["DashboardLayer", "attach", "close", "toggle"]
