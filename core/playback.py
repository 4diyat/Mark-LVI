"""
Playback decisions for the HUD's video and audio — Qt-free, so they can be tested.

WHY THE DECISIONS LIVE HERE AND NOT IN ui/window.py
    The surface itself has to be Qt: a `QMediaPlayer`, a graphics item, an
    output. But almost every bug this feature has ever had is a *decision* made
    around that surface, and decisions can be tested on a machine with no
    display:

      * when a video reaches its end, what should happen? (It used to be
        nothing at all — the HUD froze on the last frame, `video_is_playing()`
        kept answering yes, and if the sound had been on, the microphone stayed
        closed for the rest of the session.)
      * when a second video opens while one is playing, what must be stopped
        first? (It used to be nothing, so a YouTube soundtrack kept playing
        underneath the new file.)
      * when the separate audio stream fails, what does the user see? (It used
        to be a bar that said SOUND ON over silence.)
      * when the sound is 200 ms out of step, is that worth correcting? (No —
        the correction is more audible than the error.)
      * what exactly is a playable source, given the user typed it?

    So the rules are here, written as small pure functions over plain data, and
    `ui/window.py` is reduced to carrying them out. A regression in "the
    microphone is given back when the video ends" becomes a failing assertion
    instead of something discovered by talking to a JARVIS that cannot hear.
"""

from __future__ import annotations

import re
import urllib.parse
from pathlib import Path

# ── what a source is ────────────────────────────────────────────────────────

# Every hostname YouTube actually serves a watchable page from. The first
# version matched only `youtube.com/` and `youtu.be/`, so a link copied from a
# phone (`m.youtube.com`) or from an embed (`youtube-nocookie.com`) was handed
# to Qt as if it were a media file: Qt fetched an HTML page, failed with a
# message about an unsupported format, and the user was told their link was
# broken.
_YT_HOSTS = (
    "youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com",
    "youtu.be", "www.youtu.be", "youtube-nocookie.com",
    "www.youtube-nocookie.com",
)

# Extensions Qt's multimedia backend can open without help. Used only to decide
# whether a bare filename is worth a second look — a file that exists on disk is
# played whatever it is called.
_MEDIA_EXT = (
    ".mp4", ".m4v", ".mkv", ".webm", ".mov", ".avi", ".mpg", ".mpeg", ".wmv",
    ".flv", ".ts", ".m3u8", ".mpd",
)
_AUDIO_EXT = (
    ".mp3", ".m4a", ".aac", ".wav", ".flac", ".ogg", ".oga", ".opus", ".wma",
)

# A bare host with no scheme: "example.com/clip.mp4" typed by a human. Only
# treated as a URL when it has a dot AND a path or a known media extension —
# otherwise "Dune part two.mp4" (a filename with a dot and a space) would be
# requested over HTTP.
_BARE_HOST = re.compile(r"^[\w-]+(\.[\w-]+)+(:\d+)?(/.*)?$", re.I)
# Path endings that mean "a web page", never a media stream.
_PAGE_EXT = (".html", ".htm", ".php", ".asp", ".aspx", ".jsp", "/")

# What a hostname's first label looks like, as opposed to a filename's stem. A
# media or audio extension is the giveaway that the dot belongs to a file.
_HOSTLIKE = re.compile(r"^([\w-]+\.)+[A-Za-z]{2,}$")
# A bare IPv4 endpoint — a camera or a stream on the local network, which has
# no TLD at all and would otherwise fall through as "not a URL".
_IPV4 = re.compile(r"^\d{1,3}(\.\d{1,3}){3}$")


def clean_source(text: str) -> str:
    """The user's words with the wrapping that people paste around paths.

    Explorer's "Copy as path" gives `"C:\\clips\\a b.mp4"` — quotes included —
    and dragging a file into a terminal often adds a trailing newline. Qt treats
    both as part of the filename, so the file "does not exist" and the URL
    branch produces a baffling error instead.
    """
    raw = (text or "").strip()
    # Repeated because a path can be wrapped twice by two different tools.
    for _ in range(2):
        raw = raw.strip().strip('"').strip("'").strip()
    return raw


