import numpy as np

from listens_common import mood

C_MAJOR_PROFILE = [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88]
C_MINOR_PROFILE = [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17]


def vec(chroma, centroid=2000.0, zcr=0.08):
    """A 34-dim fingerprint with the layout the worker writes: 13 MFCC, 12 chroma, 7 contrast, centroid, zcr."""
    return [0.0] * 13 + list(chroma) + [0.0] * 7 + [centroid, zcr]


def test_major_and_minor_keys_are_told_apart_in_any_key():
    for shift in (0, 3, 7):
        assert mood.mode_score(np.roll(C_MAJOR_PROFILE, shift)) > 0.3
        assert mood.mode_score(np.roll(C_MINOR_PROFILE, shift)) < -0.3
    assert mood.mode_score([1.0] * 12) == 0.0  # flat chroma has no key
    assert mood.mode_score([0.5, 0.2]) == 0.0  # malformed input is neutral, not an error


def test_slow_dark_minor_is_sad_and_fast_bright_major_is_upbeat():
    raw = {}
    for k in range(6):  # a spread of filler songs so z-scores have something to compare against
        raw[f"mid{k}"] = (vec(np.roll(C_MAJOR_PROFILE if k % 2 else C_MINOR_PROFILE, k), 2000 + 100 * k, 0.08), 100 + 4 * k, 0.05 + 0.002 * k)
    raw["sad"] = (vec(C_MINOR_PROFILE, 1200, 0.04), 60, 0.02)
    raw["happy"] = (vec(C_MAJOR_PROFILE, 3200, 0.14), 150, 0.12)
    m = mood.compute_moods(raw)
    assert m["sad"].valence < -0.8 and m["sad"].arousal < -0.8 and m["sad"].label == "melancholic"
    assert m["happy"].valence > 0.8 and m["happy"].arousal > 0.8 and m["happy"].label == "upbeat"
    assert mood.match(m["sad"], m["sad"]) == 1.0
    assert mood.match(m["sad"], m["happy"]) < 0.05


def test_too_few_songs_or_missing_fingerprints_give_no_mood():
    assert mood.compute_moods({"a": (vec(C_MAJOR_PROFILE), 100, 0.05)}) == {}
    assert mood.compute_moods({str(i): (None, 100, 0.05) for i in range(8)}) == {}


def test_missing_tempo_or_energy_still_gives_a_mood():
    raw = {str(i): (vec(np.roll(C_MAJOR_PROFILE, i), 2000 + 150 * i), None if i % 2 else 100 + i, None if i % 3 == 0 else 0.05 + 0.01 * i) for i in range(8)}
    assert len(mood.compute_moods(raw)) == 8
