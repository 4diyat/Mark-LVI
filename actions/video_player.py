"""
Play a video where the avatar normally is.

The HUD already had a surface for this — the live camera takes the centre of
the screen and gives it back — so a video is the same idea with a different
source, and it shares the same stack rather than inventing a second one. That
means the avatar, the camera and a video can never be on screen together.

WHAT IT ACCEPTS
    a local file        C:\\Users\\me\\clip.mp4, ~/Videos/holiday.mkv
    a direct media URL  https://example.com/trailer.mp4
    a YouTube link      https://youtube.com/watch?v=...
    a YouTube search    "play the new Dune trailer"

    The first two are handed straight to Qt. The last two have to be resolved
    to something playable first, which is what yt-dlp does; without it, this
    says so and offers to open the video in the browser instead of failing.

SOUND IS OFF UNTIL ASKED FOR
    A soundtrack talking over the assistant is the one way this feature could
    make JARVIS worse rather than better, and the microphone is open while it
    plays. So it starts muted, and the user turns sound on — from the button in
    the video header, or by saying so. Closing it works both ways too.
"""
from __future__ import annotations

import re
import threading
import webbrowser
from pathlib import Path

from core import playback as _pb

# The source classifier is shared with the window (core/playback), so the tool
# and the surface it drives cannot disagree about what they were handed. The
# local regex it replaced matched only `youtube.com/` and `youtu.be/`, so a link
# copied from a phone (`m.youtube.com`) was sent to Qt as a media file and the
# user was told their link was broken.
_YT = re.compile(r"(youtube\.com/|youtu\.be/)", re.I)

# Which open request is the current one. Opening happens on a thread now, so
# "stop" can arrive while a video is still being resolved — and without this the
# stop would find nothing playing, say so, and then the video would appear
# anyway a second later. Bumping the number abandons whatever is in flight.
_open_lock = threading.Lock()
_open_seq = 0


def _begin_open() -> int:
    global _open_seq
    with _open_lock:
        _open_seq += 1
        return _open_seq


def _still_wanted(token: int) -> bool:
    with _open_lock:
        return token == _open_seq


def _is_url(text: str) -> bool:
    """Kept for callers that still ask; the answer comes from the shared
    classifier so there is one definition of "this is a URL"."""
    return _pb.is_http_url(text) or _pb.clean_source(text).lower().startswith("file://")


def _local_path(text: str) -> str:
    """The text as an existing file on disk, or ''.

    Delegates to the shared cleaner, which also handles a `file://` URL and the
    quoting that Explorer's "Copy as path" adds.
    """
    return _pb.local_file(text)


