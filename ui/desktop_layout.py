"""Desktop navigation and conversation surfaces; the window owns all callbacks.

This module only builds widgets on the Qt thread. Audio, file drops, plugin
consent and action confirmation remain owned by MainWindow and their existing
signals; rearranging them must not create another session or another log.
"""
from PyQt6.QtCore import QObject, Qt
from PyQt6.QtGui import QFont
from PyQt6.QtWidgets import (QApplication, QHBoxLayout, QLabel, QLineEdit, QMenu,
                             QPlainTextEdit, QPushButton, QSizePolicy, QTextEdit, QToolButton,
                             QVBoxLayout, QWidget)

from core.i18n import label as _t
from ui.theme import C, workspace_stylesheet


class _EditFocusTracker(QObject):
    """Keep the last text focus only while its Edit menu takes focus."""
    def __init__(self, parent):
        super().__init__(parent)
        self.target = None
        self.button = None
        self.menu = None

    def changed(self, old, new):
        del old
        if isinstance(new, (QLineEdit, QPlainTextEdit, QTextEdit)):
            self.target = new
        elif new is not None and new is not self.button and new is not self.menu:
            self.target = None


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
    layout.setContentsMargins(12, 10, 12, 12)
    layout.setSpacing(7)
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
    window._log.setStyleSheet(f"QTextEdit {{ background: {C.DESKTOP_PANEL}; color: {C.DESKTOP_TEXT}; "
                              f"border: none; border-radius: 10px; padding: 10px; }}")
    layout.addWidget(window._log, stretch=1)
    window._file_heading = _label(_t("desktop.files"), 8, bold=True)
    layout.addWidget(window._file_heading)
    window._file_heading.hide()
    window._attachment_toggle = QPushButton(_t("desktop.attach"))
    window._attachment_toggle.setCheckable(True)
    window._attachment_toggle.setStyleSheet(f"QPushButton {{ color: {C.DESKTOP_MUTED}; background: transparent; "
                                             "border: none; text-align: left; padding: 4px; }")
    window._drop_zone = drop_cls()
    window._drop_zone.file_selected.connect(window._on_file_selected)
    window._file_hint = _label(_t("ui.drop.empty"), 8)
    window._file_hint.setWordWrap(True)
    window._drop_zone.hide()
    window._file_hint.hide()
    def toggle_attachment(checked):
        window._drop_zone.setVisible(checked)
        window._file_hint.setVisible(checked)
        window._attachment_toggle.setText(_t("desktop.hide_attach" if checked else "desktop.attach"))
    window._attachment_toggle.toggled.connect(toggle_attachment)
    # Suggestions are optional drafts, never commands sent on the user's behalf.
    window._suggestions_card = QWidget()
    window._suggestions_card.setObjectName("AssistantSuggestions")
    window._suggestions_card.setStyleSheet(
        f"QWidget#AssistantSuggestions {{ background: {C.DESKTOP_PANEL}; "
        f"border: 1px solid {C.DESKTOP_BORDER}; border-radius: 10px; }}")
    suggestions = QVBoxLayout(window._suggestions_card)
    suggestions.setContentsMargins(9, 7, 9, 7)
    suggestions.setSpacing(4)
    window._suggestions_heading = _label(_t("desktop.suggestions"), 8, bold=True, color=C.DESKTOP_MUTED)
    suggestions.addWidget(window._suggestions_heading)
    window._suggestion_buttons = []
    for key in ("desktop.suggest_tasks", "desktop.suggest_timeline", "desktop.suggest_release"):
        button = QPushButton(_t(key))
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setStyleSheet(f"QPushButton {{ text-align: left; padding: 5px 9px; color: {C.DESKTOP_TEXT}; "
                             f"background: {C.DESKTOP_DOCK}; border: 1px solid {C.DESKTOP_BORDER}; "
                             "border-radius: 8px; } QPushButton:hover { border-color: #69c8f4; }")
        def draft(_checked=False, prompt_key=key):
            # Do not destroy an unsent draft, and never submit automatically.
            if not window._input.text().strip():
                window._input.setText(_t(prompt_key))
            window._input.setFocus()
        button.clicked.connect(draft)
        suggestions.addWidget(button)
        window._suggestion_buttons.append((button, key))
    layout.addWidget(window._suggestions_card)
    layout.addWidget(window._attachment_toggle)
    layout.addWidget(window._drop_zone)
    layout.addWidget(window._file_hint)
    layout.addLayout(window._build_input_row())
    return panel


