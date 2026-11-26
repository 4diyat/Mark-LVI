"""The main panel displays real session exchanges, never mockup sample data."""
from __future__ import annotations

from types import SimpleNamespace

from tests.qtstub import fresh_ui, restore_ui


def test_panel_command_and_exchanges_are_bounded_and_escaped():
    saved = fresh_ui()
    try:
        from ui.tray_panel import TrayPanel
        from ui.tray_pages import render_conversation

        sent = []
        panel = TrayPanel({"command": lambda text: sent.append(text)})
        assert panel.open()
        assert panel.submit_command("  hello <b>  ")
        assert sent == ["hello <b>"]
        assert panel._messages == [("user", "hello <b>")]
        panel.add_message("assistant", "A & B")

        class View:
            def setHtml(self, value):
                self.html = value
            def verticalScrollBar(self):
                return None

        panel._conversation = View()
        render_conversation(panel)
        assert "hello &lt;b&gt;" in panel._conversation.html
        assert "A &amp; B" in panel._conversation.html
        for i in range(105):
            panel.add_message("assistant", str(i))
        assert len(panel._messages) == 100
        assert panel._messages[-1] == ("assistant", "104")
    finally:
        restore_ui(saved)


def test_failed_send_keeps_text_and_is_not_shown_as_a_message():
    saved = fresh_ui()
    try:
        from ui.tray_panel import TrayPanel
        panel = TrayPanel({"command": lambda _text: False})
        assert panel.open()
        panel._field.setText("keep this")
        assert not panel.submit_command()
        assert panel._field.text() == "keep this"
        assert panel._messages == []
    finally:
        restore_ui(saved)


def test_only_explicit_speaker_prefixes_reach_the_panel():
    from ui.voice_wiring import show_panel_exchange

    messages = []
    panel = SimpleNamespace(add_message=lambda role, text: messages.append((role, text)))
    shell = SimpleNamespace(_panel=panel, _assistant_name="Ada")
    for line in ("SYS: ready", "ERR: oops", "TOOL: done", "unprefixed log",
                 "You: hello", "Ada: hi: there"):
        show_panel_exchange(shell, line)
    assert messages == [("user", "hello"), ("assistant", "hi: there")]


def test_page_switch_refreshes_and_has_a_return_control():
    saved = fresh_ui()
    try:
        from ui.tray_panel import TrayPanel
        panel = TrayPanel({})
        assert panel.open()
        assert panel.set_page("memory")
        assert panel._buttons["panel_back"].isVisible()
        assert not panel._buttons["nav:orb"].isVisible()
        assert panel.set_page("main")
        assert not panel._buttons["panel_back"].isVisible()
        assert panel._buttons["nav:orb"].isVisible()
    finally:
        restore_ui(saved)


def test_send_button_passes_the_field_not_the_qt_checked_flag():
    saved = fresh_ui()
    try:
        from ui.tray_panel import TrayPanel
        sent = []
        panel = TrayPanel({"command": lambda text: sent.append(text)})
        assert panel.open()
        panel._field.setText("hello")
        panel._buttons["send"].clicked.emit(False)
        assert sent == ["hello"]
    finally:
        restore_ui(saved)


def test_worker_dispatch_uses_the_qt_owned_receiver(monkeypatch):
    from ui import qt_thread

    queued = []
    dispatcher = SimpleNamespace(queued=SimpleNamespace(emit=queued.append))
    monkeypatch.setattr(qt_thread, "_dispatcher", dispatcher)
    result = []
    qt_thread.run_on_qt_thread(0, lambda: result.append("delivered"))
    assert result == []
    assert len(queued) == 1
    queued[0]()
    assert result == ["delivered"]


def test_real_qt_event_loop_delivers_worker_call_to_owner_thread():
    """Run in a subprocess so a live Qt application cannot leak into other tests."""
    import subprocess
    import sys
    import pytest

    code = '''
import sys, threading
try:
    from PyQt6.QtCore import QCoreApplication, QTimer
except ImportError:
    sys.exit(77)
from ui import qt_thread
app = QCoreApplication([])
qt_thread.init_dispatcher()
assert qt_thread._dispatcher is not None
owner = threading.get_ident()
received = []
def work():
    received.append(threading.get_ident())
    app.quit()
t = threading.Thread(target=lambda: qt_thread.run_on_qt_thread(owner, work))
t.start()
t.join()
QTimer.singleShot(2000, app.quit)
app.exec()
assert received == [owner], received
'''
    result = subprocess.run([sys.executable, "-c", code], capture_output=True,
                            text=True, timeout=10)
    if result.returncode == 77:
        pytest.skip("PyQt6 QtCore not installed")
    assert result.returncode == 0, result.stderr


