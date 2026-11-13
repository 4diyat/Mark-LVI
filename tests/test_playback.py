"""What the video and audio surfaces DECIDE — checked with no display.

WHY THIS FILE EXISTS
    The players themselves need Qt and a codec, and neither is on a CI runner.
    Everything around them, though, is a decision, and every bug this feature has
    had was one of those decisions:

      * a video reached its end and nothing happened: the HUD froze on the last
        frame, `video_is_playing()` kept saying yes, and the microphone JARVIS
        had closed for the soundtrack stayed closed for the rest of the session;
      * a second video opened over a YouTube one and left the first soundtrack
        playing underneath it;
      * the separate audio stream failed and the bar still said SOUND ON;
      * a soundtrack that ended 300 ms early left the rest of the video silent;
      * a link copied from a phone (`m.youtube.com`) was handed to Qt as a media
        file, and the user was told their link was broken.

    Each of those is a pure function of a few numbers now, so each of them is a
    test that runs anywhere. What cannot be tested here — that a codec decodes a
    frame — is the one thing a test would not have caught anyway.
"""
from __future__ import annotations

import pytest

from core import playback as pb


# ── what the user typed ─────────────────────────────────────────────────────

@pytest.mark.parametrize("raw, expected", [
    ('"C:\\clips\\a b.mp4"', "C:\\clips\\a b.mp4"),
    ("  ~/Videos/holiday.mkv  ", "~/Videos/holiday.mkv"),
    ("'/tmp/x y.mp3'\n", "/tmp/x y.mp3"),
    ("", ""),
    (None, ""),
])
def test_cleaning_a_source_removes_what_people_paste_with_it(raw, expected):
    """Explorer's Copy-as-path includes the quotes; a drag out of a terminal
    includes the newline. Qt treats both as part of the filename, so the file
    "does not exist" and the error blames the wrong thing."""
    assert pb.clean_source(raw) == expected


def test_a_real_file_is_recognised_and_missing_one_is_not(tmp_path):
    f = tmp_path / "clip with spaces.mp4"
    f.write_bytes(b"\x00" * 8)
    assert pb.local_file(str(f)) == str(f)
    assert pb.local_file('"%s"' % f) == str(f)          # quoted, as pasted
    assert pb.local_file(str(tmp_path / "nope.mp4")) == ""
    assert pb.local_file("") == ""


def test_a_file_url_becomes_a_path(tmp_path):
    """`file:///C:/x.mp4` reaches QUrl.fromLocalFile as a URL, not a path, and
    the file is then never found."""
    f = tmp_path / "a.mp4"
    f.write_bytes(b"\x00")
    assert pb.local_file(f.as_uri()) == str(f)


@pytest.mark.parametrize("link", [
    "https://www.youtube.com/watch?v=abc",
    "https://youtube.com/watch?v=abc",
    "https://m.youtube.com/watch?v=abc",              # copied from a phone
    "https://music.youtube.com/watch?v=abc",
    "https://youtu.be/abc",
    "https://www.youtube-nocookie.com/embed/abc",     # copied from an embed
    "youtu.be/abc",                                   # typed without a scheme
])
def test_every_youtube_host_counts_as_youtube(link):
    """The old check matched only `youtube.com/` and `youtu.be/`. Everything
    else was sent to QMediaPlayer as if it were a video file; Qt fetched an HTML
    page, failed on the format, and the user was told their link was broken."""
    assert pb.is_youtube(link)


@pytest.mark.parametrize("link", [
    "https://example.com/watch?v=abc",
    "https://notyoutube.com/watch?v=abc",
    "https://youtube.com.evil.test/watch",           # suffix must not match
])
def test_a_similar_looking_host_is_not_youtube(link):
    assert not pb.is_youtube(link)


