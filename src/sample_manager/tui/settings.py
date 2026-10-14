"""TUI playback preferences stored alongside the existing YAML configuration."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path

from ..config import get_config_path, get_default_config_template, load_config, save_config


@dataclass(frozen=True)
class TuiPreferences:
    """Playback choices independent of Qt and terminal widget implementations."""

    auto_audition: bool = True
    audio_output: str = "system_default"  # system_default, disabled, or device:<index>

    def __post_init__(self) -> None:
        """Reject invalid output identifiers before saving or creating a player."""
        if self.audio_output not in ("system_default", "disabled"):
            prefix, separator, index = self.audio_output.partition(":")
            if prefix != "device" or not separator or not index.isdecimal():
                raise ValueError("Choose System Default, Disabled, or an output device")


def load_tui_preferences(config_path: Path | None = None) -> TuiPreferences:
    """Read optional TUI keys, keeping older configurations compatible."""
    path = config_path if config_path is not None else get_config_path()
    if not path.exists():
        return TuiPreferences()
    config = load_config(path)
    raw = config.get("tui", {}) if isinstance(config, dict) else {}
    if not isinstance(raw, dict):
        return TuiPreferences()
    auto_audition = raw.get("auto_audition", True)
    if not isinstance(auto_audition, bool):
        auto_audition = True
    try:
        return TuiPreferences(auto_audition, str(raw.get("audio_output", "system_default")))
    except ValueError:
        return TuiPreferences(auto_audition)


def save_tui_preferences(
    preferences: TuiPreferences, config_path: Path | None = None,
) -> None:
    """Preserve other configuration keys while updating only TUI preferences."""
    path = config_path if config_path is not None else get_config_path()
    config = load_config(path) if path.exists() else get_default_config_template()
    if not isinstance(config, dict):
        raise ValueError("Configuration must contain a YAML mapping")
    previous = config.get("tui", {})
    config["tui"] = {
        **(previous if isinstance(previous, dict) else {}),
        **asdict(preferences),
    }
    save_config(config, path)


def build_tui_player(preferences: TuiPreferences):
    """Construct playback for the selected device without opening a stream yet."""
    from ..audio import AudioPlayer
    from ..audio.sounddevice_output import NullOutput, SoundDeviceOutput

    if preferences.audio_output == "disabled":
        output = NullOutput()
    else:
        device = (
            int(preferences.audio_output.partition(":")[2])
            if preferences.audio_output.startswith("device:") else None
        )
        output = SoundDeviceOutput(device=device)
    return AudioPlayer(output=output)
