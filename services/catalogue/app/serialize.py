import time
import uuid

from listens_common.config import Settings
from listens_common.models import Track
from listens_common.signing import sign_token

from .schemas import AlbumRef, ArtistRef, TrackOut


def _bucketed_ttl(full_ttl: int) -> int:
    """Rounds the token's expiry up to the next multiple of full_ttl (an epoch-aligned grid),
    so repeated calls within the same window mint the identical signed token - same URL, so the
    browser's own HTTP cache (Cache-Control in services/stream) actually hits instead of every
    list/page that shows a track re-downloading its cover under a brand-new one-off URL. A
    cover image never changes after a track is transcoded, so there's no freshness downside to
    a day-long cache window - see cover_url_ttl_seconds."""
    now = int(time.time())
    bucket_end = ((now // full_ttl) + 1) * full_ttl
    return bucket_end - now


def track_out(track: Track, settings: Settings, user_id: uuid.UUID | None = None) -> TrackOut:
    cover_url = None
    if track.cover_key:
        token = sign_token(settings.stream_signing_secret, "cover", track.id, _bucketed_ttl(settings.cover_url_ttl_seconds), user_id)
        cover_url = f"{settings.stream_public_prefix}/cover/{token}"
    return TrackOut(
        id=track.id,
        title=track.title,
        artist=ArtistRef(id=track.artist.id, name=track.artist.name),
        album=AlbumRef(id=track.album.id, title=track.album.title) if track.album else None,
        genre=track.genre,
        license=track.license,
        status=track.status,
        duration_ms=track.duration_ms,
        cover_url=cover_url,
        error=track.error,
        created_at=track.created_at,
    )
