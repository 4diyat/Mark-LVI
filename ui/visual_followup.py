"""Put a complete visual follow-up draft in the assistant input, never send it."""
from PyQt6.QtWidgets import QLineEdit

from core.i18n import label as _t
from core.visual_followup import fits_qlineedit, question


def question_input(parent):
    field = QLineEdit(parent)
    retranslate_input(field)
    return field


def retranslate_input(field):
    field.setPlaceholderText(_t('visual.custom_question'))
    field.setAccessibleName(_t('visual.custom_question'))


def draft(host, notice, prefix, source, snapshot, custom_question=''):
    field = host._input
    # Even whitespace is the user's draft, and should not be overwritten.
    if field.text():
        notice.setText(_t('visual.draft_busy'))
        return False
    custom_question = custom_question.strip()
    if custom_question:
        prefix = custom_question + ' ' + _t('visual.untrusted_instruction')
    text = question(prefix, source, snapshot)
    if not fits_qlineedit(text, field.maxLength()):
        notice.setText(_t('visual.draft_too_long'))
        return False
    field.setText(text)
    # Guard unusual input masks or other Qt restrictions as well as maxLength.
    if field.text() != text:
        field.clear()
        notice.setText(_t('visual.draft_too_long'))
        return False
    notice.setText(_t('visual.drafted'))
    assistant = host._desktop_windows['assistant']
    assistant.showNormal()
    host._desktop_mdi.setActiveSubWindow(assistant)
    field.setFocus()
    return True
