"""Shared optional-engine selection, used by frontends and diagnostics."""

from __future__ import annotations

from .player import AudioPlayer
from .decode_cache import DecodeCache
from .sounddevice_output import NullOutput
from .stream_output import StreamingSoundDeviceOutput
from .streaming import PlaybackSources


def build_player(*, output="system_default", engine="python", buffer_frames=1024, cache_mb=256, backend="device"):
    """Keep Python usable without native binaries and own each player's cache.

    Native selection is explicit; auto tries it and reports any fallback through
    engine diagnostics. No output device is opened by the Python constructor.
    """
    device = int(output.partition(":")[2]) if output.startswith("device:") else None
    warning = None
    if output != "disabled" and engine in ("native", "auto"):
        try:
            from .native import build_native_player
            return build_native_player(device=device, buffer_frames=buffer_frames, cache_mb=cache_mb, backend=backend)
        except Exception as exc:
            if engine == "native":
                raise RuntimeError(f"Native engine unavailable: {exc}. Select Python or install sample-manager[native].") from exc
            warning = f"Native unavailable; using Python: {exc}"
    cache = DecodeCache(max_bytes=cache_mb * 1024 * 1024)
    if output == "disabled":
        adapter = NullOutput()
    elif backend == "null":
        from .null_stream import NullStreamOutput
        adapter = NullStreamOutput(blocksize=buffer_frames)
    else:
        adapter = StreamingSoundDeviceOutput(device=device, blocksize=buffer_frames)
    return CachedPlayer(decoder=PlaybackSources(cache), output=adapter, cache=cache, warning=warning)


class CachedPlayer(AudioPlayer):
    """Own prefetch/cache lifetime so device/settings changes do not leak workers."""

    def __init__(self, *, cache, warning=None, **kwargs):
        super().__init__(**kwargs)
        self._cache = cache
        self._warning = warning

    @property
    def waveform_decoder(self):
        """Share decoded short-file PCM with lazy waveform analysis."""
        return self._cache

    def engine_stats(self):
        """Expose only supported diagnostics, including truthful fallback status."""
        return {**super().engine_stats(), "engine": "python", "warning": self._warning,
                "cache_bytes": self._cache.size_bytes}

    def close(self):
        """Close output before shutting down background prefetch."""
        super().close()
        self._cache.close()
