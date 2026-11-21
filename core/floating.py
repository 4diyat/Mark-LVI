"""Floating widgets — what a widget may become when it leaves this window.

WHY THIS IS A SEPARATE MODULE AND NOT FOUR LINES IN `ui/window.py`
    `ui/window.py` is at its ceiling (`tests/test_ui_split.py`), and more to the
    point: "can this widget float" is a question with an answer that does not
    need a display. The three rules below are strings, integers and a decision
    about a platform — they can be tested on a machine with no Qt at all, which
    is what every CI runner is. `ui/floating_window.py` does the Qt part and is
    a thin wrapper around this.

THE THREE RULES, AND WHY EACH ONE EXISTS

    1. ONLY A WIDGET THAT CAN LEAVE CAN LEAVE.
       A `QWidget` has exactly ONE parent. Moving a widget out of the window is
       not "showing it again somewhere else": it is a re-parent, and the layout
       that used to hold it will report an empty cell where it was. So a widget
       that is the only thing in a panel, or that the window reads back (a
       drawer anchored to a button, the conversation itself), cannot float.
       `FLOATABLE` names the ones that can, and the reason each one is NOT in
       it is written down rather than left to be rediscovered.

    2. ON WAYLAND IT FLOATS, BUT IT IS NOT ALWAYS ON TOP — AND IT SAYS SO.
       Wayland deliberately gives a client no way to position its own top-level
       window and no always-on-top. Qt's `WindowStaysOnTopHint` is accepted and
       then ignored by the compositor. A floating widget there is a normal
       window that may be covered. This module does not pretend otherwise: it
       returns a `Fit` with `always_on_top=False` and a sentence explaining
       why, because the failure mode this project keeps designing against is an
       interface that claims something it did not observe.

    3. THE WINDOW REMEMBERS WHERE IT WAS, AND FORGETS WHEN ASKED.
       A floating widget that reappears in the top-left corner every launch is
       worse than one that stays docked. Positions are stored per widget name,
       clamped into the visible area on the way out (a monitor that was
       unplugged must not take the widget with it), and `forget()` exists so a
       user who moved something to a strange place has a way back.

WHAT THIS MODULE DOES NOT DO
    It does not touch Qt, create a window, or move anything. `fit()` decides;
    `ui/floating_window.py` acts.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# ── the catalogue ─────────────────────────────────────────────────────────
#
# The answer to "can this float" is a deliberate list, not a rule applied to
# whatever happens to be a QWidget today. A widget gets added here when its
# parentless behaviour has been thought about; it does not get here by being
# convenient.
FLOATABLE = {
    "speech_caption": "captions of what the assistant is saying, read-only",
    "metric_bar": "CPU/memory/network readout, read-only",
    "camera_preview": "live camera panel, already has its own lease",
    "hud": "the avatar itself, already floating in ui/face_bubble.py",
}

# Explicitly not floatable, with the reason. This table is the interesting half:
# every entry is a way the feature would have broken something.
NOT_FLOATABLE = {
    "drawer": "anchored to its header button through mapTo(); as a window it "
              "has nothing to anchor to and would open at a random place",
    "setup_drawer": "same anchoring problem, and its rows are config the window "
                    "reads back on every translation pass",
    "conversation": "the primary surface: a frameless 300px chat with no resize "
                    "is worse than the window it came from",
    "input_row": "typing box for the conversation above it; the two cannot be "
                 "split across surfaces without becoming two conversations",
    "order_dialog": "an application-modal LIVE acknowledgement. Making a "
                    "confirmation float over other apps is how somebody "
                    "approves an order they did not see",
}


@dataclass(frozen=True)
class Fit:
    """Whether one widget may float here, and what that will actually mean."""

    allowed: bool
    reason: str = ""
    always_on_top: bool = True
    frameless: bool = True
    note: str = ""                      # shown to the user when it matters

    def describe(self) -> str:
        """One line for the drawer or the log."""
        if not self.allowed:
            return f"cannot float: {self.reason}"
        if self.note:
            return f"floating — {self.note}"
        return "floating, always on top"


def platform_note(os_name: str, session: str = "") -> tuple[bool, str]:
    """`(always_on_top, note)` for this platform.

    `session` is `core/platform_support._linux_session()`: "wayland", "x11" or
    "". Passed in rather than re-detected so this stays a pure function.
    """
    os_name = (os_name or "").strip().lower()
    if os_name == "linux" and (session or "").strip().lower() == "wayland":
        return (False,
                "this is a Wayland session, which does not let a program keep "
                "its own window above others — it will float, but another "
                "window can cover it")
    if os_name == "darwin":
        return (True,
                "on macOS it will also appear on every Space, including over "
                "full-screen apps, unless the system refuses the collection "
                "behaviour")
    if os_name == "windows":
        return (True,
                "on Windows an exclusive-fullscreen game hides it, which is "
                "the system's rule and not something this program can change")
    return (True, "")


def fit(name: str, os_name: str = "", session: str = "") -> Fit:
    """May `name` float on this machine? A refusal is a sentence."""
    name = (name or "").strip().lower()
    if name in NOT_FLOATABLE:
        return Fit(allowed=False, reason=NOT_FLOATABLE[name])
    if name not in FLOATABLE:
        # Unknown names are refused rather than allowed: a plugin asking for a
        # capability that was never reviewed should not get one by default.
        return Fit(allowed=False,
                   reason=f"'{name}' is not a widget this program can float")

    on_top, note = platform_note(os_name, session)
    return Fit(allowed=True, always_on_top=on_top, note=note)


# ── where it goes ─────────────────────────────────────────────────────────

# Kept small on purpose: this is a position on a screen, and a widget that
# lands deliberately 12 pixels from the corner is easier to explain than one
# that lands wherever the last resize left it.
_MARGIN = 24


def clamp(x: int, y: int, width: int, height: int,
          screen_w: int, screen_h: int, margin: int = _MARGIN) -> tuple[int, int]:
    """Keep a floating window on screen, whatever was saved last time.

    A monitor that was unplugged — or a laptop that came back with a different
    resolution — must not take the widget with it. The rule is that at least a
    corner of the window stays reachable, not that it lands somewhere pretty.
    """
    try:
        x, y = int(x), int(y)
        width, height = max(1, int(width)), max(1, int(height))
        screen_w, screen_h = max(1, int(screen_w)), max(1, int(screen_h))
    except (TypeError, ValueError):
        return margin, margin

    # The window may be WIDER than the screen (a small laptop, a large saved
    # size): then pin it to the left/top rather than to a negative corner.
    max_x = max(margin, screen_w - width - margin) if width < screen_w else margin
    max_y = max(margin, screen_h - height - margin) if height < screen_h else margin
    return (min(max(x, margin), max_x), min(max(y, margin), max_y))


@dataclass(frozen=True)
class Placement:
    """Where a widget sits, and whether that was its own choice."""

    x: int
    y: int
    width: int
    height: int
    stored: bool = False                # True when it came from the config
    adjusted: bool = False              # True when `clamp` moved it

    def as_dict(self) -> dict:
        return {"x": self.x, "y": self.y, "width": self.width, "height": self.height}


def place(saved: dict | None, default: tuple[int, int, int, int],
          screen: tuple[int, int]) -> Placement:
    """Work out where to put a widget from its saved geometry.

    `saved` is whatever came out of the config file, which means it is
    whatever somebody edited by hand last week: every field is read defensively
    and a broken record falls back to the default rather than raising into the
    Qt thread.
    """
    dx, dy, dw, dh = default
    screen_w, screen_h = screen

    if not isinstance(saved, dict):
        x, y = clamp(dx, dy, dw, dh, screen_w, screen_h)
        return Placement(x, y, dw, dh, stored=False,
                         adjusted=(x, y) != (dx, dy))

    def _num(key: str, fallback: int) -> int:
        try:
            return int(float(saved.get(key, fallback)))
        except (TypeError, ValueError):
            return fallback

    width = max(120, min(_num("width", dw), screen_w))
    height = max(80, min(_num("height", dh), screen_h))
    x, y = clamp(_num("x", dx), _num("y", dy), width, height, screen_w, screen_h)
    return Placement(x, y, width, height, stored=True,
                     adjusted=(x, y) != (_num("x", dx), _num("y", dy)))


# ── which widgets are floating, right now ─────────────────────────────────

@dataclass
class State:
    """The set of widgets currently floating. One per process.

    A plain object rather than module-level globals so a test can make its own
    and the window can hold one, the way `ui/metrics` holds its sampler.
    """

    floating: dict = field(default_factory=dict)    # name -> Placement

    def is_floating(self, name: str) -> bool:
        return (name or "").lower() in self.floating

    def add(self, name: str, placement: Placement) -> None:
        self.floating[(name or "").lower()] = placement

    def remove(self, name: str) -> None:
        self.floating.pop((name or "").lower(), None)

    def forget(self, name: str | None = None) -> None:
        if name is None:
            self.floating.clear()
        else:
            self.remove(name)

    def names(self) -> list[str]:
        return sorted(self.floating)


__all__ = ["FLOATABLE", "NOT_FLOATABLE", "Fit", "Placement", "State",
           "clamp", "fit", "place", "platform_note"]
