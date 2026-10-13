"""Hybrid, taste-aware track scoring: the part of "made for you" and "similar tracks" that works
with ONE listener and a small library, where collaborative filtering (ALS) has almost nothing to
learn from.

How two tracks are compared (`similarity`, 0..1). Each signal is optional - a track missing a
signal just drops that term and the rest are re-weighted, so a brand-new upload still scores:

  audio     cosine of the librosa timbre/harmony fingerprint (standardised across the library)
  artist    how related the two artists are: the same artist; ListenBrainz co-listening (real
            listening sessions); overlap of their neighbour lists (two artists both close to a
            third are close to each other, which matters for sparse Tamil film-music coverage);
            and MusicBrainz tag overlap
  rhythm    tempo (half/double-time counts as a match) and loudness
  album     same album - for film music this is "same film soundtrack"
  era       release-year closeness (a 90s Rahman song sits nearer 90s songs than 2020s ones)
  language  same script (Tamil vs other); unknown when titles are romanised, then skipped
  genre     same genre tag
  mood      how close the two songs feel (listens_common.mood: sad..happy x calm..intense, estimated from the
            fingerprint). When both songs have a mood it is the dominant signal and artist closeness shrinks to
            a small one, and a mood mismatch scales the whole score down, so a sad song's neighbours are sad
            songs, whoever sings them.

A listener's taste is the weighted set of tracks they liked, saved to playlists, or finished
(repeat listens count more), minus tracks they skipped early. A candidate scores by its
similarity to the closest of those, then results are re-ranked with MMR so the list is varied
rather than ten clones of one song.
"""
from __future__ import annotations

import math
import uuid
from dataclasses import dataclass, field

import numpy as np

from listens_common import mood as moodlib

W_AUDIO, W_ARTIST, W_RHYTHM, W_ALBUM, W_ERA, W_LANGUAGE, W_GENRE = 0.30, 0.28, 0.12, 0.12, 0.06, 0.07, 0.05
# Weights once both songs have a mood: mood leads, artist is a minor tie-breaker (the listener asked for "sad songs", not
# "more of this singer").
M_MOOD, M_AUDIO, M_ARTIST, M_RHYTHM, M_ALBUM, M_ERA, M_LANGUAGE, M_GENRE = 0.40, 0.18, 0.07, 0.08, 0.05, 0.04, 0.07, 0.03
MOOD_GATE_FLOOR = 0.30  # a complete mood mismatch keeps at most this fraction of the score
ERA_SCALE_YEARS = 6.0
TASTE_TOP_K = 5
NEGATIVE_PENALTY = 0.5
CIRCLE_AFFINITY = 0.35
MMR_LAMBDA = 0.72
MIN_EVIDENCE = 0.45  # total signal weight below this is shrunk toward 0: one weak shared signal is not 'similar'

TAMIL_BLOCK = (0x0B80, 0x0BFF)


def detect_language(*texts: str | None) -> str | None:
    """"ta" when the text is mostly Tamil script, "other" for another non-Latin script, otherwise
    None: romanised titles ("Vaathi Coming") carry no usable signal, so they are left unknown
    rather than guessed."""
    letters = [ch for t in texts if t for ch in t if ch.isalpha()]
    if len(letters) < 3:
        return None
    tamil = sum(TAMIL_BLOCK[0] <= ord(c) <= TAMIL_BLOCK[1] for c in letters)
    latin = sum(ord(c) < 0x250 for c in letters)
    if tamil / len(letters) >= 0.3:
        return "ta"
    return "other" if latin / len(letters) < 0.3 else None


@dataclass
class Item:
    id: uuid.UUID
    artist_id: uuid.UUID
    album_key: str | None = None  # normalised album title: one film's songs by different singers are separate Album rows
    genre: str | None = None
    year: int | None = None
    tempo: float | None = None
    energy: float | None = None
    language: str | None = None
    vec: np.ndarray | None = None  # standardised + unit length, see Library.standardise
    mood: moodlib.Mood | None = None  # estimated from the fingerprint, relative to the library (listens_common.mood)


