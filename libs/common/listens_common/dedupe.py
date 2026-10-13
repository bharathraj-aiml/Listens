"""Duplicate-song detection, shared by the upload endpoint (reject), the transcode worker (delete the
lower-quality copy once a track is ready) and scripts/dedupe_library.py (one-off cleanup of the library).

Byte-identical files are already stopped by the (uploader, sha256) unique index. This covers the same
SONG in a different file, e.g. a re-encode: same uploader, same normalised title + artist, compatible
album, and (once both are transcoded) lengths within a few seconds.
"""
import difflib
import re
import unicodedata
import uuid
from dataclasses import dataclass, field

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from .models import Album, Artist, Like, PlayEvent, PlaylistTrack, Track, TrackArtist

DURATION_TOLERANCE_MS = 3000
LIVE_STATUSES = ("uploaded", "processing", "ready")
# Untagged files fall back to a filename title + this artist, so a match proves nothing.
UNKNOWN_ARTISTS = {"", "unknown artist"}


def norm(text: str | None) -> str:
    """Case/punctuation/spacing-insensitive key. Keeps letters, marks and digits of every script
    (marks matter: dropping Tamil vowel signs would make different words collide)."""
    s = unicodedata.normalize("NFKC", text or "").casefold()
    return " ".join("".join(ch if unicodedata.category(ch)[0] in "LMN" else " " for ch in s).split())


# ---------------------------------------------------------------- spelling variants of the same song

# Words that make two similar titles DIFFERENT recordings (a slowed edit, a live take, a remix...): never merged.
_VERSION = re.compile(
    r"\b(slowed|sped ?up|reverb|remix|live|acoustic|instrumental|karaoke|cover|colou?rs show|lo-?fi|mashup|unplugged|demo|"
    r"remaster(?:ed)?|female|male|reprise|bgm)\b"
)
_ROMANISATION = (("aa", "a"), ("ee", "i"), ("ii", "i"), ("oo", "u"), ("uu", "u"), ("ai", "i"), ("ei", "i"), ("th", "t"), ("dh", "d"),
                 ("zh", "l"), ("ph", "f"), ("kh", "k"), ("gh", "g"), ("w", "v"), ("y", "i"))


def title_skeleton(title: str | None) -> str:
    """A title with spelling noise removed, so "Veettu Thottathil" and "Veetu Thotathil" match: drops "(From ...)" /
    "[...]" / "- From ..." suffixes, folds doubled letters and common Tamil romanisation variants (aa/a, th/t, zh/l, ...)."""
    t = unicodedata.normalize("NFKC", title or "").casefold()
    t = re.sub(r"\(.*?\)|\[.*?\]", " ", t)
    t = re.split(r"\s[-–—]\s", t)[0]
    t = re.sub(r"[^a-z0-9஀-௿ ]", "", t)
    for a, b in _ROMANISATION:
        t = t.replace(a, b)
    t = re.sub(r"(.)\1+", r"\1", t)  # doubled letters: "tt" -> "t"
    return re.sub(r"\s+", "", t)


def version_words(title: str | None) -> frozenset[str]:
    return frozenset(m.group(0) for m in _VERSION.finditer((title or "").casefold()))


@dataclass
class SongInfo:
    title: str
    people: set = field(default_factory=set)  # credited artist ids
    album: str | None = None
    duration_ms: int | None = None

    @classmethod
    def of(cls, track: Track, album_title: str | None = None) -> "SongInfo":
        album = album_title if album_title is not None else (track.album.title if track.album else None)
        return cls(track.title, {a.id for a in (track.artists or [track.artist])}, album, track.duration_ms)


SAME_DURATION_MS = 5_000
DIFFERENT_DURATION_MS = 12_000


def likely_same_song(a: SongInfo, b: SongInfo, *, strict: bool = False) -> bool:
    """True when two files are probably the same recording with a spelling change in the title or credit: similar title
    skeleton, the same version (no "slowed" vs plain), compatible length, and a shared artist or album. `strict` (used
    for automatic removal) additionally requires both lengths to be known and within 5 s, and a near-identical title."""
    if version_words(a.title) != version_words(b.title):
        return False
    ka, kb = title_skeleton(a.title), title_skeleton(b.title)
    if not ka or not kb:
        return False
    ratio = 1.0 if ka == kb else difflib.SequenceMatcher(None, ka, kb).ratio()
    known = a.duration_ms is not None and b.duration_ms is not None
    gap = abs(a.duration_ms - b.duration_ms) if known else None
    related = bool(a.people & b.people) or (a.album is not None and b.album is not None and norm(a.album) == norm(b.album))
    if strict:
        return known and gap <= SAME_DURATION_MS and ratio >= 0.9 and related
    if ratio < 0.84 or (known and gap > DIFFERENT_DURATION_MS):
        return False
    return (known and gap <= SAME_DURATION_MS) or (related and ratio >= 0.88)


