"""ORB — the Opening Range Breakout, computed from closed M30 bars.

WHAT THE STRATEGY IS, IN ONE PARAGRAPH
    The first hours of a session set a range: the high and the low that price
    made while the market was deciding what the day is about. A break of that
    range afterwards is the classic signal — buyers or sellers took the other
    side's stops, and the range becomes support or resistance. On M30 there are
    six bars in a four-hour session window, so a "session range" is the high and
    low of those bars, and a breakout is a CLOSE beyond it.

WHY "CLOSE BEYOND", AND NOT "TOUCHED"
    A wick through the range high is noise (a stop hunt, a spread widening at
    the open). A bar that closes beyond it is a decision that survived thirty
    minutes. Every false breakout this module refuses to call is one the user
    would otherwise have traded.

THE FOUR ASSUMPTIONS, AND WHY EACH ONE IS VISIBLE IN THE ANSWER
    A trading answer that is confidently wrong is worse than no answer, and each
    of the following can make it wrong:

    1. BAR TIME IS THE BROKER'S. MetaTrader hands out bar timestamps in the
       broker server's time zone, and most FX brokers run GMT+2/GMT+3 (with
       daylight saving). Comparing those stamps against a UTC session clock is
       off by two or three hours — so the offset is an argument, the default is
       stated, and the summary repeats it.
    2. THE SESSION WINDOW IS A CONVENTION. London 07:00-11:00 UTC and New York
       12:00-16:00 UTC are the windows used here; a user trading the Tokyo open
       or a broker's own session needs a different one. The window that was
       actually used is printed with every result.
    3. M30 HAS ENOUGH BUT NOT MUCH. Six bars per window: enough for a range,
       too few for anything statistical. There is no probability claim here, on
       purpose — this app should not invent an edge.
    4. HISTORY IS CAPPED BY THE TERMINAL. If only 200 bars are available, only
       the most recent sessions can be scanned; `sessions_scanned` says how many
       were actually examined rather than implying more.

WHAT THIS MODULE DOES NOT DO
    It does not predict. It reports a range, whether price closed beyond it, on
    what bar, how far, and what would invalidate the idea. That is the part a
    person can check; the rest is their decision.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

# Session windows, in UTC, as (name, start hour, end hour). End is exclusive.
# These are the two liquid FX windows; Tokyo is included because a user in
# Jakarta may well be trading it, and an empty answer would be worse than a
# short one.
SESSIONS: dict[str, tuple[int, int]] = {
    "london": (7, 11),
    "newyork": (12, 16),
    "tokyo": (0, 4),
}

# The default broker offset. Most FX brokers run GMT+2 in winter and GMT+3 in
# summer; the parameter is in hours relative to UTC and is applied to the bar
# timestamps before anything is bucketed into a session.
DEFAULT_BROKER_UTC_OFFSET_H = 2


@dataclass
class Range:
    """One session's opening range."""
    session: str
    day: str                  # YYYY-MM-DD in UTC, after the offset is applied
    high: float
    low: float
    bars: int
    start: datetime
    end: datetime

    @property
    def size(self) -> float:
        return self.high - self.low

    @property
    def mid(self) -> float:
        return (self.high + self.low) / 2.0


@dataclass
class Breakout:
    direction: str            # "up" | "down"
    bar_time: datetime        # UTC, offset already applied
    close: float
    distance: float           # how far beyond the range, in price
    bars_after_range: int


@dataclass
class Analysis:
    symbol: str
    timeframe: str
    range: Range | None = None
    breakout: Breakout | None = None
    sessions_scanned: int = 0
    bars_used: int = 0
    last_close: float = 0.0
    last_bar_time: datetime | None = None
    offset_hours: int = DEFAULT_BROKER_UTC_OFFSET_H
    notes: list[str] = field(default_factory=list)

    @property
    def state(self) -> str:
        """One of: no-range, inside, broke-up, broke-down, beyond."""
        if self.range is None:
            return "no-range"
        if self.breakout is None:
            return "inside"
        return "broke-up" if self.breakout.direction == "up" else "broke-down"


