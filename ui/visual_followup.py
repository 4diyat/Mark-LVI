"""Put a complete visual follow-up draft in the assistant input, never send it."""
from core.i18n import label as _t
from core.visual_followup import fits_qlineedit, question


def draft(host, notice, prefix, source, snapshot):
    field = host._input
    # Even whitespace is the user's draft, and should not be overwritten.
    if field.text():
        notice.setText(_t('visual.draft_busy'))
        return False
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