def refresh_assistant_tools(window):
    """Collapse the auxiliary splitter only when all of its sections are hidden."""
    split = getattr(window, "_center_split", None)
    sections = tuple(getattr(window, name, None) for name in
                     ("_hud_cam_stack", "_content_panel", "_quiz_panel", "_audio_cont"))
    if split is not None and all(section is not None for section in sections):
        split.setVisible(any(not section.isHidden() for section in sections))


def set_assistant_tool(window, section, visible):
    section.setVisible(visible)
    refresh_assistant_tools(window)


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
    window._assistant_mark = _label("◉", 20, bold=True, color=C.PRI)
    window._assistant_mark.setAccessibleName(window._assistant_name)
    header.addWidget(window._assistant_mark)
    header.addWidget(window._assistant_heading)
    header.addStretch()
    header.addWidget(window._desktop_state)
    layout.addLayout(header)
    window.hud.setMinimumSize(110, 110)
    layout.addWidget(window._center_split, stretch=1)
    # Keep the real conversation and input as the primary surface. The HUD and
    # existing tool/media panes remain available in the splitter above it.
    layout.addWidget(window._right_panel, stretch=4)
    window._voice_hint = _label(_t("desktop.voice_hint"), 8)
    window._voice_hint.setWordWrap(True)
    layout.addWidget(window._voice_hint)
    window._mute_btn = QPushButton(_t("ui.mic.active"))
    window._mute_btn.setFixedHeight(28)
    window._mute_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    window._mute_btn.clicked.connect(window._toggle_mute)
    window._style_mute_btn()
    voice_controls = QHBoxLayout()
    voice_controls.addWidget(window._mute_btn)
    window._interrupt_btn = QPushButton(_t("ui.interrupt"))
    window._interrupt_btn.setFixedHeight(28)
    window._interrupt_btn.setCursor(Qt.CursorShape.PointingHandCursor)
    window._interrupt_btn.setStyleSheet(f"""
        QPushButton {{ background: {C.DESKTOP_DOCK}; color: {C.DESKTOP_TEXT};
                       border: 1px solid {C.DESKTOP_BORDER}; border-radius: 6px; }}
        QPushButton:hover {{ border-color: {C.MUTED_C}; }}
    """)
    window._interrupt_btn.clicked.connect(window._do_interrupt)
    voice_controls.addWidget(window._interrupt_btn)
    layout.addLayout(voice_controls)
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
    window._suggestions_heading.setText(_t("desktop.suggestions"))
    for button, key in window._suggestion_buttons:
        button.setText(_t(key))
    for widget, key in getattr(window, "_desktop_menu_labels", ()):
        widget.setText(_t(key))
    window._ctrl_btn.setText(_t("desktop.controls"))
    window._drawer_btn.setText(_t("desktop.settings"))
    update_state(window, window.hud.state)


def state_label(state):
    """Translate only the authoritative HUD state, not a decorative guess."""
    key = {"LISTENING": "desktop.state_listening", "SPEAKING": "desktop.state_speaking",
           "SLEEPING": "desktop.state_sleeping", "MUTED": "desktop.state_muted",
           "NO MIC": "desktop.state_no_mic", "THINKING": "desktop.state_thinking",
           "PROCESSING": "desktop.state_processing", "IDLE": "desktop.state_idle"}.get(state, "desktop.initialising")
    return _t(key)


