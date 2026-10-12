"""Artist credits written in different separators ("A/B", "A, B", "A;B") are the same credit.

Tags in the wild separate collaborators with "/", ",", or ";" depending on the tagger, so the same song's
credit arrived as different strings, each became its own artist row, and the artist pages, album lists and
"more from this artist" shelves fragmented. This module gives every credit ONE spelling for display
(`canonical_credit`: names joined by ", ") and ONE comparison key (`credit_key`: case, punctuation, spacing and
order insensitive), and `merge_artists` folds the existing duplicate rows together.
"""
import re
import uuid
from collections import defaultdict
from dataclasses import dataclass, field

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from .dedupe import norm
from .models import Album, Artist, ArtistMeta, Follow, Track

_SEPARATORS = re.compile(r"\s*[/,;]\s*")
# Names that legitimately contain a separator and must stay whole.
_PROTECTED = {"ac/dc"}


def credit_names(raw: str | None) -> list[str]:
    """The individual names in a credit, in order, without blanks or repeats."""
    text = " ".join((raw or "").split())
    if text.casefold() in _PROTECTED:
        return [text]
    seen, out = set(), []
    for part in _SEPARATORS.split(text):
        part = part.strip()
        key = norm(part)
        if key and key not in seen:
            seen.add(key)
            out.append(part)
    return out


def canonical_credit(raw: str | None) -> str:
    """One spelling for display: names joined by ", ". Unsplittable input is returned trimmed."""
    names = credit_names(raw)
    return (", ".join(names) if names else " ".join((raw or "").split()))[:200]


def credit_key(raw: str | None) -> str:
    """Comparison key: the same set of people gives the same key whatever the separators, case or order."""
    names = credit_names(raw)
    if not names:
        return norm(raw)
    return "|".join(sorted({norm(n) for n in names}))


def find_artist(db: Session, owner_id: uuid.UUID, raw: str) -> Artist | None:
    """The owner's existing artist for this credit, whatever separators it was stored with."""
    want = credit_key(raw)
    for artist in db.scalars(select(Artist).where(Artist.owner_user_id == owner_id)):
        if credit_key(artist.name) == want:
            return artist
    return None


@dataclass
class MergeReport:
    renamed: int = 0
    artists_merged: int = 0
    albums_merged: int = 0
    empty_removed: int = 0
    details: list[str] = field(default_factory=list)


def _album_count(db: Session, artist_id: uuid.UUID) -> int:
    return db.scalar(select(func.count()).select_from(Album).where(Album.artist_id == artist_id)) or 0


def merge_artists(db: Session) -> MergeReport:
    """Fold artist rows of the same credit into one (per owner), give each the canonical spelling, merge the
    albums that then collide, and drop artists nothing refers to. Moves tracks, albums, follows and open-data
    metadata onto the survivor. Does not commit: the caller decides (dry run = rollback)."""
    report = MergeReport()
    track_counts = dict(db.execute(select(Track.artist_id, func.count()).group_by(Track.artist_id)).all())

    groups: dict[tuple, list[Artist]] = defaultdict(list)
    for a in db.scalars(select(Artist).order_by(Artist.created_at, Artist.id)):
        groups[(a.owner_user_id, credit_key(a.name))].append(a)

    for rows in groups.values():
        survivor = min(rows, key=lambda a: (-track_counts.get(a.id, 0), a.created_at, str(a.id)))
        for loser in (a for a in rows if a.id != survivor.id):
            db.execute(update(Track).where(Track.artist_id == loser.id).values(artist_id=survivor.id))
            db.execute(update(Album).where(Album.artist_id == loser.id).values(artist_id=survivor.id))
            for f in db.scalars(select(Follow).where(Follow.target_type == "artist", Follow.target_id == loser.id)):
                if db.get(Follow, (f.follower_id, "artist", survivor.id)) is None:
                    db.add(Follow(follower_id=f.follower_id, target_type="artist", target_id=survivor.id, created_at=f.created_at))
                db.delete(f)
            if db.get(ArtistMeta, survivor.id) is None and (meta := db.get(ArtistMeta, loser.id)) is not None:
                db.execute(update(ArtistMeta).where(ArtistMeta.artist_id == meta.artist_id).values(artist_id=survivor.id))
            else:
                db.execute(delete(ArtistMeta).where(ArtistMeta.artist_id == loser.id))
            survivor.bio = survivor.bio or loser.bio
            survivor.image_key = survivor.image_key or loser.image_key
            report.details.append(f"merge  {loser.name!r} -> {survivor.name!r}")
            db.flush()
            db.delete(loser)
            report.artists_merged += 1
        db.flush()

        canonical = canonical_credit(survivor.name)
        if canonical != survivor.name:
            report.details.append(f"rename {survivor.name!r} -> {canonical!r}")
            survivor.name = canonical
            report.renamed += 1

        # albums of the same title now sit under one artist: keep the oldest, move its tracks over
        by_title: dict[str, list[Album]] = defaultdict(list)
        for al in db.scalars(select(Album).where(Album.artist_id == survivor.id).order_by(Album.created_at, Album.id)):
            by_title[norm(al.title)].append(al)
        for same in by_title.values():
            keep = same[0]
            for dup in same[1:]:
                db.execute(update(Track).where(Track.album_id == dup.id).values(album_id=keep.id))
                keep.cover_key = keep.cover_key or dup.cover_key
                keep.release_date = keep.release_date or dup.release_date
                db.flush()
                db.delete(dup)
                report.albums_merged += 1

        if (
            not track_counts.get(survivor.id) and not any(a.id != survivor.id and track_counts.get(a.id) for a in rows)
            and not _album_count(db, survivor.id) and not survivor.bio and not survivor.image_key
            and db.scalar(select(func.count()).select_from(Follow).where(Follow.target_type == "artist", Follow.target_id == survivor.id)) == 0
        ):
            db.execute(delete(ArtistMeta).where(ArtistMeta.artist_id == survivor.id))
            report.details.append(f"drop   {survivor.name!r} (no songs, albums, bio or followers)")
            db.delete(survivor)
            report.empty_removed += 1
    db.flush()
    return report
