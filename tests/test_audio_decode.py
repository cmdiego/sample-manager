"""Decode tests for sample_manager.audio.decode.

Backend routing is a pure function (no deps). WAV decode is tested via both the
soundfile backend and the dependency-free stdlib `wave` fallback. Compressed
formats are round-tripped only when the backend can actually produce them, so
the suite stays hermetic on machines without ffmpeg / libsndfile-MPEG.
"""

import pytest

from sample_manager.audio.decode import (
    AudioDecodeError,
    decode,
    select_backend,
)
from sample_manager.audio.backends import BackendUnavailable


# --- pure backend routing (no optional deps needed) ----------------------- #

def test_select_backend_soundfile_exts():
    for ext in (".wav", ".flac", ".ogg", ".aiff"):
        assert select_backend(ext) == "soundfile"


def test_select_backend_audioread_exts():
    for ext in (".mp3", ".aac", ".m4a", ".mp4"):
        assert select_backend(ext) == "audioread"


def test_select_backend_case_insensitive():
    assert select_backend(".WAV") == "soundfile"
    assert select_backend(".MP3") == "audioread"


def test_select_backend_unknown_is_none():
    assert select_backend(".xyz") is None


# --- error handling for bad inputs (needs numpy for the fallback path) ----- #

pytest.importorskip("numpy")


def test_missing_file_raises(tmp_path):
    with pytest.raises(AudioDecodeError):
        decode(tmp_path / "nope.wav")


def test_zero_length_file_raises(tmp_path):
    p = tmp_path / "empty.wav"
    p.write_bytes(b"")
    with pytest.raises(AudioDecodeError):
        decode(p)


def test_corrupt_wav_raises(tmp_path):
    p = tmp_path / "garbage.wav"
    p.write_bytes(b"RIFFnot-a-real-wav-file\x00\x01\x02\x03" * 4)
    with pytest.raises(AudioDecodeError):
        decode(p)


# --- WAV decode via stdlib wave fallback (numpy-only) ---------------------- #

def test_decode_wav_stdlib_backend(tmp_path, write_sine_wav):
    p = write_sine_wav(tmp_path / "tone.wav", seconds=0.2, sample_rate=22050)
    result = decode(p, backend="wave")
    assert result.backend == "wave"
    assert result.sample_rate == 22050
    assert result.channels == 1
    assert result.frames == pytest.approx(int(22050 * 0.2), abs=2)
    assert result.duration_seconds == pytest.approx(0.2, abs=0.01)


def test_decode_wav_stereo_stdlib(tmp_path, write_sine_wav):
    p = write_sine_wav(tmp_path / "st.wav", channels=2, seconds=0.1)
    result = decode(p, backend="wave")
    assert result.channels == 2
    assert result.samples.ndim == 2
    assert result.samples.shape[1] == 2


# --- WAV/FLAC/OGG/MP3 via soundfile, guarded by availability --------------- #

sf = pytest.importorskip("soundfile")


def _sf_supports(fmt: str) -> bool:
    return fmt in sf.available_formats()


def test_decode_wav_soundfile_default(tmp_path, write_sine_wav):
    p = write_sine_wav(tmp_path / "tone.wav", seconds=0.15, sample_rate=44100)
    result = decode(p)  # default routing -> soundfile
    assert result.backend == "soundfile"
    assert result.sample_rate == 44100
    assert result.channels == 1
    assert result.duration_seconds == pytest.approx(0.15, abs=0.01)


@pytest.mark.skipif(not _sf_supports("FLAC"), reason="libsndfile lacks FLAC")
def test_decode_flac_roundtrip(tmp_path):
    import numpy as np

    sr = 44100
    tone = (0.4 * np.sin(2 * np.pi * 220 * np.arange(sr // 5) / sr)).astype("float32")
    p = tmp_path / "tone.flac"
    sf.write(str(p), tone, sr, format="FLAC")
    result = decode(p)
    assert result.backend == "soundfile"
    assert result.sample_rate == sr
    assert result.channels == 1


@pytest.mark.skipif(not _sf_supports("OGG"), reason="libsndfile lacks OGG")
def test_decode_ogg_roundtrip(tmp_path):
    import numpy as np

    sr = 44100
    tone = (0.4 * np.sin(2 * np.pi * 330 * np.arange(sr // 5) / sr)).astype("float32")
    p = tmp_path / "tone.ogg"
    sf.write(str(p), tone, sr, format="OGG", subtype="VORBIS")
    result = decode(p)
    assert result.sample_rate == sr
    assert result.channels == 1


@pytest.mark.skipif(not _sf_supports("MP3"), reason="libsndfile lacks MPEG")
def test_decode_mp3_roundtrip(tmp_path):
    import numpy as np

    sr = 44100
    tone = (0.4 * np.sin(2 * np.pi * 440 * np.arange(sr // 4) / sr)).astype("float32")
    p = tmp_path / "tone.mp3"
    sf.write(str(p), tone, sr, format="MP3")
    result = decode(p)
    assert result.sample_rate == sr
    assert result.channels == 1
    assert result.frames > 0