def local_file(text: str) -> str:
    """The source as an existing file on disk, or "" — never raises.

    `~` is expanded and a `file://` URL is turned back into a path, because
    both are things a person or a model legitimately produces and neither
    reaches `QUrl.fromLocalFile` as a path.
    """
    raw = clean_source(text)
    if not raw:
        return ""
    if raw.lower().startswith("file://"):
        try:
            raw = urllib.parse.unquote(urllib.parse.urlparse(raw).path)
            # Windows: "/C:/x/y.mp4" is not a path, "C:/x/y.mp4" is.
            if re.match(r"^/[A-Za-z]:", raw):
                raw = raw[1:]
        except Exception:
            return ""
    try:
        p = Path(raw).expanduser()
        if p.exists() and p.is_file():
            return str(p)
    except Exception:
        pass
    return ""


def is_youtube(text: str) -> bool:
    """True for any YouTube page URL, including the mobile and nocookie ones."""
    raw = clean_source(text)
    if not raw:
        return False
    try:
        parsed = urllib.parse.urlparse(raw if "://" in raw else "https://" + raw)
        host = (parsed.hostname or "").lower()
    except Exception:
        return False
    return host in _YT_HOSTS or host.endswith(".youtube.com")


def is_http_url(text: str) -> bool:
    return clean_source(text).lower().startswith(("http://", "https://"))


def kind_of(text: str) -> str:
    """Classify a source: 'file', 'youtube', 'url', 'audio' or 'unknown'.

    `audio` is the same thing as a URL or a file whose extension says it is
    sound — the distinction matters because audio is played by the audio tool
    and video by the video one, and the model is told which is which.
    """
    raw = clean_source(text)
    if not raw:
        return "unknown"
    if local_file(raw):
        ext = Path(local_file(raw)).suffix.lower()
        return "audio" if ext in _AUDIO_EXT else "file"
    if is_youtube(raw):
        return "youtube"
    if is_http_url(raw):
        try:
            path = urllib.parse.urlparse(raw).path.lower()
        except Exception:
            return "url"
        if any(path.endswith(e) for e in _AUDIO_EXT):
            return "audio"
        return "url"
    bare = _bare_kind(raw)
    if bare == "host":
        return "url"
    if bare == "file":
        # A media filename that is not on disk is still a file the user meant;
        # the player will say it does not exist, which is the honest answer.
        return "audio" if raw.lower().endswith(_AUDIO_EXT) else "file"
    return "unknown"


def _bare_kind(raw: str) -> str:
    """Classify something typed without a scheme: 'host', 'file' or 'other'.

    The whole difficulty is that `example.com/clip.mp4` and `song.mp3` have the
    same shape. What separates them is the first label: a host label is a name
    someone registered, a filename's stem is whatever the file is called — and a
    file extension in the LAST label settles it. Getting this wrong is not
    cosmetic: it is the difference between fetching a video and asking DNS for a
    song in the user's Music folder.
    """
    head = raw.partition("/")[0]
    low = raw.lower()
    # HOST EVIDENCE FIRST. A host-shaped head plus a path or a port is a URL
    # even when the path ends in .mp4 — `example.com/clip.mp4` is a video to
    # fetch, while `clip.mp4` is a file to open, and the extension alone cannot
    # tell them apart.
    if _HOSTLIKE.match(head.split(":")[0]) and (":" in head or "/" in raw):
        return "host"
    if _IPV4.match(head.split(":")[0]) and "/" in raw:
        return "host"
    # A media extension with no host evidence means a filename.
    if low.endswith(_MEDIA_EXT + _AUDIO_EXT):
        return "file"
    if not _HOSTLIKE.match(head.split(":")[0]):
        return "other"
    # A port is a host's signature; so is a path after the host.
    if ":" in head or "/" in raw:
        return "host"
    # Bare `example.com` with no path: a host only if the last label is a short
    # alphabetic TLD. `photo.2024` is not a website.
    return "host" if re.match(r"^[A-Za-z]{2,6}$", head.rsplit(".", 1)[-1]) else "other"


def media_url(text: str) -> str:
    """What to hand to `QUrl`: a local path stays a path, a bare host gets https.

    Calling `media_url` on something already resolved (a googlevideo URL with
    its own query string) must return it unchanged — that is the case the player
    hits most often, and an accidental re-encoding of the query breaks the
    signature on the stream.
    """
    raw = clean_source(text)
    if not raw:
        return ""
    if local_file(raw):
        return local_file(raw)
    low = raw.lower()
    if low.startswith(("http://", "https://", "file://")):
        return raw
    if _bare_kind(raw) == "host":
        return "https://" + raw
    return raw


