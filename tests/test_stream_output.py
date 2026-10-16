"""Persistent-stream adapter contract tests without real hardware."""

from types import SimpleNamespace

import pytest

np = pytest.importorskip("numpy")

from sample_manager.audio.decode import DecodedAudio
from sample_manager.audio.stream_output import StreamingSoundDeviceOutput


class FakeStream:
    def __init__(self, **kwargs) -> None:
        self.kwargs = kwargs
        self.callback = kwargs["callback"]
        self.started = False
        self.stopped = False
        self.closed = False
        self.latency = 0.012

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.stopped = True

    def close(self) -> None:
        self.closed = True

    def pull(self, frames: int, status=None):
        out = np.empty((frames, self.kwargs["channels"]), dtype="float32")
        self.callback(out, frames, None, status)
        return out


@pytest.fixture
def streams(monkeypatch):
    created = []

    def output_stream(**kwargs):
        stream = FakeStream(**kwargs)
        created.append(stream)
        return stream

    fake_sd = SimpleNamespace(
        OutputStream=output_stream,
        query_devices=lambda device, kind: {
            "default_samplerate": 48000.0,
            "max_output_channels": 8,
        },
    )
    monkeypatch.setattr("sample_manager.audio.stream_output.require", lambda name: fake_sd)
    return created


def _audio(samples, rate=48000):
    return DecodedAudio(samples=np.asarray(samples, dtype="float32"), sample_rate=rate, backend="fake")


def test_stream_opens_once_at_device_format_and_stays_open(streams):
    output = StreamingSoundDeviceOutput(device=3)
    try:
        output.start(_audio([[0.1]] * 10), 0, lambda: None)
        output.start(_audio([[0.2]] * 10), 0, lambda: None)

        assert len(streams) == 1
        assert streams[0].kwargs["device"] == 3
        assert streams[0].kwargs["samplerate"] == 48000
        assert streams[0].kwargs["channels"] == 2
        assert streams[0].started and not streams[0].stopped
    finally:
        output.close()
    assert streams[0].stopped and streams[0].closed


def test_samples_render_and_completion_is_dispatched_off_the_callback(streams):
    output = StreamingSoundDeviceOutput()
    completed = []
    try:
        output.start(_audio([[0.25], [-0.5], [0.75]]), 0, lambda: completed.append(True))
        out = streams[0].pull(4)

        assert out[:, 0].tolist() == [0.25, -0.5, 0.75, 0.0]
        assert out[:, 1].tolist() == [0.25, -0.5, 0.75, 0.0]
        assert completed == []  # never called on the audio thread
        output.dispatch_pending()
        assert completed == [True]
        assert output.position_frames() == 3
    finally:
        output.close()


def test_pause_returns_source_position_without_stopping_stream(streams):
    output = StreamingSoundDeviceOutput()
    try:
        output.start(_audio(np.ones((24000, 1)), rate=24000), 0, lambda: None)
        streams[0].pull(4800)  # 0.1 s at the 48 kHz device rate

        position = output.pause()

        assert position == 2400  # 0.1 s at the 24 kHz source rate
        assert not streams[0].stopped
        tail = streams[0].pull(512)
        assert np.all(tail[200:] == 0.0)  # faded out within 3 ms
    finally:
        output.close()


def test_resume_mid_file_starts_at_mapped_frame(streams):
    output = StreamingSoundDeviceOutput()
    try:
        ramp = np.arange(48000, dtype="float32")[:, None] / 48000
        output.start(_audio(ramp), 24000, lambda: None)
        out = streams[0].pull(512)
        # Fades in from the resume point instead of jumping to full level.
        assert out[0, 0] < out[-1, 0]
        assert out[-1, 0] == pytest.approx(ramp[24000 + 511, 0])
    finally:
        output.close()


def test_stats_report_latency_and_xruns(streams):
    output = StreamingSoundDeviceOutput()
    try:
        output.start(_audio([[0.1]] * 100), 0, lambda: None)
        streams[0].pull(32, status=SimpleNamespace(output_underflow=True))

        stats = output.stats()

        assert stats["device_rate"] == 48000
        assert stats["output_latency_s"] == pytest.approx(0.012)
        assert stats["xruns"] == 1
        assert stats["last_start_to_render_s"] >= 0.0
    finally:
        output.close()


def test_resuming_same_audio_reuses_conversion(streams, monkeypatch):
    from sample_manager.audio import stream_output

    calls = []
    real = stream_output.conform
    monkeypatch.setattr(
        stream_output, "conform", lambda *args: calls.append(args) or real(*args)
    )
    output = StreamingSoundDeviceOutput()
    try:
        audio = _audio(np.ones((100, 1)), rate=44100)
        output.start(audio, 0, lambda: None)
        output.pause()
        output.start(audio, 10, lambda: None)
        output.start(_audio(np.ones((100, 1)), rate=44100), 0, lambda: None)
        assert len(calls) == 2
    finally:
        output.close()
