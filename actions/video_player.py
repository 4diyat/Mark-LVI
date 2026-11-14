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

import inspect
import json
import re
import threading
import urllib.parse
import urllib.request
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


_META_LOCK = threading.Lock()
_META_CACHE: dict[tuple, dict] = {}
_MAX_RETRY_SEARCHES = 3
_YT_CLIENT_PASSES: tuple[tuple[str, ...] | None, ...] = (
    None,
    ("android", "ios"),
    ("tv", "web_safari"),
)


def _remember_meta(vcands: list[dict[str, str]], acands: list[str],
                   vid: str) -> None:
    urls_key = tuple(c["url"] for c in vcands)
    audio_key = ("__audio__", acands[0]) if acands else None
    payload = {"video": list(vcands), "audio": list(acands), "vid": vid}
    with _META_LOCK:
        if len(_META_CACHE) > 32:
            _META_CACHE.clear()
        if urls_key:
            _META_CACHE[urls_key] = payload
        if audio_key:
            _META_CACHE[audio_key] = payload


def _pop_video_meta(urls: list[str]) -> dict | None:
    if not urls:
        return None
    with _META_LOCK:
        return _META_CACHE.pop(tuple(urls), None)


def _pop_audio_meta(audio_url: str) -> dict | None:
    if not audio_url:
        return None
    with _META_LOCK:
        return _META_CACHE.pop(("__audio__", audio_url), None)


