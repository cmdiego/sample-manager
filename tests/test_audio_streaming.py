"""Streaming long files: probing, source selection, and progressive fill."""

from pathlib import Path
from types import SimpleNamespace

import pytest

np = pytest.importorskip("numpy")
sf = pytest.importorskip("soundfile")

from sample_manager.audio.decode import DecodedAudio
from sample_manager.audio.decode_cache import DecodeCache
from sample_manager.audio.mixer import Mixer, Voice
from sample_manager.audio.stream_output import StreamingSoundDeviceOutput
from sample_manager.audio.streaming import (
    PlaybackSources,
    StreamFill,
    StreamingSource,
    probe_streaming_source,
)


def _ramp_wav(path: Path, seconds: float, rate: int = 8000, channels: int = 1) -> Path:
    frames = int(seconds * rate)
    ramp = (np.arange(frames, dtype="float32") / frames)[:, None]
    sf.write(path, np.repeat(ramp, channels, axis=1), rate, subtype="FLOAT")
    return path


def _drain(fill: StreamFill):
    """Consume while producing so bounded rings can wrap without deadlocking."""
    import time
    fill.start_background()
    mixer = Mixer(int(fill._source.sample_rate * fill.ratio), fill._channels, fade_seconds=0)
    mixer.play(fill.voice, fade_in=False)
    chunks = []
    deadline = time.monotonic() + 5
    while not fill.voice.complete or fill.voice.cursor < fill.voice.filled:
        assert time.monotonic() < deadline
        available = fill.voice.filled - fill.voice.cursor
        if not available:
            time.sleep(0.001)
            continue
        out = np.empty((min(512, available), fill._channels), dtype="float32")
        mixer.render(out)
        chunks.append(out)
    fill.join(1)
    return np.concatenate(chunks)


# -- probing and source selection ------------------------------------------------


def test_probe_streams_only_long_seekable_files(tmp_path):
    long = _ramp_wav(tmp_path / "long.wav", 2.0)
    short = _ramp_wav(tmp_path / "short.wav", 0.5)
    mp3 = tmp_path / "song.mp3"
    mp3.write_bytes(b"not decoded")

    source = probe_streaming_source(long, min_seconds=1.0)

    assert source == StreamingSource(long, 8000, 16000, 1)
    assert source.duration_seconds == pytest.approx(2.0)
    assert probe_streaming_source(short, min_seconds=1.0) is None
    assert probe_streaming_source(mp3, min_seconds=1.0) is None


def test_playback_sources_stream_long_files_unless_cached(tmp_path):
    long = _ramp_wav(tmp_path / "long.wav", 2.0)
    short = _ramp_wav(tmp_path / "short.wav", 0.5)
    cache = DecodeCache()
    sources = PlaybackSources(cache, stream_min_seconds=1.0)

    assert isinstance(sources(long), StreamingSource)
    assert isinstance(sources(short), DecodedAudio)
    assert cache.contains(short)

    cache.get(long)  # e.g. the waveform service decoded it
    assert isinstance(sources(long), DecodedAudio)


# -- progressive fill ------------------------------------------------------------


def test_fill_matches_full_decode_at_same_rate(tmp_path):
    path = _ramp_wav(tmp_path / "long.wav", 5.0)
    source = probe_streaming_source(path, min_seconds=1.0)
    fill = StreamFill(source, 0, token=1, device_rate=8000, device_channels=2)

    fill.fill_first_block()
    assert 0 < fill.voice.filled < source.frames and not fill.voice.complete
    rendered = _drain(fill)

    expected, _rate = sf.read(path, dtype="float32", always_2d=True)
    assert fill.voice.filled == source.frames
    np.testing.assert_array_equal(rendered[:, 0], expected[:, 0])
    np.testing.assert_array_equal(rendered[:, 1], expected[:, 0])


def test_fill_from_mid_file_starts_at_mapped_offset(tmp_path):
    path = _ramp_wav(tmp_path / "long.wav", 5.0)
    source = probe_streaming_source(path, min_seconds=1.0)
    fill = StreamFill(source, 20000, token=1, device_rate=8000, device_channels=1)

    assert fill.voice.cursor == 20000
    fill.fill_first_block()
    rendered = _drain(fill)

    expected, _rate = sf.read(path, dtype="float32", always_2d=True)
    np.testing.assert_array_equal(rendered[:, 0], expected[20000:, 0])


def test_fill_resamples_to_device_rate(tmp_path):
    pytest.importorskip("soxr")
    path = _ramp_wav(tmp_path / "long.wav", 5.0, rate=8000)
    source = probe_streaming_source(path, min_seconds=1.0)
    fill = StreamFill(source, 0, token=1, device_rate=12000, device_channels=1)

    fill.fill_first_block()
    rendered = _drain(fill)

    assert abs(fill.voice.filled - 60000) <= 64
    # The ramp keeps its shape after conversion (ignoring filter edges).
    middle = rendered[30000, 0]
    assert middle == pytest.approx(0.5, abs=0.01)


