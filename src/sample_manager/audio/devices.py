"""Audio output-device discovery independent of any frontend."""

from __future__ import annotations

from dataclasses import dataclass

from .backends import require


@dataclass(frozen=True)
class AudioOutputDevice:
    index: int
    name: str
    host_api: str
    max_output_channels: int
    default_sample_rate: float
    is_system_default: bool


def list_output_devices() -> tuple[AudioOutputDevice, ...]:
    """Return devices that can accept output audio from sounddevice."""
    sd = require("sounddevice")
    raw_devices = sd.query_devices()
    host_apis = sd.query_hostapis()
    try:
        default_output = int(sd.default.device[1])
    except (AttributeError, IndexError, TypeError, ValueError):
        default_output = -1

    devices = []
    for index, info in enumerate(raw_devices):
        channels = int(info.get("max_output_channels", 0))
        if channels <= 0:
            continue
        host_index = int(info.get("hostapi", -1))
        host_name = "Unknown"
        if 0 <= host_index < len(host_apis):
            host_name = str(host_apis[host_index].get("name", "Unknown"))
        devices.append(
            AudioOutputDevice(
                index=index,
                name=str(info.get("name", f"Device {index}")),
                host_api=host_name,
                max_output_channels=channels,
                default_sample_rate=float(info.get("default_samplerate", 0.0)),
                is_system_default=index == default_output,
            )
        )
    return tuple(devices)