def _fetch_youtube_title(url: str) -> str:
    """Best-effort title lookup when yt-dlp fails with 403/age-gate."""
    vid = _pb.youtube_video_id(url)
    target = f"https://www.youtube.com/watch?v={vid}" if vid else url
    oembed = ("https://www.youtube.com/oembed?url="
              f"{urllib.parse.quote(target, safe='')}&format=json")
    try:
        req = urllib.request.Request(oembed, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            data = json.loads(resp.read().decode("utf-8", errors="replace"))
        return str(data.get("title") or "").strip()
    except Exception:
        return ""


def _extract_candidates(
    info: dict,
    exclude_urls: set[str] | None = None,
) -> tuple[list[dict[str, str]], list[str], str]:
    """Return `(video_candidates, audio_urls, title)` from a yt-dlp info dict."""
    excluded = exclude_urls or set()
    raw_formats = [
        f for f in (info.get("formats") or [])
        if f.get("url") and f["url"] not in excluded
    ]
    http_formats = [
        f for f in raw_formats
        if str(f.get("protocol") or "") in ("http", "https", "")
        and str(f.get("url") or "").startswith(("http://", "https://"))
    ]
    hls_formats = [
        f for f in raw_formats
        if str(f.get("protocol") or "") in ("m3u8", "m3u8_native")
    ]

    def has(f, key):
        return f.get(key) not in (None, "none")

    def audio_key(f):
        return (
            f.get("language_preference") or 0,
            1 if f.get("ext") == "m4a" else 0,
            f.get("tbr") or 0,
        )

    audio_formats = sorted(
        [f for f in http_formats if has(f, "acodec") and not has(f, "vcodec")],
        key=audio_key,
        reverse=True,
    )
    audio_urls: list[str] = []
    chosen_audio_meta = None
    for f in audio_formats:
        if f["url"] not in audio_urls:
            audio_urls.append(f["url"])
            if chosen_audio_meta is None:
                chosen_audio_meta = f
        if len(audio_urls) >= 4:
            break
    primary_audio = audio_urls[0] if audio_urls else ""

    video_candidates: list[dict[str, str]] = []
    seen_video: set[str] = set()

    def add_video(f: dict, audio: str) -> None:
        url = f.get("url") or ""
        if not url or url in seen_video or len(video_candidates) >= 6:
            return
        seen_video.add(url)
        video_candidates.append({"url": url, "audio": audio})

    combined = sorted(
        [f for f in http_formats if has(f, "vcodec") and has(f, "acodec")],
        key=lambda f: (
            1 if (f.get("height") or 0) <= 720 else 0,
            1 if f.get("ext") == "mp4" else 0,
            f.get("tbr") or 0,
        ),
        reverse=True,
    )
    for f in combined:
        add_video(f, "")

    mp4_720 = sorted(
        [
            f for f in http_formats
            if has(f, "vcodec") and not has(f, "acodec")
            and f.get("ext") == "mp4" and (f.get("height") or 0) <= 720
        ],
        key=lambda f: (
            1 if str(f.get("vcodec") or "").startswith("avc") else 0,
            f.get("tbr") or 0,
        ),
        reverse=True,
    )
    for f in mp4_720:
        add_video(f, primary_audio)

    other_http = sorted(
        [f for f in http_formats if has(f, "vcodec") and not has(f, "acodec")],
        key=lambda f: (
            1 if (f.get("height") or 0) <= 720 else 0,
            1 if f.get("ext") == "mp4" else 0,
            f.get("tbr") or 0,
        ),
        reverse=True,
    )
    for f in other_http:
        add_video(f, primary_audio)

    hls_video = sorted(
        [f for f in hls_formats if has(f, "vcodec")],
        key=lambda f: (
            1 if (f.get("height") or 0) <= 720 else 0,
            1 if has(f, "acodec") else 0,
            f.get("tbr") or 0,
        ),
        reverse=True,
    )
    for f in hls_video:
        add_video(f, "" if has(f, "acodec") else primary_audio)

    if not audio_urls:
        for f in combined:
            if f["url"] not in audio_urls:
                audio_urls.append(f["url"])
            if len(audio_urls) >= 2:
                break

    if chosen_audio_meta and chosen_audio_meta.get("language"):
        print(f"[Video] audio track: {chosen_audio_meta.get('language')} "
              f"({chosen_audio_meta.get('format_note') or chosen_audio_meta.get('format_id')})")
    return video_candidates, audio_urls, info.get("title") or ""


def _resolve_youtube_candidates(
    url_or_query: str,
    exclude_ids: set[str] | None = None,
    exclude_urls: set[str] | None = None,
    client_pass: int = 0,
    for_audio: bool = False,
    fallback_title: str = "",
) -> tuple[list[dict[str, str]], list[str], str, str, str]:
    """Resolve YouTube URL or query into ranked video/audio candidate streams.

    Returns `(video_candidates, audio_urls, title, video_id, error)`.
    When the first video or stream cannot be resolved/played (e.g. 403
    Forbidden), automatically tries alternate yt-dlp clients and up to 5
    search results, skipping `exclude_ids` and `exclude_urls`.
    """
    try:
        import yt_dlp
    except Exception:
        return [], [], "", "", (
            "yt-dlp is not installed, so a YouTube video "
            "cannot be played inside the HUD. Run: pip install yt-dlp"
        )

    skip_ids = set(exclude_ids or ())
    skip_urls = set(exclude_urls or ())

    def extract(target: str, *, flat: bool = False,
                client: tuple[str, ...] | None = None):
        opts = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "noplaylist": True,
        }
        if flat:
            opts["extract_flat"] = "in_playlist"
        if client:
            opts["extractor_args"] = {"youtube": {"player_client": list(client)}}
        with yt_dlp.YoutubeDL(opts) as ydl:
            return ydl.extract_info(target, download=False)

    last_err = ""
    search_query = ""
    is_yt = bool(_YT.search(url_or_query) or _pb.is_youtube(url_or_query))

    if is_yt:
        vid = _pb.youtube_video_id(url_or_query)
        known_title = _pb.fallback_search_query(url_or_query, fallback_title)
        if not (vid and vid in skip_ids):
            for client in _YT_CLIENT_PASSES[client_pass:]:
                try:
                    info = extract(url_or_query, client=client)
                    if info and info.get("entries"):
                        info = info["entries"][0]
                    if info:
                        known_title = info.get("title") or known_title
                        vcands, acands, title = _extract_candidates(
                            info, exclude_urls=skip_urls
                        )
                        usable = acands if for_audio else vcands
                        if usable:
                            return (
                                vcands, acands, title,
                                str(info.get("id") or vid), "",
                            )
                except Exception as e:
                    last_err = str(e)
        if vid:
            skip_ids.add(vid)
        search_query = known_title or _fetch_youtube_title(url_or_query)
        if not search_query:
            return (
                [], [], known_title, vid,
                last_err or "no playable stream was offered for that video.",
            )
    else:
        search_query = url_or_query

    entries = []
    for search_target, flat in (
        (f"ytsearch5:{search_query}", True),
        (f"ytsearch5:{search_query}", False),
        (f"ytsearch1:{search_query}", False),
    ):
        try:
            res = extract(search_target, flat=flat)
            if res and res.get("entries"):
                entries = [e for e in res["entries"] if e]
                if entries:
                    break
            elif res and res.get("formats"):
                entries = [res]
                break
        except Exception as e:
            last_err = str(e)

    if not entries:
        return (
            [], [], "", "",
            f"the video could not be resolved: {last_err}"
            if last_err else "nothing was found for that.",
        )

    for entry in entries[:5]:
        eid = str(
            entry.get("id") or _pb.youtube_video_id(entry.get("url") or "")
        )
        if eid and eid in skip_ids:
            continue
        target = entry.get("url") or (
            f"https://www.youtube.com/watch?v={eid}" if eid else ""
        )
        # A search result can contain formats that are all unusable by Qt.
        # Try the other clients for the *same* video before skipping it.
        if entry.get("formats"):
            vcands, acands, title = _extract_candidates(entry, exclude_urls=skip_urls)
            if acands if for_audio else vcands:
                return vcands, acands, title or entry.get("title") or "", str(entry.get("id") or eid), ""
        info = {}
        for client in (None, ("android", "ios")):
            if not target:
                break
            try:
                info = extract(target, client=client)
                if info and info.get("entries"):
                    info = info["entries"][0]
                if info:
                    vcands, acands, title = _extract_candidates(info, exclude_urls=skip_urls)
                    usable = acands if for_audio else vcands
                    if usable:
                        return (
                            vcands, acands, title or entry.get("title") or "",
                            str(info.get("id") or eid), "",
                        )
            except Exception as e:
                last_err = str(e)
                info = {}
        info = info or {}
        if info.get("id") or eid:
            skip_ids.add(str(info.get("id") or eid))

    return (
        [], [], "", "",
        last_err or "no playable stream was offered for that video.",
    )


