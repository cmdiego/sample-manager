"""Milestone 2: peak pyramids, loudness, and DB-backed waveforms."""

import math
import os
import threading

import pytest

np = pytest.importorskip("numpy")
sf = pytest.importorskip("soundfile")

from sample_manager.audio.analysis import ANALYSIS_VERSION
from sample_manager.audio.decode import decode
from sample_manager.audio.loudness import _high_pass, _high_shelf, measure_loudness
from sample_manager.audio.peaks import (
    compute_peak_pyramid,
    decode_pyramid,
    encode_pyramid,
)
from sample_manager.audio.waveform import WaveformBin
from sample_manager.repos.sample_analysis_repo import SampleAnalysisRepo
from sample_manager.scanner import scan_library
from sample_manager.services.sample_analysis import (
    StoredWaveformService,
    backfill_analysis,
    resolve_sample_id,
)


def _sine(freq, seconds, rate=48000, amplitude=1.0, channels=1):
    t = np.arange(int(rate * seconds)) / rate
    tone = (amplitude * np.sin(2 * math.pi * freq * t)).astype("float32")
    return np.repeat(tone[:, None], channels, axis=1)


# -- loudness ------------------------------------------------------------------


def _iir(x, b, a):
    y = np.zeros_like(x)
    x1 = x2 = y1 = y2 = 0.0
    for index, value in enumerate(x.tolist()):
        out = b[0] * value + b[1] * x1 + b[2] * x2 - a[1] * y1 - a[2] * y2
        x2, x1, y2, y1 = x1, value, y1, out
        y[index] = out
    return y


def _reference_lufs(pcm, rate):
    """Time-domain BS.1770 with per-sample biquads, as the standard specifies."""
    filtered = []
    for channel in range(pcm.shape[1]):
        shelved = _iir(pcm[:, channel].astype("float64"), *_high_shelf(rate))
        filtered.append(_iir(shelved, *_high_pass(rate)))
    weighted = np.stack(filtered, axis=1)
    block, hop = int(0.4 * rate), int(0.1 * rate)
    energy = np.array([
        (weighted[start:start + block] ** 2).mean(axis=0).sum()
        for start in range(0, weighted.shape[0] - block + 1, hop)
    ])
    energy = energy[-0.691 + 10 * np.log10(energy) > -70]
    gate = -0.691 + 10 * np.log10(energy.mean()) - 10
    energy = energy[-0.691 + 10 * np.log10(energy) > gate]
    return -0.691 + 10 * np.log10(energy.mean())


def test_khz_sine_at_full_scale_reads_minus_three_lufs():
    # BS.1770's calibration point: 997 Hz, 0 dBFS, one channel → −3.01 LUFS.
    assert measure_loudness(_sine(997, 3), 48000).integrated_lufs == pytest.approx(-3.01, abs=0.01)


@pytest.mark.parametrize("rate", [44100, 48000, 96000])
def test_matches_time_domain_reference_including_sub_bass(rate):
    rng = np.random.default_rng(7)
    # Brown noise is mostly below the 38 Hz high-pass: the case that a
    # per-block spectral shortcut gets wrong by several LU.
    brown = np.cumsum(rng.standard_normal((int(rate * 1.5), 2)), axis=0) * 0.002
    brown = (brown - brown.mean(axis=0)).astype("float32")

    assert measure_loudness(brown, rate).integrated_lufs == pytest.approx(
        _reference_lufs(brown, rate), abs=0.01
    )


def test_identical_stereo_channels_read_three_lu_louder_than_mono():
    mono = measure_loudness(_sine(440, 2, amplitude=0.25), 48000).integrated_lufs
    stereo = measure_loudness(_sine(440, 2, amplitude=0.25, channels=2), 48000).integrated_lufs
    assert stereo - mono == pytest.approx(10 * math.log10(2), abs=0.01)


def test_silence_has_no_loudness():
    result = measure_loudness(np.zeros((48000, 2), dtype="float32"), 48000)
    assert result.integrated_lufs is None and result.short_term_max_lufs is None


def test_one_shots_shorter_than_a_block_report_ungated_loudness():
    result = measure_loudness(_sine(997, 0.2), 48000)
    assert result.integrated_lufs == pytest.approx(-3.01, abs=0.1)
    assert result.short_term_max_lufs == result.integrated_lufs