@dataclass
class ArtistInfo:
    mbid: str | None = None
    extra_mbids: tuple[str, ...] = ()  # the other people named in a joint credit ("A.R. Rahman/Hariharan/...")
    tags: dict[str, int] = field(default_factory=dict)
    neighbours: dict[str, float] = field(default_factory=dict)  # mbid -> 0..1 (strongest = 1)
    circle: str | None = None  # tamil_seed circle ("classic" / "modern"); same circle = baseline affinity

    @property
    def all_mbids(self) -> tuple[str, ...]:
        return tuple(m for m in (self.mbid, *self.extra_mbids) if m)


def _cosine_sparse(a: dict[str, float], b: dict[str, float]) -> float:
    if not a or not b:
        return 0.0
    dot = sum(v * b[k] for k, v in a.items() if k in b)
    na = math.sqrt(sum(v * v for v in a.values()))
    nb = math.sqrt(sum(v * v for v in b.values()))
    return dot / (na * nb) if na and nb else 0.0


class Library:
    """Everything needed to compare tracks, loaded once per request."""

    def __init__(self, items: list[Item], artists: dict[uuid.UUID, ArtistInfo] | None = None):
        self.items = {i.id: i for i in items}
        self.artists = artists or {}
        self._artist_cache: dict[tuple[uuid.UUID, uuid.UUID], float | None] = {}

    @staticmethod
    def standardise(raw: dict[uuid.UUID, list[float]]) -> dict[uuid.UUID, np.ndarray]:
        """Per-dimension z-score across the library, then unit length, so no single wide-ranging
        dimension (spectral centroid is in the thousands) drowns out the rest. With fewer than
        three fingerprinted tracks there is no meaningful spread, so nothing is returned."""
        if len(raw) < 3:
            return {}
        ids = list(raw)
        m = np.array([raw[i] for i in ids], dtype=float)
        std = m.std(axis=0)
        z = (m - m.mean(axis=0)) / np.where(std < 1e-9, 1.0, std)
        norms = np.linalg.norm(z, axis=1)
        z = z / np.where(norms < 1e-9, 1.0, norms)[:, None]
        return {i: z[k] for k, i in enumerate(ids)}

    def artist_affinity(self, a: Item, b: Item) -> float | None:
        if a.artist_id == b.artist_id:
            return 1.0
        key = (a.artist_id, b.artist_id) if str(a.artist_id) < str(b.artist_id) else (b.artist_id, a.artist_id)
        if key in self._artist_cache:
            return self._artist_cache[key]
        ia, ib = self.artists.get(a.artist_id), self.artists.get(b.artist_id)
        value: float | None = None
        if ia and ib and (ia.neighbours or ib.neighbours or ia.tags or ib.tags):
            mine, theirs = ia.all_mbids, ib.all_mbids
            direct = max([ia.neighbours.get(m, 0.0) for m in theirs] + [ib.neighbours.get(m, 0.0) for m in mine] + [0.0])
            # both artists' neighbour lists, each including the artist itself, so a direct link
            # also raises the overlap
            na = {**ia.neighbours, **dict.fromkeys(mine, 1.0)}
            nb = {**ib.neighbours, **dict.fromkeys(theirs, 1.0)}
            listening = max(direct, 0.85 * _cosine_sparse(na, nb))
            tags = _cosine_sparse({k: float(v) for k, v in ia.tags.items()}, {k: float(v) for k, v in ib.tags.items()})
            value = 0.8 * listening + 0.2 * tags if (ia.tags and ib.tags) else listening
        if ia and ib and ia.circle and ia.circle == ib.circle:
            value = max(value or 0.0, CIRCLE_AFFINITY)  # a floor: open data may know nothing of older artists
        self._artist_cache[key] = value
        return value

    def similarity(self, a: Item, b: Item) -> float:
        moody = a.mood is not None and b.mood is not None
        w_audio, w_artist, w_rhythm, w_album, w_era, w_language, w_genre = (
            (M_AUDIO, M_ARTIST, M_RHYTHM, M_ALBUM, M_ERA, M_LANGUAGE, M_GENRE) if moody
            else (W_AUDIO, W_ARTIST, W_RHYTHM, W_ALBUM, W_ERA, W_LANGUAGE, W_GENRE)
        )
        parts: list[tuple[float, float]] = []  # (weight, value 0..1)
        mood_match = moodlib.match(a.mood, b.mood) if moody else None
        if mood_match is not None:
            parts.append((M_MOOD, mood_match))
        if a.vec is not None and b.vec is not None:
            parts.append((w_audio, max(0.0, float(a.vec @ b.vec))))
        affinity = self.artist_affinity(a, b)
        if affinity is not None:
            parts.append((w_artist, affinity))
        rhythm = []
        if a.tempo and b.tempo:
            r = abs(math.log2(a.tempo / b.tempo))
            rhythm.append(math.exp(-min(r, abs(r - 1.0)) / 0.25))  # half/double time counts as a match
        if a.energy and b.energy:
            rhythm.append(math.exp(-abs(math.log(a.energy / b.energy))))
        if rhythm:
            parts.append((w_rhythm, sum(rhythm) / len(rhythm)))
        if a.album_key and b.album_key:
            parts.append((w_album, 1.0 if a.album_key == b.album_key else 0.0))
        if a.year and b.year:
            parts.append((w_era, math.exp(-abs(a.year - b.year) / ERA_SCALE_YEARS)))
        if a.language and b.language:
            parts.append((w_language, 1.0 if a.language == b.language else 0.0))
        if a.genre and b.genre:
            parts.append((w_genre, 1.0 if a.genre.casefold() == b.genre.casefold() else 0.0))
        total = sum(w for w, _ in parts)
        score = sum(w * v for w, v in parts) / max(total, MIN_EVIDENCE) if total else 0.0
        if mood_match is not None:
            score *= mood_gate(mood_match)  # a mood mismatch scales everything down
        return score


