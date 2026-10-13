"""Song mood from the audio fingerprint the worker already stores: no new audio processing, no labelled dataset.

Mood is placed on two axes (Russell's circumplex model, the standard in music-emotion research):

  valence   sad / dark  ...  happy / bright
  arousal   calm / soft ...  energetic / intense

so "sad" is low valence and low arousal, "romantic/calm" is higher valence and low arousal, "upbeat" is high on both,
and "intense" is low valence and high arousal. The estimate uses what music-emotion studies find most predictive and
what librosa gave us (see services/worker/app/audio_features.py for the vector layout):

  valence  key mode (major vs minor, from the chroma means via the Krumhansl-Schmuckler key profiles), plus brightness
           (spectral centroid) and tempo: minor, dark and slow sounds sad, major, bright and quick sounds happy
  arousal  loudness (RMS energy), brightness, percussiveness (zero-crossing rate) and tempo

Each feature is z-scored across the library, so the axes are relative to YOUR songs: "sad" means sadder than the rest
of the library, which is the useful reading for ranking neighbours. It is an estimate, not ground truth (mode is a
weak signal for modal Indian film music, and the beat tracker can halve or double tempo), which is why it is blended
with the other similarity signals rather than used alone.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

CHROMA = slice(13, 25)
CENTROID, ZCR = 32, 33

# Krumhansl-Kessler key profiles (C major / C minor); rotated to test all 12 keys.
_MAJOR = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
_MINOR = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])

MIN_TRACKS = 5  # z-scores need some spread to mean anything


@dataclass(frozen=True)
class Mood:
    valence: float  # z-score across the library: negative = sadder/darker
    arousal: float  # z-score across the library: negative = calmer/softer

    @property
    def label(self) -> str:
        return label(self.valence, self.arousal)


def mode_score(chroma) -> float:
    """-1 (clearly minor) .. +1 (clearly major): how much better the best major key fits the chroma than the best minor."""
    c = np.asarray(chroma, dtype=float)
    if c.size != 12 or not np.isfinite(c).all() or c.std() < 1e-9:
        return 0.0

    def best(profile: np.ndarray) -> float:
        return max(float(np.corrcoef(c, np.roll(profile, k))[0, 1]) for k in range(12))

    return float(np.clip((best(_MAJOR) - best(_MINOR)) * 4.0, -1.0, 1.0))


def _z(values: np.ndarray) -> np.ndarray:
    std = values.std()
    return (values - values.mean()) / (std if std > 1e-9 else 1.0)


def compute_moods(raw: dict) -> dict:
    """{track id: Mood} from {track id: (fingerprint vector, tempo_bpm or None, energy or None)}.
    Tracks without a fingerprint are left out; tempo/energy fall back to the library average when missing."""
    ids = [i for i, (vec, _, _) in raw.items() if vec is not None and len(vec) >= 34]
    if len(ids) < MIN_TRACKS:
        return {}
    vecs = np.array([raw[i][0] for i in ids], dtype=float)
    tempo = np.array([raw[i][1] or np.nan for i in ids], dtype=float)
    energy = np.array([raw[i][2] or np.nan for i in ids], dtype=float)
    # tempo on a log scale: 60 -> 120 bpm is the same step as 90 -> 180; energy likewise (loudness is ratio-like)
    tempo = np.log2(np.where(np.isnan(tempo), np.nanmean(tempo) if not np.isnan(tempo).all() else 100.0, tempo))
    energy = np.log(np.where(np.isnan(energy), np.nanmean(energy) if not np.isnan(energy).all() else 0.05, energy))

    mode = np.array([mode_score(v[CHROMA]) for v in vecs])
    bright = _z(vecs[:, CENTROID])
    perc = _z(vecs[:, ZCR])
    t, e = _z(tempo), _z(energy)

    valence = 0.50 * _z(mode) + 0.25 * bright + 0.25 * t
    arousal = 0.40 * e + 0.25 * bright + 0.20 * t + 0.15 * perc
    valence, arousal = _z(valence), _z(arousal)
    return {i: Mood(float(valence[k]), float(arousal[k])) for k, i in enumerate(ids)}


SIGMA = 1.0  # how far apart (in z-score units) two moods can be before they stop counting as the same mood


def match(a: Mood, b: Mood) -> float:
    """0..1: 1 for the same mood, falling smoothly with distance on the valence/arousal plane."""
    d2 = (a.valence - b.valence) ** 2 + (a.arousal - b.arousal) ** 2
    return math.exp(-d2 / (2 * SIGMA**2))


def label(valence: float, arousal: float) -> str:
    """A human word for the quadrant, with a neutral band so a middling song is not forced into a mood."""
    if abs(valence) < 0.3 and abs(arousal) < 0.3:
        return "balanced"
    if valence < 0:
        return "melancholic" if arousal < 0 else "intense"
    return "calm" if arousal < 0 else "upbeat"