def _resolve_youtube(url_or_query: str) -> tuple[list[str], str, str, str]:
    """(video_urls, audio_url, title, error). Needs yt-dlp; says so when absent.

    `video_urls` is a ranked list of playable picture streams, best first. The
    first entry is what gets opened; the rest are fallbacks the HUD tries
    automatically if the first one is refused (for example a 403 Forbidden or an
    expired signature) instead of giving up on the video outright.
    """
    vcands, acands, title, vid, err = _resolve_youtube_candidates(url_or_query)
    if vcands or acands:
        _remember_meta(vcands, acands, vid)
    return ([c["url"] for c in vcands],
            acands[0] if acands else "",
            title,
            err)


_ORIG_RESOLVE_YOUTUBE = _resolve_youtube


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
        _begin_open()
        player.show_video(_pb.media_url(local), Path(local).name, muted=True)
        return f"Playing {Path(local).name} on the display, muted."

    # A direct media URL can go straight to the player; a YouTube page cannot.
    if _pb.is_http_url(source) and not _pb.is_youtube(source):
        if _pb.kind_of(source) == "audio" and hasattr(player, "play_audio"):
            return _play_audio(player, {"source": source, "action": "play_audio"})
        token = _begin_open()
        media = _pb.media_url(source)
        label = _pb.audio_title(source)[:44] or "VIDEO"
        retry_cb = _make_video_retry_cb(
            player, token, origin=source, title=label,
            tried_ids=set(), tried_urls={media}, attempt=0, client_pass=0,
        )
        _call_with_supported(
            player.show_video, media, label, muted=True, on_exhausted=retry_cb
        )
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


