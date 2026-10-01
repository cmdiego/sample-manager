"""Decode-free metadata tests for sample_manager.audio.metadata."""

import pytest

pytest.importorskip("mutagen")

from sample_manager.audio.metadata import (
    AudioMetadataError,
    ContainerMetadata,
    read_metadata,
)


def test_read_metadata_wav(tmp_path, write_sine_wav):
    p = write_sine_wav(
        tmp_path / "tone.wav", sample_rate=44100, seconds=0.25, channels=2
    )
    meta = read_metadata(p)
    assert isinstance(meta, ContainerMetadata)
    assert meta.extension == ".wav"
    assert meta.sample_rate == 44100
    assert meta.channels == 2
    assert meta.bit_depth == 16
    assert meta.duration_seconds == pytest.approx(0.25, abs=0.02)
    assert meta.format  # some non-empty label


def test_read_metadata_missing_file_raises(tmp_path):
    with pytest.raises(AudioMetadataError):
        read_metadata(tmp_path / "nope.wav")


def test_read_metadata_zero_length_raises(tmp_path):
    p = tmp_path / "empty.wav"
    p.write_bytes(b"")
    with pytest.raises(AudioMetadataError):
        read_metadata(p)


def test_read_metadata_unrecognized_container_raises(tmp_path):
    p = tmp_path / "notaudio.wav"
    p.write_bytes(b"this is definitely not audio data" * 10)
    with pytest.raises(AudioMetadataError):
        read_metadata(p)
