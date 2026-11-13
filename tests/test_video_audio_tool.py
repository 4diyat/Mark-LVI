"""The video/audio TOOL — what it routes where, and what it refuses.

WHY THIS IS A FAKE PLAYER AND NOT A WIDGET TEST
    `actions/video_player.py` never touches Qt: it decides, then calls a handful
    of methods on `player`. So the whole tool can be driven with a stand-in that
    records what it was asked to do, which is exactly how the interesting
    failures show up:

      * an .mp3 sent to the VIDEO surface gives a black page and a Qt error,
        where the user asked for music and expected to keep seeing the
        assistant — so the routing decision is worth asserting;
      * a web page offered as audio must be refused with a reason, not handed to
        a decoder that can only answer "format not supported";
      * `stop` while nothing plays must not pretend something was stopped;
      * the answer must come back immediately even when the work takes seconds,
        because the model is waiting on it.

    What a fake player cannot prove is that a codec decodes. That gap is real
    and is stated in the PR rather than papered over.
"""
from __future__ import annotations

import threading

import pytest

from actions import video_player as vp


class FakePlayer:
    """Every method the tool is allowed to call, recording its arguments."""

    def __init__(self):
        self.calls: list[tuple] = []
        self._video_on = False
        self._audio_on = False

    # video
    def show_video(self, source, title="", muted=True, audio_source=""):
        self.calls.append(("show_video", source, title, muted, audio_source))
        self._video_on = True

    def stop_video(self):
        self.calls.append(("stop_video",))
        self._video_on = False

    def set_video_muted(self, muted):
        self.calls.append(("set_video_muted", muted))

    def video_is_playing(self):
        return self._video_on

    # audio
    def play_audio(self, source, title="", volume=0.7, loop=False):
        self.calls.append(("play_audio", source, title, volume, loop))
        self._audio_on = True

    def stop_audio(self):
        self.calls.append(("stop_audio",))
        self._audio_on = False

    def pause_audio(self, paused=True):
        self.calls.append(("pause_audio", paused))

    def set_audio_volume(self, volume):
        self.calls.append(("set_audio_volume", volume))

    def audio_is_playing(self):
        return self._audio_on

    def request_say(self, instruction):
        self.calls.append(("say", instruction))

    def names(self) -> list[str]:
        return [c[0] for c in self.calls]

    def first(self, name: str):
        for c in self.calls:
            if c[0] == name:
                return c
        return None


@pytest.fixture()
def player():
    return FakePlayer()


@pytest.fixture(autouse=True)
def no_browser(monkeypatch):
    """The fallback opens a browser. Never in a test suite."""
    import webbrowser
    monkeypatch.setattr(webbrowser, "open", lambda *a, **k: True)


# ── routing: a sound file is not a video ───────────────────────────────────

def test_a_sound_file_goes_to_the_audio_surface(player, tmp_path):
    """`.mp3` through the picture player is a black page and a decoder error,
    where the user asked for music and expected to keep seeing the assistant."""
    song = tmp_path / "My_Song.mp3"
    song.write_bytes(b"\x00" * 16)

    answer = vp.video_player({"action": "play", "source": str(song)}, player=player)

    assert "stop_video" not in player.names()
    call = player.first("play_audio")
    assert call is not None, f"routed to {player.names()}"
    assert call[1] == str(song)
    assert call[2] == "My Song"          # extension off, underscores to spaces
    assert "My Song" in answer


def test_a_video_file_still_goes_to_the_display(player, tmp_path):
    clip = tmp_path / "holiday.mp4"
    clip.write_bytes(b"\x00" * 16)
    vp.video_player({"action": "play", "source": str(clip)}, player=player)
    call = player.first("show_video")
    assert call is not None
    assert call[3] is True, "a video must start muted"


def test_an_audio_url_goes_to_the_audio_surface(player):
    answer = vp.video_player({"action": "play",
                              "source": "https://cdn.example/a.m4a"},
                             player=player)
    assert player.first("play_audio") is not None
    assert "a" in answer


def test_a_video_url_goes_to_the_display(player):
    vp.video_player({"action": "play", "source": "https://cdn.example/clip.mp4"},
                    player=player)
    assert player.first("show_video") is not None
    assert "play_audio" not in player.names()