def _utc(epoch: int, offset_hours: int) -> datetime:
    """Broker time → UTC. The bars are actually stamped in the broker's zone, so
    subtracting the offset is what makes '07:00' mean seven in the morning."""
    return datetime.fromtimestamp(epoch, tz=timezone.utc) - timedelta(hours=offset_hours)


def session_window(session: str) -> tuple[int, int]:
    key = (session or "").strip().lower().replace(" ", "").replace("-", "")
    if key in ("ny", "newyork", "us"):
        key = "newyork"
    if key not in SESSIONS:
        raise ValueError(
            f"Unknown session {session!r} — known ones are: "
            f"{', '.join(sorted(SESSIONS))} (also 'ny' and 'us' for New York).")
    return SESSIONS[key]


def opening_ranges(bars, session: str = "london", *, offset_hours: int = DEFAULT_BROKER_UTC_OFFSET_H,
                   days: int = 5) -> list[Range]:
    """The last `days` sessions' opening ranges, oldest first.

    A bar belongs to a session if its OPEN time, converted to UTC, falls inside
    the window. Bars straddling the end of the window are not clipped: M30 bars
    and a four-hour window line up exactly on the hour, which is why M30 is a
    reasonable choice for this strategy and M45 is not.
    """
    start_h, end_h = session_window(session)
    buckets: dict[str, list] = {}
    for bar in bars:
        when = _utc(bar.time, offset_hours)
        if not (start_h <= when.hour < end_h):
            continue
        buckets.setdefault(when.date().isoformat(), []).append((when, bar))

    out: list[Range] = []
    for day in sorted(buckets)[-days:]:
        rows = buckets[day]
        out.append(Range(
            session=session.strip().lower(),
            day=day,
            high=max(b.high for _, b in rows),
            low=min(b.low for _, b in rows),
            bars=len(rows),
            start=min(w for w, _ in rows),
            end=max(w for w, _ in rows),
        ))
    return out


def analyse(bars, symbol: str = "?", session: str = "london", *,
            offset_hours: int = DEFAULT_BROKER_UTC_OFFSET_H,
            timeframe: str = "M30") -> Analysis:
    """Range, breakout and the facts around them — never a prediction.

    The breakout is the FIRST closed bar after the range window that closes
    outside it. Later bars are not reported as "the breakout" even if they are
    further away: the interesting moment is when the range failed, not how far
    price has since travelled.
    """
    result = Analysis(symbol=symbol, timeframe=timeframe,
                      offset_hours=offset_hours, bars_used=len(bars))
    if not bars:
        result.notes.append("No bars were available at all.")
        return result

    result.last_close = float(bars[-1].close)
    result.last_bar_time = _utc(bars[-1].time, offset_hours)

    ranges = opening_ranges(bars, session, offset_hours=offset_hours, days=3)
    result.sessions_scanned = len(ranges)
    if not ranges:
        result.notes.append(
            f"No {session} session appears in the last {len(bars)} M30 bars. "
            "That either means the history is short — the terminal's 'Max. bars "
            "in chart' caps it — or the session window does not match the "
            f"broker's clock (assumed UTC{offset_hours:+d}).")
        return result

    # The most recent session that price has actually traded after. A range
    # from this morning with no bars since says nothing about a breakout; the
    # newest range that has at least one following bar is the live one.
    for candidate in reversed(ranges):
        after = [b for b in bars
                 if _utc(b.time, offset_hours) > candidate.end]
        if not after:
            continue
        result.range = candidate
        for index, bar in enumerate(after, start=1):
            if bar.close > candidate.high:
                result.breakout = Breakout("up", _utc(bar.time, offset_hours),
                                           float(bar.close),
                                           float(bar.close - candidate.high), index)
                break
            if bar.close < candidate.low:
                result.breakout = Breakout("down", _utc(bar.time, offset_hours),
                                           float(bar.close),
                                           float(candidate.low - bar.close), index)
                break
        break

    if result.range is None:
        # Every range is at the very end of the data: the current session is
        # still forming. That is worth saying rather than reporting "no signal".
        result.range = ranges[-1]
        result.notes.append(
            "The newest range is the session in progress, so there are no "
            "closed bars after it yet.")
    elif result.range.bars < 4:
        result.notes.append(
            f"Only {result.range.bars} of 8 M30 bars were present in the "
            "window — the range may be incomplete.")
    return result


