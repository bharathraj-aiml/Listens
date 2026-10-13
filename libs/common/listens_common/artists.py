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

from . import tamil_seed
from .dedupe import norm
from .models import Album, Artist, ArtistMeta, Follow, Track, TrackArtist

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
    # through person_name, so a known misspelling ("Harish Ragavendra") has the same key as the right spelling
    return "|".join(sorted({norm(person_name(n)) for n in names}))


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


def merge_albums(db: Session, artist_id: uuid.UUID, report: "MergeReport") -> None:
    """Albums of the same title under one artist are one album: keep the oldest, move its tracks over."""
    by_title: dict[str, list[Album]] = defaultdict(list)
    for al in db.scalars(select(Album).where(Album.artist_id == artist_id).order_by(Album.created_at, Album.id)):
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
            already = select(TrackArtist.track_id).where(TrackArtist.artist_id == survivor.id)
            db.execute(delete(TrackArtist).where(TrackArtist.artist_id == loser.id, TrackArtist.track_id.in_(already)))  # credits both
            db.execute(update(TrackArtist).where(TrackArtist.artist_id == loser.id).values(artist_id=survivor.id))
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

        merge_albums(db, survivor.id, report)

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


# ------------------------------------------------------------------ one artist per person

# Misspellings seen in this library's tags that the seed list does not know (keys are tamil_seed._key forms).
_SPELLING = {
    tamil_seed._key(wrong): right
    for wrong, right in {
        "Harish Ragavendra": "Harish Raghavendra",
        "S.P.Balasubramniam": "S. P. Balasubrahmanyam",
        "Sadhna Sargam": "Sadhana Sargam",
    }.items()
}


def person_name(name: str) -> str:
    """The spelling to store for one person: the Tamil seed list's canonical name when this is a known spelling or
    alias ("SPB", "Yuvanshankar Raja"), else the name as written with spacing tidied."""
    clean = " ".join(name.split())
    key = tamil_seed._key(clean)
    if key in _SPELLING:
        return _SPELLING[key]
    seed = tamil_seed._BY_KEY.get(key)
    return seed.name if seed else clean


PersonIndex = dict[tuple[uuid.UUID, str], Artist]


def person_index(db: Session) -> PersonIndex:
    """Every artist by (owner, credit key), so bulk jobs look people up in memory instead of once per name."""
    oldest_last = db.scalars(select(Artist).order_by(Artist.created_at.desc(), Artist.id.desc())).all()
    return {(a.owner_user_id, credit_key(a.name)): a for a in oldest_last}  # the oldest row wins a key clash


def _person(db: Session, owner_id: uuid.UUID, name: str, index: PersonIndex | None = None) -> Artist:
    name = person_name(name)
    key = (owner_id, credit_key(name))
    artist = index.get(key) if index is not None else find_artist(db, owner_id, name)
    if artist is None:
        artist = Artist(name=name[:200], owner_user_id=owner_id)
        db.add(artist)
        db.flush()
        if index is not None:
            index[key] = artist
    return artist


def ensure_artists(db: Session, owner_id: uuid.UUID, raw: str | None, index: PersonIndex | None = None) -> list[Artist]:
    """The artist row for every person in a credit, in credit order, creating the ones that do not exist yet.
    "A/B", "A, B" and "A;B" all give [A, B]; an empty credit gives the single "Unknown Artist"."""
    names = credit_names(raw) or ["Unknown Artist"]
    return [_person(db, owner_id, n, index) for n in names]


def set_track_artists(db: Session, track: Track, people: list[Artist]) -> None:
    """Credit exactly `people`, in order, on the track; the first becomes its primary artist."""
    seen: list[Artist] = []
    for a in people:
        if all(a.id != x.id for x in seen):
            seen.append(a)
    db.flush()
    db.execute(delete(TrackArtist).where(TrackArtist.track_id == track.id))
    for pos, a in enumerate(seen):
        db.add(TrackArtist(track_id=track.id, artist_id=a.id, position=pos))
    track.artist_id = seen[0].id
    db.flush()
    db.expire(track, ["artist", "artists"])


def credit_of(track: Track) -> str:
    """The credit as text ("A, B"), from the credited artists (the primary one when none are linked yet)."""
    return ", ".join(a.name for a in (track.artists or [track.artist]))


@dataclass
class SplitReport:
    credits_split: int = 0
    people_created: int = 0
    tracks_linked: int = 0
    albums_moved: int = 0
    albums_merged: int = 0
    removed: int = 0
    details: list[str] = field(default_factory=list)


def split_credits(db: Session) -> SplitReport:
    """Turn every multi-person credit row ("A, B, C") into one artist per person, and link each track to everyone
    credited on it. Tracks keep working throughout: Track.artist_id becomes the first person. Albums and followers
    of a credit row move to its first person; albums that then share a title merge; credit rows nothing refers to
    are removed. Idempotent. Does not commit (dry run = rollback)."""
    report = SplitReport()
    before = {a.id for a in db.scalars(select(Artist))}
    combined = [a for a in db.scalars(select(Artist).order_by(Artist.created_at, Artist.id)) if len(credit_names(a.name)) > 1]
    index = person_index(db)

    for credit in combined:
        people = ensure_artists(db, credit.owner_user_id, credit.name, index) if credit.owner_user_id else [credit]
        lead = people[0]
        for track in db.scalars(select(Track).where(Track.artist_id == credit.id)).unique().all():
            set_track_artists(db, track, people)
        moved = db.execute(update(Album).where(Album.artist_id == credit.id).values(artist_id=lead.id)).rowcount or 0
        report.albums_moved += moved
        for f in db.scalars(select(Follow).where(Follow.target_type == "artist", Follow.target_id == credit.id)).all():
            if db.get(Follow, (f.follower_id, "artist", lead.id)) is None:
                db.add(Follow(follower_id=f.follower_id, target_type="artist", target_id=lead.id, created_at=f.created_at))
            db.delete(f)
        db.execute(delete(ArtistMeta).where(ArtistMeta.artist_id == credit.id))
        lead.bio = lead.bio or credit.bio
        lead.image_key = lead.image_key or credit.image_key
        db.flush()
        report.details.append(f"split  {credit.name!r} -> {[p.name for p in people]}")
        db.delete(credit)
        report.credits_split += 1
        db.flush()

    # every remaining track gets its link rows (single-artist tracks included), so queries can rely on the table
    linked = set(db.scalars(select(TrackArtist.track_id)))
    for track in db.scalars(select(Track)).unique().all():
        if track.id not in linked:
            set_track_artists(db, track, [track.artist])
            report.tracks_linked += 1

    sub = MergeReport()
    for artist_id in {a for (a,) in db.execute(select(Album.artist_id).distinct())}:
        merge_albums(db, artist_id, sub)
    report.albums_merged = sub.albums_merged
    db.flush()
    report.people_created = len({a.id for a in db.scalars(select(Artist))} - before)
    report.removed = report.credits_split
    return report