def test_play_audio_is_explicit_and_always_audio(player, tmp_path):
    """Even a video file, when the user asked for audio — that is a legitimate
    request (the sound of a concert clip) and the model may mean it."""
    clip = tmp_path / "concert.mp4"
    clip.write_bytes(b"\x00" * 16)
    vp.video_player({"action": "play_audio", "source": str(clip)}, player=player)
    assert player.first("play_audio") is not None
    assert "show_video" not in player.names()


# ── what it refuses, and how ───────────────────────────────────────────────

def test_a_web_page_is_refused_with_a_reason(player):
    """A page has no sound file behind it. Handing it to a decoder produces
    "format not supported", which reads as "this app cannot play anything"."""
    answer = vp.video_player({"action": "play_audio",
                              "source": "https://example.com/index.html"},
                             player=player)
    assert "play_audio" not in player.names()
    assert "web page" in answer.lower() or "does not look" in answer.lower()


def test_play_with_no_source_asks_rather_than_failing(player):
    assert vp.video_player({"action": "play", "source": ""}, player=player) == \
        "What should I play?"


def test_stopping_nothing_does_not_claim_a_stop(player):
    """`video_player` is called by a model that may be guessing. Answering
    "Stopped the audio" when nothing was playing teaches it nothing and tells
    the user something untrue."""
    assert vp.video_player({"action": "stop_audio"}, player=player) == \
        "Nothing is playing."
    assert "stop_audio" not in player.names()

    player._audio_on = True
    assert vp.video_player({"action": "stop_audio"}, player=player) == \
        "Stopped the audio."
    assert "stop_audio" in player.names()


def test_volume_is_clamped_and_a_missing_one_is_questioned(player):
    vp.video_player({"action": "volume", "volume": 5}, player=player)
    assert player.first("set_audio_volume")[1] == 1.0

    vp.video_player({"action": "volume", "volume": -3}, player=player)
    assert player.calls[-1] == ("set_audio_volume", 0.0)

    player.calls.clear()
    answer = vp.video_player({"action": "volume"}, player=player)
    assert "volume" in answer.lower()
    assert "set_audio_volume" not in player.names()


def test_a_player_without_audio_says_so_instead_of_crashing():
    """An older build, or a Qt without the multimedia plugins, has the video
    half only. The tool must notice rather than raise AttributeError into the
    model's tool loop."""

    class VideoOnly:
        def show_video(self, *a, **k):
            pass

        def video_is_playing(self):
            return False

    answer = vp.video_player({"action": "play_audio", "source": "a.mp3"},
                             player=VideoOnly())
    assert "no audio output" in answer.lower()


# ── the seconds-long path ──────────────────────────────────────────────────

def test_youtube_audio_answers_immediately_and_resolves_on_a_thread(
        player, monkeypatch):
    """Resolution takes seconds that nothing can remove. Making the model wait
    for it stalls the conversation for something the user can already hear."""
    started = threading.Event()
    done = threading.Event()

    def fake_resolve(source):
        started.set()
        done.set()
        return ("", "https://audio.example/x.m4a", "A Song", "")

    monkeypatch.setattr(vp, "_resolve_youtube", fake_resolve)

    answer = vp.video_player(
        {"action": "play_audio", "source": "https://youtu.be/abc"},
        player=player)

    # Answered before any of the work happened.
    assert answer.startswith("status=opening")
    assert done.wait(5.0), "the resolver thread never ran"
    started.wait(1.0)
    # And the audio eventually reaches the player, on the other thread.
    for _ in range(100):
        if player.first("play_audio"):
            break
        done.wait(0.02)
    call = player.first("play_audio")
    assert call is not None
    assert call[1] == "https://audio.example/x.m4a"
    assert call[2] == "A Song"


def test_a_failed_resolution_says_so_rather_than_going_silent(player, monkeypatch):
    """Silence is the one answer that is never acceptable: the user asked for
    music and nothing happened."""
    monkeypatch.setattr(vp, "_resolve_youtube",
                        lambda s: ("", "", "", "the video is unavailable"))

    vp.video_player({"action": "play_audio", "source": "https://youtu.be/abc"},
                    player=player)

    for _ in range(200):
        if player.first("say"):
            break
        threading.Event().wait(0.01)
    said = player.first("say")
    assert said is not None, "a failure was swallowed"
    assert "unavailable" in said[1]