def summary(analysis: Analysis) -> str:
    """The sentence a person hears. Facts, then what would invalidate them."""
    a = analysis
    head = f"{a.symbol} on {a.timeframe}"
    if a.range is None:
        return (f"{head}: {a.notes[0] if a.notes else 'no opening range found.'}")

    r = a.range
    lines = [
        f"{head}, {r.session.capitalize()} opening range {r.day} "
        f"({r.start:%H:%M}-{r.end:%H:%M} UTC, {r.bars} bars): "
        f"high {r.high:.5f}, low {r.low:.5f}, {r.size:.5f} wide."
    ]
    if a.breakout is None:
        where = ("above" if a.last_close > r.high else
                 "below" if a.last_close < r.low else "inside")
        lines.append(
            f"Price is {where} the range at {a.last_close:.5f} "
            f"({a.last_bar_time:%H:%M} UTC). No M30 bar has CLOSED outside it, "
            "so there is no breakout — a wick through the level is not one.")
    else:
        b = a.breakout
        side = "above the high" if b.direction == "up" else "below the low"
        lines.append(
            f"Breakout {b.direction.upper()}: the M30 bar closing {b.bar_time:%Y-%m-%d %H:%M} "
            f"UTC closed {side} at {b.close:.5f}, {b.distance:.5f} beyond it "
            f"({b.bars_after_range} bar(s) after the range).")
        edge = r.high if b.direction == "up" else r.low
        lines.append(
            f"The range {'high' if b.direction == 'up' else 'low'} {edge:.5f} is the "
            f"level that now has to hold. Invalidated by a close back inside the "
            f"range; the mid {r.mid:.5f} is the first place that would be "
            f"tested on the way.")

    lines.append(
        f"Assumes broker time is UTC{a.offset_hours:+d} and the "
        f"{r.session.capitalize()} window is {r.start:%H:%M}-{r.end:%H:%M} UTC; "
        f"{a.sessions_scanned} session(s) scanned from {a.bars_used} M30 bars. "
        "No probability is implied.")
    lines.extend(a.notes)
    return " ".join(lines)


def levels(analysis: Analysis) -> dict:
    """The numbers a chart is drawn with, so the table and the text agree."""
    if analysis.range is None:
        return {}
    r = analysis.range
    return {
        "high": r.high, "low": r.low, "mid": r.mid, "size": r.size,
        "session": r.session, "day": r.day,
        "state": analysis.state,
        "breakout_at": (analysis.breakout.bar_time.strftime("%Y-%m-%d %H:%M")
                        if analysis.breakout else ""),
        "breakout_close": analysis.breakout.close if analysis.breakout else 0.0,
    }


# ---------------------------------------------------------------------------
# The chart.
#
# WHY A PICTURE AND NOT JUST THE SENTENCE
#     An opening range is a shape: a tight box, then price leaving it. Reading
#     that from "high 1.08531, low 1.08322" is arithmetic; seeing it is
#     recognition. So the plugin draws the last day or so of M30 candles, shades
#     the window the range came from, and puts the two range levels across the
#     whole chart as lines. Everything drawn comes from the same `Analysis` the
#     sentence is built from, so the two cannot disagree.
#
# WHY TWO RENDERERS
#     Pillow is in requirements.txt, so the PNG is the normal path — it is a
#     file the user can open and zoom. If Pillow is missing on some install, the
#     chart degrades to text rather than the tool failing: an all-text answer is
#     worse than a picture and much better than an error.
# ---------------------------------------------------------------------------
def _candles(bars, analysis: Analysis, limit: int) -> list:
    """The bars worth drawing: from the session before the range to the end."""
    rows = list(bars)[-limit:]
    if analysis.range is not None:
        # Start a little before the range so the breakout has context.
        keep = [b for b in rows if _utc(b.time, analysis.offset_hours) >= analysis.range.start]
        if len(keep) > 3:
            return keep
    return rows