def test_short_term_max_tracks_the_loudest_three_seconds():
    quiet = _sine(997, 6, amplitude=0.01)
    loud = _sine(997, 3, amplitude=1.0)
    result = measure_loudness(np.concatenate([quiet, loud]), 48000)
    assert result.short_term_max_lufs == pytest.approx(-3.01, abs=0.05)
    assert result.integrated_lufs < result.short_term_max_lufs + 0.01


# -- peaks ---------------------------------------------------------------------


def test_pyramid_levels_are_finest_first_and_consistent():
    samples = _sine(3, 1, rate=8192, amplitude=0.8, channels=2)
    pyramid = compute_peak_pyramid(samples)

    assert [len(level) for level in pyramid] == [4096, 1024, 256]
    fine, coarse = pyramid[0], pyramid[1]
    assert coarse[0].maximum == max(b.maximum for b in fine[:4])
    assert coarse[0].minimum == min(b.minimum for b in fine[:4])


def test_short_files_get_one_bin_per_frame():
    pyramid = compute_peak_pyramid(np.array([[0.1], [-0.2], [0.3]], dtype="float32"))
    assert [len(level) for level in pyramid] == [3, 3, 3]


def test_encoding_round_trips_and_rounds_away_from_zero():
    pyramid = (
        (WaveformBin(-0.5, 0.5), WaveformBin(-0.001, 0.002), WaveformBin(0.0, 0.0)),
        (WaveformBin(-0.5, 0.5),),
    )
    levels, blob = encode_pyramid(pyramid)
    decoded = decode_pyramid(levels, blob)

    assert levels == "3,1" and len(blob) == 8
    assert decoded[0][0].minimum <= -0.5 and decoded[0][0].maximum >= 0.5
    assert decoded[0][0].maximum - 0.5 < 1 / 127
    # Quiet but non-silent material still draws one step; silence stays flat.
    assert decoded[0][1].minimum == pytest.approx(-1 / 127)
    assert decoded[0][1].maximum == pytest.approx(1 / 127)
    assert decoded[0][2] == WaveformBin(0.0, 0.0)


def test_decoding_rejects_a_blob_of_the_wrong_size():
    with pytest.raises(ValueError):
        decode_pyramid("4", b"\x00" * 6)


# -- storage -------------------------------------------------------------------


@pytest.fixture
def library(tmp_path):
    root = tmp_path / "lib"
    (root / "drums").mkdir(parents=True)
    sf.write(root / "drums" / "kick.wav", _sine(55, 0.5, amplitude=0.9), 48000)
    sf.write(root / "drums" / "hat.wav", _sine(8000, 0.2, amplitude=0.3, channels=2), 48000)
    return root


@pytest.fixture
def indexed(db, library):
    result = scan_library(db, library)
    return result.library_root_id


def _sample_id(db, library, rel):
    return resolve_sample_id(db, library / rel)


def test_resolve_sample_id_maps_absolute_paths(db, library, indexed, tmp_path):
    assert _sample_id(db, library, "drums/kick.wav") is not None
    assert resolve_sample_id(db, tmp_path / "elsewhere.wav") is None


def test_backfill_stores_rows_and_skips_them_next_time(db, library, indexed):
    first = backfill_analysis(db, library_root_id=indexed)
    second = backfill_analysis(db, library_root_id=indexed)
    forced = backfill_analysis(db, library_root_id=indexed, force=True)

    assert (first.analyzed, first.skipped, first.failed) == (2, 0, 0)
    assert (second.analyzed, second.skipped) == (0, 2)
    assert forced.analyzed == 2

    kick = _sample_id(db, library, "drums/kick.wav")
    row = db.fetchone("SELECT * FROM sample_analysis WHERE sample_id = ?", (kick,))
    assert row["analysis_version"] == ANALYSIS_VERSION
    assert row["duration_seconds"] == pytest.approx(0.5)
    assert row["peak"] == pytest.approx(0.9, abs=1e-3)
    assert row["loudness_lufs"] is not None
    assert row["peak_levels"] == "4096,1024,256"


def test_changed_files_are_reanalysed(db, library, indexed):
    backfill_analysis(db, library_root_id=indexed)
    kick = library / "drums" / "kick.wav"
    sf.write(kick, _sine(55, 1.0, amplitude=0.5), 48000)
    stat = kick.stat()
    os.utime(kick, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000))

    result = backfill_analysis(db, library_root_id=indexed)

    assert (result.analyzed, result.skipped) == (1, 1)


