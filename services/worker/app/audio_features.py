"""Cold-start audio features (tempo, energy) via librosa - best effort, never fatal.

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


def extract_features(path) -> dict[str, float]:
    """Return {"tempo_bpm": ..., "energy": ...}, omitting keys it couldn't determine.
    Never raises - a failed or silent/beatless track just has no cold-start features, and the
    recommendation code already falls back to genre/artist in that case."""
    try:
        import librosa  # imported lazily: a heavy, native-extension-laden import

        y, sr = librosa.load(str(path), sr=SAMPLE_RATE, mono=True, duration=ANALYSIS_WINDOW_SECONDS)
        if y.size == 0:
            return {}
        out: dict[str, float] = {}

        energy = float(np.mean(librosa.feature.rms(y=y)))
        if np.isfinite(energy):
            out["energy"] = energy

        tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
        tempo_val = float(np.atleast_1d(tempo)[0])
        if np.isfinite(tempo_val) and tempo_val > 0:  # 0 means no detectable beat (e.g. ambient/silence)
            out["tempo_bpm"] = tempo_val

        return out
    except Exception:  # noqa: BLE001 - cold-start features are a nice-to-have, never worth failing the upload
        log.exception("audio feature extraction failed for %s; continuing without them", path)
        return {}