def test_a_stopped_request_is_abandoned(player, monkeypatch):
    """The user changed their mind while it was resolving. `_begin_open` is the
    token that makes the late answer harmless — without it the audio appears
    seconds after it was cancelled."""
    release = threading.Event()

    def slow_resolve(_source):
        release.wait(5.0)
        return ("", "https://audio.example/late.m4a", "Late", "")

    monkeypatch.setattr(vp, "_resolve_youtube", slow_resolve)
    vp.video_player({"action": "play_audio", "source": "https://youtu.be/abc"},
                    player=player)
    vp.video_player({"action": "stop"}, player=player)   # bumps the token
    release.set()
    threading.Event().wait(0.3)
    assert player.first("play_audio") is None


# ── fallback streams & searching another source on 403 Forbidden ───────────

class FallbackCapablePlayer(FakePlayer):
    """FakePlayer accepting optional fallback kwargs like real JarvisUI."""

    def show_video(self, source, title="", muted=True, audio_source="",
                   fallbacks=None, on_exhausted=None, audio_fallbacks=None):
        self.calls.append((
            "show_video", source, title, muted, audio_source,
            list(fallbacks or []), on_exhausted, list(audio_fallbacks or []),
        ))
        self._video_on = True


def _fake_ytdlp(monkeypatch, handler):
    import sys
    import types

    class _YDL:
        def __init__(self, opts=None):
            self.opts = opts or {}

        def __enter__(self):
            return self

        def __exit__(self, *_a):
            return False

        def extract_info(self, target, download=False):
            return handler(self.opts, target)

    mod = types.ModuleType("yt_dlp")
    mod.YoutubeDL = _YDL
    monkeypatch.setitem(sys.modules, "yt_dlp", mod)


def test_resolve_youtube_ranks_combined_without_double_audio_and_skips_forbidden_search_entry(
        monkeypatch):
    def handler(opts, target):
        if target.startswith("ytsearch5:") and opts.get("extract_flat"):
            return {
                "entries": [
                    {"id": "bad11111111", "title": "Blocked Video",
                     "url": "https://www.youtube.com/watch?v=bad11111111"},
                    {"id": "ok222222222", "title": "Working Video",
                     "url": "https://www.youtube.com/watch?v=ok222222222"},
                ]
            }
        if "bad11111111" in target:
            raise RuntimeError("HTTP Error 403: Forbidden")
        return {
            "id": "ok222222222",
            "title": "Working Video",
            "formats": [
                {"url": "https://cdn/combined360.mp4", "protocol": "https",
                 "vcodec": "avc1", "acodec": "mp4a", "ext": "mp4",
                 "height": 360, "tbr": 500},
                {"url": "https://cdn/vid720_avc.mp4", "protocol": "https",
                 "vcodec": "avc1", "acodec": "none", "ext": "mp4",
                 "height": 720, "tbr": 1500},
                {"url": "https://cdn/vid480.webm", "protocol": "https",
                 "vcodec": "vp9", "acodec": "none", "ext": "webm",
                 "height": 480, "tbr": 800},
                {"url": "https://cdn/aud.m4a", "protocol": "https",
                 "vcodec": "none", "acodec": "mp4a", "ext": "m4a",
                 "language_preference": 10, "tbr": 128},
            ],
        }

    _fake_ytdlp(monkeypatch, handler)
    vcands, acands, title, vid, err = vp._resolve_youtube_candidates("lofi beats")
    assert err == ""
    assert vid == "ok222222222"
    assert title == "Working Video"
    assert vcands[0] == {"url": "https://cdn/combined360.mp4", "audio": ""}
    assert vcands[1] == {"url": "https://cdn/vid720_avc.mp4",
                         "audio": "https://cdn/aud.m4a"}
    assert vcands[2] == {"url": "https://cdn/vid480.webm",
                         "audio": "https://cdn/aud.m4a"}
    assert acands == ["https://cdn/aud.m4a"]


