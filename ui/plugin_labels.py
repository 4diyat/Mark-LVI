"""The human names for the plugin ids this build ships.

WHY A MODULE RATHER THAN A DICT IN THE PAGE
    A manifest's `name` is a MODULE ID — `code_editor`, `mt5_orb`,
    `workspace_browser`. Board 16 draws names a person reads ("Penjadwal",
    "Notulen rapat"), and the first version of the page printed the ids. Adding
    the mapping to `ui/pages_admin.py` took that file to 612 lines against its
    600-line ceiling, which is the ceiling doing its job: a lookup table is not
    page logic and does not belong in the file that builds the page.

WHAT THIS IS NOT
    Not a filter and not a whitelist: an id with no entry here still appears in
    the list, under the name its manifest gives it. The alternative — dropping
    plugins nobody translated — would hide a real plugin from the person who
    switched it on.
"""
from __future__ import annotations

# plugin id -> catalogue key. Every id under `plugins/*.json` today.
PLUGIN_LABELS = {
    "code_editor": "ui.page.plugins.p.code_editor",
    "currency_rates": "ui.page.plugins.p.currency_rates",
    "gmail_inbox": "ui.page.plugins.p.gmail_inbox",
    "image_editor": "ui.page.plugins.p.image_editor",
    "market_price": "ui.page.plugins.p.market_price",
    "morning_brief": "ui.page.plugins.p.morning_brief",
    "mt5_orb": "ui.page.plugins.p.mt5_orb",
    "mt5_trade": "ui.page.plugins.p.mt5_trade",
    "obsidian_notes": "ui.page.plugins.p.obsidian_notes",
    "prayer_times": "ui.page.plugins.p.prayer_times",
    "quick_notes": "ui.page.plugins.p.quick_notes",
    "security_camera": "ui.page.plugins.p.security_camera",
    "ssh_manager": "ui.page.plugins.p.ssh_manager",
    "trading_terminal": "ui.page.plugins.p.trading_terminal",
    "workspace_browser": "ui.page.plugins.p.workspace_browser",
}


def label_for(name: str) -> str:
    """The catalogue key for a plugin id, or "" when there is no entry.

    "" rather than the id: the caller can tell "I have a name for this" from
    "I do not", and falls back itself. Returning the id here would make the two
    cases indistinguishable at every call site.
    """
    return PLUGIN_LABELS.get(str(name), "")


__all__ = ["PLUGIN_LABELS", "label_for"]
