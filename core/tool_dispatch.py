"""The tool calls that need nothing but their arguments.

WHY THIS IS A MODULE
    `JarvisLive._execute_tool` was one 213-line `if/elif` chain, and the reason
    it was one chain is that most of its branches need live state: the UI
    widget, the open session, the vision cooldown, the action registry. Those
    have to stay on the class.

    These four do not. Each is a pure function of `args` plus a module the
    branch already imported, so each can be read, and tested, without standing
    up a JARVIS session with a window and a Gemini socket. That is the whole
    point of taking them out: a branch you cannot test in isolation is a branch
    nobody tests.

WHAT STAYS IN main.py
    `screen_process`, `shutdown_jarvis`, the action-registry path and the
    plugin path all touch `self` — vision cooldown flags, `self.ui`, the
    session. They are not moved, and the tests that cover them still go through
    `JarvisLive`.

CONTRACT
    Every handler here takes `(args: dict) -> Awaitable[str]` and returns the
    string that is handed back to the model. `handles(name)` says which tool
    names this module owns, so `main.py` asks once instead of repeating that
    knowledge in a comment that drifts.
"""
from __future__ import annotations

import asyncio

from core import undo as undo_stack

# Imported lazily inside the handlers that use them, so importing this module
# never drags in the system monitor's psutil probe or the memory file scan —
# `main.py` imports this at startup.
_HANDLED = frozenset({"recall_memory", "undo", "system_status", "manage_monitor"})


def handles(name: str) -> bool:
    """True if `dispatch` can answer this tool name."""
    return name in _HANDLED


async def dispatch(name: str, args: dict) -> str:
    """Run one of the stateless tools. Caller must have checked `handles`."""
    if name == "recall_memory":
        # Local file search: no network, no second model. Kept out of the
        # executor deliberately — it is a dictionary scan over a few hundred
        # short strings, and a thread hop would cost more than the work itself.
        from memory.memory_manager import search_memory
        return search_memory(args.get("query", ""), limit=8)

    if name == "undo":
        if str(args.get("action", "")).lower().strip() == "list":
            items = undo_stack.history()
            if not items:
                return "I have not changed anything I can undo yet."
            return ("Things I can undo, most recent first:\n"
                    + "\n".join(f"{i + 1}. {t}" for i, t in enumerate(items)))
        return await asyncio.get_event_loop().run_in_executor(
            None, undo_stack.undo_last)

    if name == "system_status":
        from actions.system_monitor import get_system_status
        return str(await asyncio.get_event_loop().run_in_executor(
            None, get_system_status))

    if name == "manage_monitor":
        from actions.background_monitor import add_monitor, list_monitors, remove_monitor
        action = args.get("action", "").lower().strip()
        topic = args.get("topic", "").strip()
        if action == "add" and topic:
            return await asyncio.to_thread(add_monitor, topic)
        if action == "remove" and topic:
            return await asyncio.to_thread(remove_monitor, topic)
        if action == "list":
            topics = await asyncio.to_thread(list_monitors)
            return ("Monitoring: " + ", ".join(topics)) if topics else "No topics are being monitored."
        return "Specify action (add/remove/list) and a topic."

    raise KeyError(f"{name} is not handled by core.tool_dispatch")
