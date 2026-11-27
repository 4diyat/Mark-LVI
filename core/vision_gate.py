"""Run a vision capture through the tool gate without putting image bytes in audit."""
from core import action_gate


def capture(args, capture_fn):
    captured = []
    def run():
        captured.append(capture_fn())
        return 'Image captured.'
    verdict = action_gate.check('screen_process', run, args)
    return (captured[0] if captured else None), verdict.message