@pytest.mark.parametrize("source, kind", [
    ("clip.mp4", "file"),
    ("Dune part two.mp4", "file"),              # spaces are not a URL
    ("song.mp3", "audio"),
    ("https://cdn.example/a.m4a", "audio"),
    ("https://youtu.be/abc", "youtube"),
    ("example.com/clip.mp4", "url"),
    ("https://example.com/clip.mp4", "url"),
    ("192.168.1.5:8080/live", "url"),
    ("photo.2024", "unknown"),
    ("", "unknown"),
])
def test_a_source_is_classified_once_and_consistently(source, kind):
    """One classifier, so the tool, the window and the player cannot disagree
    about what they were handed. `example.com/clip.mp4` is a URL to fetch;
    `clip.mp4` is a file to open — the extension alone cannot tell them apart,
    which is why the host has to be looked at first."""
    assert pb.kind_of(source) == kind


@pytest.mark.parametrize("source, expected", [
    ("song.mp3", "song.mp3"),                       # a FILE, not https://song.mp3
    ("clip.mp4", "clip.mp4"),
    ("example.com/clip.mp4", "https://example.com/clip.mp4"),
    ("www.example.com", "https://www.example.com"),
    ("https://cdn/a.mp3?token=1", "https://cdn/a.mp3?token=1"),
    ("C:\\clips\\a b.mp4", "C:\\clips\\a b.mp4"),
])
def test_a_url_is_only_invented_when_a_host_was_meant(source, expected):
    """Turning `song.mp3` into `https://song.mp3` turns a local file into a DNS
    lookup, and the user is told a song in their own folder cannot be reached."""
    assert pb.media_url(source) == expected


@pytest.mark.parametrize("source", [
    "https://r4---sn-abc.googlevideo.com/videoplayback?expire=1&sig=xyz&itag=251",
])
def test_a_resolved_stream_url_is_passed_through_untouched(source):
    """The player receives googlevideo URLs with signed query strings. Re-encoding
    one breaks the signature and the stream 403s — so this path must be a
    no-op, and the test says so."""
    assert pb.media_url(source) == source


def test_a_page_that_says_it_is_a_page_is_refused():
    """An identifiable page — `.html`, a page extension, or a bare host with no
    path — is refused, because playing one produces "format not supported" and
    that reads as "this app cannot play anything at all"."""
    assert not pb.is_audio_source("https://example.com/index.html")
    assert not pb.is_audio_source("https://example.com/track.php")
    assert not pb.is_audio_source("https://example.com/")
    assert not pb.is_audio_source("clip.mp4")
    assert not pb.is_audio_source("")


def test_an_ambiguous_url_is_attempted_rather_than_guessed_at():
    """/radio and /page are the same shape, and no rule can tell them apart.

    Internet radio and HLS/DASH endpoints look exactly like that, so refusing
    every extension-less path would break the thing people ask for most; and
    accepting them means a page URL produces Qt's real error instead of a
    guess. The tool's job is to try and report what actually failed — a
    heuristic here would either silence radio or invent a reason.
    """
    assert pb.is_audio_source("https://stream.example/radio")
    assert pb.is_audio_source("https://example.com/page")   # ambiguous: tried


@pytest.mark.parametrize("source", [
    "song.mp3",
    "https://cdn.example/a.m4a",
    "https://example.com/a.mp4",                     # video, still sound
    "https://stream.example/radio",                  # a stream endpoint
    "https://youtu.be/abc",                          # YouTube has audio
])
def test_audio_accepts_what_people_ask_for(source):
    assert pb.is_audio_source(source)


def test_a_header_label_has_no_extension_and_no_query():
    assert pb.audio_title("https://x/y/My_song.mp3?token=1") == "My song"
    assert pb.audio_title("/home/me/Some File.mp3") == "Some File"
    assert pb.audio_title("") == ""


