"""Contract tests for the sounddevice adapter without real hardware."""

from types import SimpleNamespace

import numpy as np

from sample_manager.audio.decode import DecodedAudio
from sample_manager.audio.sounddevice_output import SoundDeviceOutput


class CallbackStop(Exception):
    pass


class FakeStream:
    def __init__(self, **kwargs) -> None:
        self.callback = kwargs["callback"]
        self.started = False
        self.stopped = False
        self.closed = False

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        self.stopped = True

    def close(self) -> None:
        self.closed = True


def test_adapter_writes_samples_completes_and_closes(monkeypatch):
    streams = []

    def output_stream(**kwargs):
        stream = FakeStream(**kwargs)
        streams.append(stream)
        return stream

    fake_sd = SimpleNamespace(OutputStream=output_stream, CallbackStop=CallbackStop)
    monkeypatch.setattr(
        "sample_manager.audio.sounddevice_output.require",
        lambda name: fake_sd,
    )
    audio = DecodedAudio(
        samples=np.array([[0.25], [-0.5], [0.75]], dtype="float32"),
        sample_rate=44100,
        backend="fake",
    )
    completed = []
    output = SoundDeviceOutput()
    output.start(audio, 0, lambda: completed.append(True))

    target = np.empty((4, 1), dtype="float32")
    try:
        streams[0].callback(target, 4, None, None)
    except CallbackStop:
        pass

    assert target[:, 0].tolist() == [0.25, -0.5, 0.75, 0.0]
    assert completed == [True]
    assert output.position_frames() == 3

    output.close()
    assert streams[0].stopped
    assert streams[0].closed


def test_adapter_uses_system_default_device(monkeypatch):
    calls = []

    def output_stream(**kwargs):
        calls.append(kwargs)
        return FakeStream(**kwargs)

    fake_sd = SimpleNamespace(OutputStream=output_stream, CallbackStop=CallbackStop)
    monkeypatch.setattr(
        "sample_manager.audio.sounddevice_output.require",
        lambda name: fake_sd,
    )
    audio = DecodedAudio(
        samples=np.array([[0.0]], dtype="float32"),
        sample_rate=44100,
        backend="fake",
    )
    output = SoundDeviceOutput()
    output.start(audio, 0, lambda: None)

    assert calls[0]["device"] is None
    output.close()


def test_adapter_uses_selected_device(monkeypatch):
    calls = []

    def output_stream(**kwargs):
        calls.append(kwargs)
        return FakeStream(**kwargs)

    fake_sd = SimpleNamespace(OutputStream=output_stream, CallbackStop=CallbackStop)
    monkeypatch.setattr(
        "sample_manager.audio.sounddevice_output.require",
        lambda name: fake_sd,
    )
    audio = DecodedAudio(
        samples=np.array([[0.0]], dtype="float32"),
        sample_rate=44100,
        backend="fake",
    )
    output = SoundDeviceOutput(device=6)
    output.start(audio, 0, lambda: None)

    assert calls[0]["device"] == 6
    output.close()
