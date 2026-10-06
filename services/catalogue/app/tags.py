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