def test_resolve_youtube_url_falls_back_to_alt_client_then_searches_by_title(
        monkeypatch):
    def handler(opts, target):
        client = (opts.get("extractor_args") or {}).get("youtube", {}).get("player_client")
        if "badvid12345" in target:
            if not client:
                raise RuntimeError("HTTP Error 403: Forbidden")
            if client == ["android", "ios"]:
                return {"id": "badvid12345", "title": "Dune Trailer", "formats": []}
            return {"id": "badvid12345", "title": "Dune Trailer", "formats": []}
        if target.startswith("ytsearch5:Dune Trailer"):
            return {
                "entries": [
                    {"id": "badvid12345", "title": "Dune Trailer", "formats": [
                        {"url": "https://cdn/old.mp4", "protocol": "https",
                         "vcodec": "avc1", "acodec": "mp4a", "ext": "mp4",
                         "height": 360, "tbr": 400},
                    ]},
                    {"id": "altvid67890", "title": "Dune Trailer Mirror", "formats": [
                        {"url": "https://cdn/mirror.mp4", "protocol": "https",
                         "vcodec": "avc1", "acodec": "mp4a", "ext": "mp4",
                         "height": 720, "tbr": 900},
                    ]},
                ]
            }
        return {}

    _fake_ytdlp(monkeypatch, handler)
    vcands, _acands, title, vid, err = vp._resolve_youtube_candidates(
        "https://www.youtube.com/watch?v=badvid12345"
    )
    assert err == ""
    assert vid == "altvid67890"
    assert title == "Dune Trailer Mirror"
    assert vcands[0]["url"] == "https://cdn/mirror.mp4"


def test_exhausted_video_streams_trigger_search_for_another_playable_source(
        monkeypatch):
    p = FallbackCapablePlayer()

    def handler(opts, target):
        if target.startswith("ytsearch5:"):
            return {
                "entries": [
                    {"id": "vid11111111", "title": "Result 1", "formats": [
                        {"url": "https://cdn/r1_a.mp4", "protocol": "https",
                         "vcodec": "avc1", "acodec": "mp4a", "ext": "mp4",
                         "height": 360, "tbr": 400},
                        {"url": "https://cdn/r1_b.mp4", "protocol": "https",
                         "vcodec": "avc1", "acodec": "none", "ext": "mp4",
                         "height": 720, "tbr": 1000},
                        {"url": "https://cdn/r1_aud.m4a", "protocol": "https",
                         "vcodec": "none", "acodec": "mp4a", "ext": "m4a",
                         "tbr": 128},
                    ]},
                    {"id": "vid22222222", "title": "Result 2", "formats": [
                        {"url": "https://cdn/r2_ok.mp4", "protocol": "https",
                         "vcodec": "avc1", "acodec": "mp4a", "ext": "mp4",
                         "height": 720, "tbr": 900},
                    ]},
                ]
            }
        return {}

    _fake_ytdlp(monkeypatch, handler)
    vp.video_player({"action": "play", "source": "cyberpunk trailer"}, player=p)

    for _ in range(200):
        if len(p.calls) >= 1:
            break
        threading.Event().wait(0.01)

    first = p.calls[0]
    assert first[1] == "https://cdn/r1_a.mp4"
    assert [c["url"] for c in first[5]] == ["https://cdn/r1_b.mp4"]
    cb = first[6]
    assert callable(cb)

    # Simulate all stream candidates from Result 1 returning 403 Forbidden.
    assert cb("Error transferring - server replied: Forbidden") is True

    for _ in range(200):
        if len(p.calls) >= 2:
            break
        threading.Event().wait(0.01)

    second = p.calls[1]
    assert second[1] == "https://cdn/r2_ok.mp4"
    assert second[2] == "Result 2"


def test_direct_forbidden_url_searches_for_another_playable_source(monkeypatch):
    p = FallbackCapablePlayer()

    def handler(_opts, target):
        if "Dune Official Trailer" in target:
            return {
                "entries": [
                    {"id": "alt99999999", "title": "Dune Official Trailer",
                     "formats": [
                         {"url": "https://cdn/dune_alt.mp4", "protocol": "https",
                          "vcodec": "avc1", "acodec": "mp4a", "ext": "mp4",
                          "height": 720, "tbr": 1200},
                     ]},
                ]
            }
        return {}

    _fake_ytdlp(monkeypatch, handler)
    vp.video_player(
        {"action": "play",
         "source": "https://blocked.example/Dune_Official_Trailer.mp4"},
        player=p,
    )
    assert len(p.calls) == 1
    cb = p.calls[0][6]
    assert callable(cb)
    assert cb("HTTP 403 Forbidden") is True

    for _ in range(200):
        if len(p.calls) >= 2:
            break
        threading.Event().wait(0.01)

    assert p.calls[1][1] == "https://cdn/dune_alt.mp4"


