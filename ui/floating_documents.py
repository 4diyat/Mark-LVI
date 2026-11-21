"""Which plugin documents are out on the desktop, and how they come back.

WHY THIS IS A SECOND PANEL AND NOT A FLAG ON `FloatingPanel`
    `ui/floating_panel.py` floats WIDGETS out of layouts, and its bookkeeping is
    a name, a `Dock` and a `Placement`. A document is a different object with a
    different lifetime: it is a `QMdiSubWindow` the MDI area owns, it is listed
    in `window._workspace_documents`, and it can be destroyed by Qt at any
    moment. Sharing one registry would mean one dict holding two shapes of
    thing, and every method asking which shape it had.

WHAT IT REMEMBERS, AND WHY EACH FIELD EARNS ITS PLACE
    sub        the subwindow itself, so recall can find it
    kind       what `fit_document` was asked about
    placement  where it was put, saved to the config on the way out AND back
    dock       the MDI area and the state it left in, so `recall` can undo it
    plugin     the manifest name, when there is one, for the revoke path

THE REVOKE PATH, WHICH IS THE INTERESTING ONE
    A floating document belongs to a plugin, and a plugin can be revoked while
    its window is on the desktop. Recommended behaviour, and what this file
    does: **recall it to the workspace using the document's own close path** —
    which means the unsaved-work veto still speaks — and only then let the
    revoke proceed. Hiding it quietly instead would leave a window the user can
    see and cannot explain, holding unsaved work that no dialog ever asked
    about; dropping it outright would destroy work to satisfy a menu action.
    When the document refuses to close, the revoke is refused too, and says why.
"""
from __future__ import annotations

from core import floating, logbook


class FloatingDocuments:
    """The window's side of floating plugin documents."""

    def __init__(self, window, os_name: str = "", session: str = ""):
        self._window = window
        from core import platform_support

        self._os_name = os_name or platform_support.os_name()
        self._session = session if os_name else platform_support._linux_session()
        self._open: dict = {}          # doc_id -> dict(sub=…, kind=…, …)

    # ── the question ──────────────────────────────────────────────────────

    def may_float(self, kind: str) -> floating.Fit:
        return floating.fit_document(kind, self._os_name, self._session)

    def is_floating(self, doc_id: str) -> bool:
        return doc_id in self._open

    def names(self) -> list[str]:
        return sorted(self._open)

    def kinds(self) -> list[str]:
        return sorted({entry["kind"] for entry in self._open.values()})

    def count(self) -> int:
        return len(self._open)

    # ── the act ───────────────────────────────────────────────────────────

    def toggle(self, doc_id: str, sub, kind: str, plugin: str = "") -> bool:
        """Float it if docked, recall it if floating. True = floating."""
        if doc_id in self._open:
            return not self.recall(doc_id)
        return self.float(doc_id, sub, kind, plugin)

    def float(self, doc_id: str, sub, kind: str, plugin: str = "") -> bool:
        """Take one document out onto the desktop. False when it may not."""
        if sub is None:
            return False
        if doc_id in self._open:
            return True                       # already out; not an error
        fit = self.may_float(kind)
        if not fit.allowed:
            self.say(fit.reason)
            return False
        try:
            from ui import floating_document

            placement = self._placement_for(doc_id, sub)
            dock = floating_document.detach(sub, _qt(), fit, placement)
        except Exception as e:              # noqa: BLE001 — a Qt edge
            logbook.get(__name__).warning("could not float %s: %s", doc_id, e)
            self.say(f"could not float {kind}")
            return False

        self._open[doc_id] = {"sub": sub, "kind": kind, "plugin": plugin,
                              "dock": dock, "placement": placement}
        self._remember(doc_id)
        if fit.note:
            self.say(f"{kind} is on the desktop — {fit.note}")
        return True

    def recall(self, doc_id: str) -> bool:
        """Bring it back into the workspace, at the state it left in."""
        entry = self._open.get(doc_id)
        if entry is None:
            return False
        self._remember(doc_id)
        try:
            from ui import floating_document

            floating_document.recall(entry["sub"], _qt(), entry["dock"])
        except Exception as e:              # noqa: BLE001
            logbook.get(__name__).warning("could not recall %s: %s", doc_id, e)
            return False
        self._open.pop(doc_id, None)
        return True

    def recall_all(self) -> None:
        """Used on close, so no document outlives the window that owns it."""
        for doc_id in list(self._open):
            self.recall(doc_id)

    # ── plugin revocation ─────────────────────────────────────────────────

    def for_plugin(self, plugin: str) -> list[str]:
        """The doc_ids currently on the desktop that belong to `plugin`."""
        if not plugin:
            return []
        return [doc_id for doc_id, entry in self._open.items()
                if entry.get("plugin") == plugin]

    def forget_plugin(self, plugin: str) -> bool:
        """A plugin's windows go back to the workspace before it is removed.

        Returns False when a document refused to close — the caller must then
        refuse the revoke, because removing a plugin whose window is still up
        is how a user ends up with a panel they cannot account for.
        """
        if not plugin:
            return True
        for doc_id, entry in list(self._open.items()):
            if entry["plugin"] != plugin:
                continue
            if not self._close_for_revoke(doc_id, entry):
                return False
        return True

    def _close_for_revoke(self, doc_id: str, entry: dict) -> bool:
        sub = entry["sub"]
        try:
            document = getattr(sub, "_document", None)
        except Exception as e:                      # noqa: BLE001
            logbook.get(__name__).debug("no document behind %s: %s", doc_id, e)
            document = None
        if document is not None:
            try:
                # The SAME veto the title bar's close button asks. If the
                # document says no (unsaved work), this returns False and the
                # revoke stops here rather than destroying it.
                if not document.close():
                    self.say(f"{entry['kind']} is still open with unsaved work; "
                             "the plugin was not removed")
                    return False
            except Exception as e:                  # noqa: BLE001
                logbook.get(__name__).warning(
                    "could not close %s before revoking: %s", doc_id, e)
        self.recall(doc_id)
        try:
            sub.close()
        except Exception as e:                      # noqa: BLE001
            logbook.get(__name__).debug("subwindow close failed: %s", e)
        return True

    # ── where it goes, and remembering that ───────────────────────────────

    def _placement_for(self, doc_id: str, sub) -> floating.Placement:
        screen = self._screen_size()
        saved = self._read_saved(doc_id)
        try:
            width = sub.width() or 720
            height = sub.height() or 520
        except Exception:                            # noqa: BLE001
            width, height = 720, 520
        return floating.place(saved, (60, 60, width, height), screen)

    def _screen_size(self) -> tuple[int, int]:
        try:
            screen = self._window.screen() or self._window.windowHandle().screen()
            area = screen.availableGeometry()
            return (area.width(), area.height())
        except Exception as e:                       # noqa: BLE001
            logbook.get(__name__).debug("no screen geometry: %s", e)
            return (1920, 1080)

    def _remember(self, doc_id: str) -> None:
        entry = self._open.get(doc_id)
        if entry is None:
            return
        try:
            from memory import config_manager
            placement = entry["placement"]

            def _apply(data: dict) -> None:
                section = data.get("floating_documents")
                if not isinstance(section, dict):
                    section = {}
                section[doc_id] = placement.as_dict()
                data["floating_documents"] = section

            if not config_manager.update_config(_apply):
                logbook.get(__name__).warning(
                    "the position of %s was not saved", doc_id)
        except Exception as e:                       # noqa: BLE001
            logbook.get(__name__).debug("could not save the position: %s", e)

    def _read_saved(self, doc_id: str) -> dict | None:
        try:
            from memory.config_manager import load_api_keys
            section = (load_api_keys() or {}).get("floating_documents")
            return section.get(doc_id) if isinstance(section, dict) else None
        except Exception as e:                       # noqa: BLE001
            logbook.get(__name__).debug("could not read a saved position: %s", e)
            return None

    def say(self, message: str) -> None:
        """Say it where the user can see it — a silent refusal is a dead end."""
        try:
            self._window.write_log(f"SYS: {message}")
        except Exception as e:                       # noqa: BLE001
            logbook.get(__name__).debug("no activity log to write to: %s", e)


