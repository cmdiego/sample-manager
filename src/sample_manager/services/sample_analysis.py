"""Scan-time analysis storage and DB-backed waveforms (v2 milestone 2).

:class:`StoredWaveformService` is a drop-in for
:class:`~sample_manager.audio.waveform.WaveformService` (same ``load`` and
``get_waveform``). When a file is an indexed sample with a current
``sample_analysis`` row, its waveform comes from SQLite without decoding.
Otherwise the envelope is computed from the decoder as before, returned at
once, and the full analysis (pyramid, peak, RMS, loudness) is stored by a
background thread, so the next focus is a database read.

:func:`backfill_analysis` analyses every indexed sample that has no valid row.
The TUI runs it after a scan; ``sampleman analyze`` runs it from the CLI.

Every method opens its own SQLite connection: callers run on worker threads,
and a ``sqlite3`` connection belongs to the thread that created it.
"""

from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from ..audio.analysis import ANALYSIS_VERSION, ScanAnalysis, analyze_decoded
from ..audio.decode import DecodedAudio, decode
from ..audio.peaks import compute_peak_pyramid, decode_level, encode_pyramid
from ..audio.waveform import (
    DEFAULT_WAVEFORM_BUCKETS,
    WaveformData,
    WaveformService,
    resample_bins,
)
from ..db import Db
from ..normalize import norm_rel_path
from ..repos.sample_analysis_repo import SampleAnalysisRepo


@dataclass(frozen=True)
class BackfillResult:
    analyzed: int
    skipped: int
    failed: int
    cancelled: bool = False


def _file_identity(path: Path) -> tuple[int, int]:
    stat = path.stat()
    return stat.st_size, stat.st_mtime_ns


def resolve_sample_id(db: Db, path: Path) -> int | None:
    """Return the sample id for an absolute *path* under an indexed root."""
    resolved = Path(path).resolve()
    for root in db.fetchall("SELECT id, path FROM library_root"):
        root_path = Path(root["path"])
        if not resolved.is_relative_to(root_path):
            continue
        rel_norm = norm_rel_path(resolved.relative_to(root_path))
        sample_id = db.fetchval(
            "SELECT id FROM sample WHERE library_root_id = ? AND rel_path_norm = ?",
            (root["id"], rel_norm),
        )
        if sample_id is not None:
            return int(sample_id)
    return None


def analysis_row(analysis: ScanAnalysis, *, size_bytes: int, mtime_ns: int) -> dict:
    """Column values for :meth:`SampleAnalysisRepo.upsert`."""
    peak_levels, blob = encode_pyramid(analysis.pyramid)
    return {
        "size_bytes": size_bytes,
        "mtime_ns": mtime_ns,
        "analysis_version": ANALYSIS_VERSION,
        "sample_rate": analysis.sample_rate,
        "channels": analysis.channels,
        "frames": analysis.frames,
        "duration_seconds": analysis.duration_seconds,
        "peak": analysis.peak,
        "rms": analysis.rms,
        "loudness_lufs": analysis.loudness_lufs,
        "short_term_max_lufs": analysis.short_term_max_lufs,
        "peak_levels": peak_levels,
        "peaks": blob,
    }


def store_analysis(db: Db, sample_id: int, path: Path, audio: DecodedAudio) -> ScanAnalysis:
    """Analyse decoded *audio* and store it against the file's current identity."""
    size_bytes, mtime_ns = _file_identity(path)
    analysis = analyze_decoded(audio)
    SampleAnalysisRepo(db).upsert(
        sample_id, analysis_row(analysis, size_bytes=size_bytes, mtime_ns=mtime_ns)
    )
    return analysis