# ── end of media ────────────────────────────────────────────────────────────

# What the window should do when a player says it has finished.
#
# `Playback` is deliberately a plain value: the window builds one, asks these
# functions, and does what they say. Nothing here knows about Qt's enums — the
# window translates Qt.MediaStatus.EndOfMedia into `state="ended"` once, in one
# place, which is also the place that is easiest to get wrong.
def ended_video_effect(state: str, sound_was_on: bool) -> dict:
    """The consequence of the PICTURE finishing.

    A finished video is not a paused one: the HUD has to come back, the timer
    has to stop, the mute button has to stop describing a stream that no longer
    exists — and, if JARVIS closed the microphone because the video was loud, it
    has to open again. That last part is the bug: without it the assistant is
    deaf for the rest of the session, with the video gone, and nothing on screen
    says why.

    Returns the flags the window applies, rather than mutating anything, so the
    rules can be asserted.
    """
    if state != "ended":
        return {"close": False, "release_mic": False, "log": ""}
    return {
        "close": True,
        "release_mic": bool(sound_was_on),
        "log": "",
    }


def ended_audio_effect(state: str) -> dict:
    """The consequence of an audio track finishing.

    Different from the picture on purpose. A soundtrack that ends 300 ms before
    the picture is normal — the two streams are not the same length — so closing
    the video on an audio end would cut the last frames off. What must happen is
    that the sound is reported as finished and the button stops claiming sound.
    """
    if state != "ended":
        return {"mark_finished": False}
    return {"mark_finished": True}


def should_open_from_ended(status: str) -> bool:
    """Whether a media status means "stop calling it playing".

    Qt reports EndOfMedia for both the picture and the sound; the window maps
    either to this. `InvalidMedia` and `NoMedia` land here too, because a source
    that cannot be opened must not leave the HUD on a black page with a mute
    button.
    """
    return status in ("ended", "invalid", "no_media")


# ── switching sources ───────────────────────────────────────────────────────

def opening_while_playing(is_playing: bool, split_sound: bool) -> dict:
    """What must be torn down before a new source is loaded.

    Opening a second video used to leave the first one's separate soundtrack
    running: `_on_video_open` set the new title and pressed play, but the audio
    player from the previous URL was never stopped, so a YouTube voice kept
    talking over the local file the user had just opened — and the mute button
    then controlled the new, silent output while the old one played on.

    Tearing down unconditionally would be wasteful but harmless; the flags
    matter because the resync timer MUST be stopped even when the old source was
    a single-stream file (it may have been left running by an earlier open that
    never closed).
    """
    return {
        "stop_video": bool(is_playing),
        "stop_audio": bool(is_playing and split_sound),
        "stop_timer": True,
        "release_mic": bool(is_playing),
    }


# ── keeping two streams in step ─────────────────────────────────────────────

# How far apart the two streams may drift before correcting them.
#
# YouTube serves picture and sound as separate streams now, so a separate player
# plays the sound, and two players started together do not stay together: they
# buffer independently. Correcting a small gap is itself audible (a click or a
# skipped syllable), so the threshold is where a drift stops being invisible —
# roughly one frame of video plus human tolerance, measured at ~300 ms on a real
# stream, which is where this number comes from.
DRIFT_LIMIT_MS = 300

# Below this, don't touch it even if it is over the limit: a correction that
# moves the sound by less than this is a click with no benefit.
DRIFT_MIN_FIX_MS = 90

# A sound stream that is further behind than this at open time is treated as
# broken rather than late, because seek() to the far end of a stream that has
# not buffered yet usually fails silently.
DRIFT_MAX_SEEK_MS = 15000


