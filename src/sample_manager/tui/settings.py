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

    theme: str = "dark"
    engine: str = "python"
    buffer_frames: int = 1024
    prefetch_depth: int = 3
    cache_mb: int = 256

    def __post_init__(self) -> None:
        """Reject invalid output identifiers before saving or creating a player."""
        if self.theme not in ("dark", "light"):
            raise ValueError("Theme must be dark or light")
        if self.engine not in ("auto", "native", "python"):
            raise ValueError("Engine must be auto, native or python")
        if type(self.buffer_frames) is not int or self.buffer_frames not in (128, 256, 512, 1024, 2048):
            raise ValueError("Buffer frames must be 128, 256, 512, 1024 or 2048")
        if (type(self.prefetch_depth) is not int or type(self.cache_mb) is not int or
                not 0 <= self.prefetch_depth <= 10 or not 16 <= self.cache_mb <= 2048):
            raise ValueError("Prefetch must be 0–10 rows and cache 16–2048 MiB")
        if not isinstance(self.audio_output, str):
            raise ValueError("Audio output must be a device identifier")
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
    audio = config.get("audio", {})
    if not isinstance(audio, dict):
        audio = {}
    defaults = TuiPreferences()
    values = dict(auto_audition=auto_audition)
    # Shared audio keys take precedence; legacy tui.audio_output is still read.
    for key in ("audio_output", "engine", "buffer_frames", "prefetch_depth", "cache_mb"):
        value = audio.get(key, raw.get(key, getattr(defaults, key)))
        try:
            TuiPreferences(**{key: value})
            values[key] = value
        except (ValueError, TypeError):
            values[key] = getattr(defaults, key)
    values["theme"] = raw.get("theme", "dark") if raw.get("theme", "dark") in ("dark", "light") else "dark"
    return TuiPreferences(**values)


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
    previous_audio = config.get("audio", {})
    config["audio"] = {
        **(previous_audio if isinstance(previous_audio, dict) else {}),
        **{key: getattr(preferences, key) for key in
           ("audio_output", "engine", "buffer_frames", "prefetch_depth", "cache_mb")},
    }
    save_config(config, path)


def build_tui_player(preferences: TuiPreferences):
    """Construct playback for the selected device without opening a stream yet."""
    from ..audio.factory import build_player

    return build_player(
        output=preferences.audio_output, engine=preferences.engine,
        buffer_frames=preferences.buffer_frames, cache_mb=preferences.cache_mb,
    )
