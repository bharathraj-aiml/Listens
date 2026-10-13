"""Album titles without the store boilerplate, and one album per film/record.

Streaming-store tags add "(Original Motion Picture Soundtrack)", "[Deluxe Edition]", "- Single" and the like, and one film
arrives under several spellings of that suffix, so the album list shows "Guru" three times under three titles. This
gives every album one clean title and folds albums that then have the same title (and share an artist) into one.

Only boilerplate is removed. Information a listener may want stays: "(From "Cobra")", "(Tamil)", "[Slowed + Reverb]".
"""
from __future__ import annotations

import re
import uuid
from collections import defaultdict
from dataclasses import dataclass, field

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from .dedupe import norm
from .models import Album, Artist, Track, TrackArtist

# Inside a trailing (...) / [...] group, or after a trailing " - ", any of these words marks it as boilerplate.
_BOILERPLATE = re.compile(
    r"\b(original|soundtrack|motion picture|music picture|ost|score|deluxe|edition|remaster(?:ed)?|expanded|bonus|single|ep)\b", re.I
)
_TRAILING_GROUP = re.compile(r"\s*[\(\[]([^\(\)\[\]]*)[\)\]]\s*$")
_DASH_TAIL = re.compile(r"\s+[-–—]\s+([^-–—]*)$")
_BARE_SUFFIX = re.compile(r"\s+original (?:motion picture )?(?:soundtrack|score)$", re.I)


def clean_album_title(title: str | None) -> str:
    """The album title without trailing boilerplate; the input (trimmed) when nothing would be left."""
    original = " ".join((title or "").split())
    t = original
    while True:
        before = t
        m = _TRAILING_GROUP.search(t)
        if m and _BOILERPLATE.search(m.group(1)):
            t = t[: m.start()].rstrip()
        m = _DASH_TAIL.search(t)
        if m and _BOILERPLATE.search(m.group(1)):
            t = t[: m.start()].rstrip()
        t = _BARE_SUFFIX.sub("", t)
        if t == before:
            break
    return t if t else original


def find_or_create_album(db: Session, people: list[Artist], title: str) -> Album:
    """The album for `title` (cleaned) that one of `people` is already on, or a new one under the first person.
    The same film credited to different first-listed singers is therefore ONE album, not one per singer."""
    clean = clean_album_title(title)[:200]
    ids = [p.id for p in people]
    credited = select(Track.album_id).join(TrackArtist, TrackArtist.track_id == Track.id).where(TrackArtist.artist_id.in_(ids), Track.album_id.is_not(None))
    candidates = db.scalars(select(Album).where(func.lower(Album.title) == clean.lower())).unique().all()
    for al in candidates:
        if al.artist_id in ids:
            return al
    for al in candidates:
        if al.id in set(db.scalars(credited)):
            return al
    album = Album(artist_id=people[0].id, title=clean)
    db.add(album)
    db.flush()
    return album


@dataclass
class AlbumReport:
    renamed: int = 0
    merged: int = 0
    details: list[str] = field(default_factory=list)


def normalize_albums(db: Session) -> AlbumReport:
    """Clean every album title, then fold albums with the same title that share an artist (their own artist, or anyone
    credited on their songs) into one. The kept album is the one with the most songs (oldest on a tie); its artist is
    the most common first-listed artist of the combined songs. Idempotent. Does not commit."""
    report = AlbumReport()
    albums = db.scalars(select(Album).order_by(Album.created_at, Album.id)).unique().all()
    for al in albums:
        clean = clean_album_title(al.title)
        if clean != al.title:
            report.details.append(f"rename {al.title!r} -> {clean!r}")
            al.title = clean[:200]
            report.renamed += 1
    db.flush()

    songs: dict[uuid.UUID, int] = dict(db.execute(select(Track.album_id, func.count()).where(Track.album_id.is_not(None)).group_by(Track.album_id)).all())
    people: dict[uuid.UUID, set[uuid.UUID]] = defaultdict(set)
    for album_id, artist_id in db.execute(
        select(Track.album_id, TrackArtist.artist_id).join(TrackArtist, TrackArtist.track_id == Track.id).where(Track.album_id.is_not(None))
    ):
        people[album_id].add(artist_id)
    for al in albums:
        people[al.id].add(al.artist_id)

    by_title: dict[str, list[Album]] = defaultdict(list)
    for al in albums:
        by_title[norm(al.title)].append(al)
    for same in by_title.values():
        if len(same) < 2:
            continue
        parent = list(range(len(same)))

        def find(i: int) -> int:
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        for i in range(len(same)):
            for j in range(i + 1, len(same)):
                if people[same[i].id] & people[same[j].id]:
                    parent[find(i)] = find(j)
        clusters: dict[int, list[Album]] = defaultdict(list)
        for i, al in enumerate(same):
            clusters[find(i)].append(al)
        for cluster in clusters.values():
            if len(cluster) < 2:
                continue
            keep = min(cluster, key=lambda a: (-songs.get(a.id, 0), a.created_at.replace(tzinfo=None), str(a.id)))  # tz-agnostic
            for dup in cluster:
                if dup.id == keep.id:
                    continue
                db.execute(update(Track).where(Track.album_id == dup.id).values(album_id=keep.id))
                keep.cover_key = keep.cover_key or dup.cover_key
                keep.release_date = keep.release_date or dup.release_date
                report.details.append(f"merge  {dup.title!r} ({dup.id.hex[:6]}) -> {keep.title!r} ({keep.id.hex[:6]})")
                db.flush()
                db.delete(dup)
                report.merged += 1
            lead = db.execute(
                select(Track.artist_id, func.count()).where(Track.album_id == keep.id).group_by(Track.artist_id).order_by(func.count().desc())
            ).first()
            if lead:
                keep.artist_id = lead[0]
    db.flush()
    return report
