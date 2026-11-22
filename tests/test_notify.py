"""When JARVIS is allowed to interrupt you, and when it must not.

WHY THE POLICY IS THE WHOLE FEATURE
    Sending a desktop notification is four lines and already proven in
    `actions/reminder.py`. What decides whether this is useful or is the thing
    the user switches off on day two is the REASON NOT TO FIRE:

      * a status cycle runs LISTENING → THINKING → SPEAKING → LISTENING dozens
        of times a minute. One banner per transition is a machine that buzzes;
      * an answer that arrived while the window was already on screen says
        nothing a banner can add;
      * a LISTENING that did not follow an answer is a reconnect, not a reply.

    None of that is testable at the `notify-send` end, and all of it is testable
    here. The platform call is injected so these run with no desktop, no
    `subprocess`, and no waiting.
"""
from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core import notify  # noqa: E402


class _Recorder:
    """Stands in for the desktop, and answers on demand."""

    def __init__(self, fail=False):
        self.calls = []
        self.fail = fail

    def __call__(self, title, body):
        self.calls.append((title, body))
        if self.fail:
            raise RuntimeError("the desktop refused")
        return True

    @property
    def bodies(self):
        return [body for _title, body in self.calls]


class _Clock:
    def __init__(self, start=1000.0):
        self.now = start

    def __call__(self):
        return self.now

    def advance(self, seconds):
        self.now += seconds


def _notifier(recorder=None, visible=False, clock=None):
    recorder = recorder or _Recorder()
    return notify.Notifier(send=recorder, visible=lambda: visible,
                           clock=clock or _Clock()), recorder


def _wait_for(predicate, timeout=1.0):
    import time
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.005)
    return False


# ── the rule: one banner per finished turn ────────────────────────────────

def test_a_finished_turn_is_announced_once():
    n, rec = _notifier()
    assert n.observe("THINKING") is False
    assert n.observe("SPEAKING") is False
    assert n.observe("LISTENING", "It is done.") is True
    assert _wait_for(lambda: rec.bodies == ["It is done."])


def test_a_status_cycle_with_no_answer_says_nothing():
    """LISTENING after LISTENING is a reconnect or a mic change, not a reply."""
    n, rec = _notifier()
    assert n.observe("LISTENING") is False
    assert n.observe("LISTENING") is False
    assert rec.calls == []


def test_the_answer_text_is_carried_into_the_banner():
    n, rec = _notifier()
    n.observe("THINKING")
    n.observe("LISTENING", "The weather in Bandung is 27 degrees.")
    assert _wait_for(lambda: rec.bodies == ["The weather in Bandung is 27 degrees."])


def test_an_empty_answer_still_announces_that_something_finished():
    """Silence would leave the user unable to tell "done" from "still working"."""
    n, rec = _notifier()
    n.observe("THINKING")
    n.observe("LISTENING", "")
    assert _wait_for(lambda: rec.bodies == ["I have finished."])


def test_a_long_answer_is_cut_before_it_reaches_the_desktop():
    """A banner is a headline. Windows truncates at ~256 characters anyway, and
    a body that has already been cut by the OS reads as a broken sentence."""
    n, rec = _notifier()
    n.observe("THINKING")
    n.observe("LISTENING", "x" * 500)
    assert _wait_for(lambda: rec.calls)
    assert len(rec.bodies[0]) == 180


# ── quiet when it would be noise ──────────────────────────────────────────

def test_nothing_is_announced_while_the_window_is_on_screen():
    n, rec = _notifier(visible=True)
    n.observe("THINKING")
    assert n.observe("LISTENING", "done") is False
    assert rec.calls == []
    assert n.suppressed == 1, "the suppression was not counted"


def test_the_cooldown_stops_a_burst_of_turns():
    """Two answers in a second is a burst, not two things worth interrupting."""
    clock = _Clock()
    n, rec = _notifier(clock=clock)
    n.observe("THINKING"); n.observe("LISTENING", "first")
    assert _wait_for(lambda: rec.bodies == ["first"])
    n.observe("THINKING"); clock.advance(5)
    assert n.observe("LISTENING", "second") is False
    assert n.suppressed == 1


def test_the_cooldown_expires():
    clock = _Clock()
    n, rec = _notifier(clock=clock)
    n.observe("THINKING"); n.observe("LISTENING", "first")
    assert _wait_for(lambda: len(rec.bodies) == 1)
    n.observe("THINKING")
    clock.advance(notify.COOLDOWN_S + 1)
    assert n.observe("LISTENING", "second") is True
    assert _wait_for(lambda: rec.bodies == ["first", "second"])


