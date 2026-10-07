from mutagen.id3 import ID3, SYLT, USLT, Encoding

from app.tags import read_lyrics
from listens_common import testing


def test_reads_unsynced_lyrics(tmp_path):
    f = testing.make_audio(tmp_path / "a.mp3", seconds=2)
    tags = ID3(f)
    tags.add(USLT(encoding=Encoding.UTF8, lang="eng", desc="", text="Line one\nLine two"))
    tags.save(f)
    with open(f, "rb") as fh:
        result = read_lyrics(fh)
    assert result == {"lyrics": "Line one\nLine two"}


def test_reads_synced_lyrics_as_lrc(tmp_path):
    f = testing.make_audio(tmp_path / "a.mp3", seconds=3)
    tags = ID3(f)
    tags.add(SYLT(encoding=Encoding.UTF8, lang="eng", format=2, type=1, desc="",
                  text=[("Hello", 0), ("World", 1500), ("Done", 61_000)]))
    tags.save(f)
    with open(f, "rb") as fh:
        result = read_lyrics(fh)
    assert result["lyrics_synced"] == "[00:00.00]Hello\n[00:01.50]World\n[01:01.00]Done"


def test_both_unsynced_and_synced_present(tmp_path):
    f = testing.make_audio(tmp_path / "a.mp3", seconds=2)
    tags = ID3(f)
    tags.add(USLT(encoding=Encoding.UTF8, lang="eng", desc="", text="Plain text"))
    tags.add(SYLT(encoding=Encoding.UTF8, lang="eng", format=2, type=1, desc="", text=[("Timed", 0)]))
    tags.save(f)
    with open(f, "rb") as fh:
        result = read_lyrics(fh)
    assert result == {"lyrics": "Plain text", "lyrics_synced": "[00:00.00]Timed"}


def test_frame_based_sylt_is_skipped_not_garbage(tmp_path):
    """format=1 is MPEG-frame-based timing, not milliseconds - we can't convert that to
    wall-clock time without the file's frame rate, so it must be silently skipped."""
    f = testing.make_audio(tmp_path / "a.mp3", seconds=2)
    tags = ID3(f)
    tags.add(SYLT(encoding=Encoding.UTF8, lang="eng", format=1, type=1, desc="", text=[("Hello", 10)]))
    tags.save(f)
    with open(f, "rb") as fh:
        result = read_lyrics(fh)
    assert "lyrics_synced" not in result


def test_no_lyrics_returns_empty_dict(tmp_path):
    f = testing.make_audio(tmp_path / "a.mp3", seconds=2)
    with open(f, "rb") as fh:
        assert read_lyrics(fh) == {}


def test_malformed_file_never_raises(tmp_path):
    junk = tmp_path / "junk.mp3"
    junk.write_bytes(b"not audio at all" * 50)
    with open(junk, "rb") as fh:
        assert read_lyrics(fh) == {}


def test_upload_stores_lyrics_on_the_track(env):
    from .test_upload import post

    f = testing.make_audio(env.dir / "song.mp3", title="With Lyrics")
    tags = ID3(f)
    tags.add(USLT(encoding=Encoding.UTF8, lang="eng", desc="", text="Verse one"))
    tags.save(f)

    tid = post(env, f).json()["track"]["id"]
    r = env.client.get(f"/tracks/{tid}/lyrics", headers=env.headers)
    assert r.status_code == 200
    assert r.json() == {"lyrics": "Verse one", "lyrics_synced": None}

    # lyrics aren't bloating the regular track response
    assert "lyrics" not in env.client.get(f"/tracks/{tid}", headers=env.headers).json()
