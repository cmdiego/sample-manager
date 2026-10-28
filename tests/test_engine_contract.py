"""Run the same player lifecycle against Python and optional native NullBackends."""

import time
import pytest
from sample_manager.audio.factory import build_player
from sample_manager.audio.player import PlaybackStatus


def wait_until(predicate, seconds=3):
    """Bound asynchronous waits without tying correctness to scheduling sleeps."""
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.002)
    assert predicate(), "engine did not reach the expected observable state"


@pytest.mark.parametrize("engine", ["python", "native"])
def test_player_null_backend_play_pause_seek_resume_complete(engine, tmp_path):
    """Both engines preserve source-frame positions and completion semantics."""
    if engine == "native":
        pytest.importorskip("sample_manager_engine")
    np = pytest.importorskip("numpy")
    sf = pytest.importorskip("soundfile")
    path = tmp_path / "loop.wav"
    sf.write(path, np.full((24000, 1), 0.25), 24000)
    player = build_player(engine=engine, backend="null", buffer_frames=256)
    try:
        player.play(path)
        wait_until(lambda: player.snapshot().position_seconds > 0.05)
        player.pause()
        paused = player.snapshot()
        assert paused.status is PlaybackStatus.PAUSED
        assert 0 < paused.position_seconds < 1
        player.seek(0.5)
        assert player.snapshot().position_seconds == pytest.approx(0.5)
        player.play(path)
        wait_until(lambda: player.snapshot().position_seconds > 0.55)
        stats = player.engine_stats()
        assert stats["engine"] == engine and stats["device_rate"] == 48000
        wait_until(lambda: player.snapshot().status is PlaybackStatus.IDLE)
        assert player.snapshot().position_seconds == 0
    finally:
        player.close()
        player.close()


@pytest.mark.parametrize("engine", ["python", "native"])
def test_same_path_replacement_is_not_reused(engine, tmp_path):
    """Loaded-source reuse must also respect file identity after rescan/replacement."""
    if engine == "native":
        pytest.importorskip("sample_manager_engine")
    np = pytest.importorskip("numpy")
    sf = pytest.importorskip("soundfile")
    path = tmp_path / "sample.wav"
    sf.write(path, np.ones((4800, 1)) * 0.2, 48000)
    player = build_player(engine=engine, backend="null", buffer_frames=256)
    try:
        player.play(path)
        wait_until(lambda: player.snapshot().duration_seconds == 0.1)
        player.pause()
        sf.write(path, np.ones((9600, 1)) * 0.5, 48000)
        player.play_from_start(path)
        wait_until(lambda: player.snapshot().duration_seconds == 0.2)
        assert player.snapshot().status is not PlaybackStatus.ERROR
    finally:
        player.close()


def test_auto_fallback_and_explicit_native_error(monkeypatch):
    """A missing/broken native extension never breaks Python-only installations."""
    def unavailable(**kwargs):
        """Model an unusable wheel/device without opening real audio hardware."""
        raise ImportError("extension missing")
    monkeypatch.setattr("sample_manager.audio.native.build_native_player", unavailable)
    player = build_player(engine="auto", backend="null")
    try:
        assert player.engine_stats()["engine"] == "python"
        assert "extension missing" in player.engine_stats()["warning"]
    finally:
        player.close()
    with pytest.raises(RuntimeError, match="Native engine unavailable"):
        build_player(engine="native", backend="null")


def test_native_decoder_error_is_reported(tmp_path):
    """Native decode failures surface through the same player ERROR snapshot."""
    pytest.importorskip("sample_manager_engine")
    path = tmp_path / "broken.wav"
    path.write_bytes(b"broken")
    player = build_player(engine="native", backend="null")
    try:
        player.play(path)
        wait_until(lambda: player.snapshot().status is PlaybackStatus.ERROR)
        assert player.snapshot().error
    finally:
        player.close()


@pytest.mark.parametrize("extension", ["wav", "aiff", "flac", "ogg", "mp3"])
def test_native_formats_and_python_pcm_bridge(extension, tmp_path):
    """Native formats and a Python-only OGG source all reach the native callback."""
    pytest.importorskip("sample_manager_engine")
    np = pytest.importorskip("numpy")
    sf = pytest.importorskip("soundfile")
    path = tmp_path / ("tone." + extension)
    try:
        sf.write(path, np.sin(np.arange(9600) / 20)[:, None] * 0.25, 48000)
    except (ValueError, RuntimeError):
        pytest.skip("Installed libsndfile cannot encode this test format")
    player = build_player(engine="native", backend="null", buffer_frames=256)
    try:
        player.play(path)
        wait_until(lambda: player.snapshot().status is PlaybackStatus.ERROR or
                   player.engine_stats().get("last_first_render_at") is not None)
        assert player.snapshot().status is not PlaybackStatus.ERROR, player.snapshot().error
        assert player.engine_stats()["engine"] == "native"
        if extension == "mp3":
            assert player.snapshot().duration_seconds == pytest.approx(0.2, abs=1 / 48000)
    finally:
        player.close()
