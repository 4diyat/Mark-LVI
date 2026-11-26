"""core/action_gate.py — where a tool call is allowed, recorded, or parked.

WHY A GATE AND NOT FOUR CALLS AT EVERY TOOL
    Each piece already exists and each is right on its own:

        core/tool_risk    the level of THIS call, arguments included
        core/risk_policy  the level of a tool, extended by phases and plugins
        core/confirm      the trusted-UI gate the model cannot forge
        core/audit_log    what actually happened

    Wiring them by hand per tool site would give four call sites per action and
    would drift: the fourth one somebody writes would forget the audit line, or
    check the undo stack for an action that never registers one and get told the
    wrong level. This module is that wiring, written once, in a fixed order:

        1. classify          (tool_risk.classify — per call)
        2. record the intent (audit "requested")
        3. run, or park it   (risky goes to core.confirm, unless it already gates)
        4. record the outcome (audit: done / unverified / failed / ...)

    Steps 2 and 4 are separate on purpose. A log that records only what finished
    cannot answer "it asked to send that email — did I allow it?", and the
    confirmation is exactly the case where that question matters.

WHY SOME TOOLS ARE LEFT ALONE
    Four actions already call `core.confirm.request` themselves, with a title
    and a detail written for the specific operation ("Run build.py?" rather than
    "code_helper:run"). Gating them again here would put two banners on screen
    for one shutdown, and the second one teaches the user to dismiss both. So a
    site declares `self_gated=True` when it owns its own confirmation, and the
    gate records the decision without asking a second time.

WHY IT NEVER IMPORTS Qt
    Everything here runs on whatever thread the agent loop is on. The trusted UI
    is reached through `core.confirm`, which main.py binds to the HUD. Keeping Qt
    out is what lets the whole decision path be tested with no display.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from typing import Any, Callable, Mapping

from core import audit_log, i18n, tool_risk

# The words an audit record can carry, in the vocabulary `core.outcome` already
# uses so the log and the sentence the user hears cannot disagree.
REQUESTED, AWAITING, RUN, HELD, DONE, UNVERIFIED, FAILED = (
    "requested", "awaiting", "run", "held", "done", "unverified", "failed")


@dataclass(frozen=True)
class Result:
    """What happened to one call, and what to tell the model."""

    ran: bool
    level: str
    message: str
    risk: tool_risk.CallRisk

    @property
    def needs_human(self) -> bool:
        """True when a person still has to press something."""
        return self.risk.level == tool_risk.RISKY and not self.ran


def _audit(tool: str, level: str, outcome: str, detail: str = "") -> None:
    """Never let a logging failure become the caller's problem."""
    try:
        audit_log.record(tool, level, outcome, detail)
    except Exception as e:                          # noqa: BLE001
        print(f"[Gate] audit write failed for {tool}: {e}")


def check(tool: str, run: Callable[[], Any], args: Mapping | None = None,
          *, self_gated: bool = False, confirm_title: str = "",
          confirm_detail: str = "", on_decline: Callable[[str], str] | None = None,
          plugin_level: str | None = None
          ) -> Result:
    """Classify one call, record it, then run it or park it behind a human.

    `self_gated=True` says the tool already asked through `core.confirm` with a
    better sentence than this module could write. The gate then records the
    level and runs it — the tool's own gate is still the only one that can let
    the action through.

    `args` is what makes the classification per-call: pass the tool's arguments
    and `computer_settings(action='shutdown')` is asked about while
    `computer_settings(action='volume_up')` is not.

    `plugin_level` is the level a plugin's manifest claims, and it is the reason
    this is a parameter rather than a second function. A plugin is CLASSIFIED
    differently (see `tool_risk.classify_plugin`), but everything after that —
    the audit line, the banner, the fact that it did not run — is identical, and
    a second code path is the one that drifts. `None` means "not a plugin" and
    leaves every existing call unchanged.
    """
    risk = (tool_risk.classify(tool, args) if plugin_level is None
            else tool_risk.classify_plugin(tool, plugin_level))
    name = risk.audit_name
    _audit(name, risk.level, REQUESTED, confirm_title or "")

    if risk.level == tool_risk.RISKY and not self_gated:
        from core import confirm          # imported here: see the module docstring
        title = confirm_title or _default_title(risk)
        try:
            parameters = json.dumps(dict(args or {}), ensure_ascii=False, sort_keys=True,
                                    separators=(', ', ': '), allow_nan=False)
        except (TypeError, ValueError):
            return Result(ran=False, level=risk.level,
                          message='Cannot display the complete action parameters for confirmation. Nothing was done.',
                          risk=risk)
        label = "Parameter" if i18n.active_locale() == "id" else "Parameters"
        detail = (confirm_detail or _default_detail(risk)) + f"\n{label}: {parameters}"
        message = confirm.request(key=name, title=title, detail=detail,
                                  run=lambda: _run_and_audit(name, risk.level, run))
        if message.startswith('[CONFIRMATION_PENDING]'):
            _audit(name, risk.level, AWAITING, title)
        outcome = on_decline(message) if on_decline is not None else message
        return Result(ran=False, level=risk.level, message=outcome, risk=risk)

    return Result(ran=True, level=risk.level,
                  message=_run_and_audit(name, risk.level, run), risk=risk)


def _default_title(risk: tool_risk.CallRisk) -> str:
    return f"Run {risk.tool}?" if not risk.action else f"Run {risk.tool}: {risk.action}?"


def _default_detail(risk: tool_risk.CallRisk) -> str:
    return f"{risk.reason}. Review the requested action before approving."


def _run_and_audit(name: str, level: str, run: Callable[[], Any]) -> str:
    """Run one action and record what happened, including when it exploded.

    An exception is recorded and turned into a sentence rather than propagated:
    the caller is a model-facing tool, and a traceback in the conversation is
    both useless to the user and a source of invented detail.
    """
    try:
        value = run()
    except Exception as e:                          # noqa: BLE001
        _audit(name, level, FAILED, f"{type(e).__name__}: {e}")
        return f"That failed: {type(e).__name__}: {e}"

    message = "Done." if value is None else str(value)
    lowered = message.lower()
    # `core.outcome` marks its results with bracketed tags; mirroring them here
    # keeps the audit vocabulary identical to the sentence the user hears.
    if "[unverified" in lowered or lowered.startswith("unverified"):
        outcome = UNVERIFIED
    elif "[failed" in lowered or lowered.startswith("failed"):
        outcome = FAILED
    else:
        outcome = DONE
    _audit(name, level, outcome, message[:200])
    return message


def describe(tool: str, args: Mapping | None = None) -> str:
    """One line for the risk table in the UI, without running anything."""
    risk = tool_risk.classify(tool, args)
    return f"{risk.audit_name}: {risk.level} — {risk.reason}"
