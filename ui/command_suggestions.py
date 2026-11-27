"""Non-executing prompt suggestions; never call them tool-risk classifications.

Natural language is sent to the model and cannot predict which tools it will
choose. Selection only fills the editor; actual tool calls still go through
their own guards where wired. Suggestions are never coloured as approved.
"""


def install(field, window):
    from PyQt6.QtCore import QSize
    from PyQt6.QtWidgets import QMenu, QToolButton
    from ui.hud_icons import icon
    from ui.hud_pages import tr

    prompts = [
        tr('Tampilkan status sistem', 'Show system status'),
        tr('Jelaskan kemampuanmu', 'Explain what you can do'),
        tr('Bagaimana cara menjaga privasi?', 'How can I protect my privacy?'),
    ]
    button = QToolButton(window)
    button.setIcon(icon('sparkles', '#58aaff', 28))
    button.setIconSize(QSize(28, 28))
    button.setAccessibleName(tr('Saran perintah', 'Prompt suggestions'))
    button.setToolTip(tr('Pilih hanya mengisi draf, tidak mengirim.',
                         'Selecting only fills the draft; it does not send.'))
    button.setGeometry(856, 82, 60, 52)
    button.setStyleSheet('QToolButton { background:transparent; border:0; border-left:1px solid #304155; } '
                         'QToolButton:hover { background:#172a40; } QToolButton::menu-indicator { image:none; }')
    menu = QMenu(button)
    menu.setStyleSheet('QMenu { background:#14273a; color:#e1effa; border:1px solid #427493; padding:5px; } '
                       'QMenu::item { padding:7px 12px; } QMenu::item:selected { background:#285274; }')
    def select(text):
        if field.isEnabled():
            field.setText(text)
            field.setFocus()
    for prompt in prompts:
        action = menu.addAction(prompt)
        action.triggered.connect(lambda _checked=False, text=prompt: select(text))
    button.setMenu(menu)
    button.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
    return button