def mood_gate(match: float) -> float:
    """Factor 0.3..1 applied to a score by how well the moods match (1 = same mood)."""
    return MOOD_GATE_FLOOR + (1 - MOOD_GATE_FLOOR) * match


def mood_gate_for(a: Item, b: Item) -> float:
    """The gate for two items; 1 (no effect) when either has no mood estimate."""
    return mood_gate(moodlib.match(a.mood, b.mood)) if a.mood is not None and b.mood is not None else 1.0


def taste_score(lib: Library, candidate: Item, weights: dict[uuid.UUID, float]) -> float | None:
    """How well `candidate` fits the listener. `weights` maps track id -> signed weight (liked or
    finished tracks positive, early skips negative). None when there is nothing to go on."""
    positives = [(lib.items[t], w) for t, w in weights.items() if w > 0 and t in lib.items and t != candidate.id]
    if not positives:
        return None
    scored = sorted(((lib.similarity(candidate, p), w) for p, w in positives), key=lambda x: -x[0])[:TASTE_TOP_K]
    positive = sum(s * w for s, w in scored) / sum(w for _, w in scored)
    negatives = [(lib.items[t], w) for t, w in weights.items() if w < 0 and t in lib.items and t != candidate.id]
    penalty = max((lib.similarity(candidate, n) * min(1.0, -w / 4) for n, w in negatives), default=0.0)
    return max(0.0, positive - NEGATIVE_PENALTY * penalty)


def mmr(lib: Library, scores: dict[uuid.UUID, float], limit: int, lam: float = MMR_LAMBDA, per_artist: int = 2) -> list[uuid.UUID]:
    """Maximal marginal relevance: repeatedly take the candidate that is best by score but least
    like what is already chosen, with a hard cap per artist."""
    pool = sorted(scores, key=lambda t: -scores[t])[: max(limit * 4, 20)]
    chosen: list[uuid.UUID] = []
    per: dict[uuid.UUID, int] = {}
    while pool and len(chosen) < limit:
        def value(t: uuid.UUID) -> float:
            redundancy = max((lib.similarity(lib.items[t], lib.items[c]) for c in chosen), default=0.0)
            return lam * scores[t] - (1 - lam) * redundancy

        best = max(pool, key=value)
        pool.remove(best)
        artist = lib.items[best].artist_id
        if per.get(artist, 0) >= per_artist:
            continue
        per[artist] = per.get(artist, 0) + 1
        chosen.append(best)
    return chosen


def rank_normalise(values: dict[uuid.UUID, float]) -> dict[uuid.UUID, float]:
    """Min-max to 0..1 so ALS dot products and content similarity can be blended."""
    if not values:
        return {}
    lo, hi = min(values.values()), max(values.values())
    return {k: (v - lo) / (hi - lo) if hi - lo > 1e-12 else 0.5 for k, v in values.items()}
