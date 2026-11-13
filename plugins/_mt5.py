"""MetaTrader 5 access, in one place, with the limits stated up front.

WHY THIS IS A HELPER AND NOT PART OF THE PLUGIN
    Two plugins will want it (this one, and anything that prices a position), the
    `MetaTrader5` package is Windows-only, and the connection has to be opened
    and closed the same way every time. The loader skips files starting with an
    underscore, so this is not a tool — see AGENTS.md.

THE FOUR THINGS THAT MAKE MT5 DIFFERENT FROM "just an API"
    1. IT IS WINDOWS-ONLY. The PyPI package ships CPython wheels for Windows
       x86-64 and nothing else — there is no Linux or macOS build to install, so
       this cannot work on the machine the rest of this repository is developed
       on. Every function here raises `MT5Unavailable` with the reason, and the
       plugin turns that into a sentence instead of a traceback.

    2. IT IS A BRIDGE, NOT A SERVICE. `initialize()` attaches to a MetaTrader 5
       TERMINAL that is already running and logged in. Without the terminal
       there is no data, no matter how correct the Python is: the symbols, the
       history depth and the account all come from the terminal's own settings.
       "Max. bars in chart" in the terminal caps `copy_rates_from_pos`, which is
       why a 200-bar request can come back with 37 rows.

    3. TIME IS THE BROKER'S, NOT UTC. Bar timestamps arrive in the broker
       server's time zone, and most FX brokers run GMT+2 or GMT+3. An opening
       range computed by comparing those stamps to a UTC session clock is off by
       two or three hours — silently, and it still produces a confident answer.
       So the offset is a parameter, the answer states the assumption, and
       nothing here guesses a broker's time zone.

    4. POSITION 0 IS THE FORMING BAR. It has an open, a high so far, and a close
       that will move. Anything that decides whether a range was broken must use
       closed bars only, or a two-minute-old wick becomes a "breakout".

WHAT THIS MODULE DOES NOT DO
    It does not trade. There is no `order_send` here and there never will be:
    the confirmation gate in this app is built for reversible actions, and a
    market order is not one.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import NamedTuple


class MT5Unavailable(RuntimeError):
    """The package or the terminal is not there. Carries a sentence for a
    person, because it is spoken aloud rather than logged."""


class Bar(NamedTuple):
    """One M30 bar, in the order MT5 returns it."""
    time: int          # epoch seconds, in the BROKER's time zone (see above)
    open: float
    high: float
    low: float
    close: float
    tick_volume: int = 0


# Timeframe name → the constant's name in the package. Kept as strings so this
# module can be imported (and tested) on a machine with no MetaTrader5 at all.
TIMEFRAMES = ("M1", "M5", "M15", "M30", "H1", "H4", "D1", "W1")


def _module():
    """The package, or MT5Unavailable with a sentence that says which of the
    two problems it is — not installed, or installed on the wrong operating
    system, which are different fixes."""
    try:
        import MetaTrader5 as mt5  # noqa: PLC0415 — Windows-only, imported late
    except ImportError as e:
        # The two failures have different fixes, so the sentence says which one
        # this is: a Windows user needs `pip install MetaTrader5`, everybody
        # else needs a different machine.
        import platform
        if platform.system() == "Windows":
            why = ("the MetaTrader5 package is not installed "
                   "(pip install MetaTrader5)")
        else:
            why = (f"this is {platform.system()}, and the MetaTrader5 package "
                   "ships Windows wheels only")
        raise MT5Unavailable(f"MetaTrader 5 is not available here: {why} ({e}).") from e
    return mt5


@dataclass
class Session:
    """An open MT5 connection. Use as a context manager; it always shuts down,
    because a half-open bridge holds the terminal's IPC slot."""
    mt5: object
    terminal: str = ""

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False

    def close(self) -> None:
        try:
            self.mt5.shutdown()
        except Exception:
            # Shutting down a bridge that is already gone is the normal case
            # when the terminal was closed under us. Nothing to report.
            pass

    def select(self, symbol: str) -> None:
        """Make sure the broker actually offers this symbol.

        Brokers rename things — `EURUSD.a`, `XAUUSDm`, `EURUSD.pro` — and
        `copy_rates_from_pos` on an unselected symbol returns None rather than
        raising, which reads as "no data" when the truth is "no such symbol".
        """
        if not self.mt5.symbol_select(symbol, True):
            raise MT5Unavailable(
                f"Your broker's terminal does not offer a symbol called "
                f"{symbol!r}. Broker symbols often carry a suffix — check the "
                "Market Watch window for the exact name.")

    def symbol_info(self, symbol: str):
        info = self.mt5.symbol_info(symbol)
        if info is None:
            raise MT5Unavailable(f"No symbol information for {symbol!r}.")
        return info

    def bars(self, symbol: str, timeframe: str = "M30",
             count: int = 400, closed_only: bool = True) -> list[Bar]:
        """The most recent `count` bars, oldest first.

        `closed_only` skips the forming bar. It defaults to True because the
        common mistake on this API is a strategy reacting to a bar that has not
        finished — a "breakout" that is really a spike in a bar that still has
        twenty minutes to run.
        """
        tf_name = f"TIMEFRAME_{timeframe.upper()}"
        constant = getattr(self.mt5, tf_name, None)
        if constant is None:
            raise MT5Unavailable(f"No timeframe {timeframe!r} (expected one of "
                                 f"{', '.join(TIMEFRAMES)}).")
        start = 1 if closed_only else 0
        # One extra so a closed-only request still returns `count` rows.
        raw = self.mt5.copy_rates_from_pos(symbol, constant, start, count)
        if raw is None:
            raise MT5Unavailable(
                f"No bars came back for {symbol} ({self.mt5.last_error()}). "
                "The terminal's 'Max. bars in chart' limits how much history "
                "it will hand out.")
        rows = [Bar(int(r["time"]), float(r["open"]), float(r["high"]),
                    float(r["low"]), float(r["close"]),
                    int(r["tick_volume"]) if "tick_volume" in r.dtype.names else 0)
                for r in raw]
        if not rows:
            raise MT5Unavailable(f"The terminal returned zero bars for {symbol}.")
        return rows