def _call_with_supported(fn, *args, **kwargs):
    """Pass optional fallback kwargs only when `fn` accepts them."""
    try:
        params = inspect.signature(fn).parameters
        if any(p.kind == inspect.Parameter.VAR_KEYWORD for p in params.values()):
            extra = kwargs
        else:
            extra = {k: v for k, v in kwargs.items() if k in params}
    except (ValueError, TypeError):
        extra = {}
    return fn(*args, **extra)


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

    token = _begin_open()
    media = _pb.media_url(source)
    label = title or _pb.audio_title(source) or "AUDIO"
    retry_cb = (
        _make_audio_retry_cb(
            player, token, origin=source, title=label, volume=volume,
            loop=loop, tried_ids=set(), tried_urls={media}, attempt=0,
            client_pass=0,
        )
        if _pb.is_http_url(source) else None
    )
    _call_with_supported(
        player.play_audio, media, label, volume, loop, on_exhausted=retry_cb
    )
    return f"Playing {label}, at {int(volume * 100)}% volume."


def _make_audio_retry_cb(player, token: int, *, origin: str, title: str,
                         volume: float, loop: bool, tried_ids: set[str],
                         tried_urls: set[str], attempt: int,
                         client_pass: int):
    state = {
        "origin": origin,
        "title": title,
        "volume": volume,
        "loop": loop,
        "tried_ids": set(tried_ids),
        "tried_urls": set(tried_urls),
        "attempt": attempt,
        "client_pass": client_pass,
    }

    def on_exhausted(reason: str = "") -> bool:
        if not _still_wanted(token):
            return False
        if not _pb.should_search_alternate(
            state["origin"], reason, state["title"],
            attempt=state["attempt"], max_attempts=_MAX_RETRY_SEARCHES,
        ):
            return False
        threading.Thread(
            target=_retry_audio_source,
            args=(player, token, state, reason),
            daemon=True, name="audio-retry",
        ).start()
        return True

    return on_exhausted


def _retry_audio_source(player, token: int, state: dict, reason: str) -> None:
    if not _still_wanted(token):
        return
    acands: list[str] = []
    title = ""
    vid = ""
    err = reason or ""
    use_yt_url = _pb.is_youtube(state["origin"]) and state["client_pass"] == 0
    query = (
        state["origin"] if use_yt_url
        else _pb.fallback_search_query(state["origin"], state["title"])
    )
    if query:
        try:
            if _resolve_youtube is not _ORIG_RESOLVE_YOUTUBE:
                _v, audio_url, title, err = _resolve_youtube(query)
                acands = [
                    u for u in _pb.normalize_audio_candidates([audio_url])
                    if u not in state["tried_urls"]
                ]
            else:
                origin_vid = _pb.youtube_video_id(state["origin"])
                skip_ids = (
                    state["tried_ids"] - {origin_vid}
                    if use_yt_url and origin_vid else state["tried_ids"]
                )
                _vc, acands, title, vid, err = _resolve_youtube_candidates(
                    query,
                    exclude_ids=skip_ids,
                    exclude_urls=state["tried_urls"],
                    client_pass=1 if use_yt_url else 0,
                    for_audio=True,
                    fallback_title=state["title"],
                )
        except Exception as e:                              # noqa: BLE001
            err = str(e)
    if not _still_wanted(token):
        return
    if acands:
        next_ids = set(state["tried_ids"])
        if vid:
            next_ids.add(vid)
        next_urls = set(state["tried_urls"]) | set(acands)
        next_cb = _make_audio_retry_cb(
            player, token, origin=state["origin"],
            title=title or state["title"], volume=state["volume"],
            loop=state["loop"], tried_ids=next_ids, tried_urls=next_urls,
            attempt=state["attempt"] + 1, client_pass=1,
        )
        try:
            _call_with_supported(
                player.play_audio, acands[0],
                title or state["title"] or _pb.audio_title(state["origin"]),
                state["volume"], state["loop"],
                fallbacks=acands[1:], on_exhausted=next_cb,
            )
            return
        except Exception as e:                              # noqa: BLE001
            err = str(e)
    _say(player, "Tell the user, in one short sentence in their own language: "
                 f"'{state['origin']}' could not be played as audio ({err}).")


