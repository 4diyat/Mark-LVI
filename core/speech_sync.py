"""Small loop-to-UI bridge for estimated playback-time speech captions."""


def reset(owner):
    owner._caption_epoch = getattr(owner, '_caption_epoch', 0) + 1
    send = getattr(owner.ui, 'speech_caption', None)
    if callable(send):
        send({'kind': 'reset', 'epoch': owner._caption_epoch})


def schedule(owner, text, at):
    send = getattr(owner.ui, 'speech_caption', None)
    if callable(send):
        send({'kind': 'caption', 'epoch': getattr(owner, '_caption_epoch', 0),
              'text': text, 'at': at})
