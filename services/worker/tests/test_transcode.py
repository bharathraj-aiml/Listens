import pytest

from app import transcode
from listens_common import testing


def test_select_renditions():
    names = lambda kbps: [n for n, _ in transcode.select_renditions(kbps)]  # noqa: E731
    assert names(None) == ["q96", "q160", "q320"]
    assert names(900) == ["q96", "q160", "q320"]  # lossless-ish source
    assert names(320) == ["q96", "q160", "q320"]
    assert names(256) == ["q96", "q160", "q320"]  # 256 >= 0.8 * 320
    assert names(192) == ["q96", "q160"]
    assert names(128) == ["q96", "q160"]  # 128 >= 0.8 * 160
    assert names(64) == ["q96"]  # 96k is always produced


def test_probe_reads_duration_and_rejects_non_audio(tmp_path):
    f = testing.make_audio(tmp_path / "a.mp3", seconds=3, bitrate="128k")
    p = transcode.probe(f)
    assert 2900 <= p.duration_ms <= 3300 and p.bitrate_kbps == 128

    junk = tmp_path / "junk.mp3"
    junk.write_bytes(b"this is not audio at all" * 100)
    with pytest.raises(transcode.TranscodeError) as exc:
        transcode.probe(junk)
    assert str(tmp_path) not in str(exc.value)  # no internal paths in user-visible errors


def test_transcode_produces_hls_ladder_with_master(tmp_path):
    src = testing.make_audio(tmp_path / "a.flac", seconds=14)
    out = tmp_path / "out"
    transcode.transcode_hls(src, out, transcode.RENDITIONS)
    master = (out / "master.m3u8").read_text()
    assert master.count("#EXT-X-STREAM-INF") == 3
    for name, kbps in transcode.RENDITIONS:
        assert f"{name}/index.m3u8" in master
        playlist = (out / name / "index.m3u8").read_text()
        assert "#EXT-X-ENDLIST" in playlist  # VOD
        segs = sorted((out / name).glob("seg_*.ts"))
        assert len(segs) == 3  # 14 s / 6 s segments -> 3
    bw = sorted(int(x) for x in __import__("re").findall(r"BANDWIDTH=(\d+)", master))
    assert bw[0] < bw[1] < bw[2]  # distinct, ordered bitrates so the player can pick levels


def test_extract_cover(tmp_path):
    with_art = testing.make_audio(tmp_path / "c.mp3", cover=True, title="x")
    assert transcode.extract_cover(with_art, tmp_path / "cover.jpg") is True
    assert (tmp_path / "cover.jpg").read_bytes()[:2] == b"\xff\xd8"  # JPEG magic
    without = testing.make_audio(tmp_path / "n.mp3")
    assert transcode.extract_cover(without, tmp_path / "none.jpg") is False


def _stream_info(segment):
    import json
    import subprocess
    out = subprocess.run(["ffprobe", "-v", "error", "-show_streams", "-of", "json", str(segment)],
                         capture_output=True, text=True, check=True).stdout
    return json.loads(out)["streams"][0]


def test_default_codec_is_aac_stereo_44k_and_decodable(tmp_path):
    """What browsers will actually be handed: decode a produced segment and check its parameters."""
    src = testing.make_audio(tmp_path / "a.flac", seconds=8)
    transcode.transcode_hls(src, tmp_path / "out", transcode.RENDITIONS)
    for name, _ in transcode.RENDITIONS:
        info = _stream_info(tmp_path / "out" / name / "seg_000.ts")
        assert (info["codec_name"], info["sample_rate"], info["channels"]) == ("aac", "44100", 2)
    assert 'CODECS="mp4a.40.2"' in (tmp_path / "out" / "master.m3u8").read_text()


def test_mp3_codec_option_and_validation(tmp_path):
    src = testing.make_audio(tmp_path / "a.flac", seconds=4)
    transcode.transcode_hls(src, tmp_path / "out", transcode.RENDITIONS[:2], codec="mp3")
    assert _stream_info(tmp_path / "out" / "q96" / "seg_000.ts")["codec_name"] == "mp3"
    with pytest.raises(transcode.TranscodeError):
        transcode.transcode_hls(src, tmp_path / "bad", transcode.RENDITIONS, codec="wma")
