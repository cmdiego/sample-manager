"""Pure DSP math tests for sample_manager.audio.analysis.

These exercise the deterministic peak/RMS/mono helpers with in-memory arrays,
no file IO. Guarded behind numpy availability so the suite stays hermetic.
"""

import math

import pytest

np = pytest.importorskip("numpy")

from sample_manager.audio.analysis import (
    AudioFeatures,
    compute_peak,
    compute_rms,
    to_mono,
)


def test_compute_peak_known_values():
    arr = np.array([0.0, -0.8, 0.3, 0.5], dtype="float32")
    assert compute_peak(arr) == pytest.approx(0.8)


def test_compute_peak_empty_is_zero():
    assert compute_peak(np.array([], dtype="float32")) == 0.0


def test_compute_rms_full_scale_square_is_one():
    arr = np.array([1.0, -1.0, 1.0, -1.0], dtype="float64")
    assert compute_rms(arr) == pytest.approx(1.0)


def test_compute_rms_sine_is_amplitude_over_sqrt2():
    t = np.linspace(0, 1, 4000, endpoint=False)
    sine = 0.9 * np.sin(2 * np.pi * 5 * t)
    assert compute_rms(sine) == pytest.approx(0.9 / math.sqrt(2), abs=1e-3)


def test_compute_rms_empty_is_zero():
    assert compute_rms(np.array([], dtype="float32")) == 0.0


def test_to_mono_averages_channels():
    stereo = np.array([[1.0, 0.0], [0.0, 1.0], [0.5, 0.5]], dtype="float64")
    mono = to_mono(stereo)
    assert mono.shape == (3,)
    assert list(mono) == pytest.approx([0.5, 0.5, 0.5])


def test_to_mono_1d_passthrough():
    arr = np.array([0.1, 0.2, 0.3], dtype="float64")
    assert list(to_mono(arr)) == pytest.approx([0.1, 0.2, 0.3])


def test_to_mono_rejects_3d():
    with pytest.raises(ValueError):
        to_mono(np.zeros((2, 2, 2)))


def test_peak_matches_loudest_channel():
    # Peak is the max abs across ALL channels, not the mono mix.
    stereo = np.array([[0.9, 0.0], [-0.1, 0.1]], dtype="float64")
    assert compute_peak(stereo) == pytest.approx(0.9)


def test_features_dbfs_properties():
    f = AudioFeatures(
        path="x.wav",
        format="WAVE",
        duration_seconds=1.0,
        sample_rate=44100,
        channels=1,
        bit_depth=16,
        peak=1.0,
        rms=0.5,
    )
    assert f.peak_dbfs == pytest.approx(0.0, abs=1e-9)
    assert f.rms_dbfs == pytest.approx(-6.0206, abs=1e-3)


def test_features_dbfs_silence_is_neg_inf():
    f = AudioFeatures(
        path="x.wav",
        format="WAVE",
        duration_seconds=1.0,
        sample_rate=44100,
        channels=1,
        bit_depth=16,
        peak=0.0,
        rms=0.0,
    )
    assert f.peak_dbfs == -math.inf
    assert f.rms_dbfs == -math.inf
