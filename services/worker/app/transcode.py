"""FFmpeg/ffprobe wrappers. Pure functions over files: no DB, no S3, easy to test."""
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

# (rendition name, target kbps). The name becomes the folder: hls/<track>/q160/...
RENDITIONS = [("q96", 96), ("q160", 160), ("q320", 320)]
SEGMENT_SECONDS = 6


class TranscodeError(Exception):
    pass


@dataclass
class Probe:
    duration_ms: int
    bitrate_kbps: int | None


def _run(cmd: list[str], timeout: int) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout, check=False)
    except subprocess.TimeoutExpired:
        raise TranscodeError(f"{cmd[0]} timed out after {timeout}s") from None


def _clean(stderr: str, src: Path) -> str:
    """Error text is shown to users: don't leak the worker's temp paths."""
    return stderr.strip().replace(str(src.parent), "").replace(str(src), "the uploaded file")


def probe(src: Path) -> Probe:
    """Validate that this is real audio and read duration/bitrate. Raises TranscodeError if not."""
    res = _run(["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(src)], 60)
    if res.returncode != 0:
        raise TranscodeError(f"Not a readable media file: {_clean(res.stderr, src)[:300]}")
    info = json.loads(res.stdout or "{}")
    audio = [s for s in info.get("streams", []) if s.get("codec_type") == "audio"]
    if not audio:
        raise TranscodeError("File has no audio stream")
    fmt = info.get("format", {})
    duration = float(fmt.get("duration") or audio[0].get("duration") or 0)
    if duration <= 0:
        raise TranscodeError("Could not determine duration")
    bitrate = audio[0].get("bit_rate") or fmt.get("bit_rate")
    return Probe(duration_ms=int(duration * 1000), bitrate_kbps=int(int(bitrate) / 1000) if bitrate else None)


def select_renditions(source_kbps: int | None) -> list[tuple[str, int]]:
    """Skip renditions that would just inflate a low-bitrate source (a 128k MP3 re-encoded at
    320k sounds identical but costs 2.5x the disk). 96k is always produced; a higher tier is
    produced when the source is at least 80% of it. Unknown bitrate -> everything."""
    if source_kbps is None:
        return list(RENDITIONS)
    return [r for r in RENDITIONS if r[1] == RENDITIONS[0][1] or source_kbps >= r[1] * 0.8]


CODEC_ARGS = {"aac": "aac", "mp3": "libmp3lame"}


def transcode_hls(src: Path, out_dir: Path, renditions: list[tuple[str, int]], codec: str = "aac") -> None:
    """One ffmpeg run -> N AAC (or MP3) renditions as 6 s MPEG-TS segments + a master playlist.
    Video/cover streams are dropped (-vn); audio is normalised to stereo 44.1 kHz."""
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, _ in renditions:
        (out_dir / name).mkdir(exist_ok=True)  # ffmpeg's %v folders must pre-exist

    cmd = ["ffmpeg", "-y", "-v", "error", "-i", str(src), "-vn"]
    for _ in renditions:
        cmd += ["-map", "0:a:0"]
    if codec not in CODEC_ARGS:
        raise TranscodeError(f"Unsupported HLS_AUDIO_CODEC {codec!r}; use one of {sorted(CODEC_ARGS)}")
    cmd += ["-c:a", CODEC_ARGS[codec], "-ar", "44100", "-ac", "2"]
    for i, (_, kbps) in enumerate(renditions):
        cmd += [f"-b:a:{i}", f"{kbps}k"]
    var_map = " ".join(f"a:{i},name:{name}" for i, (name, _) in enumerate(renditions))
    cmd += [
        "-f", "hls", "-hls_time", str(SEGMENT_SECONDS), "-hls_playlist_type", "vod",
        "-hls_segment_type", "mpegts", "-hls_flags", "independent_segments",
        "-master_pl_name", "master.m3u8", "-var_stream_map", var_map,
        "-hls_segment_filename", str(out_dir / "%v" / "seg_%03d.ts"),
        str(out_dir / "%v" / "index.m3u8"),
    ]
    res = _run(cmd, timeout=60 * 30)
    if res.returncode != 0:
        raise TranscodeError(f"ffmpeg failed: {_clean(res.stderr, src)[-500:]}")
    if not (out_dir / "master.m3u8").exists():
        raise TranscodeError("ffmpeg produced no master playlist")


def extract_cover(src: Path, out_file: Path) -> bool:
    """Pull embedded cover art (if any) as a <=600px JPEG. Missing art is normal -> False."""
    res = _run(
        ["ffmpeg", "-y", "-v", "error", "-i", str(src), "-an", "-map", "0:v:0", "-frames:v", "1",
         "-vf", "scale='min(600,iw)':-2", "-q:v", "3", str(out_file)],
        timeout=60,
    )
    return res.returncode == 0 and out_file.exists() and out_file.stat().st_size > 0
