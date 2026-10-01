"""Audio output-device discovery tests."""

from types import SimpleNamespace

from sample_manager.audio.devices import list_output_devices


def test_lists_only_output_capable_devices(monkeypatch):
    fake_sd = SimpleNamespace(
        query_devices=lambda: [
            {
                "name": "MacBook Microphone",
                "hostapi": 0,
                "max_output_channels": 0,
                "default_samplerate": 48000.0,
            },
            {
                "name": "MacBook Speakers",
                "hostapi": 0,
                "max_output_channels": 2,
                "default_samplerate": 48000.0,
            },
            {
                "name": "Studio DAC",
                "hostapi": 0,
                "max_output_channels": 8,
                "default_samplerate": 96000.0,
            },
        ],
        query_hostapis=lambda: [{"name": "Core Audio"}],
        default=SimpleNamespace(device=(0, 1)),
    )
    monkeypatch.setattr(
        "sample_manager.audio.devices.require",
        lambda name: fake_sd,
    )

    devices = list_output_devices()

    assert [device.name for device in devices] == ["MacBook Speakers", "Studio DAC"]
    assert devices[0].host_api == "Core Audio"
    assert devices[0].is_system_default
    assert devices[1].max_output_channels == 8
