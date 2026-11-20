"""Worker-to-Qt request bridge for the two interactive content families."""
import threading

from core.workspace_control import WorkspaceRequest


def _parts(kind):
    if kind == 'narrative':
        from core.narrative_content import validate
        return validate, '_narrative_content_sig'
    if kind == 'chart':
        from core.visual_content import validate
        return validate, '_visual_content_sig'
    raise ValueError('Unknown content type')


def request(window, kind, payload):
    if threading.get_ident() == window._ui_thread_id:
        return {'ok': False, 'message': 'Interactive content must be requested from a worker.'}
    try:
        validate, signal = _parts(kind)
        envelope = WorkspaceRequest(validate(payload))
    except ValueError as exc:
        return {'ok': False, 'message': str(exc)}
    getattr(window, signal).emit(envelope)
    return envelope.wait(3.0)


def open_content(window, kind, envelope):
    if not envelope.claim():
        return
    try:
        from ui.desktop_workspace import show_document
        validate, _ = _parts(kind)
        if kind == 'narrative':
            from ui.narrative_content import NarrativeContent
            view = NarrativeContent(window, validate(envelope.command))
            doc_kind = 'narrative_content'
        else:
            from ui.visual_content import VisualContent
            view = VisualContent(window, validate(envelope.command))
            doc_kind = 'visual_content'
        show_document(window, view, doc_kind)
        result = {'ok': True, 'message': 'Interactive content opened. Source attribution is unverified.'}
    except Exception as exc:
        result = {'ok': False, 'message': f'Could not open interactive content: {type(exc).__name__}.'}
    envelope.finish(result)
