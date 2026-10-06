import uuid

from listens_common.config import Settings
from listens_common.models import Track
from listens_common.signing import sign_token

from .schemas import AlbumRef, ArtistRef, TrackOut


def track_out(track: Track, settings: Settings, user_id: uuid.UUID | None = None) -> TrackOut:
    cover_url = None
    if track.cover_key:
        token = sign_token(settings.stream_signing_secret, "cover", track.id, settings.cover_url_ttl_seconds, user_id)
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
