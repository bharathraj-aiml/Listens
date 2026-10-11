"""Cold-start audio features (tempo, energy, and a timbre/harmony fingerprint) via librosa - best
effort, never fatal.

These exist for Phase 5's "similar tracks": a brand-new upload has no play history yet, so
there's no ALS vector for it (see services/recommender). Tempo/energy give a weak but immediate
similarity signal ("fast and loud" vs "slow and quiet") until real listening data accumulates.

Performance note: librosa's beat tracker is numba-jitted, so the *first* call in a process pays
a one-time JIT-compilation cost (seconds); every call after that in the same worker process is
fast (well under a second for a 60 s analysis window). This is why extraction only analyses the
first 60 s of a track rather than the whole file - full-length analysis of a multi-minute song
gains little accuracy here for a large, fixed speed cost.
"""
import logging

import numpy as np

log = logging.getLogger("worker")

ANALYSIS_WINDOW_SECONDS = 60
SAMPLE_RATE = 22_050  # downsampled: plenty for tempo/energy, much faster to load than 44.1/48 kHz


VECTOR_DIMS = 13 + 12 + 7 + 2  # MFCC means, chroma means, spectral contrast means, centroid + zero-crossing


def _fingerprint(librosa, y, sr) -> list[float] | None:
    """Mean MFCC (timbre: "what it sounds like"), chroma (harmony/key colour), spectral contrast
    (how peaky vs noisy), spectral centroid (brightness) and zero-crossing rate (percussiveness).
    Means over the analysis window, left raw: dimensions have very different scales, so the
    recommender standardises each one across the whole library before comparing tracks."""
    mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13).mean(axis=1)
    chroma = librosa.feature.chroma_stft(y=y, sr=sr).mean(axis=1)
    contrast = librosa.feature.spectral_contrast(y=y, sr=sr).mean(axis=1)
    centroid = float(librosa.feature.spectral_centroid(y=y, sr=sr).mean())
    zcr = float(librosa.feature.zero_crossing_rate(y).mean())
    vec = [*map(float, mfcc), *map(float, chroma), *map(float, contrast), centroid, zcr]
    return vec if len(vec) == VECTOR_DIMS and all(np.isfinite(vec)) else None


def extract_features(path) -> dict:
    """Return {"tempo_bpm": ..., "energy": ..., "vector": [...]}, omitting keys it couldn't determine.
    Never raises - a failed or silent/beatless track just has no cold-start features, and the
    recommendation code already falls back to genre/artist in that case."""
    try:
        import librosa  # imported lazily: a heavy, native-extension-laden import

        y, sr = librosa.load(str(path), sr=SAMPLE_RATE, mono=True, duration=ANALYSIS_WINDOW_SECONDS)
        if y.size == 0:
            return {}
        out: dict = {}

        energy = float(np.mean(librosa.feature.rms(y=y)))
        if np.isfinite(energy):
            out["energy"] = energy

        tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
        tempo_val = float(np.atleast_1d(tempo)[0])
        if np.isfinite(tempo_val) and tempo_val > 0:  # 0 means no detectable beat (e.g. ambient/silence)
            out["tempo_bpm"] = tempo_val

        vector = _fingerprint(librosa, y, sr)
        if vector:
            out["vector"] = vector

        return out
    except Exception:  # noqa: BLE001 - cold-start features are a nice-to-have, never worth failing the upload
        log.exception("audio feature extraction failed for %s; continuing without them", path)
        return {}