def sync_decision(picture_ms: int, sound_ms: int, sound_state: str) -> dict:
    """Whether to nudge the soundtrack, and in which direction.

    One function rather than three conditions inline, because the interesting
    case is the one the old code got wrong: when the sound stream has STOPPED
    but the picture is still going, there is nothing to compare and nothing to
    seek — the sound must simply be restarted at the picture's position. The old
    check only ever ran while both were playing, so a soundtrack that ended
    early left the rest of the video silent with the button still saying
    SOUND ON.
    """
    if sound_state == "stopped" and picture_ms > 0:
        return {"restart": True, "seek": True, "position": int(picture_ms),
                "why": "the sound stream stopped before the picture"}
    if sound_state != "playing":
        # Buffering, loading or paused: a seek now would be discarded, so leave
        # it alone and look again on the next tick.
        return {"restart": False, "seek": False, "position": 0, "why": ""}

    drift = int(sound_ms) - int(picture_ms)
    if abs(drift) <= DRIFT_LIMIT_MS:
        return {"restart": False, "seek": False, "position": 0, "why": ""}
    if abs(drift) < DRIFT_MIN_FIX_MS:
        return {"restart": False, "seek": False, "position": 0, "why": ""}
    if abs(drift) > DRIFT_MAX_SEEK_MS:
        return {"restart": True, "seek": True, "position": int(picture_ms),
                "why": f"the sound was {abs(drift) / 1000:.1f}s out"}
    return {"restart": False, "seek": True, "position": int(picture_ms),
            "why": f"the sound was {drift:+d} ms out"}


# ── the microphone ──────────────────────────────────────────────────────────

def mic_plan(video_on: bool, sound_muted: bool, already_auto_muted: bool,
             user_muted: bool) -> dict:
    """Whether JARVIS should close its own microphone, and whether to reopen it.

    JARVIS subtracts its own output from the microphone (`core/echo.py`), but a
    video plays through a different output entirely, so the guard has never
    heard of it and the assistant answers the film. There is no arrangement in
    which an open microphone and a loudspeaker in the same room do not do that.

    The rule, stated as the small set of cases it is:

      * sound on, microphone open        -> close it, and remember that WE did;
      * sound off or no video, and we closed it -> open it again;
      * the user muted themselves         -> never reopen it, in any case.

    The last rule is the one that makes this safe to automate at all: pressing
    the mute key during a video hands the decision back to the person for good,
    because `user_muted` then wins over every branch below.
    """
    if user_muted and not already_auto_muted:
        # The user closed it, or it was already closed for their own reason.
        return {"close": False, "reopen": False, "set_auto": False}

    want_silent = bool(video_on and not sound_muted)
    if want_silent and not user_muted:
        return {"close": True, "reopen": False, "set_auto": True}
    if not want_silent and already_auto_muted:
        return {"close": False, "reopen": True, "set_auto": False}
    return {"close": False, "reopen": False, "set_auto": False}


# ── audio playback ──────────────────────────────────────────────────────────

def audio_title(path_or_url: str) -> str:
    """A short human label for the audio header.

    A file name without its extension and with its underscores turned into
    spaces is what people expect to see; a URL has no name, so the last path
    segment is the best there is — and a query string on the end of it is noise
    that belongs nowhere near a header.
    """
    raw = clean_source(path_or_url)
    if not raw:
        return ""
    try:
        parsed = urllib.parse.urlparse(raw)
        last = parsed.path.rsplit("/", 1)[-1]
    except Exception:
        last = raw.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
    if not last:
        return ""
    last = urllib.parse.unquote(last)
    stem = last.rsplit(".", 1)[0] if "." in last else last
    return stem.replace("_", " ").strip()


def is_audio_source(text: str) -> bool:
    """Is this something the audio player can play?

    Deliberately broader than `kind_of(...) == "audio"`: a YouTube link has
    sound, and so does a direct stream URL with no extension at all, and
    refusing those would make the tool useless for the two things people
    actually ask for. But a web PAGE is not audio: handing one to QMediaPlayer
    produces "format not supported", which reads to the user as "this app cannot
    play anything".
    """
    k = kind_of(text)
    if k in ("audio", "youtube"):
        return True
    raw = clean_source(text)
    if not raw:
        return False
    low = raw.lower()
    if low.endswith(_PAGE_EXT):
        return False
    if not is_http_url(raw):
        return False
    try:
        path = urllib.parse.urlparse(raw).path.lower()
    except Exception:
        return False
    if path.endswith(_PAGE_EXT):
        return False
    if path.endswith(_AUDIO_EXT) or path.endswith(_MEDIA_EXT):
        return True
    # A stream endpoint: a path with no filename-dot in its last segment
    # (`/radio`, `/live/stream`), as opposed to a page (`/watch`, `/index`).
    last = path.rsplit("/", 1)[-1]
    return bool(last) and "." not in last
