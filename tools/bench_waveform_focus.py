"""Measure focus-to-waveform time for stored analysis (v2 milestone 2).

Usage:
    python tools/bench_waveform_focus.py [SAMPLE_COUNT]

Builds a temporary library of SAMPLE_COUNT short WAVs (default 2000) plus one
240 s stem, indexes and analyses it, then times ``StoredWaveformService.load``
for a stored row (what a TUI focus costs once a scan has run) against the
v1 path that decodes the file and computes its envelope.
"""

from __future__ import annotations

import statistics
import sys
import tempfile
import time
from pathlib import Path

import numpy as np
import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sample_manager.audio.waveform import WaveformService  # noqa: E402
from sample_manager.db import Db  # noqa: E402
from sample_manager.migrations import apply_migrations  # noqa: E402
from sample_manager.scanner import scan_library  # noqa: E402
from sample_manager.services.sample_analysis import (  # noqa: E402
    StoredWaveformService,
    backfill_analysis,
)


def _median_ms(fn, runs: int = 25) -> float:
    times = []
    for _ in range(runs):
        start = time.perf_counter()
        fn()
        times.append((time.perf_counter() - start) * 1000)
    return statistics.median(times)


def main() -> None:
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 2000
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "lib"
        root.mkdir()
        noise = (np.random.rand(24000, 2).astype("float32") - 0.5)
        for index in range(count):
            folder = root / f"pack{index // 200:02d}"
            folder.mkdir(exist_ok=True)
            sf.write(folder / f"hit_{index:05d}.wav", noise, 48000, subtype="PCM_24")
        stem = root / "stem_240s.wav"
        sf.write(stem, np.random.rand(48000 * 240, 2).astype("float32") - 0.5, 48000, subtype="PCM_24")
        db_path = Path(tmp) / "index.sqlite3"
        with Db(db_path) as db:
            apply_migrations(db)
            scan_library(db, root)
            started = time.perf_counter()
            result = backfill_analysis(db)
            backfill_s = time.perf_counter() - started
        print(f"backfill: {result.analyzed} samples in {backfill_s:.1f} s")

        stored = StoredWaveformService(db_path=db_path)
        v1 = WaveformService()
        hit = root / "pack05" / "hit_01000.wav"
        for label, path in (("one-shot 0.5 s", hit), ("stem 240 s", stem)):
            stored_ms = _median_ms(lambda: stored.load(path))
            v1_ms = _median_ms(lambda: (v1._cache.clear(), v1.load(path)), runs=5)
            print(f"{label:15} stored {stored_ms:6.2f} ms   v1 decode+envelope {v1_ms:7.1f} ms")
        stored.close()


if __name__ == "__main__":
    main()
