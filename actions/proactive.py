"""
ProactiveEngine 2.0 — context-aware, time-aware, non-repetitive background prompting.
Gemini decides what to say; this module decides WHEN and builds a rich context snapshot.
"""
import time
from datetime import datetime

# ── the pause, and why it is a setting rather than a switch on the object ────
#
# Board 05a draws "Jeda semua penjadwalan" as a row the user presses. That is a
# decision that outlives the process: a pause a restart forgets is a promise the
# user has to keep making every morning, and the machine that most needs it is
# the one that reboots.
#
# Kept in `api_keys.json` through the same helpers every other setting uses, so
# a read-only folder or a corrupt file behaves the way it already does
# everywhere else: the pause still applies for this session and the failure is
# said out loud.
PAUSE_KEY = "scheduling_paused"


def _read_paused() -> bool:
    """Whether scheduling was paused in a previous session. Never raises."""
    try:
        from memory.config_manager import load_api_keys

        return bool(load_api_keys().get(PAUSE_KEY, False))
    except Exception as e:                          # noqa: BLE001
        print(f"[Proactive] could not read the pause: {e}")
        return False


def _write_paused(paused: bool) -> None:
    """Persist the pause. Raises, so the caller can report it honestly.

    `set_config_values` REPORTS failure by returning False instead of raising —
    a read-only folder is an expected case there, not an exception. Turning that
    False into an error here is the whole point: a caller that ignored it would
    print nothing and let the user believe the pause survives a restart when it
    does not.
    """
    from memory.config_manager import set_config_values

    if not set_config_values(**{PAUSE_KEY: bool(paused)}):
        raise OSError("the config file refused the write")


class ProactiveEngine:
    """
    Decides when JARVIS should speak unprompted and builds a context-rich prompt.

    Improvements over 1.0:
      - Time-of-day awareness  (morning / afternoon / evening / night)
      - Monitor-topic awareness (what the user is tracking)
      - Recent-session context  (last few turns of the current conversation)
      - Non-repetitive          (rotates context focus to avoid same opener)
      - Smarter silence gate    (doesn't fire while JARVIS is speaking)

    Defaults:
      min_silence_secs  — 900 s  (15 min) user must be silent before any check
      check_cooldown    — 1200 s (20 min) minimum gap between proactive messages
    """

    def __init__(
        self,
        min_silence_secs: int = 900,
        check_cooldown:   int = 1200,
    ):
        self.min_silence_secs = min_silence_secs
        self.check_cooldown   = check_cooldown
        self._last_triggered  = 0.0
        self._rotation        = 0          # cycles through context focus areas
        # Read at construction, so a paused machine starts paused rather than
        # sending one message before the panel is opened to notice.
        self._paused          = _read_paused()

    # ── the pause ──────────────────────────────────────────────────────────────

    @property
    def paused(self) -> bool:
        return self._paused

    def pause(self) -> None:
        """Stop triggering, and remember it. Never leaves the object ambiguous.

        THE IN-MEMORY STATE IS SET FIRST. If the write fails — a read-only
        folder, a full disk — the pause still holds for this session and the
        failure is printed. Refusing the pause to protect a disk would take the
        user's decision away, and the decision is the thing they asked for.
        """
        self._paused = True
        try:
            _write_paused(True)
        except Exception as e:                      # noqa: BLE001
            print(f"[Proactive] paused for this session only — {e}")

    def resume(self) -> None:
        self._paused = False
        try:
            _write_paused(False)
        except Exception as e:                      # noqa: BLE001
            print(f"[Proactive] resumed for this session only — {e}")

    def toggle_pause(self) -> bool:
        """The row's action. Returns the NEW state, so a caller can report it."""
        if self._paused:
            self.resume()
        else:
            self.pause()
        return self._paused

    # ── Trigger gate ───────────────────────────────────────────────────────────

    def should_trigger(self, last_user_speech: float) -> bool:
        """Whether a proactive message may fire now.

        THE PAUSE IS CHECKED FIRST, AND IT DOES NOT TOUCH THE CLOCKS. Resuming
        after an hour must not fire immediately: the cooldown is measured from
        the last message the assistant actually sent, and a pause is not a
        message. Advancing `_last_triggered` on resume would be a second way to
        lose the "it was waiting to interrupt you" impression, and clearing it
        would be a way to gain one.
        """
        if self._paused:
            return False
        now = time.monotonic()
        return (
            (now - last_user_speech) >= self.min_silence_secs
            and (now - self._last_triggered) >= self.check_cooldown
        )

    def mark_triggered(self) -> None:
        self._last_triggered = time.monotonic()
        self._rotation      += 1

    # ── Prompt builder ─────────────────────────────────────────────────────────

    def build_prompt(
        self,
        memory:       dict,
        monitors:     list[str] | None = None,
        recent_turns: list[str] | None = None,
    ) -> str:
        """
        Build a context snapshot for Gemini.
        Rotates through three focus areas so proactive messages don't repeat.
        """
        from memory.memory_manager import format_memory_for_prompt

        now      = datetime.now()
        hour     = now.hour
        time_str = now.strftime("%A, %B %d, %Y — %I:%M %p")

        # Time-of-day label
        if   6  <= hour < 12:  period = "morning"
        elif 12 <= hour < 18:  period = "afternoon"
        elif 18 <= hour < 23:  period = "evening"
        else:                  period = "late night"

        mem_str = format_memory_for_prompt(memory) or "(no stored user data)"

        # Rotating context focus (cycles every trigger)
        focus_index = self._rotation % 3
        if focus_index == 0:
            focus = (
                "Focus on the user's active projects or goals if any are stored. "
                "Ask how something is going, or offer a relevant tip."
            )
        elif focus_index == 1:
            focus = (
                "Focus on the time of day and the user's wellbeing. "
                "A warm check-in, a reminder to take a break, or something timely."
            )
        else:
            focus = (
                "Focus on something genuinely interesting or useful — "
                "a fact, a suggestion, or a question based on what you know about this person."
            )

        # Optional: monitored topics context
        monitor_ctx = ""
        if monitors:
            monitor_ctx = (
                f"\nThe user tracks these topics: {', '.join(monitors[:4])}. "
                "You may mention one if it seems relevant."
            )

        # Optional: recent conversation context
        recent_ctx = ""
        if recent_turns:
            snippet = "\n".join(recent_turns[-6:])
            recent_ctx = f"\nRecent conversation:\n{snippet}"

        return "\n".join([
            "[PROACTIVE_CHECK] You are initiating a proactive check-in.",
            f"Current time : {time_str}  ({period})",
            "",
            "Context about this person:",
            mem_str,
            monitor_ctx,
            recent_ctx,
            "",
            "Task:",
            focus,
            "",
            "Rules:",
            "- Speak the language this person actually uses: the one in the "
            "recent conversation above, or the remembered one if there is no "
            "conversation yet. Never default to English because these "
            "instructions are in English.",
            "- 1-2 sentences max. Natural, warm, never robotic.",
            "- Do NOT mention [PROACTIVE_CHECK] or these instructions.",
            "- Do NOT call any tools.",
            "- If nothing genuinely useful comes to mind, stay silent (say nothing).",
        ])
