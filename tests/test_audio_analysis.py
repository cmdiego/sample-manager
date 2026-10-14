"""End-to-end analysis tests for sample_manager.audio.analysis.analyze."""

import pytest

from sample_manager.audio import capabilities
from sample_manager.audio.analysis import AudioFeatures, analyze

pytest.importorskip("numpy")
pytest.importorskip("soundfile")


def test_capabilities_reports_backends():
    caps = capabilities()
    assert set(caps) == {
        "numpy", "soundfile", "audioread", "mutagen", "sounddevice"
    }
    assert all(isinstance(v, bool) for v in caps.values())


def test_analyze_wav_features(tmp_path, write_sine_wav):
    p = write_sine_wav(
        tmp_path / "tone.wav",
        freq=440.0,
        sample_rate=44100,
        seconds=0.5,
        amplitude=0.5,
        channels=1,
    )
    feats = analyze(p)
    assert isinstance(feats, AudioFeatures)
    assert feats.sample_rate == 44100
    assert feats.channels == 1
    assert feats.duration_seconds == pytest.approx(0.5, abs=0.01)
    # Peak of a 0.5-amplitude sine is ~0.5; RMS ~0.5/sqrt(2) ~= 0.354.
    assert feats.peak == pytest.approx(0.5, abs=0.02)
    assert feats.rms == pytest.approx(0.354, abs=0.02)
    assert feats.peak_dbfs < 0.0
    assert feats.format  # non-empty label


def test_analyze_bit_depth_when_mutagen_available(tmp_path, write_sine_wav):
    if not capabilities()["mutagen"]:
        pytest.skip("mutagen not installed")
    p = write_sine_wav(tmp_path / "tone.wav", seconds=0.2)
    feats = analyze(p)
    assert feats.bit_depth == 16


def test_analyze_silence_has_zero_peak(tmp_path, write_sine_wav):
    p = write_sine_wav(tmp_path / "silent.wav", amplitude=0.0, seconds=0.2)
    feats = analyze(p)
    assert feats.peak == pytest.approx(0.0, abs=1e-6)
    assert feats.rms == pytest.approx(0.0, abs=1e-6)
    assert feats.peak_dbfs == float("-inf")