def _start_youtube_audio(player, source: str, volume: float, loop: bool,
                         token: int) -> None:
    """Resolve YouTube audio on a thread; speak only if it fails."""
    acands: list[str] = []
    title = ""
    vid = ""
    err = ""
    try:
        if _resolve_youtube is not _ORIG_RESOLVE_YOUTUBE:
            _video, audio_url, title, err = _resolve_youtube(source)
            meta = _pop_audio_meta(audio_url)
            acands = (
                list(meta["audio"]) if meta and meta.get("audio")
                else _pb.normalize_audio_candidates([audio_url])
            )
            vid = (meta or {}).get("vid") or _pb.youtube_video_id(source)
        else:
            _vc, acands, title, vid, err = _resolve_youtube_candidates(
                source, for_audio=True
            )
    except Exception as e:                                  # noqa: BLE001
        acands = []
        title = ""
        vid = ""
        err = str(e)

    if not _still_wanted(token):
        return
    vid = vid or _pb.youtube_video_id(source)
    if acands:
        tried_ids = {vid} if vid else set()
        retry_cb = _make_audio_retry_cb(
            player, token, origin=source, title=title or _pb.audio_title(source),
            volume=volume, loop=loop, tried_ids=tried_ids,
            tried_urls=set(acands), attempt=0, client_pass=0,
        )
        try:
            _call_with_supported(
                player.play_audio, acands[0],
                title or _pb.audio_title(source), volume, loop,
                fallbacks=acands[1:], on_exhausted=retry_cb,
            )
            return
        except Exception as e:                              # noqa: BLE001
            err = str(e)
    _say(player, "Tell the user, in one short sentence in their own language: "
                 f"'{source}' could not be played as audio ({err}).")


def _make_video_retry_cb(player, token: int, *, origin: str, title: str,
                         tried_ids: set[str], tried_urls: set[str],
                         attempt: int, client_pass: int):
    state = {
        "origin": origin,
        "title": title,
        "tried_ids": set(tried_ids),
        "tried_urls": set(tried_urls),
        "attempt": attempt,
        "client_pass": client_pass,
    }

    def on_exhausted(reason: str = "") -> bool:
        if not _still_wanted(token):
            return False
        if not _pb.should_search_alternate(
            state["origin"], reason, state["title"],
            attempt=state["attempt"], max_attempts=_MAX_RETRY_SEARCHES,
        ):
            return False
        threading.Thread(
            target=_retry_video_source,
            args=(player, token, state, reason),
            daemon=True, name="video-retry",
        ).start()
        return True

    return on_exhausted


