"""Desktop navigation and conversation surfaces; the window owns all callbacks.

This module only builds widgets on the Qt thread. Audio, file drops, plugin
consent and action confirmation remain owned by MainWindow and their existing
signals; rearranging them must not create another session or another log.
"""
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget

from core.i18n import label as _t
from ui.theme import C


def _label(text, size=9, *, bold=False, color=None):
    label = QLabel(text)
    label.setFont(QFont("Arial", size, QFont.Weight.Bold if bold else QFont.Weight.Normal))
    label.setStyleSheet(f"color: {color or C.TEXT_MED}; background: transparent; border: none;")
    return label


def build_navigation(window, metric_cls, width):
    panel = QWidget()
    panel.setObjectName("DesktopNavigation")
    panel.setFixedWidth(width)
    panel.setStyleSheet(f"QWidget#DesktopNavigation {{ background: {C.DARK}; border-right: 1px solid {C.BORDER}; }}")
    layout = QVBoxLayout(panel)
    layout.setContentsMargins(10, 14, 10, 10)
    layout.setSpacing(5)
    window._nav_title = _label(_t("desktop.navigation"), 8, bold=True, color=C.PRI_DIM)
    layout.addWidget(window._nav_title)
    window._desktop_nav = []
    buttons = (
        ("desktop.conversation", lambda: window._input.setFocus()),
        ("desktop.activity", lambda: window._log.setFocus()),
        ("desktop.plugins", window._open_plugin_manager),
        ("desktop.remote", window._open_remote),
        ("desktop.settings", lambda: window._drawer_btn.click()),
        ("desktop.controls", lambda: window._ctrl_btn.click()),
    )
    for key, callback in buttons:
        button = QPushButton(_t(key))
        button.setFixedHeight(32)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setFont(QFont("Arial", 9))
        button.setStyleSheet(f"""
            QPushButton {{ text-align: left; padding: 0 9px; color: {C.TEXT};
                           background: {C.PANEL}; border: 1px solid {C.BORDER}; border-radius: 5px; }}
            QPushButton:hover, QPushButton:focus {{ color: {C.PRI}; border-color: {C.PRI_DIM}; }}
        """)
        # clicked carries a bool; do not pass it to slots that take no args.
        button.clicked.connect(lambda _checked=False, fn=callback: fn())
        layout.addWidget(button)
        window._desktop_nav.append((button, key))
    layout.addSpacing(8)
    window._metrics_heading = _label(_t("desktop.system"), 8, bold=True, color=C.PRI_DIM)
    layout.addWidget(window._metrics_heading)
    window._bar_cpu = metric_cls("CPU", C.PRI)
    window._bar_mem = metric_cls("MEM", C.ACC2)
    window._bar_net = metric_cls("NET", C.GREEN)
    window._bar_gpu = metric_cls("GPU", C.ACC)
    window._bar_tmp = metric_cls("TMP", "#ff6688")
    for bar in (window._bar_cpu, window._bar_mem, window._bar_net, window._bar_gpu, window._bar_tmp):
        layout.addWidget(bar)
    layout.addStretch()
    window._uptime_lbl = _label(_t("ui.uptime_idle"), 8, color=C.GREEN)
    window._proc_lbl = _label(_t("ui.proc_idle"), 8)
    layout.addWidget(window._uptime_lbl)
    layout.addWidget(window._proc_lbl)
    return panel


