import subprocess

from app import audio_features
from listens_common import testing


def _rhythmic_file(tmp_path, seconds=20):
    """A plain sine tone has no beat for librosa to lock onto (tempo comes back 0/unusable);
    this amplitude-modulated tone gives it something rhythmic to actually detect."""
    p = tmp_path / "rhythmic.mp3"
    subprocess.run([
        "ffmpeg", "-y", "-v", "error", "-f", "lavfi",
        "-i", f"sine=frequency=220:duration={seconds},volume='if(mod(floor(t*2),2),1,0.3)':eval=frame",
        "-b:a", "192k", str(p),
    ], check=True)
    return p


def test_extracts_tempo_and_energy_from_rhythmic_audio(tmp_path):
    f = _rhythmic_file(tmp_path)
    features = audio_features.extract_features(f)
    assert "energy" in features and features["energy"] > 0
    assert "tempo_bpm" in features and features["tempo_bpm"] > 0


def test_silent_or_beatless_audio_omits_tempo_not_crash(tmp_path):
    f = testing.make_audio(tmp_path / "plain.mp3", seconds=5)  # a constant sine tone: no beat
    features = audio_features.extract_features(f)
    assert "energy" in features  # energy is always computable
    # tempo may or may not be detected on a pure tone depending on librosa's onset heuristics;
    # the only hard requirement is that a nonsense/zero value is never stored
    assert features.get("tempo_bpm", 1) > 0


def test_malformed_file_returns_empty_dict_not_raise(tmp_path):
    junk = tmp_path / "junk.mp3"
    junk.write_bytes(b"not audio at all" * 200)
    assert audio_features.extract_features(junk) == {}


def test_missing_file_returns_empty_dict_not_raise(tmp_path):
    assert audio_features.extract_features(tmp_path / "does_not_exist.mp3") == {}


def test_extracts_a_fixed_length_fingerprint_vector(tmp_path):
    vec = audio_features.extract_features(_rhythmic_file(tmp_path)).get("vector")
    assert vec is not None and len(vec) == audio_features.VECTOR_DIMS


def test_fingerprint_tells_different_sounds_apart(tmp_path):
    low = tmp_path / "low.mp3"
    high = tmp_path / "high.mp3"
    for path, freq in ((low, 110), (high, 1760)):
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"sine=frequency={freq}:duration=8",
                        "-b:a", "192k", str(path)], check=True)
    a = audio_features.extract_features(low)["vector"]
    b = audio_features.extract_features(high)["vector"]
    assert a != b