def update_state(window, state):
    window._desktop_state.setText(state_label(state))


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
    # An original JARVIS mark rather than an operating-system brand.
    mark = _label("◉", 17, bold=True, color="#6ed8ff")
    mark.setAccessibleName("JARVIS")
    row.addWidget(mark)
    window._title_lbl = _label(window._assistant_name.upper(), 9, bold=True, color=C.DESKTOP_TEXT)
    row.addWidget(window._title_lbl)
    window._sub_lbl = _label("", 7, color=C.DESKTOP_MUTED)
    window._sub_lbl.hide()  # retained for existing name/locale updates
    row.addWidget(window._sub_lbl)
    window._desktop_menu_labels = []
    window._desktop_menus = {}
    window._desktop_focus_tracker = _EditFocusTracker(window)
    QApplication.instance().focusChanged.connect(window._desktop_focus_tracker.changed)

    def workspace_action(action, target):
        from ui.workspace_commands import execute
        result = execute(window, {"action": action, "target": target})
        if not result.get("ok"):
            window.write_log("SYS: " + result.get("message", ""))

    def edit_action(method):
        widget = window._desktop_focus_tracker.target
        try:
            if isinstance(widget, (QLineEdit, QPlainTextEdit, QTextEdit)):
                getattr(widget, method)()
        except RuntimeError:
            pass  # The focused document was closed after the menu opened.

    def update_edit_actions():
        widget = QApplication.focusWidget()
        if isinstance(widget, (QLineEdit, QPlainTextEdit, QTextEdit)):
            window._desktop_focus_tracker.target = widget
        for action in window._desktop_edit_actions:
            action.setEnabled(window._desktop_focus_tracker.target is not None)

    def help_action():
        window._show_content(_t("desktop.menu_help"), _t("desktop.menu_help_content"))

    groups = (
        ("desktop.menu_file", (("workspace.files", lambda: workspace_action("focus", "files")),
                               ("workspace.code", lambda: workspace_action("open", "code_editor")),
                               ("workspace.image", lambda: workspace_action("open", "image_editor")))),
        ("desktop.menu_edit", (("desktop.menu_undo", lambda: edit_action("undo")),
                               ("desktop.menu_redo", lambda: edit_action("redo")),
                               ("desktop.menu_cut", lambda: edit_action("cut")),
                               ("desktop.menu_copy", lambda: edit_action("copy")),
                               ("desktop.menu_paste", lambda: edit_action("paste")),
                               ("desktop.menu_select_all", lambda: edit_action("selectAll")))),
        ("desktop.menu_view", (("workspace.assistant", lambda: workspace_action("focus", "assistant")),
                               ("workspace.navigation", lambda: workspace_action("focus", "navigation")))),
        ("desktop.menu_window", (("workspace.minimize", lambda: workspace_action("minimize", "active")),
                                 ("workspace.restore_clap", lambda: window._desktop_mdi.restore_clap_windows()))),
        ("desktop.menu_help", (("desktop.menu_help", help_action),)),
    )
    for key, entries in groups:
        button = QToolButton()
        button.setText(_t(key))
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setStyleSheet(f"QToolButton {{ color: {C.DESKTOP_TEXT}; background: transparent; "
                             "border: none; padding: 0 4px; } "
                             f"QToolButton:hover {{ background: {C.DESKTOP_DOCK}; border-radius: 4px; }}")
        menu = QMenu(button)
        menu.setStyleSheet(workspace_stylesheet())
        actions = []
        for label_key, callback in entries:
            action = menu.addAction(_t(label_key))
            action.triggered.connect(lambda _checked=False, fn=callback: fn())
            window._desktop_menu_labels.append((action, label_key))
            actions.append(action)
        if key == "desktop.menu_edit":
            window._desktop_edit_actions = actions
            window._desktop_focus_tracker.button = button
            window._desktop_focus_tracker.menu = menu
            menu.aboutToShow.connect(update_edit_actions)
        window._desktop_menus[key] = (button, menu)
        window._desktop_menu_labels.append((button, key))
        button.setMenu(menu)
        button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        row.addWidget(button)
    row.addStretch(1)
    # This badge is driven by the real hand controller, not by the mockup.
    window._hand_badge = _label("", 8, bold=True, color="#83e4b6")
    window._hand_badge.setAccessibleName(_t("gesture.badge_accessible"))
    window._hand_badge.setStyleSheet(f"color: #83e4b6; background: {C.DESKTOP_DOCK}; "
                                     "border: 1px solid #326b66; border-radius: 8px; padding: 3px 8px;")
    window._hand_badge.hide()
    row.addWidget(window._hand_badge)
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
