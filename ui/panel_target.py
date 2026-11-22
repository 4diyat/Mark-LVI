"""What the last click in the panel chose: board 10's memory, board 12's hits.

WHY THIS IS ITS OWN MODULE
    Twice now the tray panel has crossed the 600-line ceiling, and both times
    the lines that pushed it over were not lifecycle — they were "remember what
    the user just picked". That is view state: it belongs to a page, it is
    cleared by a page switch, and none of it needs to know how a window opens.

    Extracting it is also what makes it testable without a window: every rule
    below is plain Python, and the two that are subtle (a target is a PAIR, and a
    search refreshes the panel) are tested directly.

THE ONE RULE THAT MATTERS
    A memory is identified by `(category, key)` and never by its position in a
    list. `memory_manager.all_entries_for_ui()` re-sorts newest-first on every
    read, so an index into it points at a different memory the moment one above
    it is deleted — and the "Lupakan" button would then delete something the
    user never opened. An index is resolved HERE, once, at click time.
"""
from __future__ import annotations


class PanelTarget:
    """The panel's current selection: one memory, and one set of search hits."""

    def __init__(self) -> None:
        self._target: tuple[str, str] = ("", "")
        self._hits: tuple = ()

    # ── board 10 ─────────────────────────────────────────────────────────────

    @property
    def target(self) -> tuple[str, str]:
        """The `(category, key)` the memory detail page is showing."""
        return self._target

    def open_memory(self, index: int) -> bool:
        """Resolve a row index to a memory identity. False if the row is gone.

        THE INDEX IS RESOLVED HERE AND NOT KEPT. `pages_memory.entries()` is
        re-read at this moment and the `(category, key)` at that index is what
        is remembered; keeping the index would mean the detail page showed
        whatever had moved into that slot by the time it painted.
        """
        from ui import pages_memory

        rows = pages_memory.entries()
        try:
            row = rows[int(index)]
        except (IndexError, TypeError, ValueError):
            return False
        self._target = (str(row.get("category") or ""), str(row.get("key") or ""))
        return bool(self._target[1])

    def clear(self) -> None:
        """Forget the selection. Named so a page switch can call it deliberately
        rather than reaching into `_target`."""
        self._target = ("", "")

    # ── board 12 ─────────────────────────────────────────────────────────────

    @property
    def hits(self) -> tuple:
        """The last search's results, newest search whole. Empty before one."""
        return self._hits

    def run_search(self, query: str, refresh=None) -> int:
        """Run board 12's file search and count the hits.

        `refresh` IS CALLED AND NOT ASSUMED. The search field's text does not
        change, so nothing would repaint the page on its own: a panel that
        stored the hits and did not repaint would show the PREVIOUS search's
        files under the words the user just typed. That is the bug this
        parameter exists to make impossible.
        """
        from ui import pages_people

        self._hits = tuple(pages_people.find_files(str(query)))
        if refresh is not None:
            refresh()
        return len(self._hits)


__all__ = ["PanelTarget"]