def _resolve_youtube(url_or_query: str) -> tuple[str, str, str, str]:
    """(video_url, audio_url, title, error). Needs yt-dlp; says so when absent.

    TWO urls, because YouTube no longer offers one.
    The first version of this asked for a format carrying both picture and
    sound and got "Requested format is not available". That was not a bad
    selector, it was a wrong assumption: checked against three videos —
    including the oldest upload on the site — every one offered ZERO combined
    formats. Picture and sound are separate streams now, and both are returned
    so the player can run them together.

    `audio_url` comes back empty when only a combined or video-only stream
    exists, which is the normal case for everything that is not YouTube.
    """
    try:
        import yt_dlp
    except Exception:
        return "", "", "", ("yt-dlp is not installed, so a YouTube video "
                            "cannot be played inside the HUD. "
                            "Run: pip install yt-dlp")

    query = url_or_query if _YT.search(url_or_query) else f"ytsearch1:{url_or_query}"
    # No "format" here on purpose: ask for everything and choose below, so a
    # video that lacks whatever was requested cannot fail outright.
    opts = {"quiet": True, "no_warnings": True, "skip_download": True,
            "noplaylist": True}
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(query, download=False)
        if info and info.get("entries"):
            info = info["entries"][0]
        if not info:
            return "", "", "", "nothing was found for that."
    except Exception as e:
        return "", "", "", f"the video could not be resolved: {e}"

    formats = [f for f in (info.get("formats") or [])
               if str(f.get("protocol") or "").startswith("http") and f.get("url")]

    def has(f, key):
        return f.get(key) not in (None, "none")

    def best(candidates):
        """Highest quality — but the ORIGINAL language before quality.

        YouTube auto-dubs a lot of videos now, and it offers every dub as its
        own audio stream at the SAME bitrate as the original: measured on one
        video, English original at 129.483 and Arabic, Bangla, German, Spanish,
        French, Hindi and Indonesian all at 129.482. Choosing on bitrate alone
        therefore came down to a thousandth of a kilobit, and a video would play
        in Arabic one time and English the next for no reason the user could
        see.

        YouTube marks the original track with language_preference 10 and every
        dub with -1, so that decides it first and bitrate only breaks ties
        within the same track. Video formats carry no language, so this is the
        same ordering for them with the first term always equal.
        """
        if not candidates:
            return None
        return max(candidates,
                   key=lambda f: (f.get("language_preference") or 0,
                                  f.get("tbr") or 0))

    # Combined first — if a video still has one, one player is simpler and
    # cannot drift. Then picture and sound separately.
    combined = best([f for f in formats if has(f, "vcodec") and has(f, "acodec")])
    if combined:
        return combined["url"], "", info.get("title") or "", ""

    # 720p is the ceiling on purpose: the HUD panel is nowhere near 4K, and a
    # smaller stream starts sooner and drifts less.
    video = best([f for f in formats
                  if has(f, "vcodec") and not has(f, "acodec")
                  and f.get("ext") == "mp4" and (f.get("height") or 0) <= 720])
    if not video:
        video = best([f for f in formats
                      if has(f, "vcodec") and not has(f, "acodec")])
    audio = best([f for f in formats
                  if has(f, "acodec") and not has(f, "vcodec")
                  and f.get("ext") == "m4a"])
    if not audio:
        audio = best([f for f in formats
                      if has(f, "acodec") and not has(f, "vcodec")])

    if not video:
        return "", "", "", "no playable stream was offered for that video."
    if audio and audio.get("language"):
        print(f"[Video] audio track: {audio.get('language')} "
              f"({audio.get('format_note') or audio.get('format_id')})")
    return video["url"], (audio or {}).get("url", ""), info.get("title") or "", ""


def _search_page(query: str) -> str:
    from urllib.parse import quote_plus
    return f"https://www.youtube.com/results?search_query={quote_plus(query)}"


def video_player(parameters: dict = None, response=None, player=None,
                 session_memory=None) -> str:
    params = parameters or {}
    action = (params.get("action") or "play").strip().lower()
    source = (params.get("source") or "").strip()

    if player is None:
        return "There is no display to play a video on."

    # ---- stop -------------------------------------------------------------
    if action in ("stop", "close", "hide"):
        # Cancel an open that has not finished yet, so a video the user has
        # already changed their mind about never reaches the screen.
        was_opening = not player.video_is_playing()
        _begin_open()
        player.stop_video()
        if was_opening:
            return "Stopped it before it opened."
        return "Closed the video."

    # ---- audio (not video) ------------------------------------------------
    #
    # One tool for both surfaces on purpose: the user says "put on some music"
    # and the model should not have to decide which of two tools owns the word
    # "play". `kind` is what separates them, and it is derived from the source
    # itself, not guessed.
    if action in ("play_audio", "audio", "music", "music_play"):
        return _play_audio(player, params, explicit=True)
    if action in ("stop_audio", "audio_stop", "music_stop"):
        if not getattr(player, "audio_is_playing", lambda: False)():
            return "Nothing is playing."
        player.stop_audio()
        return "Stopped the audio."
    if action in ("pause_audio", "audio_pause"):
        player.pause_audio(True)
        return "Paused."
    if action in ("resume_audio", "audio_resume", "unpause_audio"):
        player.pause_audio(False)
        return "Playing again."
    if action in ("volume", "set_volume", "audio_volume"):
        vol = params.get("volume")
        try:
            vol = max(0.0, min(1.0, float(vol)))
        except (TypeError, ValueError):
            return "What volume? Say a number out of 100."
        player.set_audio_volume(vol)
        return f"Volume set to {int(vol * 100)}%."

    # ---- sound ------------------------------------------------------------
    if action in ("mute", "unmute", "sound_on", "sound_off"):
        if not player.video_is_playing():
            return "Nothing is playing."
        muted = action in ("mute", "sound_off")
        player.set_video_muted(muted)
        return "Muted the video." if muted else "Turned the video's sound on."

    # ---- play -------------------------------------------------------------
    if not source:
        return "What should I play?"

    local = _local_path(source)
    if local:
        # A SOUNDFILE goes to the audio surface, even when the model asked for
        # a video: sending an .mp3 to the picture player produces a black page
        # and a Qt error, where the user asked for music and expects to keep
        # looking at the assistant.
        if _pb.kind_of(local) == "audio" and hasattr(player, "play_audio"):
            return _play_audio(player, {"source": local, "action": "play_audio"},
                               title=_pb.audio_title(local))
        player.show_video(_pb.media_url(local), Path(local).name, muted=True)
        return f"Playing {Path(local).name} on the display, muted."

    # A direct media URL can go straight to the player; a YouTube page cannot.
    if _pb.is_http_url(source) and not _pb.is_youtube(source):
        if _pb.kind_of(source) == "audio" and hasattr(player, "play_audio"):
            return _play_audio(player, {"source": source, "action": "play_audio"})
        player.show_video(_pb.media_url(source),
                          _pb.audio_title(source)[:44] or "VIDEO", muted=True)
        return "Playing that on the display, muted."

    # ANSWER FIRST, OPEN SECOND.
    #
    # Working out what to play takes seconds that nothing can remove: measured
    # against YouTube, 3.3s for a spoken phrase (a search, then the video) and
    # 2.0s for a link, plus however long Qt spends buffering before the first
    # frame. Restricting yt-dlp to a lighter client was tried and is not the
    # answer — the fast clients came back with zero usable formats.
    #
    # So the seconds stay, and what changes is where the user spends them:
    # listening to JARVIS say it is coming, instead of watching nothing happen.
    # The same shape whatsapp_call uses, and for the same reason.
    threading.Thread(target=_play_youtube, args=(player, source, _begin_open()),
                     daemon=True, name="video-open").start()
    # Deliberately a status line rather than a finished English sentence: the
    # model writes the words, in the user's own language.
    return f"status=opening source={source}"