def _qt():
    """`Qt` from the already-loaded module. See `ui/floating_panel._qt()`."""
    import sys

    return sys.modules["PyQt6.QtCore"].Qt


def return_before_disabling(window, plugin: str) -> bool:
    """Before a plugin is switched OFF, bring its floating windows home.

    WHY DISABLING IS THE HOOK, AND NOT "REVOKING"
        There is no uninstall in this program — the plugin manager's switch is
        per-plugin ON/OFF (`ui/overlays.py::PluginManagerOverlay._toggle`), and
        that is the moment a plugin stops being part of the session. A window
        belonging to a plugin the user just switched off, still sitting on the
        desktop, is the failure this prevents.

    WHY IT RETURNS A BOOL
        A document with unsaved work refuses to close. The caller must then
        leave the plugin ON rather than switch off a plugin whose window is
        still up — the user asked for one thing and would get two.
        `ui/floating_documents.FloatingDocuments.forget_plugin` does the asking,
        through the document's own close veto.
    """
    panel = getattr(window, "_floating_docs", None)
    if panel is None or not panel.for_plugin(plugin):
        return True
    return panel.forget_plugin(plugin)


def toggle_hook():
    """A ready-made `_recall_floating_plugin` METHOD for the window to bind.

    `ui/window.py` is at exactly 3,800 lines, so the three lines this method
    would take there are three it does not have. The returned function is
    written as a plain method taking `self` first — binding it with
    `_recall_floating_plugin = toggle_hook()` inside the class makes it an
    ordinary method, NOT a plain function, which is why `self` is in the
    signature and why this docstring says so out loud.
    """

    def _recall_floating_plugin(self, name: str) -> bool:
        """Called by the plugin manager before a plugin is switched off."""
        return return_before_disabling(self, name)

    return _recall_floating_plugin


__all__ = ["FloatingDocuments", "return_before_disabling", "toggle_hook"]
