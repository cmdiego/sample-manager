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


@pytest.mark.parametrize("preparation", ["pcm", "stream"])
@pytest.mark.parametrize("action", ["pause", "close", "replace", "guard"])
def test_pending_preparation_cannot_outlive_lifecycle(
    streams, monkeypatch, tmp_path, preparation, action,
):
    """Block preparation so cancellation wins deterministically, without sleeps."""
    import threading
    from concurrent.futures import ThreadPoolExecutor
    from sample_manager.audio import stream_output
    from sample_manager.audio.streaming import StreamFill, StreamingSource

    entered, release = threading.Event(), threading.Event()
    output = StreamingSoundDeviceOutput()
    completed, fills = [], []
    current = True
    if preparation == "pcm":
        audio = _audio(np.full((4096, 1), 0.5))
        real = stream_output.conform

        def blocked_conform(*args):
            """Block only the older voice, allowing replacement to complete."""
            if args[0] is audio.samples:
                entered.set()
                assert release.wait(5)
            return real(*args)

        monkeypatch.setattr(stream_output, "conform", blocked_conform)
    else:
        sf = pytest.importorskip("soundfile")
        path = tmp_path / "pending.wav"
        sf.write(path, np.full((8192, 1), 0.5), 48000)
        audio = StreamingSource(path, 48000, 8192, 1)
        real = StreamFill.fill_first_block

        def blocked_first_block(fill):
            """Retain the abandoned fill to verify its file is closed."""
            fills.append(fill)
            entered.set()
            assert release.wait(5)
            return real(fill)

        monkeypatch.setattr(StreamFill, "fill_first_block", blocked_first_block)

    with ThreadPoolExecutor(max_workers=1) as executor:
        pending = executor.submit(
            output.start_if_current, audio, 0, lambda: completed.append("old"),
            lambda: current,
        )
        try:
            assert entered.wait(5)
            if action == "pause":
                output.pause()
            elif action == "close":
                output.close()
            elif action == "guard":
                current = False
            else:
                output.start(_audio(np.full((4096, 1), 0.25)), 0, lambda: None)
            release.set()
            pending.result(timeout=5)
            rendered = streams[0].pull(512)
            assert np.allclose(rendered, 0.25 if action == "replace" else 0.0)
            output.dispatch_pending()
            assert completed == []
            for fill in fills:
                assert fill._file.closed
                assert fill._thread is None
        finally:
            release.set()
            output.close()


def test_closed_output_never_reopens(streams):
    """Shutdown is terminal even if a delayed worker calls start afterward."""
    output = StreamingSoundDeviceOutput()
    output.close()
    output.start(_audio([[0.5]]), 0, lambda: None)
    output.close()
    assert streams == []


def test_guard_rejects_before_stream_registration(streams):
    """Player cancellation before output entry must not open a device."""
    output = StreamingSoundDeviceOutput()
    try:
        output.start_if_current(_audio([[0.5]]), 0, lambda: None, lambda: False)
        assert streams == []
    finally:
        output.close()


def test_first_block_failure_closes_unpublished_fill(streams, monkeypatch, tmp_path):
    """A failed synchronous first read must release its open native file."""
    from sample_manager.audio.streaming import StreamFill, StreamingSource

    sf = pytest.importorskip("soundfile")
    path = tmp_path / "broken.wav"
    sf.write(path, np.zeros((8192, 1)), 48000)
    fills = []

    def fail_first_block(fill):
        """Simulate a decoder failure after the file was opened."""
        fills.append(fill)
        raise RuntimeError("first block failed")

    monkeypatch.setattr(StreamFill, "fill_first_block", fail_first_block)
    output = StreamingSoundDeviceOutput()
    try:
        with pytest.raises(RuntimeError, match="first block failed"):
            output.start(StreamingSource(path, 48000, 8192, 1), 0, lambda: None)
        assert fills[0]._file.closed
        assert np.all(streams[0].pull(512) == 0)
    finally:
        output.close()