def connect(timeout_ms: int = 60_000, portable: bool = False) -> Session:
    """Open the bridge to the running terminal.

    `portable` is MetaQuotes' flag for a terminal installed in portable mode —
    the one case where the data directory is not under the user's AppData. It
    is a parameter rather than a guess because guessing it wrong silently
    connects to a different terminal with different symbols.
    """
    mt5 = _module()
    if not mt5.initialize(timeout=timeout_ms, portable=portable):
        code = mt5.last_error()
        raise MT5Unavailable(
            "Could not attach to a MetaTrader 5 terminal "
            f"({code}). The terminal has to be running and logged in — the "
            "Python package is a bridge to it, not a data service of its own.")
    info = mt5.terminal_info()
    name = getattr(info, "name", "") if info is not None else ""
    return Session(mt5=mt5, terminal=str(name or ""))


def pip_size(symbol_info) -> float:
    """How much one 'pip' is worth for this symbol, from the terminal.

    Taken from the symbol rather than assumed: a 5-digit FX pair has a point of
    0.00001 and a pip of 0.0001, gold is quoted in cents, and an index has no
    meaningful pip at all. A hardcoded 0.0001 is how a 30-pip range becomes a
    3-pip one.
    """
    point = float(getattr(symbol_info, "point", 0.0) or 0.0)
    digits = int(getattr(symbol_info, "digits", 0) or 0)
    if point <= 0:
        return 0.0
    # Three and five digits are the fractional-pip convention: the pip is ten
    # points. Everything else quotes the pip at one point.
    return point * 10 if digits in (3, 5) else point
