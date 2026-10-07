"""Nightly ALS training: turns the weighted interaction matrix (matrix.py) into per-user and
per-track latent-factor vectors, stored in the user_vectors / track_vectors tables.

--- The maths, briefly ---

ALS (Alternating Least Squares) for implicit feedback (Hu, Koren & Volinsky, "Collaborative
Filtering for Implicit Feedback Datasets", 2008) factorizes the user x track interaction
matrix R into two low-rank matrices: a user-factor matrix X (n_users x k) and a track-factor
matrix Y (n_tracks x k), such that a user's affinity for a track is approximated by the dot
product of their rows:

    r_hat(u, i) = x_u . y_i

Unlike classic factorization for *explicit* ratings (stars, thumbs), implicit feedback (play
counts, skips, saves) has no "0 = dislikes it" signal - a 0 just means "not observed yet",
which is very different from "observed and rejected". The implicit-ALS trick is to split the
raw weight r_ui (from matrix.py) into two separate things:
  - a binary preference indicator       p_ui = 1 if r_ui > 0 else 0
  - a confidence in that preference     c_ui = 1 + alpha * r_ui
so a track played a lot or saved is a *more confident* positive example, while every
unobserved (u, i) pair is still used as a (very low-confidence, c=1) negative - which is what
lets the model learn from the *absence* of interaction, not just the presence of it.

The loss ALS minimizes is a confidence-weighted squared error over EVERY (u, i) pair (not
just the observed ones), plus L2 regularization so a handful of plays can't overfit a whole
user vector:

    L = sum_{u,i} c_ui * (p_ui - x_u . y_i)^2  +  lambda * (sum_u |x_u|^2 + sum_i |y_i|^2)

This is non-convex in (X, Y) jointly - but if you FIX Y, it becomes an ordinary weighted
ridge-regression problem in X alone (and vice versa), which has a closed-form solution.
ALS exploits exactly this, alternating:
    1. fix Y, solve for every x_u in closed form (weighted least squares, one user at a time)
    2. fix X, solve for every y_i in closed form (weighted least squares, one track at a time)
repeating for a fixed number of iterations. Each half-step can only decrease (or hold) the
loss, so the process converges to a local optimum - not guaranteed global, but good in
practice - and each step is an easily-parallelizable per-row linear solve, which is why ALS
scales better here than gradient descent. The `implicit` library implements exactly this (with
the conjugate-gradient speedup from Hu et al.'s follow-up work) in compiled native code, which
is why this file is a thin wrapper around it rather than a from-scratch solver.

Once trained, x_u . y_i IS the recommendation score for showing user u track i (see
services/catalogue/app/recommendations.py's made-for-you endpoint); cosine similarity between
two y_i vectors is the "similar tracks" score, since tracks that appeal to the same kinds of
listeners end up with factor vectors pointing in similar directions.
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime

from implicit.als import AlternatingLeastSquares
from sqlalchemy import delete
from sqlalchemy.orm import Session

from listens_common.models import TrackVector, UserVector

from . import matrix as matrix_mod

log = logging.getLogger("recommender")

FACTORS = 32
REGULARIZATION = 0.05
ITERATIONS = 20
ALPHA = 40.0  # confidence scaling c_ui = 1 + ALPHA * r_ui; 40 is the value used in Hu et al.'s own experiments


def train(db: Session) -> int:
    """Rebuild every UserVector/TrackVector row from the current interaction matrix.
    Returns the number of users trained (0 if there isn't enough data yet - a fresh install
    with no plays/likes - in which case callers should keep using the cold-start heuristics)."""
    m = matrix_mod.build(db)
    if m is None:
        log.info("not enough interaction data to train ALS yet")
        return 0

    model = AlternatingLeastSquares(factors=FACTORS, regularization=REGULARIZATION, iterations=ITERATIONS, alpha=ALPHA)
    model.fit(m.csr)  # implicit applies the c_ui = 1 + alpha * r_ui confidence weighting internally

    now = datetime.now(UTC)
    db.execute(delete(UserVector))
    db.execute(delete(TrackVector))
    db.add_all(
        UserVector(user_id=uid, vector=model.user_factors[i].tolist(), trained_at=now)
        for i, uid in enumerate(m.user_ids)
    )
    db.add_all(
        TrackVector(track_id=tid, vector=model.item_factors[i].tolist(), trained_at=now)
        for i, tid in enumerate(m.track_ids)
    )
    db.commit()
    log.info("ALS trained: %d users, %d tracks, %d factors", len(m.user_ids), len(m.track_ids), FACTORS)
    return len(m.user_ids)
