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

import queue
import threading


class PanelTarget:
    """The panel's current selection: one memory, and one set of search hits."""

    def __init__(self) -> None:
        self._target: tuple[str, str] = ("", "")
        self._hits: tuple = ()
        self._search_status = "idle"
        self._search_generation = 0
        self._search_lock = threading.Lock()
        self._search_pending = None
        self._search_running_cancel = None
        self._search_worker = None
        self._search_results = queue.SimpleQueue()

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

    def open_memory_id(self, category: str, key: str) -> bool:
        """Open a memory the row already identified — no index involved.

        WHY THIS EXISTS BESIDE `open_memory(index)`. The index version does the
        right thing, but it has to re-read the store and resolve a position
        that the click did not actually name: between the paint and the click,
        one deletion above the row moves every row under it. A row built by
        `pages_memory.populate_memory` already carries `(category, key)`, so
        this path resolves nothing and cannot land on the wrong memory.

        The index version stays because other callers and one test still use
        it; the scrolling list uses this one.
        """
        identity = (str(category or ""), str(key or ""))
        if not identity[1]:
            return False
        self._target = identity
        return True

    def clear(self) -> None:
        """Forget the selection. Named so a page switch can call it deliberately
        rather than reaching into `_target`."""
        self._target = ("", "")

    # ── board 12 ─────────────────────────────────────────────────────────────

    @property
    def hits(self) -> tuple:
        """The last search's results, newest search whole. Empty before one."""
        return self._hits

    @property
    def search_status(self) -> str:
        return self._search_status

    @property
    def search_worker_running(self) -> bool:
        with self._search_lock:
            return self._search_worker is not None

    def cancel_search(self) -> None:
        """Invalidate in-flight results without waiting for filesystem calls."""
        self._search_generation += 1
        self._hits = ()
        self._search_status = "idle"
        with self._search_lock:
            self._search_pending = None
            if self._search_running_cancel is not None:
                self._search_running_cancel.set()

    def start_search(self, query: str) -> bool:
        """Queue the newest search; at most one filesystem worker per panel."""
        self.cancel_search()
        text = str(query or "")
        if not any(len(word) > 2 for word in text.split()):
            self._search_status = "invalid"
            return False
        self._search_status = "searching"
        cancel = threading.Event()
        with self._search_lock:
            self._search_pending = (self._search_generation, text, cancel)
            if self._search_worker is None:
                worker = threading.Thread(target=self._search_loop, daemon=True,
                                          name="panel-file-search")
                self._search_worker = worker
                try:
                    worker.start()
                except Exception:  # thread creation failed, no work was started
                    self._search_worker = None
                    self._search_pending = None
                    self._search_status = "error"
                    return False
        return True

    def _search_loop(self) -> None:
        """Background-only: no widget access, and pending searches coalesce."""
        while True:
            with self._search_lock:
                job = self._search_pending
                self._search_pending = None
                if job is None:
                    self._search_running_cancel = None
                    self._search_worker = None
                    return
                generation, query, cancel = job
                self._search_running_cancel = cancel
            try:
                from ui import pages_people
                hits = tuple(pages_people.find_files(query, cancel=cancel.is_set))
                status = "done"
            except Exception:  # inaccessible filesystem is not an empty result
                hits, status = (), "error"
            if not cancel.is_set():
                self._search_results.put((generation, status, hits))

    def poll_search(self) -> bool:
        """Apply completed work on the caller's UI thread; ignore stale jobs."""
        changed = False
        while True:
            try:
                generation, status, hits = self._search_results.get_nowait()
            except queue.Empty:
                return changed
            if generation == self._search_generation and self._search_status == "searching":
                self._hits, self._search_status = hits, status
                changed = True


class PanelSearchMixin:
    """Qt-thread control of the panel search timer and display state."""

    def run_search(self, query: str) -> bool:
        """Start a bounded background search; results arrive through the Qt timer."""
        started = self._view.start_search(query)
        if started and getattr(self, "_search_timer", None) is not None:
            self._search_timer.start()
        self.refresh()
        return started

    def poll_search(self) -> None:
        if self._view.poll_search():
            self.refresh()
        if self._view.search_status != "searching":
            self._search_timer.stop()

    def invalidate_search(self) -> None:
        if self._view.search_status != "idle":
            self._view.cancel_search()
            self._search_timer.stop()
            self.refresh()

    @property
    def search_status(self) -> str:
        return self._view.search_status

    @property
    def hits(self) -> tuple:
        """The last search's results, for `pages_paint.paint_tools`."""
        return self._view.hits


__all__ = ["PanelTarget"]
