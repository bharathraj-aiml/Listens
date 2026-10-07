"""Build the weighted user x track implicit-feedback matrix that ALS trains on (see train.py).

Signal weights, summed per (user, track):
  - a "full" listen (play_end with ms_played >= FULL_LISTEN_FRACTION of duration_ms): +1
  - a *repeat* full listen - every full listen after the first one                  : +2 additional
  - a save (a like, or being added to one of the user's playlists)                  : +3
  - an early skip (a skip with position_ms < EARLY_SKIP_MS)                         : -2

The sum is clamped to >= 0 before being handed to ALS: the standard confidence-weighted
implicit-feedback formulation (Hu, Koren & Volinsky, 2008 - see train.py for the full
derivation) assumes confidence c_ui = 1 + alpha * r_ui with r_ui >= 0. A heavily-skipped
track simply contributes no positive confidence rather than being fed as a negative one -
"train the model to actively avoid this" is a different, out-of-scope formulation.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass

import scipy.sparse as sp
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from listens_common.models import Like, PlayEvent, PlaylistTrack, Track

FULL_LISTEN_FRACTION = 0.9  # mirrors catalogue's analytics.py "verified stream" threshold in spirit
EARLY_SKIP_MS = 30_000

FULL_LISTEN_WEIGHT = 1
REPEAT_LISTEN_WEIGHT = 2
SAVE_WEIGHT = 3
EARLY_SKIP_WEIGHT = -2

Key = tuple[uuid.UUID, uuid.UUID]  # (user_id, track_id)


@dataclass
class Matrix:
    user_ids: list[uuid.UUID]
    track_ids: list[uuid.UUID]
    csr: sp.csr_matrix  # rows=users, cols=tracks; nonzero entries are confidence weights >= 0


def _full_listen_counts(db: Session) -> dict[Key, int]:
    rows = db.execute(
        select(PlayEvent.user_id, PlayEvent.track_id, func.count())
        .join(Track, Track.id == PlayEvent.track_id)
        .where(
            PlayEvent.event_type == "play_end",
            Track.duration_ms.is_not(None),
            PlayEvent.ms_played >= Track.duration_ms * FULL_LISTEN_FRACTION,
        )
        .group_by(PlayEvent.user_id, PlayEvent.track_id)
    ).all()
    return {(u, t): n for u, t, n in rows}


def _early_skip_counts(db: Session) -> dict[Key, int]:
    rows = db.execute(
        select(PlayEvent.user_id, PlayEvent.track_id, func.count())
        .where(PlayEvent.event_type == "skip", PlayEvent.position_ms < EARLY_SKIP_MS)
        .group_by(PlayEvent.user_id, PlayEvent.track_id)
    ).all()
    return {(u, t): n for u, t, n in rows}


def _save_counts(db: Session) -> dict[Key, int]:
    """A "save" is a like or an add-to-playlist - both are a deliberate, lasting keep decision,
    unlike a play (which could just be curiosity)."""
    counts: dict[Key, int] = {}
    for u, t in db.execute(select(Like.user_id, Like.track_id)).all():
        counts[(u, t)] = counts.get((u, t), 0) + 1
    added = db.execute(
        select(PlaylistTrack.added_by, PlaylistTrack.track_id).where(PlaylistTrack.added_by.is_not(None))
    ).all()
    for u, t in added:
        counts[(u, t)] = counts.get((u, t), 0) + 1
    return counts


def build(db: Session) -> Matrix | None:
    """Returns None if there isn't any usable interaction data yet (brand-new install)."""
    weights: dict[Key, float] = {}
    for key, n in _full_listen_counts(db).items():
        weights[key] = weights.get(key, 0) + FULL_LISTEN_WEIGHT * n + REPEAT_LISTEN_WEIGHT * max(0, n - 1)
    for key, n in _save_counts(db).items():
        weights[key] = weights.get(key, 0) + SAVE_WEIGHT * n
    for key, n in _early_skip_counts(db).items():
        weights[key] = weights.get(key, 0) + EARLY_SKIP_WEIGHT * n

    weights = {k: v for k, v in weights.items() if v > 0}  # clamp (see module docstring)
    if not weights:
        return None

    user_ids = sorted({u for u, _ in weights}, key=str)
    track_ids = sorted({t for _, t in weights}, key=str)
    u_index = {u: i for i, u in enumerate(user_ids)}
    t_index = {t: i for i, t in enumerate(track_ids)}

    items = list(weights.items())
    rows = [u_index[u] for (u, _t), _v in items]
    cols = [t_index[t] for (_u, t), _v in items]
    vals = [float(v) for _k, v in items]
    csr = sp.csr_matrix((vals, (rows, cols)), shape=(len(user_ids), len(track_ids)))
    return Matrix(user_ids=user_ids, track_ids=track_ids, csr=csr)
