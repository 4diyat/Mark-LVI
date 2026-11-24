"""core/onboarding.py — the four-step first-run flow, decided in pure logic.

BOARD 7 IS A LADDER, NOT A SINGLE QUESTION. The artboard (`b07`) draws a
four-step onboarding, and for a long time this build asked the only question
the program actually had — the microphone — and wrote "Step 1 of 1". That was
honest about the one step it had, but it was not the four-step flow the artboard
promises. This module is the ladder.

WHY THE DECISION IS PURE
    The four steps are: a welcome (informational), the microphone consent, the
    presence mode, and a summary. Two of them write to a store (consent, mode);
    two are navigation. Deciding where the flow is, whether a step counts as
    done or skipped, and what the summary says is all arithmetic over a record
    — so it lives here, with no Qt and no config file, and the tests can drive
    every path without a widget or a backend.

THE FOUR STEPS, IN ORDER
    welcome   the introduction. No decision to record; "next" completes it.
    mic       the microphone consent. `allow` records consent; `deny` skips it
              (a refusal is not the same as never being asked, but neither is
              a skip a stored consent — the summary says which).
    presence  the presence mode (active / focus / quiet). Picking one records
              the choice; this is the same `presence_mode` the tray segments
              drive, so the onboarding and the panel cannot disagree.
    done      the summary. It reads the record and states what was chosen.

WHAT THIS DOES NOT DO
    It does not touch a store and it does not know the config file exists.
    `actions/onboarding.py` is the adapter that maps a recorded decision to
    `pages_people.record_consent` and `presence_mode.set_mode`, and persists
    where the flow has reached. A pure model that already knew those would not
    be testable without them, and would drift from them on the next change.
"""
from __future__ import annotations

WELCOME, MIC, PRESENCE, DONE = "welcome", "mic", "presence", "done"

# The ladder, in order. Frozen: the flow is the product's, not a setting.
STEPS: tuple[str, ...] = (WELCOME, MIC, PRESENCE, DONE)

# A decision per step kind, so `answer()` can validate without knowing which
# step it is being handed beyond its position.
#   welcome / done : no real decision; any value completes them.
#   mic            : a bool — True allows, False skips.
#   presence       : a mode name string.
_STEP_DECISION = {
    WELCOME: "any",
    MIC: "bool",
    PRESENCE: "str",
    DONE: "any",
}


class Onboarding:
    """The state of one onboarding flow: where it is, and what was decided.

    Frozen record semantics — every `answer()` returns a NEW `Onboarding`, so
    the UI can hold the current one and tests can compare two without a shared
    mutable object slipping between them.
    """

    __slots__ = ("_done", "_skipped", "_presence", "_current")

    def __init__(
        self,
        done: frozenset[str] | None = None,
        skipped: frozenset[str] | None = None,
        presence: str | None = None,
        current: int = 0,
    ) -> None:
        self._done = frozenset(done or ())
        self._skipped = frozenset(skipped or ())
        self._presence = presence
        # The index of the step being shown. Clamped so a restored state can
        # never point outside the ladder.
        self._current = max(0, min(int(current), len(STEPS) - 1))

    # ── constructors ──────────────────────────────────────────────────────

    @classmethod
    def start(cls) -> "Onboarding":
        """A fresh flow at the welcome step, nothing decided."""
        return cls()

    @classmethod
    def restore(cls, done=None, skipped=None, presence=None, current=0) -> "Onboarding":
        """Rebuild a flow from what was persisted, so a reopened panel continues.

        The `current` index is recomputed from the decisions: the flow shows the
        first step not yet completed or skipped, never a stale position.
        """
        flow = cls(done=done, skipped=skipped, presence=presence)
        return flow._advance_to_first_open()

    def _advance_to_first_open(self) -> "Onboarding":
        """Show the first step that has not been decided yet."""
        for index, step in enumerate(STEPS):
            if step not in self._done and step not in self._skipped:
                return Onboarding(self._done, self._skipped,
                                  self._presence, index)
        # Every step decided: the summary is the last thing shown.
        return Onboarding(self._done, self._skipped, self._presence,
                          len(STEPS) - 1)

    # ── reads ─────────────────────────────────────────────────────────────

    @property
    def current(self) -> str:
        return STEPS[self._current]

    @property
    def current_index(self) -> int:
        return self._current

    @property
    def total(self) -> int:
        return len(STEPS)

    @property
    def is_complete(self) -> bool:
        """Whether every step has been decided (the summary is the last)."""
        return all(step in self._done or step in self._skipped
                   for step in STEPS)

    def is_done(self, step: str) -> bool:
        return step in self._done

    def is_skipped(self, step: str) -> bool:
        return step in self._skipped

    @property
    def presence_mode(self) -> str | None:
        return self._presence

    def decided_count(self) -> int:
        return len(self._done | self._skipped)

    def progress(self) -> tuple[int, int]:
        """(decided, total) — the fraction the step indicator draws."""
        return self.decided_count(), self.total

    # ── the decision ──────────────────────────────────────────────────────

    def answer(self, decision) -> "Onboarding":
        """Record one step's decision and move to the next open step.

        A decision for the step currently shown. `welcome` and `done` accept
        anything (they are navigation); `mic` wants a bool; `presence` wants a
        mode name. A wrong kind raises `OnboardingError` rather than recording
        a decision that means nothing — a flow that silently accepts a mode
        string as a consent answer is how the two get out of step.
        """
        step = self.current
        kind = _STEP_DECISION[step]
        if kind == "bool" and not isinstance(decision, bool):
            raise OnboardingError(f"{step} needs a bool, got {type(decision).__name__}")
        if kind == "str" and not isinstance(decision, str):
            raise OnboardingError(f"{step} needs a mode name, got {type(decision).__name__}")

        if step == MIC:
            if decision:
                done, skipped = frozenset(self._done | {MIC}), self._skipped
            else:
                done, skipped = self._done, frozenset(self._skipped | {MIC})
        elif step == PRESENCE:
            done = frozenset(self._done | {PRESENCE})
            skipped = self._skipped
            # The mode is the decision itself; keep it for the summary.
            return Onboarding(done, skipped, str(decision))._advance_to_first_open()
        else:
            done = frozenset(self._done | {step})
            skipped = self._skipped

        flow = Onboarding(done, skipped, self._presence)
        return flow._advance_to_first_open()

    # ── the summary ────────────────────────────────────────────────────────

    def summary_lines(self) -> list[str]:
        """The sentences the done step shows. Honest about what was chosen.

        A skipped step is named as skipped, never as decided; a present mode
        that was never picked is named as "not chosen", because the summary's
        whole job is to be a readout of the record rather than a nicer story.
        """
        lines: list[str] = []
        mic = "consented" if self.is_done(MIC) else \
              "skipped" if self.is_skipped(MIC) else "not asked"
        lines.append(f"Microphone: {mic}.")
        if self._presence:
            lines.append(f"Presence mode: {self._presence}.")
        else:
            lines.append("Presence mode: not chosen (the tray default stands).")
        lines.append(f"{self.decided_count()} of {self.total} steps done.")
        return lines


class OnboardingError(ValueError):
    """A decision that does not match the step that was asked."""


__all__ = ["STEPS", "WELCOME", "MIC", "PRESENCE", "DONE",
           "Onboarding", "OnboardingError"]
