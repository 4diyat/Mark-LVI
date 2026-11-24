"""actions/onboarding.py — adapter: run a reviewed onboarding decision to the stores.

THE POLICY IS PURE, THE TRANSPORT IS NOT. `core/onboarding.Onboarding` decides
where the flow is and what the summary says; it knows nothing about
`microphone_consent` or `presence_mode`. This module is the one place that
turns a recorded decision into a real write:

    welcome / done    no store to touch — navigation only.
    mic   True         `pages_people.record_consent(True)`
    mic   False        `pages_people.record_consent(False)`  (a skip is recorded
                       as a refused consent, not as "never asked" — the config
                       has one field and the summary reads it back)
    presence  <mode>   `presence_mode.set_mode(<mode>)`

WHY THE CONSENT WRITE IS HERE AND NOT IN THE POLICY
    `record_consent` writes through `memory.config_manager.set_config_values`,
    which reads a real file on import. Keeping it out of `core/onboarding.py`
    is what lets the policy be tested with no config file and no backend — the
    same split the form-filling and installer boards use.

WHY A FAILED WRITE IS REPORTED, NOT IGNORED
    A step the policy marked done but whose store write returned False would
    leave the UI and the config disagreeing — the panel would say "recorded"
    about a write that did not happen. `answer_step` returns False so the UI
    can keep the step open and say so, rather than advance on a lie.
"""
from __future__ import annotations

from core.onboarding import DONE, MIC, PRESENCE, WELCOME, Onboarding


def answer_step(flow: Onboarding, decision, log=None) -> tuple[Onboarding, bool]:
    """Record one step's decision through the policy, then apply the store write.

    Returns the new `Onboarding` and whether every write for this step
    succeeded. For the navigation steps (`welcome`, `done`) there is no store
    to write, so the write-ok flag is True and the flow advances. For `mic`
    and `presence` a failed write returns the ORIGINAL flow unchanged with
    ok=False — the step did not land, so the caller keeps it open. Advancing
    the screen while the config disagrees is the lie this build removes.
    """
    step = flow.current
    # The policy validates the decision kind and computes the next flow first;
    # a bad decision raises before any store is touched.
    new_flow = flow.answer(decision)

    if step in (WELCOME, DONE):
        return new_flow, True

    if step == MIC:
        ok = _record_consent(bool(decision))
        return (new_flow if ok else flow), ok

    if step == PRESENCE:
        ok = _set_presence(str(decision))
        return (new_flow if ok else flow), ok

    # Unreachable: the policy only exposes the four steps.
    return new_flow, True


def _record_consent(allowed: bool) -> bool:
    """Write the microphone consent. Returns whether it reached the file."""
    from ui import pages_people

    return bool(pages_people.record_consent(bool(allowed)))


def _set_presence(mode: str) -> bool:
    """Set the presence mode. Returns whether `set_mode` accepted it."""
    from core import presence_mode

    return bool(presence_mode.set_mode(str(mode)))


def run_onboarding(flow: Onboarding, decisions, log=None) -> Onboarding:
    """Walk a whole flow to the end, applying each decision in order.

    `decisions` is an iterable of one decision per step, in step order. Stops
    at the first step whose store write fails and returns the flow as it stood
    before that step was applied, so the caller can resume. A complete walk
    returns a flow with every step decided.
    """
    current = flow
    for decision in decisions:
        current, ok = answer_step(current, decision, log)
        if not ok:
            # `current` is the last valid flow (a failed write returned the
            # pre-answer flow); stop here so the caller can resume.
            return current
    return current


__all__ = ["answer_step", "run_onboarding"]
