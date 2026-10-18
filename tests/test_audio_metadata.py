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


def test_id3_text_custom_fields_and_artwork_are_read_only(tmp_path, write_sine_wav):
    """WAV ID3 uses the same frames as MP3; all text survives without binary dumps."""
    from mutagen.wave import WAVE
    from mutagen.id3 import APIC, COMM, TALB, TBPM, TIT2, TKEY, TPE1, TXXX

    path = write_sine_wav(tmp_path / "tagged.wav", seconds=0.1)
    audio = WAVE(path)
    audio.add_tags()
    for frame in (
        TIT2(encoding=3, text=["[Kick] One"]),
        TPE1(encoding=3, text=["Artist A", "Artist B"]),
        TALB(encoding=3, text=["Drum pack"]),
        TBPM(encoding=3, text=["98"]),
        TKEY(encoding=3, text=["Am"]),
        COMM(encoding=3, lang="eng", desc="Notes", text=["Line one\nLine two\x1b"]),
        TXXX(encoding=3, desc="Microphone", text=["SM57"]),
        APIC(encoding=3, mime="image/png", type=3, data=b"secret picture payload"),
    ):
        audio.tags.add(frame)
    audio.save()
    before = path.read_bytes()
    tags = dict(read_metadata(path).tags)
    assert tags["Title"] == "[Kick] One"
    assert tags["Artist"] == "Artist A; Artist B"
    assert tags["Album"] == "Drum pack"
    assert tags["BPM"] == "98" and tags["Key"] == "Am"
    assert tags["Custom (Microphone)"] == "SM57"
    assert any(value == "Line one Line two" for key, value in tags.items() if key.startswith("Comment"))
    artwork = next(value for key, value in tags.items() if key.startswith("Artwork"))
    assert "image/png" in artwork and "bytes" in artwork
    assert "secret picture payload" not in artwork
    assert path.read_bytes() == before


def test_vorbis_fields_and_flac_picture_are_exposed(tmp_path, write_sine_wav):
    """Format-native and custom fields are retained alongside technical properties."""
    import soundfile
    from mutagen.flac import FLAC, Picture

    wav = write_sine_wav(tmp_path / "source.wav", seconds=0.1)
    samples, rate = soundfile.read(wav)
    path = tmp_path / "tagged.flac"
    soundfile.write(path, samples, rate)
    audio = FLAC(path)
    audio["title"] = "A loop"
    audio["artist"] = ["One", "Two"]
    audio["custom_field"] = "custom value"
    picture = Picture()
    picture.mime = "image/jpeg"
    picture.data = b"binary picture"
    audio.add_picture(picture)
    audio.save()
    metadata = read_metadata(path)
    tags = dict(metadata.tags)
    assert tags["Title"] == "A loop"
    assert tags["Artist"] == "One; Two"
    assert tags["Custom Field"] == "custom value"
    assert tags["Artwork 1"] == "image/jpeg · 14 bytes"
    assert metadata.sample_rate == rate


def test_mp4_binary_and_multivalue_metadata_are_summarized():
    """MP4 cover/freeform bytes never become raw terminal payloads."""
    from types import SimpleNamespace
    from mutagen.mp4 import MP4Cover, MP4FreeForm
    from sample_manager.audio.metadata import _read_tags

    tags = dict(_read_tags(SimpleNamespace(tags={
        "©nam": ["Title"], "aART": ["Album artist"],
        "trkn": [(2, 12)], "covr": [MP4Cover(b"private bytes")],
        "----:com.apple.iTunes:Microphone": [MP4FreeForm(b"SM57")],
    })))
    assert tags["Title"] == "Title"
    assert tags["Album artist"] == "Album artist"
    assert tags["Track"] == "2/12"
    assert "bytes (binary)" in tags["Artwork"]
    assert "private bytes" not in tags["Artwork"]
    assert any(value == "SM57" for value in tags.values())


def test_real_mp3_id3_metadata(tmp_path, write_sine_wav):
    """Read ID3 from an actual generated MP3 when libsndfile can encode it."""
    import soundfile
    from mutagen.mp3 import MP3
    from mutagen.id3 import TIT2, TPE1

    if "MP3" not in soundfile.available_formats():
        pytest.skip("Installed libsndfile cannot generate an MP3 fixture")
    wav = write_sine_wav(tmp_path / "source.wav", seconds=0.2)
    samples, rate = soundfile.read(wav)
    path = tmp_path / "tagged.mp3"
    try:
        soundfile.write(path, samples, rate, format="MP3")
    except (soundfile.LibsndfileError, ValueError):
        pytest.skip("Installed libsndfile has no MP3 encoder")
    audio = MP3(path)
    if audio.tags is None:
        audio.add_tags()
    audio.tags.add(TIT2(encoding=3, text=["MP3 loop"]))
    audio.tags.add(TPE1(encoding=3, text=["Sample artist"]))
    audio.save()
    metadata = read_metadata(path)
    assert metadata.extension == ".mp3"
    assert dict(metadata.tags)["Title"] == "MP3 loop"
    assert dict(metadata.tags)["Artist"] == "Sample artist"
    assert metadata.duration_seconds > 0 and metadata.bitrate > 0