def test_quick_cards_prepare_localized_drafts_without_sending_or_overwriting():
    saved = fresh_ui()
    try:
        from core import i18n
        from ui.tray_panel import TrayPanel
        i18n.set_locale("id")
        sent = []
        panel = TrayPanel({"command": lambda text: sent.append(text)})
        assert panel.open()
        panel._buttons["quick:summarize"].clicked.emit(False)
        assert panel._field.text() == i18n.label("ui.panel.card.summarize.prompt")
        assert sent == []
        panel._field.setText("draf yang belum selesai")
        panel._buttons["quick:analyze"].clicked.emit(False)
        assert panel._field.text() == "draf yang belum selesai"
        panel._field.clear()
        panel._buttons["quick:chat"].clicked.emit(False)
        assert panel._field.text() == ""
        assert sent == []
    finally:
        i18n.set_locale("en")
        restore_ui(saved)


def test_legacy_capture_and_dictation_remain_on_the_tools_page():
    saved = fresh_ui()
    try:
        from ui.tray_panel import TrayPanel
        calls = []
        panel = TrayPanel({"quick": calls.append})
        assert panel.open() and panel.set_page("tools")
        panel._buttons["tl_quick:screenshot"].clicked.emit(False)
        panel._buttons["tl_quick:dictate"].clicked.emit(False)
        assert calls == ["screenshot", "dictate"]
    finally:
        restore_ui(saved)


def test_microphone_availability_is_not_a_fake_permission_switch(monkeypatch):
    from core import audio_devices
    from ui.tray_panel_model import _permissions

    monkeypatch.setattr(audio_devices, "input_available", lambda: True)
    assert _permissions()["microphone"] == {"on": True, "fixed": True, "note": ""}


def test_missing_command_callback_does_not_clear_the_users_draft():
    from ui import ambient_shell, tray_panel_wiring
    shell = SimpleNamespace(on_text_command=None)
    assert ambient_shell.submit_from_bar(shell, "hello") is False
    assert tray_panel_wiring.send_command(shell, "hello") is False


def test_command_bar_also_adds_its_sent_message_to_the_panel(monkeypatch):
    from ui import ambient_shell
    messages = []
    panel = SimpleNamespace(add_message=lambda role, text: messages.append((role, text)))
    shell = SimpleNamespace(_panel=panel)
    monkeypatch.setattr(ambient_shell, "submit_from_bar", lambda _shell, _text: True)
    assert ambient_shell.submit_command_bar(shell, "hello")
    assert messages == [("user", "hello")]
    monkeypatch.setattr(ambient_shell, "submit_from_bar", lambda _shell, _text: False)
    assert not ambient_shell.submit_command_bar(shell, "not sent")
    assert messages == [("user", "hello")]


def test_configured_assistant_name_is_displayed_and_escaped():
    saved = fresh_ui()
    try:
        from ui.tray_panel import TrayPanel
        from ui.voice_wiring import show_panel_exchange
        panel = TrayPanel({})
        assert panel.open()
        shell = SimpleNamespace(_panel=panel, _assistant_name="Ada <AI>")
        show_panel_exchange(shell, "Ada <AI>: Hello")
        assert panel._messages == [("assistant", "Hello")]
        class View:
            def setHtml(self, value):
                self.html = value
            def verticalScrollBar(self):
                return None
        panel._conversation = View()
        panel._render_conversation()
        assert "Ada &lt;AI&gt;" in panel._conversation.html
    finally:
        restore_ui(saved)


def test_layout_preference_does_not_claim_to_move_windows(monkeypatch):
    from actions import window_layout
    from ui import pages_actions
    from core import i18n

    i18n.set_locale("id")
    calls, messages = [], []
    decision = SimpleNamespace(allowed=True, reason="unused")
    monkeypatch.setattr(window_layout, "choose", lambda mode: calls.append(mode) or decision)
    monkeypatch.setattr(window_layout, "apply", lambda _decision: True)
    monkeypatch.setattr(pages_actions, "_refresh", lambda _shell: None)
    monkeypatch.setattr(pages_actions, "_say", lambda _shell, text: messages.append(text))
    try:
        assert not pages_actions.tools_layout(None, -1)
        assert not calls
        assert pages_actions.tools_layout(None, 1)
        assert calls == ["columns3"]
        assert "tidak dipindahkan" in messages[-1]
        assert "tidak dipindahkan" in i18n.label("ui.page.tools.snap_note", mode="2 kolom")
    finally:
        i18n.set_locale("en")