def _retry_video_source(player, token: int, state: dict, reason: str) -> None:
    if not _still_wanted(token):
        return
    vcands: list[dict[str, str]] = []
    acands: list[str] = []
    title = ""
    vid = ""
    err = reason or ""
    use_yt_url = _pb.is_youtube(state["origin"]) and state["client_pass"] == 0
    query = (
        state["origin"] if use_yt_url
        else _pb.fallback_search_query(state["origin"], state["title"])
    )
    if query:
        try:
            if _resolve_youtube is not _ORIG_RESOLVE_YOUTUBE:
                raw_urls, audio_url, title, err = _resolve_youtube(query)
                urls = (
                    [raw_urls] if isinstance(raw_urls, str)
                    else list(raw_urls or [])
                )
                vcands = [
                    c for c in _pb.normalize_video_candidates(
                        urls, default_audio=audio_url
                    )
                    if c["url"] not in state["tried_urls"]
                ]
                acands = _pb.normalize_audio_candidates([audio_url])
            else:
                origin_vid = _pb.youtube_video_id(state["origin"])
                skip_ids = (
                    state["tried_ids"] - {origin_vid}
                    if use_yt_url and origin_vid else state["tried_ids"]
                )
                vcands, acands, title, vid, err = _resolve_youtube_candidates(
                    query,
                    exclude_ids=skip_ids,
                    exclude_urls=state["tried_urls"],
                    client_pass=1 if use_yt_url else 0,
                    fallback_title=state["title"],
                )
        except Exception as e:                              # noqa: BLE001
            err = str(e)
    if not _still_wanted(token):
        return
    if vcands:
        next_ids = set(state["tried_ids"])
        if vid:
            next_ids.add(vid)
        next_urls = set(state["tried_urls"]) | {c["url"] for c in vcands}
        next_cb = _make_video_retry_cb(
            player, token, origin=state["origin"],
            title=title or state["title"], tried_ids=next_ids,
            tried_urls=next_urls, attempt=state["attempt"] + 1, client_pass=1,
        )
        try:
            _call_with_supported(
                player.show_video,
                vcands[0]["url"],
                title or state["title"] or state["origin"],
                muted=True,
                audio_source=vcands[0]["audio"],
                fallbacks=vcands[1:],
                audio_fallbacks=acands[1:],
                on_exhausted=next_cb,
            )
            return
        except Exception as e:                              # noqa: BLE001
            err = str(e)
    _report_youtube_failure(
        player, state["origin"], err or reason, title=state["title"]
    )


def _report_youtube_failure(player, source: str, err: str,
                            title: str = "") -> None:
    q = _pb.fallback_search_query(source, title) or source
    page = (
        source if (_YT.search(source) or _pb.is_youtube(source))
        else _search_page(q)
    )
    opened = ""
    try:
        webbrowser.open(page)
        opened = " and it has been opened in the browser instead"
    except Exception:
        pass
    _say(player, "Tell the user, in one short sentence in their own language: "
                 f"'{source}' could not be played on the display "
                 f"({err}){opened}.")


def _play_youtube(player, source: str, token: int) -> None:
    """The part that takes seconds. Speaks only if something goes wrong —
    silence means the video is on screen, which the user can see for
    themselves."""
    try:
        raw_urls, audio_url, title, err = _resolve_youtube(source)
    except Exception as e:                                  # noqa: BLE001
        raw_urls, audio_url, title = [], "", ""
        err = str(e)

    if not _still_wanted(token):
        return                       # the user closed it while it was resolving

    urls = (
        [raw_urls] if isinstance(raw_urls, str)
        else list(raw_urls or [])
    )
    meta = _pop_video_meta(urls)
    if meta:
        vcands = list(meta["video"])
        acands = list(meta["audio"])
        vid = meta.get("vid") or _pb.youtube_video_id(source)
    else:
        vcands = _pb.normalize_video_candidates(urls, default_audio=audio_url)
        acands = _pb.normalize_audio_candidates([audio_url])
        vid = _pb.youtube_video_id(source)

    if vcands:
        tried_ids = {vid} if vid else set()
        tried_urls = {c["url"] for c in vcands}
        retry_cb = _make_video_retry_cb(
            player, token, origin=source, title=title,
            tried_ids=tried_ids, tried_urls=tried_urls, attempt=0,
            client_pass=0,
        )
        try:
            _call_with_supported(
                player.show_video,
                vcands[0]["url"],
                title or source,
                muted=True,
                audio_source=vcands[0]["audio"],
                fallbacks=vcands[1:],
                audio_fallbacks=acands[1:],
                on_exhausted=retry_cb,
            )
            return
        except Exception as e:                              # noqa: BLE001
            err = str(e)

    # Resolution failed. Opening it in a browser is worse than playing it in the
    # HUD, but it is a great deal better than doing nothing, and the reason is
    # reported rather than swallowed.
    _report_youtube_failure(player, source, err, title=title)


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
