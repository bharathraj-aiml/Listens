"""Best-effort ID3/Vorbis/MP4 tag reading with mutagen."""
from typing import BinaryIO

import mutagen


def read_tags(fileobj: BinaryIO) -> dict[str, str]:
    """Return any of title/artist/album/genre found; never raises on bad files."""
    try:
        fileobj.seek(0)
        audio = mutagen.File(fileobj, easy=True)
    except Exception:
        return {}
    finally:
        fileobj.seek(0)
    if not audio or not audio.tags:
        return {}
    out = {}
    for key in ("title", "artist", "album", "genre"):
        values = audio.tags.get(key)
        if values and str(values[0]).strip():
            out[key] = str(values[0]).strip()
    return out


def _sylt_to_lrc(sylt) -> str | None:
    """Convert an ID3 SYLT frame's (text, ms) pairs into LRC "[mm:ss.xx]line" text.
    SYLT.format == 2 means milliseconds (the common case); frame-count timing (format 1)
    can't be converted to wall-clock time without the file's frame rate, so it's skipped."""
    if getattr(sylt, "format", None) != 2 or not sylt.text:
        return None
    lines = []
    for text, ms in sylt.text:
        if not text.strip():
            continue
        m, s = divmod(ms / 1000, 60)
        lines.append(f"[{int(m):02d}:{s:05.2f}]{text.strip()}")
    return "\n".join(lines) or None


def read_lyrics(fileobj: BinaryIO) -> dict[str, str]:
    """Return {"lyrics": ..., "lyrics_synced": ...} for whatever embedded lyrics exist.
    Never raises on bad/missing files; returns an empty dict when there's nothing to find."""
    try:
        fileobj.seek(0)
        audio = mutagen.File(fileobj, easy=False)
    except Exception:
        return {}
    finally:
        fileobj.seek(0)
    if not audio or not audio.tags:
        return {}
    tags = audio.tags
    out: dict[str, str] = {}

    # ID3 (MP3): USLT = plain lyrics, SYLT = time-synced lyrics.
    if hasattr(tags, "getall"):
        uslt = tags.getall("USLT")
        if uslt and uslt[0].text.strip():
            out["lyrics"] = uslt[0].text.strip()
        for sylt in tags.getall("SYLT"):
            lrc = _sylt_to_lrc(sylt)
            if lrc:
                out["lyrics_synced"] = lrc
                break
        return out

    # Vorbis comments (FLAC/OGG) and MP4 atoms: flat, mostly-lowercase key/value tags.
    lower = {str(k).lower(): v for k, v in tags.items()}
    for key, field in (("unsyncedlyrics", "lyrics"), ("lyrics", "lyrics"), ("\xa9lyr", "lyrics")):
        values = lower.get(key)
        if values and str(values[0]).strip():
            out.setdefault(field, str(values[0]).strip())
    for key in ("syncedlyrics", "lyrics_sync"):
        values = lower.get(key)
        if values and str(values[0]).strip():
            out["lyrics_synced"] = str(values[0]).strip()
            break
    return out
