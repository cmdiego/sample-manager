"""Shared decode cache: dedupe, eviction, invalidation, and prefetch."""

import threading
import time
from pathlib import Path

import pytest

np = pytest.importorskip("numpy")

from sample_manager.audio.decode import DecodedAudio
from sample_manager.audio.decode_cache import DecodeCache


def _decoded(frames: int = 10) -> DecodedAudio:
    return DecodedAudio(np.zeros((frames, 1), dtype="float32"), 44100, "fake")


def _file(tmp_path: Path, name: str, content: bytes = b"x") -> Path:
    path = tmp_path / name
    path.write_bytes(content)
    return path


def test_repeat_requests_decode_once(tmp_path):
    calls = []
    cache = DecodeCache(decoder=lambda path: calls.append(path) or _decoded())
    path = _file(tmp_path, "a.wav")

    first = cache(path)

    assert cache.get(path) is first
    assert calls == [path]


def test_concurrent_requests_share_one_inflight_decode(tmp_path):
    release = threading.Event()
    calls = []

    def decoder(path):
        calls.append(path)
        release.wait(timeout=1.0)
        return _decoded()

    cache = DecodeCache(decoder=decoder)
    path = _file(tmp_path, "a.wav")
    results = []
    threads = [threading.Thread(target=lambda: results.append(cache.get(path))) for _ in range(3)]
    for thread in threads:
        thread.start()
    time.sleep(0.05)
    release.set()
    for thread in threads:
        thread.join(timeout=1.0)

    assert len(calls) == 1
    assert len(results) == 3 and all(result is results[0] for result in results)


def test_changed_file_is_decoded_again(tmp_path):
    calls = []
    cache = DecodeCache(decoder=lambda path: calls.append(path) or _decoded())
    path = _file(tmp_path, "a.wav", b"one")
    cache.get(path)

    path.write_bytes(b"longer content")
    cache.get(path)

    assert len(calls) == 2
    assert cache.size_bytes == _decoded().samples.nbytes


def test_byte_budget_evicts_least_recently_used(tmp_path):
    entry_bytes = _decoded(100).samples.nbytes
    cache = DecodeCache(decoder=lambda path: _decoded(100), max_bytes=entry_bytes * 2)
    a, b, c = (_file(tmp_path, f"{name}.wav") for name in "abc")
    cache.get(a)
    cache.get(b)
    cache.get(a)  # a is now most recent
    cache.get(c)

    assert cache.contains(a) and cache.contains(c)
    assert not cache.contains(b)


def test_decode_errors_propagate_and_are_not_cached(tmp_path):
    attempts = []

    def decoder(path):
        attempts.append(path)
        raise ValueError("corrupt")

    cache = DecodeCache(decoder=decoder)
    path = _file(tmp_path, "bad.wav")
    for _ in range(2):
        with pytest.raises(ValueError):
            cache.get(path)
    assert len(attempts) == 2


def test_prefetch_decodes_in_background_and_skips_large_files(tmp_path):
    cache = DecodeCache(decoder=lambda path: _decoded(), prefetch_max_file_bytes=4)
    small = _file(tmp_path, "small.wav", b"abc")
    large = _file(tmp_path, "large.wav", b"too large")
    try:
        cache.prefetch([small, large])
        deadline = time.monotonic() + 1.0
        while not cache.contains(small) and time.monotonic() < deadline:
            time.sleep(0.01)
        time.sleep(0.05)

        assert cache.contains(small)
        assert not cache.contains(large)
    finally:
        cache.close()
