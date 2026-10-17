"""Waveform DSP, service-cache, and terminal rendering tests."""

from pathlib import Path

import pytest

np = pytest.importorskip("numpy")

from sample_manager.audio.decode import DecodedAudio
from sample_manager.audio.waveform import (
    DEFAULT_WAVEFORM_BUCKETS,
    WaveformBin,
    WaveformService,
    compute_waveform_envelope,
)
from sample_manager.tui.widgets.waveform import _fit_bins, render_waveform


def test_envelope_preserves_signed_extrema_across_channels():
    samples = np.array(
        [[-0.8, 0.2], [0.4, 0.9], [-0.3, 0.1], [0.7, -0.6]],
        dtype="float32",
    )
    bins = compute_waveform_envelope(samples, 2)
    assert bins[0].minimum == pytest.approx(-0.8)
    assert bins[0].maximum == pytest.approx(0.9)
    assert bins[1].minimum == pytest.approx(-0.6)
    assert bins[1].maximum == pytest.approx(0.7)


def test_envelope_handles_silence_short_input_and_clipping():
    silence = compute_waveform_envelope(np.zeros(3), 10)
    assert len(silence) == 3
    assert all(item == WaveformBin(0.0, 0.0) for item in silence)

    clipped = compute_waveform_envelope(np.array([-2.0, 2.0]), 1)
    assert clipped == (WaveformBin(-1.0, 1.0),)


def test_envelope_validates_shape_and_bucket_count():
    with pytest.raises(ValueError):
        compute_waveform_envelope(np.zeros(3), 0)
    with pytest.raises(ValueError):
        compute_waveform_envelope(np.zeros((2, 2, 2)), 2)


def test_service_caches_until_file_identity_changes(tmp_path):
    path = tmp_path / "sample.wav"
    path.write_bytes(b"first")
    calls = []

    def decoder(requested: Path) -> DecodedAudio:
        calls.append(requested)
        samples = np.array([[-0.5], [0.75]], dtype="float32")
        return DecodedAudio(samples, 2, "fake")

    service = WaveformService(decoder=decoder, bucket_count=2)
    first = service.load(path)
    assert service.load(path) is first
    assert len(calls) == 1

    path.write_bytes(b"changed-size")
    second = service.load(path)
    assert second is not first
    assert len(calls) == 2


def test_service_default_uses_high_resolution_envelope(tmp_path):
    path = tmp_path / "long.wav"
    path.write_bytes(b"audio")
    samples = np.linspace(-1.0, 1.0, DEFAULT_WAVEFORM_BUCKETS * 2)
    service = WaveformService(
        decoder=lambda requested: DecodedAudio(samples, 44100, "fake")
    )

    assert len(service.load(path).bins) == DEFAULT_WAVEFORM_BUCKETS


def test_fit_bins_aggregates_extrema_to_terminal_width():
    bins = tuple(WaveformBin(-index / 10, index / 10) for index in range(8))
    fitted = _fit_bins(bins, 2)
    assert fitted == (WaveformBin(-0.3, 0.3), WaveformBin(-0.7, 0.7))


def test_render_waveform_has_stable_dimensions_and_cursor():
    bins = (WaveformBin(-1.0, 1.0), WaveformBin(-0.5, 0.5))
    rendered = render_waveform(bins, width=8, height=3, progress=0.5)
    lines = rendered.plain.splitlines()
    assert len(lines) == 3
    assert all(len(line) == 8 for line in lines)
    assert all(line[4] == "│" for line in lines)


def _reference_envelope(samples, bucket_count):
    """The original per-bucket loop, kept to pin vectorised behaviour."""
    values = np.asarray(samples, dtype="float64")
    count = min(bucket_count, int(values.shape[0]))
    edges = np.linspace(0, values.shape[0], count + 1, dtype=int)
    return tuple(
        WaveformBin(
            minimum=max(-1.0, min(1.0, float(np.min(values[edges[i]:edges[i + 1]])))),
            maximum=max(-1.0, min(1.0, float(np.max(values[edges[i]:edges[i + 1]])))),
        )
        for i in range(count)
    )


@pytest.mark.parametrize("shape,buckets", [((1000,), 64), ((997, 2), 100), ((50, 3), 50), ((7, 1), 4096)])
def test_vectorised_envelope_matches_reference(shape, buckets):
    rng = np.random.default_rng(1)
    samples = (rng.random(shape, dtype="float32") * 2.4 - 1.2).astype("float32")
    actual = compute_waveform_envelope(samples, buckets)
    expected = _reference_envelope(samples, buckets)
    assert len(actual) == len(expected)
    for got, want in zip(actual, expected):
        assert got.minimum == pytest.approx(want.minimum)
        assert got.maximum == pytest.approx(want.maximum)
