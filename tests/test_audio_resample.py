"""Conforming decoded PCM to the device format."""

import pytest

np = pytest.importorskip("numpy")

from sample_manager.audio import resample
from sample_manager.audio.resample import conform


def test_matching_rate_and_layout_passes_samples_through():
    pcm = np.array([[0.1, -0.2], [0.3, -0.4]], dtype="float32")
    out = conform(pcm, 48000, 48000, 2)
    assert out.tolist() == pcm.tolist()
    assert out.dtype == np.float32 and out.flags.c_contiguous


def test_mono_source_is_duplicated_to_stereo():
    out = conform(np.array([0.5, -0.5], dtype="float32"), 44100, 44100, 2)
    assert out.tolist() == [[0.5, 0.5], [-0.5, -0.5]]


def test_stereo_to_mono_output_uses_channel_mean():
    out = conform(np.array([[1.0, 0.0]], dtype="float32"), 44100, 44100, 1)
    assert out.tolist() == [[0.5]]


@pytest.mark.parametrize("use_soxr", [True, False])
def test_rate_conversion_scales_length(monkeypatch, use_soxr):
    if use_soxr:
        pytest.importorskip("soxr")
    else:
        monkeypatch.setattr(resample, "is_available", lambda name: False)
    tone = np.sin(np.linspace(0, 200 * np.pi, 44100)).astype("float32")

    out = conform(tone, 44100, 48000, 2)

    assert out.shape[1] == 2
    assert abs(out.shape[0] - 48000) <= 2
    assert np.max(np.abs(out)) == pytest.approx(1.0, abs=0.05)


def test_invalid_rates_are_rejected():
    with pytest.raises(ValueError):
        conform(np.zeros(4, dtype="float32"), 0, 48000, 2)