def similar_groups(songs: list[SongInfo], *, strict: bool = False) -> list[list[int]]:
    """Groups (as index lists, only those with 2+ members) of songs that are likely the same recording."""
    parent = list(range(len(songs)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for i in range(len(songs)):
        for j in range(i + 1, len(songs)):
            if likely_same_song(songs[i], songs[j], strict=strict):
                parent[find(i)] = find(j)
    groups: dict[int, list[int]] = {}
    for i in range(len(songs)):
        groups.setdefault(find(i), []).append(i)
    return [g for g in groups.values() if len(g) > 1]


def _album_compatible(a: str | None, b: str | None) -> bool:
    na, nb = norm(a), norm(b)
    return not na or not nb or na == nb  # a missing album doesn't make it a different song


def find_duplicates(
    db: Session, uploader_id: uuid.UUID | None, title: str, artist: str, album: str | None = None,
    *, duration_ms: int | None = None, exclude_id: uuid.UUID | None = None,
) -> list[Track]:
    """Existing (not failed) tracks of this uploader that are the same song. With duration_ms given,
    a candidate must also have a known duration within DURATION_TOLERANCE_MS."""
    if uploader_id is None or norm(artist) in UNKNOWN_ARTISTS or not norm(title):
        return []
    from .artists import credit_key, credit_of  # lazy: artists imports norm from here

    nt, na = norm(title), credit_key(artist)
    rows = db.execute(
        select(Track, Artist.name, Album.title)
        .join(Artist, Artist.id == Track.artist_id)
        .outerjoin(Album, Album.id == Track.album_id)
        .where(Track.uploader_id == uploader_id, Track.status.in_(LIVE_STATUSES))
    ).all()
    out = []
    for t, artist_name, album_title in rows:
        # the same people, whatever the separators or order, so "A/B" and "B, A" are one credit
        if t.id == exclude_id or norm(t.title) != nt or credit_key(credit_of(t) or artist_name) != na:
            continue
        if not _album_compatible(album, album_title):
            continue
        if duration_ms is not None and (t.duration_ms is None or abs(t.duration_ms - duration_ms) > DURATION_TOLERANCE_MS):
            continue
        out.append(t)
    return out


def pick_keeper(tracks: list[Track]) -> Track:
    """Highest source bitrate wins; on a tie the oldest upload (it's the one already in playlists)."""
    return min(tracks, key=lambda t: (-(t.source_bitrate_kbps or 0), t.created_at, str(t.id)))


def remove_track(db: Session, s3, settings, track: Track, keep: Track | None = None) -> None:
    """Delete a track's rows and its B2 files. Likes and playlist entries move to `keep` first."""
    from .storage import delete_prefix  # lazy: only services with the [storage] extra need boto3

    tid, cover_key = track.id, track.cover_key
    if keep is not None:
        for like in db.scalars(select(Like).where(Like.track_id == tid)).all():
            if db.get(Like, (like.user_id, keep.id)) is None:
                db.add(Like(user_id=like.user_id, track_id=keep.id, created_at=like.created_at))
        db.execute(update(PlaylistTrack).where(PlaylistTrack.track_id == tid).values(track_id=keep.id))
        db.execute(update(PlayEvent).where(PlayEvent.track_id == tid).values(track_id=keep.id))  # listens count for the kept copy
    db.execute(delete(Like).where(Like.track_id == tid))
    db.execute(delete(TrackArtist).where(TrackArtist.track_id == tid))
    db.delete(track)
    db.commit()
    delete_prefix(s3, settings.s3_bucket_audio, f"originals/{tid}/")
    delete_prefix(s3, settings.s3_bucket_audio, f"hls/{tid}/")
    if cover_key:
        s3.delete_object(Bucket=settings.s3_bucket_covers, Key=cover_key)


def duplicate_group(db: Session, track: Track) -> list[Track]:
    """`track` plus every other READY copy of the same song (empty list entries excluded)."""
    artist = db.get(Artist, track.artist_id)
    album = db.get(Album, track.album_id) if track.album_id else None
    from .artists import credit_of

    twins = find_duplicates(db, track.uploader_id, track.title, credit_of(track) if artist else "",
                            album.title if album else None, duration_ms=track.duration_ms, exclude_id=track.id)
    twins = [t for t in twins if t.status == "ready"]
    # plus spelling variants of the title/credit (strict: same length within 5 s and a shared artist or album)
    me = SongInfo.of(track)
    have = {t.id for t in twins} | {track.id}
    for other in db.scalars(select(Track).where(Track.uploader_id == track.uploader_id, Track.status == "ready", Track.id.notin_(have))).unique():
        if likely_same_song(me, SongInfo.of(other), strict=True):
            twins.append(other)
    return [track, *twins] if twins else []


def resolve_duplicates(db: Session, s3, settings, track_id: uuid.UUID) -> list[uuid.UUID]:
    """Called when a track becomes ready: keep the best copy of the song, delete the rest.
    Returns the ids that were removed (possibly including `track_id` itself)."""
    track = db.get(Track, track_id)
    if track is None or track.status != "ready":
        return []
    group = duplicate_group(db, track)
    if not group:
        return []
    keeper = pick_keeper(group)
    removed = []
    for t in group:
        if t.id != keeper.id:
            removed.append(t.id)
            remove_track(db, s3, settings, t, keep=keeper)
    return removed
