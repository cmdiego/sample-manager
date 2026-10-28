"""Timer-driven Python NullBackend using the same persistent mixer/output port."""

import threading
from .backends import require
from .mixer import Mixer
from .stream_output import StreamingSoundDeviceOutput


class _NullStream:
    """Drive callback work at device cadence without opening hardware."""

    latency = 0.0

    def __init__(self, mixer, frames):
        self._stop = threading.Event()
        self._mixer, self._frames = mixer, frames
        self._thread = threading.Thread(target=self._run, name="sample-manager-null-output", daemon=True)
        self._thread.start()

    def _run(self):
        """Allocate once outside the callback and reuse each output buffer."""
        np = require("numpy")
        out = np.empty((self._frames, self._mixer.channels), dtype="float32")
        while not self._stop.wait(self._frames / self._mixer.sample_rate):
            self._mixer.render(out)

    def stop(self):
        """Wake and join the timer before releasing its mixer."""
        self._stop.set()
        self._thread.join(timeout=2)

    def close(self):
        """Match the sounddevice lifecycle port."""
        self.stop()


class NullStreamOutput(StreamingSoundDeviceOutput):
    """Exercise real PCM, fades and streaming headlessly at 48 kHz stereo."""

    def _ensure_stream(self):
        """Open a timer/mixer once; caller holds the inherited lifecycle lock."""
        if self._mixer is None:
            self._mixer = Mixer(48000, 2)
            self._stream = _NullStream(self._mixer, self._blocksize or 256)
            self._events_thread = threading.Thread(target=self._dispatch_events,
                name="sample-manager-null-events", daemon=True)
            self._events_thread.start()
        return self._mixer