def test_a_windows_path_shows_its_file_name_not_the_whole_path():
    """CI on windows-latest caught this; Linux never could.

    "C:\\Users\\me\\song.mp3" has no "://", so urlparse reports the entire
    string as its path, there is no "/" to split on, and the audio header showed
    the user's entire folder tree. Fixed by splitting on both separators first
    and only then looking for a query string.
    """
    assert pb.audio_title(r"C:\Users\me\Music\song.mp3") == "song"
    assert pb.audio_title(r"C:\Users\me\Music\My_Song.mp3") == "My Song"
    # A quoted path arrives from Explorer's "Copy as path" and must survive.
    assert pb.audio_title(r'"C:\Users\me\Music\My Song.mp3"') == "My Song"


def test_a_path_is_not_a_url_and_a_bare_host_is_not_a_path():
    """"Which builder" is the question the window asks before making a QUrl.

    `QUrl` reads a Windows drive letter as a scheme and a bare URL as a path, so
    both directions are wrong: a file must go through `fromLocalFile`, and a
    bare host (`example.com/clip.mp4`) must become https rather than a file that
    does not exist.
    """
    assert pb.qurl_safe(r"C:\clips\a b.mp4") is True
    assert pb.qurl_safe("C:/clips/a.mp4") is True
    assert pb.qurl_safe("/home/me/a b.mp3") is True
    assert pb.qurl_safe("~/Videos/holiday.mkv") is True
    assert pb.qurl_safe(r"\\server\share\a.mp4") is True       # a UNC share

    assert pb.qurl_safe("https://cdn.example/a.mp4") is False
    assert pb.qurl_safe("http://cdn.example/a.mp4") is False
    assert pb.qurl_safe("file:///C:/a.mp4") is False
    assert pb.qurl_safe("example.com/clip.mp4") is False          # bare host
    assert pb.qurl_safe("youtube.com/watch?v=1") is False
    assert pb.qurl_safe("") is False


def test_a_query_string_never_reaches_the_header():
    assert pb.audio_title("https://cdn.example/a/My%20Song.m4a?token=abc") == "My Song"
    assert pb.audio_title("https://radio.example/stream#t=90") == "stream"


# ── end of media: the bug that made JARVIS deaf ─────────────────────────────

def test_a_finished_video_closes_and_gives_the_microphone_back():
    """THE BUG. Nothing listened for EndOfMedia, so when a video ended the HUD
    stayed on it, `video_is_playing()` stayed True, and — if the sound had been
    on — the microphone JARVIS closed for it stayed closed. The assistant was
    deaf for the rest of the session, with no video on screen and nothing
    anywhere saying why."""
    effect = pb.ended_video_effect("ended", sound_was_on=True)
    assert effect["close"] is True
    assert effect["release_mic"] is True


def test_a_finished_video_with_the_sound_off_does_not_touch_the_microphone():
    """Reopening a microphone nobody closed is not harmless: it undoes a mute
    the user asked for."""
    effect = pb.ended_video_effect("ended", sound_was_on=False)
    assert effect["close"] is True
    assert effect["release_mic"] is False


def test_playing_on_is_not_an_end():
    for state in ("playing", "paused", "buffering", "loading"):
        assert pb.ended_video_effect(state, True)["close"] is False


def test_a_finished_soundtrack_does_not_cut_the_picture_off():
    """Picture and sound are separate streams and are not the same length, so
    the sound routinely ends a few hundred milliseconds early. Closing the video
    on an audio end would truncate the last frames; what must happen instead is
    that the bar stops claiming sound."""
    assert pb.ended_audio_effect("ended") == {"mark_finished": True}
    assert pb.ended_audio_effect("playing") == {"mark_finished": False}


def test_a_broken_source_stops_counting_as_playing():
    """InvalidMedia and NoMedia must also tear the surface down — otherwise the
    HUD sits on a black page with a mute button and no way to tell that anything
    failed."""
    for status in ("ended", "invalid", "no_media"):
        assert pb.should_open_from_ended(status)
    assert not pb.should_open_from_ended("buffering")


# ── opening over something ──────────────────────────────────────────────────

