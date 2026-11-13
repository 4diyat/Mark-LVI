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
