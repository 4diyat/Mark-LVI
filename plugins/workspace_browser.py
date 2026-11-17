"""Request an embedded browser, without granting the assistant vault access."""
from core.browser_url import validate_browser_url

PLUGIN = {
    'name': 'workspace_browser',
    'description': ('Open an explicit HTTP or HTTPS URL requested by the user in the JARVIS workspace browser. '
                    'This only requests navigation, never reads a page or saved credentials.'),
    'parameters': {'type': 'OBJECT', 'properties': {
        'url': {'type': 'STRING', 'description': 'Explicit URL requested by the user.'}}, 'required': ['url']},
    'behavior': 'NON_BLOCKING', 'scheduling': 'WHEN_IDLE', 'tier': 'core',
}


def run(parameters, player=None, session_memory=None):
    del session_memory
    try:
        url = validate_browser_url(parameters.get('url') if isinstance(parameters, dict) else None)
        callback = getattr(player, 'show_code_job', None) if player is not None else None
        if not callable(callback):
            return 'The internal browser requires the desktop interface.'
        callback({'kind': 'workspace_browser', 'url': url})
        return 'Requested the internal browser. Check the window for loading status.'
    except ValueError:
        return 'Provide a valid HTTP or HTTPS URL without embedded credentials.'
    except Exception:
        return 'Could not request the internal browser.'