def build_conversation(window, log_cls, drop_cls):
    panel = QWidget()
    panel.setObjectName("DesktopConversation")
    panel.setMinimumWidth(280)
    panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    panel.setStyleSheet(f"QWidget#DesktopConversation {{ background: {C.DESKTOP_PANEL}; border: none; }}")
    layout = QVBoxLayout(panel)
    layout.setContentsMargins(8, 6, 8, 8)
    layout.setSpacing(5)
    window._conversation_heading = _label(_t("desktop.conversation"), 15, bold=True, color=C.WHITE)
    window._conversation_subtitle = _label(_t("desktop.conversation_hint"), 8)
    # The window title already identifies this panel; keep labels for locale
    # updates but give the real conversation the available vertical space.
    layout.addWidget(window._conversation_heading)
    layout.addWidget(window._conversation_subtitle)
    window._conversation_heading.hide()
    window._conversation_subtitle.hide()
    window._log = log_cls()
    window._log._ai_name_lc = window._assistant_name.lower()
    window._log.setFont(QFont("Arial", 10))
    window._log.setMinimumHeight(48)
    window._log.setStyleSheet(f"QTextEdit {{ background: {C.DESKTOP_DOCK}; color: {C.DESKTOP_TEXT}; "
                              f"border: none; border-radius: 10px; padding: 10px; }}")
    layout.addWidget(window._log, stretch=1)
    window._file_heading = _label(_t("desktop.files"), 8, bold=True)
    layout.addWidget(window._file_heading)
    window._file_heading.hide()
    window._attachment_toggle = QPushButton(_t("desktop.attach"))
    window._attachment_toggle.setCheckable(True)
    window._attachment_toggle.setStyleSheet(f"QPushButton {{ color: {C.DESKTOP_MUTED}; background: transparent; "
                                             "border: none; text-align: left; padding: 4px; }")
    layout.addWidget(window._attachment_toggle)
    window._drop_zone = drop_cls()
    window._drop_zone.file_selected.connect(window._on_file_selected)
    layout.addWidget(window._drop_zone)
    window._file_hint = _label(_t("ui.drop.empty"), 8)
    window._file_hint.setWordWrap(True)
    layout.addWidget(window._file_hint)
    window._drop_zone.hide()
    window._file_hint.hide()
    def toggle_attachment(checked):
        window._drop_zone.setVisible(checked)
        window._file_hint.setVisible(checked)
        window._attachment_toggle.setText(_t("desktop.hide_attach" if checked else "desktop.attach"))
    window._attachment_toggle.toggled.connect(toggle_attachment)
    layout.addLayout(window._build_input_row())
    return panel


def build_assistant_panel(window):
    """Place the existing HUD, workspace, media and voice controls together."""
    panel = QWidget()
    panel.setObjectName("DesktopAssistant")
    panel.setMinimumWidth(240)
    panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
    panel.setStyleSheet(f"QWidget#DesktopAssistant {{ background: {C.DESKTOP_PANEL}; }}")
    layout = QVBoxLayout(panel)
    layout.setContentsMargins(10, 8, 10, 8)
    layout.setSpacing(5)
    header = QHBoxLayout()
    window._assistant_heading = _label(window._assistant_name, 13, bold=True, color=C.WHITE)
    window._desktop_state = _label(_t("desktop.initialising"), 8, color=C.PRI)
    header.addWidget(window._assistant_heading)
    header.addStretch()
    header.addWidget(window._desktop_state)
    layout.addLayout(header)
    window.hud.setMinimumSize(110, 110)
    layout.addWidget(window._center_split, stretch=2)
    # Keep the real conversation and input in the assistant window, not a mock.
    layout.addWidget(window._right_panel, stretch=3)
    window._voice_hint = _label(_t("desktop.voice_hint"), 8)
    window._voice_hint.setWordWrap(True)
    layout.addWidget(window._voice_hint)
    window._mute_btn = QPushButton(_t("ui.mic.active"))
    window._mute_btn.setFixedHeight(28)
    window._mute_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    window._mute_btn.clicked.connect(window._toggle_mute)
    window._style_mute_btn()
    layout.addWidget(window._mute_btn)
    window._interrupt_btn = QPushButton(_t("ui.interrupt"))
    window._interrupt_btn.setFixedHeight(28)
    window._interrupt_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    window._interrupt_btn.setStyleSheet(f"""
        QPushButton {{ background: {C.DESKTOP_DOCK}; color: {C.DESKTOP_TEXT};
                       border: 1px solid {C.DESKTOP_BORDER}; border-radius: 6px; }}
        QPushButton:hover {{ border-color: {C.MUTED_C}; }}
    """)
    window._interrupt_btn.clicked.connect(window._do_interrupt)
    layout.addWidget(window._interrupt_btn)
    return panel