def test_an_unknown_status_is_ignored():
    n, rec = _notifier()
    assert n.observe("") is False
    assert n.observe("SLEEPING") is False
    assert n.observe("NO MIC") is False
    assert rec.calls == []


def test_visibility_that_raises_is_treated_as_not_visible():
    """Showing a redundant banner is a smaller failure than swallowing an answer."""
    rec = _Recorder()

    def _boom():
        raise RuntimeError("no window")

    n = notify.Notifier(send=rec, visible=_boom, clock=_Clock())
    n.observe("THINKING")
    assert n.observe("LISTENING", "still worth telling you") is True
    assert _wait_for(lambda: rec.bodies == ["still worth telling you"])


# ── never the thing that raises ───────────────────────────────────────────

def test_a_desktop_that_refuses_does_not_raise_or_retry():
    n, rec = _notifier(recorder=_Recorder(fail=True))
    n.observe("THINKING")
    assert n.observe("LISTENING", "done") is True     # accepted by the policy
    assert _wait_for(lambda: rec.calls)               # and the failure was reached
    assert len(rec.calls) == 1, "a refused banner must not be retried"


def test_the_bookkeeping_survives_concurrent_status_updates():
    """`set_state` is called from the audio, session and UI threads."""
    import threading
    n, rec = _notifier()
    clock = _Clock()
    n._clock = clock
    errors = []

    def _spam():
        try:
            for _ in range(50):
                n.observe("THINKING")
                n.observe("LISTENING", "x")
                clock.advance(0.001)
        except Exception as e:                      # noqa: BLE001
            errors.append(e)

    threads = [threading.Thread(target=_spam) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert errors == []
    # The cooldown is what bounds it: at most one per window, no matter how
    # many threads asked.
    assert n.sent <= 1


# ── the platform call ─────────────────────────────────────────────────────

def test_linux_uses_notify_send_when_it_is_there(monkeypatch):
    seen = []

    def _run(cmd, **kwargs):
        seen.append(cmd)
        return 0

    monkeypatch.setattr(notify.shutil, "which", lambda name: f"/usr/bin/{name}")
    assert notify.send_native("T", "B", os_name="Linux", runner=_run) is True
    assert seen and seen[0][0] == "notify-send"
    assert seen[0][-2:] == ["T", "B"]
    assert "--expire-time=8000" in seen[0]


def test_linux_without_notify_send_tries_plyer_and_says_so(monkeypatch, capsys):
    monkeypatch.setattr(notify.shutil, "which", lambda _name: None)
    monkeypatch.setitem(sys.modules, "plyer", None)     # import raises
    assert notify.send_native("T", "B", os_name="Linux", runner=lambda *a, **k: 0) is False
    assert "no notification backend" in capsys.readouterr().out


def test_macos_escapes_quotes_instead_of_stripping_them(monkeypatch):
    """`display notification` takes the text inside AppleScript quotes. Stripping
    the quotes would silently change what the user is told."""
    seen = []
    monkeypatch.setattr(notify.shutil, "which", lambda _n: None)
    monkeypatch.setitem(sys.modules, "plyer", None)

    def _run(cmd, **kwargs):
        seen.append(cmd)
        return 0

    ok = notify.send_native('Say "hi"', 'path C:\\temp', os_name="Darwin", runner=_run)
    assert ok is True
    script = seen[0][2]
    assert '\\"hi\\"' in script, "quotes were stripped rather than escaped"
    assert "C:\\\\temp" in script, "a backslash in the body broke the AppleScript"


def test_the_title_does_not_depend_on_the_users_assistant_name(monkeypatch):
    """A banner titled "FRIDAY" from an unknown app is worse than one that says
    what it is. The name is user-editable; the banner must not follow it."""
    assert notify.TITLE == "J.A.R.V.I.S"
    # Read the CODE, not the file: the docstring names the function it is
    # deliberately not calling, and a substring search over the source finds
    # that sentence and fails on a module that is correct.
    import ast
    tree = ast.parse((ROOT / "core" / "notify.py").read_text(encoding="utf-8"))
    called = {node.func.id for node in ast.walk(tree)
              if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)}
    called |= {node.func.attr for node in ast.walk(tree)
               if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)}
    assert "get_assistant_name" not in called


def test_the_statuses_that_announce_are_the_ones_that_mean_finished():
    """SPEAKING must not announce: it fires before the answer exists, and the
    user hears the answer anyway."""
    assert notify.ANNOUNCE_ON == ("LISTENING",)
    assert "SPEAKING" in notify._TURN_PREFIX
    assert "SPEAKING" not in notify.ANNOUNCE_ON