def test_exhausted_audio_stream_searches_another_audio_source(monkeypatch):
    class AudioFallbackPlayer(FakePlayer):
        def play_audio(self, source, title="", volume=0.7, loop=False,
                       fallbacks=None, on_exhausted=None):
            self.calls.append((
                "play_audio", source, title, volume, loop,
                list(fallbacks or []), on_exhausted,
            ))
            self._audio_on = True

    p = AudioFallbackPlayer()

    def handler(opts, target):
        client = (opts.get("extractor_args") or {}).get("youtube", {}).get("player_client")
        if "aud11111111" in target and not target.startswith("ytsearch"):
            if client:
                raise RuntimeError("HTTP Error 403: Forbidden")
            return {
                "id": "aud11111111", "title": "Ambient Study Music",
                "formats": [
                    {"url": "https://cdn/a1.m4a", "protocol": "https",
                     "vcodec": "none", "acodec": "mp4a", "ext": "m4a",
                     "tbr": 128},
                    {"url": "https://cdn/a1_alt.webm", "protocol": "https",
                     "vcodec": "none", "acodec": "opus", "ext": "webm",
                     "tbr": 96},
                ],
            }
        if target.startswith("ytsearch5:Ambient Study Music"):
            return {
                "entries": [
                    {"id": "aud11111111", "title": "Ambient Study Music",
                     "formats": [{"url": "https://cdn/a1.m4a",
                                  "protocol": "https", "vcodec": "none",
                                  "acodec": "mp4a", "ext": "m4a", "tbr": 128}]},
                    {"id": "aud22222222", "title": "Ambient Study Alt",
                     "formats": [{"url": "https://cdn/a2_ok.m4a",
                                  "protocol": "https", "vcodec": "none",
                                  "acodec": "mp4a", "ext": "m4a", "tbr": 128}]},
                ]
            }
        return {}

    _fake_ytdlp(monkeypatch, handler)
    vp.video_player(
        {"action": "play_audio",
         "source": "https://www.youtube.com/watch?v=aud11111111"},
        player=p,
    )

    for _ in range(200):
        if len(p.calls) >= 1:
            break
        threading.Event().wait(0.01)

    first = p.calls[0]
    assert first[1] == "https://cdn/a1.m4a"
    assert first[5] == ["https://cdn/a1_alt.webm"]
    assert first[6]("server replied: Forbidden") is True

    for _ in range(200):
        if len(p.calls) >= 2:
            break
        threading.Event().wait(0.01)

    assert p.calls[1][1] == "https://cdn/a2_ok.m4a"


def test_retry_cap_stops_looping_and_stop_cancels_inflight_retry(monkeypatch):
    p = FallbackCapablePlayer()
    opened_pages = []
    monkeypatch.setattr(vp.webbrowser, "open",
                        lambda url: opened_pages.append(url) or True)

    counter = {"n": 0}

    def handler(_opts, target):
        counter["n"] += 1
        vid = f"vid{counter['n']:08d}"
        return {
            "entries": [{
                "id": vid, "title": f"Try {counter['n']}",
                "formats": [{"url": f"https://cdn/{vid}.mp4",
                             "protocol": "https", "vcodec": "avc1",
                             "acodec": "mp4a", "ext": "mp4",
                             "height": 480, "tbr": 500}],
            }]
        }

    _fake_ytdlp(monkeypatch, handler)
    vp.video_player({"action": "play", "source": "jazz piano"}, player=p)

    # Walk through all retries until the cap stops scheduling new searches.
    cb = None
    for idx in range(vp._MAX_RETRY_SEARCHES + 1):
        for _ in range(200):
            if len([c for c in p.calls if c[0] == "show_video"]) > idx:
                break
            threading.Event().wait(0.01)
        show_calls = [c for c in p.calls if c[0] == "show_video"]
        cb = show_calls[-1][6]
        if idx < vp._MAX_RETRY_SEARCHES:
            assert cb("403 Forbidden") is True
        else:
            assert cb("403 Forbidden") is False

    # Now verify stop cancels an un-fired retry callback as well.
    p2 = FallbackCapablePlayer()
    vp.video_player({"action": "play", "source": "ambient rain"}, player=p2)
    for _ in range(200):
        if p2.calls:
            break
        threading.Event().wait(0.01)
    cb2 = p2.calls[0][6]
    vp.video_player({"action": "stop"}, player=p2)
    assert cb2("403 Forbidden") is False