def test_missing_and_corrupt_files_count_as_failures(db, library, indexed):
    (library / "drums" / "hat.wav").unlink()
    (library / "drums" / "kick.wav").write_bytes(b"RIFF broken")

    result = backfill_analysis(db, library_root_id=indexed)

    assert (result.analyzed, result.failed) == (0, 2)


def test_backfill_can_be_cancelled(db, indexed):
    cancel = threading.Event()
    cancel.set()
    result = backfill_analysis(db, library_root_id=indexed, cancel=cancel)
    assert result.cancelled and result.analyzed == 0


def test_rows_are_deleted_with_their_sample(db, library, indexed):
    backfill_analysis(db, library_root_id=indexed)
    db.execute("DELETE FROM sample")
    db.conn.commit()
    assert db.fetchval("SELECT COUNT(*) FROM sample_analysis") == 0


def test_get_valid_ignores_stale_identity_and_version(db, library, indexed):
    backfill_analysis(db, library_root_id=indexed)
    kick = _sample_id(db, library, "drums/kick.wav")
    stat = (library / "drums" / "kick.wav").stat()
    repo = SampleAnalysisRepo(db)
    current = dict(size_bytes=stat.st_size, mtime_ns=stat.st_mtime_ns)

    assert repo.get_valid(kick, **current, analysis_version=ANALYSIS_VERSION) is not None
    assert repo.get_valid(kick, **current, analysis_version=ANALYSIS_VERSION + 1) is None
    stale = dict(current, mtime_ns=current["mtime_ns"] + 1)
    assert repo.get_valid(kick, **stale, analysis_version=ANALYSIS_VERSION) is None


# -- StoredWaveformService -------------------------------------------------------


@pytest.fixture
def file_db(tmp_path, library):
    from sample_manager.db import Db
    from sample_manager.migrations import apply_migrations

    path = tmp_path / "library.sqlite3"
    with Db(path) as setup:
        apply_migrations(setup)
        scan_library(setup, library)
    return path


class CountingDecoder:
    def __init__(self) -> None:
        self.calls = []

    def __call__(self, path):
        self.calls.append(path)
        return decode(path)


def test_first_focus_computes_and_stores_then_reads_from_the_database(file_db, library):
    decoder = CountingDecoder()
    service = StoredWaveformService(decoder=decoder, db_path=file_db)
    kick = library / "drums" / "kick.wav"
    try:
        computed = service.load(kick)
        service.flush(5)
        stored = service.load(kick)
    finally:
        service.close()

    assert decoder.calls == [kick]
    assert len(stored.bins) == 4096
    assert stored.bins == computed.bins  # same quantised envelope both times
    assert stored.duration_seconds == pytest.approx(0.5)


def test_waveforms_reflect_changed_files(file_db, library):
    decoder = CountingDecoder()
    service = StoredWaveformService(decoder=decoder, db_path=file_db)
    kick = library / "drums" / "kick.wav"
    try:
        service.load(kick)
        service.flush(5)
        sf.write(kick, _sine(55, 1.0, amplitude=0.5), 48000)
        stat = kick.stat()
        os.utime(kick, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000))
        changed = service.load(kick)
    finally:
        service.close()

    assert len(decoder.calls) == 2
    assert changed.duration_seconds == pytest.approx(1.0)


def test_unindexed_files_and_unbound_service_use_the_v1_path(tmp_path, file_db):
    loose = tmp_path / "loose.wav"
    sf.write(loose, _sine(220, 0.3), 48000)
    for service in (
        StoredWaveformService(decoder=decode, db_path=file_db),
        StoredWaveformService(decoder=decode),
    ):
        try:
            data = service.load(loose)
            service.flush(5)
        finally:
            service.close()
        assert data.duration_seconds == pytest.approx(0.3)

    from sample_manager.db import Db

    with Db(file_db) as check:
        assert check.fetchval("SELECT COUNT(*) FROM sample_analysis") == 0


def test_get_waveform_rebins_stored_data(file_db, library):
    service = StoredWaveformService(decoder=decode, db_path=file_db)
    try:
        data = service.get_waveform(library / "drums" / "kick.wav", 300)
    finally:
        service.close()
    assert len(data.bins) == 300


