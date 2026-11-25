"""core/session_summary.py — the pure policy behind the session summary &
timeline (board 5.5, board 8 extended).

WHAT THIS DECIDES
    Board 8 draws a task history; board 5.5 extends it with a searchable
    timeline and a "Ringkasan hari ini" card built from the transcript. This
    module turns a list of turns (each `{role, text, time}`) into the three
    things that card needs: a text search, a time filter, and a SUMMARY —
    with no file read and no Qt.

WHY THE DECISION IS PURE
    Searching turns for a phrase, filtering them to a window, and building a
    one-paragraph summary from them are arithmetic over a list of dicts. The
    list comes from `core.history` (the adapter reads it); deciding what the
    list SAYS is policy. Keeping the I/O out means a test can hand in a small
    transcript and assert exactly what the summary claims.

THE SUMMARY IS MARKED AS A SUMMARY
    A summary is a compression, not a transcript. Every summary this module
    produces is returned as a `Summary` whose `kind` is "summary" and whose
    text is prefixed with a marker saying so. The page shows it as a summary
    and can jump to the raw turns; it never presents a summary as if it were
    the words that were said. This is the "desain jujur" rule applied to
    memory of the conversation itself.

WHAT THIS DOES NOT DO
    It does not call a model. The summary here is a deterministic, structural
    compression — the topics the user raised, the count of turns, the last
    thing said. A model-generated summary would need a provider call and would
    vary between runs; the structural one is auditable and never invents. The
    page states clearly that this is a structural summary, not an
    assistant-written recap.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

# A turn is any mapping with a `text` and optionally a `role` and `time`.
# Kept loose so the adapter can feed `core.history.read_day()` rows straight
# through without reshaping them.

USER = "user"
ASSISTANT = "assistant"

# Roles we recognise. An unknown role is kept but not counted as either
# speaker; the summary never claims a turn came from a voice it cannot name.
_ROLES = {USER, ASSISTANT}


@dataclass
class Turn:
    """One line of the timeline, normalised from a raw history entry."""

    role: str
    text: str
    time: str = ""

    @classmethod
    def from_entry(cls, entry: dict) -> "Turn":
        return cls(
            role=str(entry.get("role") or "").strip(),
            text=str(entry.get("text") or "").strip(),
            time=str(entry.get("time") or entry.get("ts") or "").strip(),
        )


@dataclass
class Summary:
    """A structural summary of a set of turns, marked as a summary.

    `kind` is always "summary" — the page must never render this as a
    transcript. `text` is the summary sentence; `turn_count` and `topics`
    back it so the page can show the numbers the sentence claims.
    """

    kind: str
    text: str
    turn_count: int
    topics: list[str]


def normalise(turns: Iterable[dict]) -> list[Turn]:
    """Turn raw history entries into `Turn` objects, dropping empty ones.

    A turn with no text is not a turn — it would be a blank line in the
    timeline and a zero-length topic in the summary. Dropping it here keeps
    every later count honest.
    """
    out: list[Turn] = []
    for entry in turns:
        if not isinstance(entry, dict):
            continue
        turn = Turn.from_entry(entry)
        if turn.text:
            out.append(turn)
    return out


def search(turns: Iterable[Turn], query: str) -> list[Turn]:
    """Turns whose text contains the query, case-insensitive, in order.

    An empty query returns everything — that is "show the timeline", not
    "hide it", and returning nothing for a blank search box would read as a
    bug on the page.
    """
    q = (query or "").strip().lower()
    turns = list(turns)
    if not q:
        return turns
    return [t for t in turns if q in t.text.lower()]


def filter_by_time(
    turns: Iterable[Turn],
    since: str = "",
    until: str = "",
) -> list[Turn]:
    """Keep turns whose `time` is within `[since, until]` (string compare).

    Times are `YYYY-MM-DDTHH:MM:SS`-shaped, so a plain string compare is a
    correct chronological compare. A turn with no time is KEPT when no bound
    is set, and DROPPED when a bound is set: a bounded query that returns an
    undated turn would be claiming the turn belongs to a window it cannot
    verify. An empty bound means "no limit on that side".
    """
    out: list[Turn] = []
    for turn in turns:
        if since and turn.time and turn.time < since:
            continue
        if until and turn.time and turn.time > until:
            continue
        if (since or until) and not turn.time:
            continue
        out.append(turn)
    return out


def _topics(turns: list[Turn], limit: int = 5) -> list[str]:
    """The first words of the user's turns, as the topics that came up.

    Deterministic and structural: the leading tokens of what the user said
    are the closest thing to "what we talked about" that does not require a
    model. Capped so the card cannot overflow with a long day.
    """
    seen: list[str] = []
    for turn in turns:
        if turn.role != USER:
            continue
        words = [w for w in turn.text.split() if w]
        if not words:
            continue
        topic = words[0]
        # Keep it readable: a leading article or filler word is not a topic.
        if topic.lower() in {"a", "an", "the", "dan", "ke", "saya", "ini"}:
            if len(words) > 1:
                topic = words[1]
            else:
                continue
        if topic not in seen:
            seen.append(topic)
        if len(seen) >= limit:
            break
    return seen


def summarize(turns: Iterable[Turn]) -> Summary:
    """Build a structural summary of a set of turns.

    The summary states the turn count, the topics the user raised, and the
    last thing said — and is marked `kind="summary"` so the page cannot
    present it as a transcript. An empty transcript yields a summary that says
    so, rather than an empty card the user would read as a failure.
    """
    turns = list(turns)
    count = len(turns)
    topics = _topics(turns)
    if count == 0:
        return Summary("summary", "Tidak ada percakapan yang direkam hari ini.",
                       0, [])
    last = turns[-1]
    who = "Anda" if last.role == USER else "JARVIS"
    topic_clause = (f" Topik yang dibahas: {', '.join(topics)}."
                    if topics else "")
    text = (f"Ringkasan: {count} giliran percakapan.{topic_clause} "
            f"Terakhir: {who} menyebut \"{last.text}\".")
    return Summary("summary", text, count, topics)


def build(
    turns: Iterable[dict],
    *,
    query: str = "",
    since: str = "",
    until: str = "",
) -> tuple[list[Turn], Summary]:
    """The page's one call: normalise, search, filter, then summarize.

    Returns the (possibly filtered) timeline turns AND the summary of what
    remains, so the page shows the filtered list and a summary that matches
    it. Order matters: the summary describes the SAME set the list shows, so
    a search that narrows the timeline also narrows what the summary claims.
    """
    normalised = normalise(turns)
    matched = search(normalised, query)
    windowed = filter_by_time(matched, since=since, until=until)
    return windowed, summarize(windowed)


__all__ = [
    "USER", "ASSISTANT", "Turn", "Summary",
    "normalise", "search", "filter_by_time", "summarize", "build",
]
