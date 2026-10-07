"""ALS-based "made for you" picks and "similar tracks" (Phase 5).

See services/recommender for the nightly ALS training job that produces the UserVector/
TrackVector rows this module scores against - the maths (confidence-weighted implicit
factorization) is explained there, not duplicated here. Both entry points degrade gracefully
when there's no ALS vector yet (a brand-new install, or a track uploaded since the last
training run): made-for-you falls back to library.py's artist-based heuristic, and
similar-tracks falls back to tempo/energy proximity (services/worker/app/audio_features.py),
then same-artist/same-genre.
"""
import uuid

import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
from sqlalchemy import select
from sqlalchemy.orm import Session

from listens_common.models import PlayEvent, Track, TrackVector, UserVector

MAX_PER_ARTIST = 2  # a Discover Weekly dominated by one artist defeats the point of the section


def cap_per_artist(tracks: list[Track], max_per_artist: int = MAX_PER_ARTIST) -> list[Track]:
    """Keeps only the first `max_per_artist` tracks per artist, preserving order. Exposed (not
    underscore-private) because made-for-you applies it once more, after heuristic/new-release
    fill-in, to keep the cap from Discover Weekly's original run."""
    counts: dict[uuid.UUID, int] = {}
    out = []
    for t in tracks:
        if counts.get(t.artist_id, 0) >= max_per_artist:
            continue
        counts[t.artist_id] = counts.get(t.artist_id, 0) + 1
        out.append(t)
    return out


def als_made_for_you(db: Session, user_id: uuid.UUID, limit: int) -> list[Track] | None:
    """Score every not-yet-played, ready track by dot product with the user's ALS vector
    (see services/recommender/app/train.py for why that dot product is the right score).
    Returns None - not [] - when there's no trained vector for this user yet, so the caller
    knows to fall back to the heuristic rather than showing a thin/empty section."""
    user_vector = db.get(UserVector, user_id)
    if user_vector is None:
        return None

    # Plain .all(), not .unique(): Track's joined relationships (artist, album) are many-to-one,
    # so this never fans out duplicate rows - and .unique() can't hash a row containing the
    # JSON vector column anyway.
    played = select(PlayEvent.track_id).where(PlayEvent.user_id == user_id)
    candidates = db.execute(
        select(Track, TrackVector.vector)
        .join(TrackVector, TrackVector.track_id == Track.id)
        .where(Track.status == "ready", Track.id.not_in(played))
    ).all()
    if not candidates:
        return []

    u = np.array(user_vector.vector)
    scored = sorted(candidates, key=lambda row: float(u @ np.array(row[1])), reverse=True)
    ranked_tracks = [row[0] for row in scored]
    return cap_per_artist(ranked_tracks)[:limit]


def _zscore(values: list[float]) -> np.ndarray:
    arr = np.array(values, dtype=float)
    std = arr.std()
    return (arr - arr.mean()) / std if std > 1e-9 else np.zeros_like(arr)


def _tempo_energy_neighbors(db: Session, track: Track, limit: int) -> list[Track]:
    candidates = list(db.scalars(
        select(Track).where(
            Track.status == "ready", Track.id != track.id,
            Track.tempo_bpm.is_not(None), Track.energy.is_not(None),
        )
    ).unique())
    if not candidates:
        return []
    # z-score both axes together with the query track, so "fast and loud" vs "slow and quiet"
    # is judged on a comparable scale rather than raw BPM dwarfing a 0-1 energy value.
    tempos = _zscore([track.tempo_bpm, *(c.tempo_bpm for c in candidates)])
    energies = _zscore([track.energy, *(c.energy for c in candidates)])
    target = np.array([tempos[0], energies[0]])
    ranked = sorted(
        range(len(candidates)),
        key=lambda i: float(np.linalg.norm(target - np.array([tempos[i + 1], energies[i + 1]]))),
    )
    return [candidates[i] for i in ranked[:limit]]


def _same_artist_then_genre(db: Session, track: Track, limit: int) -> list[Track]:
    same_artist = list(db.scalars(
        select(Track).where(Track.status == "ready", Track.id != track.id, Track.artist_id == track.artist_id)
        .order_by(Track.created_at.desc()).limit(limit)
    ).unique())
    if len(same_artist) >= limit or not track.genre:
        return same_artist[:limit]
    have = {t.id for t in same_artist} | {track.id}
    same_genre = list(db.scalars(
        select(Track).where(Track.status == "ready", Track.genre == track.genre, Track.id.not_in(have))
        .order_by(Track.created_at.desc()).limit(limit - len(same_artist))
    ).unique())
    return [*same_artist, *same_genre]


def similar_tracks(db: Session, track: Track, limit: int) -> list[Track]:
    own_vector = db.get(TrackVector, track.id)
    if own_vector is not None:
        rows = db.execute(
            select(Track, TrackVector.vector).join(TrackVector, TrackVector.track_id == Track.id)
            .where(Track.status == "ready", Track.id != track.id)
        ).all()
        if rows:
            vectors = np.array([row[1] for row in rows])
            sims = cosine_similarity([own_vector.vector], vectors)[0]
            order = np.argsort(sims)[::-1][:limit]
            return [rows[i][0] for i in order]

    picks = _tempo_energy_neighbors(db, track, limit)
    if len(picks) >= limit:
        return picks
    have = {t.id for t in picks} | {track.id}
    fallback = [t for t in _same_artist_then_genre(db, track, limit - len(picks)) if t.id not in have]
    return [*picks, *fallback]