class StoredWaveformService:
    """Waveforms from ``sample_analysis`` first, computed and stored otherwise."""

    def __init__(
        self,
        *,
        decoder: Callable[[Path], DecodedAudio] = decode,
        db_path: str | Path | None = None,
        bucket_count: int = DEFAULT_WAVEFORM_BUCKETS,
    ) -> None:
        self._decoder = decoder
        self._db_path = str(db_path) if db_path is not None else None
        self._bucket_count = bucket_count
        self._fallback = WaveformService(decoder=decoder, bucket_count=bucket_count)
        self._writer = ThreadPoolExecutor(max_workers=1, thread_name_prefix="sample-analysis")
        self._pending: set[int] = set()
        self._lock = threading.Lock()

    def bind_database(self, db_path: str | Path | None) -> None:
        """Use *db_path* for stored analysis; ``None`` turns storage off."""
        self._db_path = str(db_path) if db_path is not None else None

    def load(self, path: Path) -> WaveformData:
        requested = Path(path)
        if self._db_path is None:
            return self._fallback.load(requested)
        with Db(self._db_path) as db:
            sample_id = resolve_sample_id(db, requested)
            if sample_id is None:
                return self._fallback.load(requested)
            size_bytes, mtime_ns = _file_identity(requested)
            row = SampleAnalysisRepo(db).get_valid(
                sample_id,
                size_bytes=size_bytes,
                mtime_ns=mtime_ns,
                analysis_version=ANALYSIS_VERSION,
            )
        if row is not None:
            return WaveformData(
                path=requested,
                duration_seconds=float(row["duration_seconds"]),
                bins=_fit(decode_level(row["peak_levels"], row["peaks"]), self._bucket_count),
            )

        audio = self._decoder(requested)
        pyramid = compute_peak_pyramid(audio.samples)
        self._store_later(sample_id, requested, audio)
        # Match what the stored row will return on the next focus.
        peak_levels, blob = encode_pyramid(pyramid)
        return WaveformData(
            path=requested,
            duration_seconds=audio.duration_seconds,
            bins=_fit(decode_level(peak_levels, blob), self._bucket_count),
        )

    def get_waveform(self, path: Path, bins: int) -> WaveformData:
        if bins <= 0:
            raise ValueError("bins must be greater than zero")
        base = self.load(path)
        if len(base.bins) == bins:
            return base
        return WaveformData(base.path, base.duration_seconds, resample_bins(base.bins, bins))

    def flush(self, timeout: float | None = None) -> None:
        """Wait for queued stores (tests and shutdown)."""
        self._writer.submit(lambda: None).result(timeout)

    def close(self) -> None:
        self._writer.shutdown(wait=False, cancel_futures=True)

    def _store_later(self, sample_id: int, path: Path, audio: DecodedAudio) -> None:
        with self._lock:
            if sample_id in self._pending:
                return
            self._pending.add(sample_id)
        db_path = self._db_path

        def store() -> None:
            try:
                if db_path is not None:
                    with Db(db_path) as db:
                        store_analysis(db, sample_id, path, audio)
            except Exception:  # noqa: BLE001 - storage is an optimisation; retry on next focus
                pass
            finally:
                with self._lock:
                    self._pending.discard(sample_id)

        try:
            self._writer.submit(store)
        except RuntimeError:  # shut down
            with self._lock:
                self._pending.discard(sample_id)


def _fit(finest, bucket_count: int):
    """The finest level, re-binned only when it is finer than *bucket_count*."""
    if len(finest) <= bucket_count:
        return finest
    return resample_bins(finest, bucket_count)


def backfill_analysis(
    db: Db,
    *,
    library_root_id: int | None = None,
    force: bool = False,
    decoder: Callable[[Path], DecodedAudio] = decode,
    cancel: threading.Event | None = None,
    pause_seconds: float = 0.0,
    on_progress: Callable[[int, int], None] | None = None,
) -> BackfillResult:
    """Analyse indexed samples lacking a valid row (or all, with *force*).

    *pause_seconds* sleeps between files so a background backfill leaves the
    GIL to the audio callback. *on_progress* receives ``(done, total)``.
    """
    repo = SampleAnalysisRepo(db)
    candidates = repo.list_candidates(library_root_id, ANALYSIS_VERSION)
    analyzed = skipped = failed = 0
    total = len(candidates)
    for index, row in enumerate(candidates, start=1):
        if cancel is not None and cancel.is_set():
            return BackfillResult(analyzed, skipped, failed, cancelled=True)
        path = Path(row["root_path"]) / row["rel_path"]
        try:
            size_bytes, mtime_ns = _file_identity(path)
        except OSError:
            failed += 1
            continue
        current = (
            row["analyzed_size"] == size_bytes and row["analyzed_mtime_ns"] == mtime_ns
        )
        if current and not force:
            skipped += 1
        else:
            try:
                store_analysis(db, int(row["sample_id"]), path, decoder(path))
                analyzed += 1
            except Exception:  # noqa: BLE001 - one bad file never stops the pass
                failed += 1
            if pause_seconds:
                time.sleep(pause_seconds)
        if on_progress is not None:
            on_progress(index, total)
    return BackfillResult(analyzed, skipped, failed)