def render_text(bars, analysis: Analysis, *, width: int = 68, height: int = 16) -> str:
    """A candle chart you can read in a transcript. Rows are price, columns are
    time; '#' marks a candle body, '|' a wick, and H/L/M the range levels."""
    rows = _candles(bars, analysis, 80)
    if not rows:
        return "(no bars to draw)"
    lo = min(b.low for b in rows)
    hi = max(b.high for b in rows)
    if analysis.range is not None:
        lo, hi = min(lo, analysis.range.low), max(hi, analysis.range.high)
    span = (hi - lo) or 1e-9

    def row_of(price: float) -> int:
        return height - 1 - int((price - lo) / span * (height - 1))

    grid = [[" "] * width for _ in range(height)]
    column_of = [int(i * (width - 1) / max(len(rows) - 1, 1)) for i in range(len(rows))]

    def hline(price: float, ch: str) -> None:
        if lo <= price <= hi:
            r = row_of(price)
            for c in range(width):
                if grid[r][c] == " ":
                    grid[r][c] = ch

    if analysis.range is not None:
        hline(analysis.range.high, "H")
        hline(analysis.range.low, "L")
        hline(analysis.range.mid, "M")

    for i, bar in enumerate(rows):
        c = column_of[i]
        for price, ch in ((bar.high, "|"), (bar.low, "|")):
            r = row_of(price)
            if grid[r][c] == " ":
                grid[r][c] = ch
        top, bottom = row_of(max(bar.open, bar.close)), row_of(min(bar.open, bar.close))
        for r in range(top, bottom + 1):
            grid[r][c] = "#"

    if analysis.breakout is not None:
        idx = next((i for i, b in enumerate(rows)
                    if _utc(b.time, analysis.offset_hours) == analysis.breakout.bar_time), None)
        if idx is not None:
            c, r = column_of[idx], row_of(analysis.breakout.close)
            for rr in (r - 1, r + 1):
                if 0 <= rr < height and grid[rr][c] == " ":
                    grid[rr][c] = "^" if analysis.breakout.direction == "up" else "v"

    head = (f"{analysis.symbol} {analysis.timeframe}"
            + (f"  range {analysis.range.day} {analysis.range.session}"
               if analysis.range else ""))
    out = [head, f"{hi:>10.5f} " + "".join(grid[0])]
    for r in range(1, height - 1):
        out.append(f"{'':>10} " + "".join(grid[r]))
    out.append(f"{lo:<10.5f} " + "".join(grid[height - 1]))
    first = _utc(rows[0].time, analysis.offset_hours)
    last = _utc(rows[-1].time, analysis.offset_hours)
    out.append(f"{'':>10} {first:%m-%d %H:%M} → {last:%H:%M} UTC   "
               "H=range high  L=range low  M=mid  ^/v=closed breakout")
    return "\n".join(out)