def test_cancelled_fill_completes_early(tmp_path):
    path = _ramp_wav(tmp_path / "long.wav", 30.0)
    source = probe_streaming_source(path, min_seconds=1.0)
    fill = StreamFill(source, 0, token=1, device_rate=8000, device_channels=1)
    fill.fill_first_block()
    fill.cancel()
    fill.start_background()
    fill.join(timeout=5.0)

    assert fill.voice.complete
    assert fill.voice.filled < source.frames


# -- mixer behaviour with partially filled voices --------------------------------


def test_mixer_waits_for_fill_instead_of_completing():
    mixer = Mixer(1000, 1)
    pcm = np.ones((10, 1), dtype="float32")
    voice = Voice(token=1, pcm=pcm, filled=4, complete=False)
    mixer.play(voice, fade_in=False)

    out = np.empty((6, 1), dtype="float32")
    mixer.render(out)
    assert out[:, 0].tolist() == [1, 1, 1, 1, 0, 0]
    assert voice.starved == 1
    assert not mixer.events

    voice.filled = 10
    voice.complete = True
    mixer.render(out)
    assert out[:, 0].tolist() == [1, 1, 1, 1, 1, 1]
    mixer.render(out)
    assert list(mixer.events) == [("complete", 1)]


# -- output adapter --------------------------------------------------------------


class _FakeStream:
    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs
        self.callback = kwargs["callback"]
        self.latency = 0.01

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass

    def close(self) -> None:
        pass

    def pull(self, frames: int):
        out = np.empty((frames, self.kwargs["channels"]), dtype="float32")
        self.callback(out, frames, None, None)
        return out


@pytest.fixture
def stream(monkeypatch):
    created = []
    fake_sd = SimpleNamespace(
        OutputStream=lambda **kwargs: created.append(_FakeStream(**kwargs)) or created[-1],
        query_devices=lambda device, kind: {"default_samplerate": 8000.0, "max_output_channels": 1},
    )
    monkeypatch.setattr("sample_manager.audio.stream_output.require", lambda name: fake_sd)
    return created


def test_output_plays_streaming_source_to_completion(tmp_path, stream):
    path = _ramp_wav(tmp_path / "long.wav", 2.0)
    source = probe_streaming_source(path, min_seconds=1.0)
    output = StreamingSoundDeviceOutput()
    import threading
    completed = []
    completion = threading.Event()
    def on_complete():
        """Observe completion regardless of manual/event-thread dispatch order."""
        completed.append(True)
        completion.set()
    try:
        output.start(source, 0, on_complete)
        # Pull only available frames, modelling a consumer without real time.
        import time
        fill = output._fill
        chunks = []
        while not fill.voice.complete or fill.voice.cursor < fill.voice.filled:
            available = fill.voice.filled - fill.voice.cursor
            if available:
                chunks.append(stream[0].pull(min(512, available)))
            else:
                time.sleep(0.001)
        rendered = np.concatenate(chunks)
        # EOF may be published after the final PCM render. A persistent device
        # keeps ticking; this final silent callback observes that publication.
        assert np.all(stream[0].pull(1) == 0)
        output.dispatch_pending()
        assert completion.wait(1)

        expected, _rate = sf.read(path, dtype="float32", always_2d=True)
        np.testing.assert_array_equal(rendered[:16000, 0], expected[:, 0])
        assert completed == [True]
        assert output.stats()["last_starved_renders"] == 0
    finally:
        output.close()


def test_pause_cancels_fill_and_resume_restarts_from_position(tmp_path, stream):
    path = _ramp_wav(tmp_path / "long.wav", 30.0)
    source = probe_streaming_source(path, min_seconds=1.0)
    output = StreamingSoundDeviceOutput()
    try:
        output.start(source, 0, lambda: None)
        first_fill = output._fill  # noqa: SLF001
        stream[0].pull(1000)

        position = output.pause()
        first_fill.join(timeout=5.0)

        assert position == 1000
        assert first_fill.voice.complete
        output.start(source, position, lambda: None)
        assert output._fill is not first_fill  # noqa: SLF001
        assert output._fill.voice.cursor == 1000  # noqa: SLF001
    finally:
        output.close()


def test_ring_memory_is_independent_of_duration_and_seek(tmp_path):
    """A one-hour header/late seek must still reserve only a fixed PCM ring."""
    path = _ramp_wav(tmp_path / "tiny.wav", 0.1)
    fills = [StreamFill(StreamingSource(path, 8000, 8000 * 3600, 1), offset,
                        token=1, device_rate=48000, device_channels=2)
             for offset in (0, 400)]
    try:
        assert [fill.voice.pcm.nbytes for fill in fills] == [48000 * 4, 48000 * 4]
    finally:
        for fill in fills:
            fill.discard()