def test_opening_a_video_stops_the_previous_soundtrack():
    """Second bug: a YouTube soundtrack kept playing underneath the local file
    that had just been opened, and the mute button then controlled the new,
    silent output while the old one was audible."""
    plan = pb.opening_while_playing(is_playing=True, split_sound=True)
    assert plan["stop_video"] and plan["stop_audio"]
    assert plan["stop_timer"] is True
    assert plan["release_mic"] is True


def test_opening_over_a_single_stream_file_still_stops_the_timer():
    """The timer may be running from an earlier open that never closed, so it is
    stopped unconditionally — a leftover timer poking a player with no source is
    the kind of thing that throws on a thread with no handler."""
    plan = pb.opening_while_playing(is_playing=True, split_sound=False)
    assert plan["stop_audio"] is False        # there is no second player in play
    assert plan["stop_timer"] is True


def test_opening_with_nothing_playing_still_stops_the_timer():
    plan = pb.opening_while_playing(is_playing=False, split_sound=False)
    assert plan == {"stop_video": False, "stop_audio": False,
                    "stop_timer": True, "release_mic": False}


# ── keeping picture and sound together ──────────────────────────────────────

def test_a_small_drift_is_left_alone():
    """Correcting a gap of 200 ms is more audible than the gap: it skips or
    repeats a syllable, where the drift itself is below what people notice."""
    for drift in (-250, -120, 0, 120, 250):
        d = pb.sync_decision(10_000, 10_000 + drift, "playing")
        assert d["seek"] is False, f"{drift} ms was corrected"


def test_a_large_drift_is_corrected_to_the_picture():
    d = pb.sync_decision(10_000, 10_900, "playing")
    assert d["seek"] is True and d["position"] == 10_000
    assert not d["restart"]


def test_a_soundtrack_that_stopped_early_is_restarted():
    """The case the old check could not see: it only ran while BOTH players were
    playing, so a soundtrack that ended first left the rest of the video silent
    with the bar still saying SOUND ON."""
    d = pb.sync_decision(25_000, 1_000, "stopped")
    assert d["restart"] is True and d["seek"] is True
    assert d["position"] == 25_000


def test_a_buffering_soundtrack_is_not_seeked():
    """A seek on a stream that has not buffered is silently discarded, and the
    old code then believed it had corrected something."""
    for state in ("buffering", "loading", "paused"):
        assert pb.sync_decision(10_000, 0, state)["seek"] is False


def test_an_absurd_drift_restarts_rather_than_seeks():
    """Seeking 40 s ahead of an unstarted stream usually fails without an error;
    restarting at the picture's position is the only thing that works."""
    d = pb.sync_decision(60_000, 0, "playing")
    assert d["restart"] is True


# ── the microphone ──────────────────────────────────────────────────────────

def test_the_sound_turns_the_microphone_off_and_the_silence_turns_it_back_on():
    """JARVIS subtracts its own output from the microphone, but a video plays
    through a different output entirely, so the guard has never heard of it and
    the assistant answers the film."""
    on = pb.mic_plan(video_on=True, sound_muted=False, already_auto_muted=False,
                     user_muted=False)
    assert on == {"close": True, "reopen": False, "set_auto": True}

    off = pb.mic_plan(video_on=True, sound_muted=True, already_auto_muted=True,
                      user_muted=False)
    assert off == {"close": False, "reopen": True, "set_auto": False}


def test_a_mute_the_user_asked_for_is_never_undone():
    """The rule that makes automating this safe at all. Pressing F4 during a
    video hands the decision back to the person for good."""
    for video_on in (True, False):
        for sound_muted in (True, False):
            plan = pb.mic_plan(video_on=video_on, sound_muted=sound_muted,
                               already_auto_muted=False, user_muted=True)
            assert plan["close"] is False and plan["reopen"] is False