def _play_audio(player, params: dict, title: str = "",
                explicit: bool = False) -> str:
    """Start audio and answer immediately, the way video does.

    A YouTube link has to be resolved first, which takes seconds; making the
    model wait for it would stall the conversation for something the user can
    already hear. Everything else — a file, a stream URL — starts in one call.
    """
    source = _pb.clean_source(params.get("source") or "")
    if not source:
        return "What should I play?"
    if not hasattr(player, "play_audio"):
        return "There is no audio output in this build."
    # A GUESSED source has to pass the audio test; an EXPLICIT one only has to
    # be a real source. "Play the sound of this clip" is a legitimate request,
    # and a video file carries an audio track — but when the model merely said
    # "play" and the source is a web page, playing it produces a decoder error
    # that reads as "this app cannot play anything".
    kind = _pb.kind_of(source)
    # A PAGE is never playable, however explicitly it was asked for: the honest
    # answer costs one sentence, and trying it costs the user a decoder error
    # they cannot act on.
    page = source.lower().split("?")[0].endswith(
        (".html", ".htm", ".php", ".asp", ".aspx", ".jsp"))
    playable = (_pb.is_audio_source(source)
                or (explicit and not page
                    and kind in ("file", "url", "audio", "youtube")))
    if not playable:
        return ("That does not look like something I can play as audio — a web "
                "page has no sound file behind it. A file path, a stream link or "
                "a YouTube link works.")

    try:
        volume = float(params.get("volume", 0.7))
    except (TypeError, ValueError):
        volume = 0.7
    volume = max(0.0, min(1.0, volume))
    loop = bool(params.get("loop"))

    if _pb.is_youtube(source):
        threading.Thread(target=_start_youtube_audio,
                         args=(player, source, volume, loop, _begin_open()),
                         daemon=True, name="audio-open").start()
        return f"status=opening source={source}"

    label = title or _pb.audio_title(source) or "AUDIO"
    player.play_audio(_pb.media_url(source), label, volume, loop)
    return f"Playing {label}, at {int(volume * 100)}% volume."


def _start_youtube_audio(player, source: str, volume: float, loop: bool,
                         token: int) -> None:
    """Resolve YouTube audio on a thread; speak only if it fails."""
    try:
        _video, audio_url, title, err = _resolve_youtube(source)
    except Exception as e:                                  # noqa: BLE001
        audio_url = title = ""
        err = str(e)

    if not _still_wanted(token):
        return
    if audio_url:
        try:
            player.play_audio(audio_url, title or _pb.audio_title(source),
                              volume, loop)
            return
        except Exception as e:                              # noqa: BLE001
            err = str(e)
    _say(player, "Tell the user, in one short sentence in their own language: "
                 f"'{source}' could not be played as audio ({err}).")


