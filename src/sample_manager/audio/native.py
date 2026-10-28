"""Optional Rust output adapter; the existing player owns user-visible transport.

Native paths stay in Rust workers. Other formats use the Python decode port and
one device-rate PCM copy, preserving optional backend behavior without ffmpeg in
native wheels. Importing this module does not import the extension until build.
"""

from pathlib import Path
import threading
import time
from .player import AudioPlayer
from .decode_cache import DecodeCache
from .resample import conform
from .streaming import StreamingSource

_NATIVE_EXTENSIONS = {".wav", ".wave", ".aif", ".aiff", ".flac", ".mp3"}


class NativeSources:
    """Probe native formats cheaply; use existing decoders for all other formats."""

    def __init__(self, module, cache):
        self.module, self.cache = module, cache

    def __call__(self, path):
        """Unknown duration falls back to a complete Python decode for seek parity."""
        path = Path(path)
        if path.suffix.lower() in _NATIVE_EXTENSIONS:
            rate, frames, channels = self.module.probe(str(path))
            if frames > 0:
                return StreamingSource(path, rate, frames, channels)
        return self.cache(path)

    def prefetch(self, paths):
        """Python-only formats retain the bounded decode-cache policy."""
        self.cache.prefetch([p for p in paths if p.suffix.lower() not in _NATIVE_EXTENSIONS])


class NativeOutput:
    """Serialize Python command/event access; Rust callback never takes this lock."""

    def __init__(self, engine):
        self.engine = engine
        self._lock = threading.RLock()
        self._closed = threading.Event()
        self._generation = 0
        self._callbacks = {}
        self._ratio = 1.0
        self._error = None
        self._thread = threading.Thread(target=self._events, name="sample-manager-native-events", daemon=True)
        self._thread.start()

    def start(self, audio, start_frame, on_complete):
        """Retain the public AudioOutput contract."""
        self.start_if_current(audio, start_frame, on_complete, lambda: True)

    def start_if_current(self, audio, start_frame, on_complete, is_current):
        """Reject stale PCM preparation using the same handoff guard as Python."""
        requested_at = time.perf_counter()
        with self._lock:
            if self._closed.is_set() or not is_current():
                return
            self._generation += 1
            generation = self._generation
            rate = self.engine.snapshot()["sample_rate"]
        pcm = None
        if not isinstance(audio, StreamingSource):
            pcm = conform(audio.samples, audio.sample_rate, rate, 2).astype("<f4", copy=False).tobytes()
        with self._lock:
            if self._closed.is_set() or generation != self._generation or not is_current():
                return
            self._command_at = requested_at
            self._ratio = rate / audio.sample_rate
            self._error = None
            self._callbacks = {generation: on_complete}
            if pcm is None:
                self.engine.play(generation, str(audio.path), start_frame / audio.sample_rate)
            else:
                self.engine.play_pcm(generation, pcm, start_frame / audio.sample_rate)

    def pause(self):
        """Invalidate pending work and request a native fade without device I/O."""
        with self._lock:
            self._generation += 1
            self._callbacks.clear()
            if not self._closed.is_set():
                self.engine.pause()
                return round(self.engine.snapshot()["position_frames"] / self._ratio)
            return 0

    def position_frames(self):
        """Map device-rate frames back to the player's source-frame contract."""
        with self._lock:
            return round(self.engine.snapshot()["position_frames"] / self._ratio)

    def playback_error(self):
        """Expose worker/device failures through the shared player snapshot."""
        with self._lock:
            if self.engine.snapshot()["status"] == 4:
                return self._error or "Native audio failed; check the output device"
            return self._error

    def stats(self):
        """Report timestamps as engine/device-buffer timing, not acoustic latency."""
        with self._lock:
            state = self.engine.snapshot()
        if state["out_ns"]:
            first_render = time.perf_counter() - (state["now_ns"] - state["out_ns"]) / 1e9
        else:
            first_render = None
        # CPAL reports stream errors, not a portable hardware xrun counter.
        # Preserve truthful device errors and separately expose ring starvation.
        device_errors = state.pop("xruns", 0)
        return {**state, "device_errors": device_errors, "engine": "native", "last_first_render_at": first_render,
                "last_start_at": getattr(self, "_command_at", None), "device_rate": state["sample_rate"],
                "last_start_to_render_s": ((state["out_ns"] - state["command_ns"]) / 1e9
                                           if state["out_ns"] else None)}

    def prefetch(self, paths):
        """Only bounded native path jobs cross the binding."""
        with self._lock:
            if not self._closed.is_set():
                self.engine.prefetch([str(p) for p in paths if p.suffix.lower() in _NATIVE_EXTENSIONS])

    def _events(self):
        """Deliver completions/errors off the Rust and Python audio callbacks."""
        while not self._closed.wait(0.02):
            callbacks = []
            with self._lock:
                for kind, token, message in self.engine.drain_events():
                    if token != self._generation:
                        continue
                    if kind == "error":
                        self._error = message
                    callback = self._callbacks.pop(token, None)
                    if callback is not None:
                        callbacks.append(callback)
            for callback in callbacks:
                callback()

    def close(self):
        """Close native workers/stream before joining the event dispatcher."""
        with self._lock:
            if self._closed.is_set():
                return
            self._closed.set()
            self._generation += 1
            self._callbacks.clear()
            self.engine.close()
        if threading.current_thread() is not self._thread:
            self._thread.join(timeout=2)


class NativePlayer(AudioPlayer):
    """Share the established player API with native and Python format prefetch."""

    def __init__(self, *, sources, output, cache):
        super().__init__(decoder=sources, output=output)
        self._cache = cache

    @property
    def waveform_decoder(self):
        """Reuse Python bridge PCM when analysis also needs that format."""
        return self._cache

    def prefetch(self, paths):
        """Split prefetch by actual decoder capability."""
        paths = list(paths)
        super().prefetch(paths)
        self._output.prefetch(paths)

    def close(self):
        """Own the fallback decoder cache lifetime."""
        super().close()
        self._cache.close()


def build_native_player(*, device=None, buffer_frames=1024, cache_mb=64, backend="device"):
    """Construct explicitly; import/device errors are handled by the shared factory."""
    import sample_manager_engine as module
    if device is not None and backend == "device":
        # PortAudio and CPAL indexes enumerate different device collections.
        # Match a unique name instead of silently sending audio to another device.
        from .backends import require
        name = require("sounddevice").query_devices(device, "output")["name"]
        matches = [index for index, value in enumerate(module.devices()) if value == name]
        if len(matches) != 1:
            raise RuntimeError(f"Cannot uniquely match output {name!r} in the native engine")
        device = matches[0]
    engine = module.Engine(device=device, buffer_frames=buffer_frames, cache_mb=cache_mb, backend=backend)
    cache = DecodeCache(max_bytes=cache_mb * 1024 * 1024)
    return NativePlayer(sources=NativeSources(module, cache), output=NativeOutput(engine), cache=cache)