def test_nothing_happens_when_there_is_no_video_and_nothing_was_closed():
    plan = pb.mic_plan(video_on=False, sound_muted=True, already_auto_muted=False,
                       user_muted=False)
    assert plan == {"close": False, "reopen": False, "set_auto": False}


# ── 403 forbidden & fallback search decisions ──────────────────────────────

@pytest.mark.parametrize("detail, expected", [
    ("Error transferring https://r1.googlevideo.com/ - server replied: Forbidden", True),
    ("HTTP Error 403", True),
    ("AccessDenied", True),
    ("401 Unauthorized", True),
    ("Connection refused", True),
    ("Codec not supported", False),
    ("", False),
])
def test_forbidden_error_recognition(detail, expected):
    assert pb.is_forbidden_error(detail) is expected


@pytest.mark.parametrize("url, vid", [
    ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
    ("https://m.youtube.com/watch?v=abcDEF12345&t=12", "abcDEF12345"),
    ("https://youtu.be/xyz_987-123?si=1", "xyz_987-123"),
    ("https://www.youtube.com/shorts/shortID1234", "shortID1234"),
    ("https://www.youtube-nocookie.com/embed/embedID1234", "embedID1234"),
    ("https://example.com/clip.mp4", ""),
])
def test_youtube_video_id_extraction(url, vid):
    assert pb.youtube_video_id(url) == vid


def test_normalize_video_candidates_deduplicates_and_keeps_per_stream_audio():
    cands = pb.normalize_video_candidates(
        [
            {"url": "https://cdn/combined.mp4", "audio": ""},
            "https://cdn/video720.mp4",
            "https://cdn/video720.mp4",
            {"url": "", "audio": "https://cdn/a.m4a"},
            {"url": "https://cdn/video480.mp4", "audio": "https://cdn/a2.m4a"},
        ],
        default_audio="https://cdn/a.m4a",
    )
    assert cands == [
        {"url": "https://cdn/combined.mp4", "audio": ""},
        {"url": "https://cdn/video720.mp4", "audio": "https://cdn/a.m4a"},
        {"url": "https://cdn/video480.mp4", "audio": "https://cdn/a2.m4a"},
    ]


def test_fallback_search_query_derives_useful_queries_and_ignores_junk():
    assert pb.fallback_search_query("Dune Part Two trailer") == "Dune Part Two trailer"
    assert pb.fallback_search_query(
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ", "Never Gonna Give You Up"
    ) == "Never Gonna Give You Up"
    assert pb.fallback_search_query(
        "https://cdn.example/Dune_Official_Trailer.mp4"
    ) == "Dune Official Trailer"
    # Generic stems and local files must not spawn nonsensical web searches.
    assert pb.fallback_search_query("https://cdn.example/clip.mp4", "clip") == ""
    assert pb.fallback_search_query("http://192.168.1.5:8080/live") == ""
    assert pb.fallback_search_query(r"C:\clips\holiday.mp4", "holiday") == ""


def test_should_search_alternate_respects_origin_error_and_retry_cap():
    assert pb.should_search_alternate("lofi beats", "403 Forbidden", attempt=0) is True
    assert pb.should_search_alternate("lofi beats", "403 Forbidden", attempt=3) is False
    assert pb.should_search_alternate(
        "https://cdn.example/Dune_Official_Trailer.mp4",
        "server replied: Forbidden",
        attempt=0,
    ) is True
    assert pb.should_search_alternate(
        "https://cdn.example/Dune_Official_Trailer.mp4",
        "codec unsupported",
        attempt=0,
    ) is False
    assert pb.should_search_alternate(r"C:\clips\Dune_Trailer.mp4", "403 Forbidden") is False
    assert pb.should_search_alternate(
        "https://youtu.be/dQw4w9WgXcQ", "403 Forbidden", title="", attempt=0
    ) is True
    assert pb.should_search_alternate(
        "https://youtu.be/dQw4w9WgXcQ", "403 Forbidden", title="", attempt=1
    ) is False

