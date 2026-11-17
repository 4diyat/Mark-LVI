"""Open a local manual SSH panel; this plugin cannot execute commands."""
PLUGIN = {
    'name': 'ssh_manager',
    'description': ('Open the manual SSH manager in JARVIS. The user connects and confirms every command locally. '
                    'Never ask for passwords or keys. This plugin cannot read output or execute commands.'),
    'parameters': {'type': 'OBJECT', 'properties': {}, 'required': []},
    'behavior': 'NON_BLOCKING', 'scheduling': 'WHEN_IDLE', 'tier': 'core',
}


def run(parameters, player=None, session_memory=None):
    del parameters, session_memory
    callback = getattr(player, 'show_code_job', None) if player is not None else None
    if not callable(callback):
        return 'The SSH manager requires the desktop interface.'
    try:
        callback({'kind': 'ssh_manager'})
        return 'Requested the manual SSH manager. Connect and approve commands locally.'
    except Exception:
        return 'Could not request the SSH manager.'
