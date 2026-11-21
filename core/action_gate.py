"""core/action_gate.py — one place where an action is allowed, recorded, or held.

WHY A GATE AND NOT THREE SEPARATE CALLS
    Each of the three pieces already exists and each is correct on its own:

        core/risk_policy   what level this action is
        core/undo          how to reverse it, if it registered a closure
        core/confirm       the trusted UI gate for the irreversible ones
        core/audit_log     what actually happened

    Wiring them by hand at every tool would give four call sites per action and
    would drift: the fourth action someone writes would forget the audit line,
    or check `can_undo()` for an action that never registers an undo and get
    told the wrong level. This module is that wiring, written once, so the
    ORDER is fixed:

        1. classify         (risk_policy.decide)
        2. record the intent (audit "requested")
        3. run, or hold     (safe/medium run; risky goes to confirm)
        4. record the result (audit with the outcome core.outcome produced)

    Steps 2 and 4 are separate on purpose. An audit log that only records what
    finished cannot answer "it asked to send that email — did I allow it?", and
    the confirmation dialog is precisely the case where that question matters.

WHY THE GATE DOES NOT IMPORT Qt
    Everything here runs on whatever thread the agent loop is on. The trusted UI
    is reached through `core.confirm`, which is already bound to the HUD by
    main.py. Keeping Qt out of this file is what lets the whole decision path be
    tested on a machine with no display.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from core import audit_log, risk_policy
from core import undo as undo_stack

# The outcomes this gate records, in the words `core.outcome` already uses so
# the log and the spoken sentence cannot disagree.
RUN, HELD, REFUSED = "run", "held", "refused"


@dataclass(frozen=True)
class Result:
    """What the caller should tell the model, and whether anything ran."""

    ran: bool
    level: str
    message: str
    decision: risk_policy.Decision

    @property
    def needs_human(self) -> bool:
        return self.decision.needs_confirm and not self.ran


def _audit(tool: str, level: str, outcome: str, detail: str = "") -> None:
    """Never let a logging failure become the caller's problem."""
    try:
        audit_log.record(tool, level, outcome, detail)
    except Exception as e:                          # noqa: BLE001
        print(f"[Gate] audit write failed for {tool}: {e}")


def check(tool: str, run: Callable[[], str],
          confirm_detail: str = "", confirm_title: str = "",
          undo_registered: bool | None = None) -> Result:
    """Classify, record, then either run `run()` or park it behind confirmation.

    `undo_registered=None` means "ask the undo stack", which is the right answer
    for a tool that has already pushed its closure. Pass an explicit bool only
    when the tool knows better — for example, a tool that will register the undo
    inside `run()` and therefore cannot have registered it yet.
    """
    if undo_registered is None:
        try:
            undo_registered = undo_stack.can_undo()
        except Exception:                           # noqa: BLE001
            undo_registered = False

    decision = risk_policy.decide(tool, undo_registered=bool(undo_registered))
    _audit(tool, decision.level, "requested", confirm_title or "")

    if decision.needs_confirm:
        # Imported here, not at module scope: core.confirm writes to the Qt
        # interface when it is bound, and importing it early would make this
        # module's import order matter to the app's start-up.
        from core import confirm
        message = confirm.request(
            key=tool,
            title=(confirm_title or f"Menjalankan {tool}?")[:120],
            detail=(confirm_detail or decision.reason)[:300],
            run=lambda: _run_and_audit(tool, decision.level, run),
        )
        _audit(tool, decision.level, HELD, message[:120])
        return Result(ran=False, level=decision.level, message=message, decision=decision)

    return Result(ran=True, level=decision.level,
                  message=_run_and_audit(tool, decision.level, run), decision=decision)


def _run_and_audit(tool: str, level: str, run: Callable[[], str]) -> str:
    """Run one action and record what happened, including when it exploded.

    The exception is recorded and re-raised as a sentence rather than propagated:
    the caller is a model-facing tool, and a traceback in the conversation is
    both useless to the user and a source of invented detail. `core.outcome`
    shapes the sentence elsewhere; this keeps the audit line truthful either way.
    """
    try:
        message = run() or "Done."
    except Exception as e:                          # noqa: BLE001
        _audit(tool, level, "failed", f"{type(e).__name__}: {e}"[:200])
        return f"That failed: {type(e).__name__}: {e}"
    outcome = "done"
    lowered = str(message).lower()
    # core.outcome marks unverified results with a bracketed tag; mirroring that
    # here keeps the audit log's vocabulary identical to the spoken result.
    if "[unverified" in lowered or "unverified" in lowered:
        outcome = "unverified"
    elif "[failed" in lowered or lowered.startswith("failed"):
        outcome = "failed"
    _audit(tool, level, outcome, str(message)[:200])
    return message


def describe(tool: str) -> str:
    """One line for the risk table in the UI, without running anything."""
    decision = risk_policy.decide(tool, undo_registered=False)
    return f"{tool}: {decision.level} — {decision.reason}"
