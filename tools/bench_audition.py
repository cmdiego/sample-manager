"""Measure the v1 audition path costs that the v2 design targets.

Usage:
    python tools/bench_audition.py [WORK_DIR]

Reports, per synthetic file length (48 kHz, 24-bit stereo WAV):
  * full decode as done by ``AudioPlayer`` before the first sample is heard,
  * the v1 waveform envelope (second decode not included),
  * reading only the first block (what a streaming engine needs to start),
  * a vectorised NumPy envelope for comparison,
and the wake-up jitter of a Python thread that simulates a 256-frame audio
callback while the main thread performs pure-Python UI-like work.

Numbers are warm page-cache timings; cold-disk reads are slower. Opening a
PortAudio stream is not measured here because it needs a real output device.
"""

from __future__ import annotations

import statistics
import sys
import tempfile
import threading
import time
from pathlib import Path

import numpy as np
import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sample_manager.audio.decode import decode  # noqa: E402
from sample_manager.audio.waveform import compute_waveform_envelope  # noqa: E402

CASES = {"oneshot_0.5s": 0.5, "loop_8s": 8, "stem_60s": 60, "stem_240s": 240}
BUCKETS = 4096


def _median_ms(fn, runs: int = 5):
    times = []
    result = None
    for _ in range(runs):
        start = time.perf_counter()
        result = fn()
        times.append((time.perf_counter() - start) * 1000)
    return statistics.median(times), result


def _vector_envelope(samples):
    # Rows are contiguous, so each bucket's block spans all channels.
    usable = samples.shape[0] // BUCKETS * BUCKETS
    blocks = samples[:usable].reshape(BUCKETS, -1)
    return blocks.min(axis=1), blocks.max(axis=1)


def bench_decode(work_dir: Path) -> None:
    print(f"{'case':14} {'v1 decode':>10} {'v1 env':>9} {'first-block':>12} {'vec env':>8}")
    for name, seconds in CASES.items():
        path = work_dir / f"{name}.wav"
        if not path.exists():
            noise = np.random.rand(int(48000 * seconds), 2).astype("float32") - 0.5
            sf.write(path, noise, 48000, subtype="PCM_24")
        decode_ms, audio = _median_ms(lambda: decode(path))
        env_ms, _ = _median_ms(lambda: compute_waveform_envelope(audio.samples, BUCKETS), 3)

        def first_block():
            with sf.SoundFile(path) as handle:
                return handle.read(2048, dtype="float32")

        block_ms, _ = _median_ms(first_block)
        vec_ms, _ = _median_ms(lambda: _vector_envelope(audio.samples))
        print(f"{name:14} {decode_ms:9.1f}ms {env_ms:8.1f}ms {block_ms:11.2f}ms {vec_ms:7.1f}ms")


def bench_gil_jitter(frames: int = 256, rate: int = 48000) -> None:
    period = frames / rate
    lateness: list[float] = []
    stop = threading.Event()

    def callback_thread() -> None:
        deadline = time.perf_counter()
        while not stop.is_set():
            deadline += period
            delay = deadline - time.perf_counter()
            if delay > 0:
                time.sleep(delay)
            lateness.append((time.perf_counter() - deadline) * 1000)

    def ui_work() -> None:
        total = 0
        for index in range(3_000_000):
            total += index % 7

    thread = threading.Thread(target=callback_thread)
    thread.start()
    time.sleep(0.5)
    idle = lateness[:]
    lateness.clear()
    start = time.perf_counter()
    while time.perf_counter() - start < 2:
        ui_work()
    stop.set()
    thread.join()

    budget = period * 1000
    print(f"\nPython callback wake-up lateness ({frames} frames = {budget:.1f} ms period)")
    for label, values in (("UI idle", idle), ("UI busy", lateness)):
        ordered = sorted(values)
        late = sum(value > budget for value in ordered)
        print(
            f"{label}: p50 {ordered[len(ordered) // 2]:.2f}ms  "
            f"p99 {ordered[int(len(ordered) * 0.99)]:.2f}ms  max {ordered[-1]:.2f}ms  "
            f"missed {late}/{len(ordered)}"
        )


def main() -> None:
    if len(sys.argv) > 1:
        work_dir = Path(sys.argv[1])
        work_dir.mkdir(parents=True, exist_ok=True)
        bench_decode(work_dir)
    else:
        with tempfile.TemporaryDirectory() as tmp:
            bench_decode(Path(tmp))
    bench_gil_jitter()


if __name__ == "__main__":
    main()
