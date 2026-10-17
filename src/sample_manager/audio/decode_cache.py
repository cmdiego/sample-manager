"""Shared, byte-bounded cache of decoded audio with background prefetch.

Playback and waveform generation both need the decoded PCM of the focused
sample. Routing both through one :class:`DecodeCache` means each file is
decoded once, and concurrent requests for the same file wait for the decode
already in flight instead of starting another. ``prefetch`` decodes the rows
around the cursor in the background so moving through a folder auditions from
RAM.
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from concurrent.futures import Future
from pathlib import Path
from typing import Callable, Iterable

from .decode import DecodedAudio, decode

DEFAULT_CACHE_BYTES = 256 * 1024 * 1024
# Prefetch only files small enough to decode quickly; long stems are decoded
# on demand when they are actually auditioned.
DEFAULT_PREFETCH_MAX_FILE_BYTES = 16 * 1024 * 1024

_Key = tuple[Path, int, int]


def _cache_key(path: Path) -> _Key:
    stat = path.stat()
    return (path.resolve(), stat.st_size, stat.st_mtime_ns)


def _decoded_bytes(audio: DecodedAudio) -> int:
    return int(getattr(audio.samples, "nbytes", 0))


class DecodeCache:
    """Callable decoder port (``cache(path) -> DecodedAudio``) with an LRU."""

    def __init__(
        self,
        *,
        decoder: Callable[[Path], DecodedAudio] = decode,
        max_bytes: int = DEFAULT_CACHE_BYTES,
        prefetch_max_file_bytes: int = DEFAULT_PREFETCH_MAX_FILE_BYTES,
    ) -> None:
        if max_bytes <= 0:
            raise ValueError("max_bytes must be greater than zero")
        self._decoder = decoder
        self._max_bytes = max_bytes
        self._prefetch_max_file_bytes = prefetch_max_file_bytes
        self._lock = threading.Lock()
        self._entries: OrderedDict[_Key, DecodedAudio] = OrderedDict()
        self._bytes = 0
        self._inflight: dict[_Key, Future] = {}
        self._wanted: list[Path] = []
        self._wakeup = threading.Condition(self._lock)
        self._closed = False
        self._worker: threading.Thread | None = None

    def __call__(self, path: Path) -> DecodedAudio:
        return self.get(path)

    def get(self, path: Path) -> DecodedAudio:
        """Return decoded audio for *path*, decoding at most once at a time."""
        requested = Path(path)
        key = _cache_key(requested)
        with self._lock:
            cached = self._entries.get(key)
            if cached is not None:
                self._entries.move_to_end(key)
                return cached
            future = self._inflight.get(key)
            owner = future is None
            if owner:
                future = Future()
                self._inflight[key] = future
        if not owner:
            return future.result()
        try:
            audio = self._decoder(requested)
        except BaseException as exc:
            with self._lock:
                self._inflight.pop(key, None)
            future.set_exception(exc)
            raise
        with self._lock:
            self._inflight.pop(key, None)
            self._store(key, audio)
        future.set_result(audio)
        return audio

    def contains(self, path: Path) -> bool:
        try:
            key = _cache_key(Path(path))
        except OSError:
            return False
        with self._lock:
            return key in self._entries

    def prefetch(self, paths: Iterable[Path]) -> None:
        """Replace the background decode queue with *paths*, nearest first."""
        with self._lock:
            if self._closed:
                return
            self._wanted = [Path(path) for path in paths]
            if self._worker is None:
                self._worker = threading.Thread(
                    target=self._prefetch_loop,
                    name="sample-manager-prefetch",
                    daemon=True,
                )
                self._worker.start()
            self._wakeup.notify()

    def close(self) -> None:
        with self._lock:
            self._closed = True
            self._wanted = []
            self._wakeup.notify()
            worker = self._worker
        if worker is not None:
            worker.join(timeout=1.0)

    @property
    def size_bytes(self) -> int:
        with self._lock:
            return self._bytes

    def _prefetch_loop(self) -> None:
        while True:
            with self._lock:
                while not self._wanted and not self._closed:
                    self._wakeup.wait()
                if self._closed:
                    return
                path = self._wanted.pop(0)
            try:
                if path.stat().st_size <= self._prefetch_max_file_bytes:
                    self.get(path)
            except Exception:  # noqa: BLE001 - a failed prefetch is retried on audition
                continue

    def _store(self, key: _Key, audio: DecodedAudio) -> None:
        """Insert under ``self._lock``; oversize results are returned uncached."""
        size = _decoded_bytes(audio)
        if size > self._max_bytes // 2:
            return
        stale = [existing for existing in self._entries if existing[0] == key[0]]
        for existing in stale:
            self._bytes -= _decoded_bytes(self._entries.pop(existing))
        self._entries[key] = audio
        self._bytes += size
        while self._bytes > self._max_bytes and self._entries:
            _key, evicted = self._entries.popitem(last=False)
            self._bytes -= _decoded_bytes(evicted)


_shared_cache: DecodeCache | None = None
_shared_lock = threading.Lock()


def shared_decode_cache() -> DecodeCache:
    """Process-wide cache shared by the TUI player and waveform service."""
    global _shared_cache
    with _shared_lock:
        if _shared_cache is None:
            _shared_cache = DecodeCache()
        return _shared_cache