def render_png(bars, analysis: Analysis, path) -> str:
    """Draw the same chart as a PNG. Returns the path, or raises ImportError when
    Pillow is not installed — the caller then uses render_text()."""
    from PIL import Image, ImageDraw  # noqa: PLC0415 — optional dependency

    rows = _candles(bars, analysis, 120)
    if not rows:
        raise ValueError("no bars to draw")

    pad_l, pad_r, pad_t, pad_b = 78, 22, 54, 46
    w, h = 1000, 560
    plot_w, plot_h = w - pad_l - pad_r, h - pad_t - pad_b
    lo = min(b.low for b in rows)
    hi = max(b.high for b in rows)
    if analysis.range is not None:
        lo, hi = min(lo, analysis.range.low), max(hi, analysis.range.high)
    pad = (hi - lo) * 0.06 or 0.0001
    lo, hi = lo - pad, hi + pad
    span = hi - lo

    img = Image.new("RGB", (w, h), "#11151c")
    draw = ImageDraw.Draw(img)

    def y(price: float) -> float:
        return pad_t + (hi - price) / span * plot_h

    def x(i: int) -> float:
        return pad_l + (i + 0.5) * plot_w / len(rows)

    for price in [hi - i * span / 8 for i in range(9)]:
        draw.line([(pad_l, y(price)), (w - pad_r, y(price))], fill="#232a35")
        draw.text((8, y(price) - 5), f"{price:.5f}", fill="#8b98a8")

    # The window the range was measured in, shaded, so "which bars" is visible.
    if analysis.range is not None:
        inside = [i for i, b in enumerate(rows)
                  if analysis.range.start <= _utc(b.time, analysis.offset_hours) <= analysis.range.end]
        if inside:
            draw.rectangle([x(inside[0]) - plot_w / len(rows) / 2, pad_t,
                            x(inside[-1]) + plot_w / len(rows) / 2, pad_t + plot_h],
                           fill="#1b2735")
            draw.text((x(inside[0]), pad_t - 16), f"{analysis.range.session} window",
                      fill="#5d7fa8")
        for price, colour in ((analysis.range.high, "#3fb950"),
                              (analysis.range.low, "#f85149"),
                              (analysis.range.mid, "#6e7681")):
            draw.line([(pad_l, y(price)), (w - pad_r, y(price))], fill=colour, width=2)
            draw.text((w - pad_r + 2, y(price) - 5), f"{price:.5f}", fill=colour)

    body_w = max(1.5, plot_w / len(rows) * 0.6)
    for i, bar in enumerate(rows):
        colour = "#3fb950" if bar.close >= bar.open else "#f85149"
        draw.line([(x(i), y(bar.high)), (x(i), y(bar.low))], fill=colour, width=1)
        top, bottom = y(max(bar.open, bar.close)), y(min(bar.open, bar.close))
        if bottom - top < 1:
            bottom = top + 1
        draw.rectangle([x(i) - body_w / 2, top, x(i) + body_w / 2, bottom], fill=colour)

    if analysis.breakout is not None:
        i = next((k for k, b in enumerate(rows)
                  if _utc(b.time, analysis.offset_hours) == analysis.breakout.bar_time), None)
        if i is not None:
            px, py = x(i), y(analysis.breakout.close)
            arrow = [(px, py - 14), (px - 7, py - 24), (px + 7, py - 24)]
            if analysis.breakout.direction == "down":
                arrow = [(px, py + 14), (px - 7, py + 24), (px + 7, py + 24)]
            draw.polygon(arrow, fill="#d29922")
            draw.text((pad_l + 6, pad_t + 6),
                      f"breakout {analysis.breakout.direction} "
                      f"@ {analysis.breakout.close:.5f} "
                      f"({analysis.breakout.bar_time:%Y-%m-%d %H:%M} UTC)",
                      fill="#d29922")

    title = f"{analysis.symbol} {analysis.timeframe} — market-session ORB"
    if analysis.range is not None:
        title += f" · {analysis.range.session.capitalize()} {analysis.range.day}"
    draw.text((pad_l, 16), title, fill="#e6edf3")
    draw.text((pad_l, 32),
              f"bars: {len(rows)} · broker time UTC{analysis.offset_hours:+d} · "
              f"levels from closed M30 bars only · no prediction",
              fill="#8b98a8")
    first, last = rows[0], rows[-1]
    draw.text((pad_l, h - pad_b + 10),
              f"{_utc(first.time, analysis.offset_hours):%Y-%m-%d %H:%M} → "
              f"{_utc(last.time, analysis.offset_hours):%H:%M} UTC "
              f"({len(rows)} × {analysis.timeframe} bars)",
              fill="#8b98a8")
    img.save(str(path), format="PNG")
    return str(path)