def retranslate(window):
    for button, key in window._desktop_nav:
        button.setText(_t(key))
    for attr, key in (("_nav_title", "desktop.navigation"), ("_metrics_heading", "desktop.system"),
                      ("_conversation_heading", "desktop.conversation"),
                      ("_conversation_subtitle", "desktop.conversation_hint"),
                      ("_file_heading", "desktop.files"),
                      ("_voice_hint", "desktop.voice_hint"), ("_interrupt_btn", "ui.interrupt")):
        getattr(window, attr).setText(_t(key))
    window._attachment_toggle.setText(_t("desktop.hide_attach" if window._attachment_toggle.isChecked() else "desktop.attach"))
    window._ctrl_btn.setText(_t("desktop.controls"))
    window._drawer_btn.setText(_t("desktop.settings"))
    update_state(window, window.hud.state)


def update_state(window, state):
    # The HUD remains authoritative; never infer that a microphone or service is
    # connected from a decorative badge.
    key = {"LISTENING": "desktop.state_listening", "SPEAKING": "desktop.state_speaking",
           "SLEEPING": "desktop.state_sleeping", "MUTED": "desktop.state_muted",
           "NO MIC": "desktop.state_no_mic", "THINKING": "desktop.state_thinking",
           "PROCESSING": "desktop.state_processing", "IDLE": "desktop.state_idle"}.get(state, "desktop.initialising")
    window._desktop_state.setText(_t(key))


def build_menu_bar(window):
    """Compact top bar; existing settings and controls still use their slots."""
    bar = QWidget()
    bar.setObjectName("DesktopMenuBar")
    bar.setFixedHeight(30)
    window._desktop_menu_bar = bar
    bar.setStyleSheet(f"QWidget#DesktopMenuBar {{ background: {C.DESKTOP_BAR}; "
                      f"border-bottom: 1px solid {C.DESKTOP_BORDER}; }}")
    row = QHBoxLayout(bar)
    row.setContentsMargins(14, 0, 14, 0)
    row.setSpacing(12)
    window._title_lbl = _label(window._assistant_name.upper(), 9, bold=True, color=C.DESKTOP_TEXT)
    row.addWidget(window._title_lbl)
    window._sub_lbl = _label("", 7, color=C.DESKTOP_MUTED)
    window._sub_lbl.hide()  # retained for existing name/locale updates
    row.addWidget(window._sub_lbl)
    row.addStretch(1)
    window._clock_lbl = _label("00:00", 9, color=C.DESKTOP_TEXT)
    row.addWidget(window._clock_lbl)
    window._date_lbl = _label("", 8, color=C.DESKTOP_MUTED)
    row.addWidget(window._date_lbl)
    def menu_button(text, tip, slot):
        button = QPushButton(text)
        button.setCheckable(True)
        button.setToolTip(_t(tip))
        button.setFixedHeight(24)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setStyleSheet(f"QPushButton {{ background: transparent; color: {C.DESKTOP_TEXT}; "
                             f"border: none; padding: 0 6px; }} "
                             f"QPushButton:hover, QPushButton:checked {{ background: {C.DESKTOP_DOCK}; "
                             "border-radius: 4px; }")
        button.clicked.connect(slot)
        row.addWidget(button)
        return button
    window._ctrl_btn = menu_button(_t("desktop.controls"), "ui.controls_button", window._toggle_controls)
    window._drawer_btn = menu_button(_t("desktop.settings"), "ui.setup_button", window._toggle_drawer)
    return bar