def _play_youtube(player, source: str, token: int) -> None:
    """The part that takes seconds. Speaks only if something goes wrong —
    silence means the video is on screen, which the user can see for
    themselves."""
    try:
        url, audio_url, title, err = _resolve_youtube(source)
    except Exception as e:                                  # noqa: BLE001
        url = audio_url = title = ""
        err = str(e)

    if not _still_wanted(token):
        return                       # the user closed it while it was resolving

    if url:
        try:
            player.show_video(url, title or source, muted=True,
                              audio_source=audio_url)
            return
        except Exception as e:                              # noqa: BLE001
            err = str(e)

    # Resolution failed. Opening it in a browser is worse than playing it in the
    # HUD, but it is a great deal better than doing nothing, and the reason is
    # reported rather than swallowed.
    page = source if _YT.search(source) else _search_page(source)
    opened = ""
    try:
        webbrowser.open(page)
        opened = " and it has been opened in the browser instead"
    except Exception:
        pass
    _say(player, "Tell the user, in one short sentence in their own language: "
                 f"'{source}' could not be played on the display "
                 f"({err}){opened}.")


def _say(player, instruction: str) -> None:
    if player is not None and hasattr(player, "request_say"):
        try:
            player.request_say(instruction)
        except Exception:
            pass


# ── Tool declaration (auto-discovered by core/action_loader.py) ──────────────
TOOL = {
    "name": "video_player",
    "description": (
        "If user wants to open a video on YouTube, he will tell you that specifically"
        "If user wants to play a video, then he wants to call this feature"
        "Plays a VIDEO on the assistant's own display, where the avatar "
        "normally is — and stops it, mutes it or unmutes it. Use whenever the "
        "user wants to WATCH something on screen: 'play the new Dune trailer', "
        "'play that video', 'play C:/clips/holiday.mp4', 'put that YouTube "
        "video on the screen', 'stop the video', 'videoyu kapat', 'turn the "
        "sound on', 'sesi aç', 'mute it'. Accepts a local file path, a direct "
        "video URL, a YouTube link, or a description to search YouTube for. "
        "Video always starts MUTED — only call action='unmute' when the user "
        "actually asks to hear it. "
        "This returns the moment it is asked, before the picture appears: when "
        "it answers 'status=opening', say in one short sentence that you are "
        "putting it on the display, and do not wait or call it again. "
        "VIDEO OR AUDIO: video goes on the assistant's display and starts "
        "muted; audio plays in the background with the avatar still on screen "
        "and is what 'play some music', 'put on a song', 'play that podcast' "
        "and 'play this radio stream' mean. A sound file (.mp3, .m4a, .wav, "
        ".flac, .ogg) or a request for music means action='play_audio'. "
        "Do NOT use 'youtube_video' for this: that optional plugin opens videos "
        "in the web browser and summarises transcripts, it never plays anything "
        "on the assistant's display."
    ),
    # Used in place of `description` only when a small model is on a tool
    # budget - Gemini still gets the full text. See providers/schema.py.
    "brief": (
        "Plays a VIDEO on the HUD (a YouTube link, a local file, a URL, or a "
        "description to search for) or AUDIO in the background - use "
        "action='play_audio' for music, songs, podcasts and radio."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "action": {
                "type": "STRING",
                "description": (
                    "'play' (default) for VIDEO on the display; 'stop' to close "
                    "the video; 'mute'/'unmute' for the video's sound. For "
                    "AUDIO — music, a song, a podcast, a radio stream — use "
                    "'play_audio', 'stop_audio', 'pause_audio', "
                    "'resume_audio' or 'volume'."),
                "enum": ["play", "stop", "mute", "unmute",
                         "play_audio", "stop_audio", "pause_audio",
                         "resume_audio", "volume"],
            },
            "volume": {
                "type": "NUMBER",
                "description": ("For action='play_audio' or 'volume': 0.0 to "
                                "1.0. Omit for the assistant's default (0.7)."),
            },
            "loop": {
                "type": "BOOLEAN",
                "description": ("For action='play_audio': repeat until stopped. "
                                "Use it when the user asks for background "
                                "music already playing."),
            },
            "source": {
                "type": "STRING",
                "description": (
                    "For action='play': a local file path, a direct video URL, "
                    "a YouTube link, or what to search YouTube for. Pass what "
                    "the user actually named, in their own words."
                ),
            },
        },
        "required": ["action"],
    },
    "handler": video_player,
}