def test_the_title_is_escaped_too(monkeypatch):
    """A quote in the title used to produce a malformed AppleScript, which
    osascript rejects while still exiting successfully."""
    seen = []
    monkeypatch.setattr(notify.shutil, "which", lambda _n: None)
    monkeypatch.setitem(sys.modules, "plyer", None)
    notify.send_native('Say "hi"', "body", os_name="Darwin",
                       runner=lambda cmd, **k: seen.append(cmd) or 0)
    script = seen[0][2]
    assert 'with title "Say \\"hi\\""' in script


# ── wiring: only in ambient mode, and only when asked for ────────────────

def test_every_state_change_is_offered_to_the_policy(monkeypatch):
    """THE WIRE, DRIVEN. A policy nobody feeds never sends anything, and a
    feature that is correctly quiet looks identical to a feature that is broken.

    Found by mutation: deleting the `_announce` call from `set_state` left the
    whole suite green, because every other test here feeds `Notifier.observe`
    directly. This one goes through the surface.
    """
    from ui.shell import AmbientShell

    seen = []

    class _Recorder:
        def observe(self, status, text=""):
            seen.append((status, text))
            return False

    shell = AmbientShell("face.png", "JARVIS")
    shell._notifier = _Recorder()
    shell._last_answer = "Delapan baris diringkas."
    monkeypatch.setattr("memory.config_manager.get_desktop_notifications",
                        lambda: True, raising=False)

    shell.set_state("speaking")
    assert seen == [("SPEAKING", "Delapan baris diringkas.")], seen


def test_a_finished_answer_becomes_the_notification_body():
    """The body is the last thing the assistant SAID, not the last log line.

    A log line is usually `SYS:` or `ERR:`; sending one of those as a desktop
    notification tells the user nothing and looks like a bug.
    """
    from ui.shell import AmbientShell

    shell = AmbientShell("face.png", "JARVIS")
    shell.write_log("Baris 7 dan 11 melewati plafon.")
    assert shell._last_answer == "Baris 7 dan 11 melewati plafon."
    shell.write_log("SYS: Awaiting confirmation — Kirim laporan")
    assert shell._last_answer == "Baris 7 dan 11 melewati plafon.", (
        "a status line overwrote the answer the notification is supposed to carry")


def test_finishing_work_never_pops_a_window():
    """There is no HUD to leave alone, and no window to raise either.

    The old rule was "announce only in ambient mode", which existed because the
    HUD was already showing the answer. What is left to prove is that the
    announcement path does not reach for a window at all — and that it stays
    quiet in Fokus/Senyap, where a banner is exactly what the mode forbids.
    """
    source = (ROOT / "ui" / "lifecycle.py").read_text(encoding="utf-8")
    assert "def announce_if_finished" not in source, (
        "the HUD-aware announcer is back; there is no HUD for it to be aware of")
    # `_window` is the face bubble's own window and is fine; `_win` was the
    # main window, and a lifecycle path that still reaches for it is a
    # `None`-attribute crash waiting for the first tray click.
    assert "shell._win" not in source and "._win." not in source

    # The rule that replaced it lives in `presence_mode`, which every banner
    # path already consults.
    from core import presence_mode
    presence_mode.reset()
    presence_mode.set_mode("quiet")
    assert presence_mode.allows_banner() is False
    presence_mode.reset()


def test_notifications_can_be_switched_off(isolated_config):
    assert isolated_config.get_desktop_notifications() is True   # default on
    assert isolated_config.save_desktop_notifications(False) is True
    assert isolated_config.get_desktop_notifications() is False


# ── the setting that used to have a row ───────────────────────────────────

def test_the_notification_setting_has_no_surface_and_is_said_not_hidden():
    """The toggle lived in a settings drawer; the drawer went with the window.

    It is not silently dropped: the setting still exists and still works, so a
    user who turned notifications off keeps them off. What is missing is a way
    to change it from the screen, and that is a documented gap rather than a
    broken checkbox — `docs/mockups/NOT-IN-MOCKUP.md` names the file to edit.
    """
    settings = ROOT / "docs" / "mockups" / "NOT-IN-MOCKUP.md"
    assert settings.exists(), (
        "a setting lost its only control; that has to be written down")
    assert "notifications" in settings.read_text(encoding="utf-8").lower()

    for gone in ("notify_row.py", "drawer_note.py", "settings_drawer.py"):
        assert not (ROOT / "ui" / gone).exists(), f"ui/{gone} is back"
