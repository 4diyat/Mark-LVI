"""In-memory session conversation shared by lazily created Qt surfaces.

All functions are called on the Qt thread. Messages are capped, are not saved,
and reflect only explicit exchanges and sends whose completion was reported.
"""


def publish(shell, role, text):
    if role not in ('user', 'assistant') or not str(text or '').strip():
        return
    message = (role, str(text).strip())
    rows = getattr(shell, '_session_messages', None)
    if rows is None:
        rows = []; shell._session_messages = rows
    rows.append(message); del rows[:-100]
    for attr in ('_main_surface', '_panel'):
        surface = getattr(shell, attr, None)
        if surface is None:
            continue
        if role == 'assistant' and attr == '_panel':
            surface._assistant_label = str(getattr(shell, '_assistant_name', '') or 'JARVIS')
        surface.add_message(*message)


def hydrate(shell, surface):
    """Initialize a new surface exactly once; never duplicate a cached surface."""
    if surface is None:
        return
    surface._assistant_label = str(getattr(shell, '_assistant_name', '') or 'JARVIS')
    for role, text in getattr(shell, '_session_messages', ()):
        surface.add_message(role, text)