# -- CLI -----------------------------------------------------------------------


@pytest.fixture
def cli_config(tmp_path, monkeypatch):
    import yaml

    from sample_manager import config as config_module

    config_dir = tmp_path / "cli_home" / ".sample_manager"
    config_dir.mkdir(parents=True)
    config_path = config_dir / "config.yaml"
    monkeypatch.setattr(config_module, "DEFAULT_CONFIG_PATH", config_path)
    monkeypatch.setattr(config_module, "DEFAULT_CONFIG_DIR", config_dir)
    db_path = tmp_path / "cli.sqlite3"
    config_path.write_text(yaml.safe_dump({
        "db_path": str(db_path),
        "library_roots": [],
        "default_library_root": None,
        "defaults": {
            "export_mode": "copy", "collision_policy": "suffix", "on_violation": "autofix",
            "preview_format": "table", "confirmations": True,
        },
    }))
    return db_path


def test_cli_scan_analyze_then_analyze_reports_up_to_date(cli_runner, cli_config, library):
    from sample_manager.cli import app

    scanned = cli_runner.invoke(app, ["scan", str(library), "--analyze"])
    again = cli_runner.invoke(app, ["analyze", str(library)])
    forced = cli_runner.invoke(app, ["analyze", "--force"])

    assert scanned.exit_code == 0, scanned.output
    assert "Analyzed 2 samples" in scanned.output
    assert "Analyzed 0 samples (up to date: 2, failed: 0)" in again.output
    assert "Analyzed 2 samples" in forced.output


def test_cli_analyze_rejects_unknown_roots(cli_runner, cli_config, tmp_path):
    from sample_manager.cli import app

    result = cli_runner.invoke(app, ["analyze", str(tmp_path)])
    assert result.exit_code == 2
    assert "not an indexed library root" in result.output


def test_replacement_during_decode_never_gets_a_valid_analysis(db, library, indexed):
    """Old PCM must not be labelled with the replacement's current stat."""
    kick = library / "drums/kick.wav"

    def replacing_decoder(path):
        """Return old data after replacing the on-disk file."""
        audio = decode(path)
        if path == kick:
            sf.write(path, _sine(110, 1.0), 48000)
        return audio

    result = backfill_analysis(db, library_root_id=indexed, decoder=replacing_decoder)
    assert result.failed == 1
    assert db.fetchval("SELECT COUNT(*) FROM sample_analysis") == 1


def test_cancel_during_decode_does_not_commit(db, library, indexed):
    """Cooperative cancellation is rechecked after expensive decode/analysis."""
    cancel = threading.Event()

    def cancelled_decoder(path):
        """Cancel while an executor job is inside decoding."""
        audio = decode(path)
        cancel.set()
        return audio

    backfill_analysis(db, library_root_id=indexed, decoder=cancelled_decoder, cancel=cancel)
    assert db.fetchval("SELECT COUNT(*) FROM sample_analysis") == 0


def test_deferred_writer_carries_decode_identity(file_db, library):
    """Replacing a file while its old PCM waits in the writer queue stays invalid."""
    release = threading.Event()
    service = StoredWaveformService(decoder=decode, db_path=file_db)
    kick = library / "drums/kick.wav"
    service._writer.submit(lambda: release.wait(5))
    try:
        service.load(kick)
        sf.write(kick, _sine(110, 1.0, amplitude=0.2), 48000)
        release.set()
        service.flush(5)
        from sample_manager.db import Db
        with Db(file_db) as db:
            sid = resolve_sample_id(db, kick)
            stat = kick.stat()
            assert SampleAnalysisRepo(db).get_valid(sid, size_bytes=stat.st_size,
                mtime_ns=stat.st_mtime_ns, analysis_version=ANALYSIS_VERSION) is None
    finally:
        release.set()
        service.close()


def test_pending_writer_pcm_is_bounded(file_db, library):
    """Fast focus changes cannot retain an unbounded queue of whole decoded files."""
    release = threading.Event()
    service = StoredWaveformService(decoder=decode, db_path=file_db)
    service._writer.submit(lambda: release.wait(5))
    try:
        for path in library.rglob("*.wav"):
            service.load(path)
        assert len(service._pending) <= 2
    finally:
        release.set()
        service.flush(5)
        service.close()
