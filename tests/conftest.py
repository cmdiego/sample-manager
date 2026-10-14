"""Shared pytest fixtures for Sample Manager tests."""

import pytest
from pathlib import Path

from sample_manager.db import Db
from sample_manager.migrations import apply_migrations


@pytest.fixture
def tmp_home(tmp_path, monkeypatch):
    """Create temporary HOME directory for testing."""
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    return home


@pytest.fixture
def tmp_config_dir(tmp_home):
    """
    Create ~/.sample_manager directory in tmp home.
    Returns the config directory path.
    """
    config_dir = tmp_home / ".sample_manager"
    config_dir.mkdir(parents=True)
    return config_dir


@pytest.fixture
def sample_config_path(tmp_config_dir):
    """Returns path where config.yaml should be."""
    return tmp_config_dir / "config.yaml"


@pytest.fixture
def sample_library_root(tmp_path):
    """Create a sample library root directory."""
    lib_root = tmp_path / "sample_library"
    lib_root.mkdir()
    # Create some dummy sample files
    (lib_root / "kick.wav").touch()
    (lib_root / "snare.wav").touch()
    return lib_root


@pytest.fixture
def cli_runner():
    """Typer CliRunner for testing CLI commands."""
    from typer.testing import CliRunner
    return CliRunner()


@pytest.fixture
def write_sine_wav():
    """Return a helper that writes a PCM sine-tone WAV using only the stdlib.

    Dependency-free (no numpy/soundfile needed to *generate* fixtures), keeping
    the audio test suite hermetic. Returns the written Path.
    """
    import math
    import struct
    import wave

    def _write(
        path,
        *,
        freq=440.0,
        sample_rate=44100,
        seconds=0.1,
        amplitude=0.5,
        channels=1,
    ):
        path = Path(path)
        n = int(sample_rate * seconds)
        with wave.open(str(path), "wb") as w:
            w.setnchannels(channels)
            w.setsampwidth(2)  # 16-bit
            w.setframerate(sample_rate)
            frames = bytearray()
            for i in range(n):
                val = int(amplitude * 32767 * math.sin(2 * math.pi * freq * i / sample_rate))
                for _ in range(channels):
                    frames += struct.pack("<h", val)
            w.writeframes(bytes(frames))
        return path

    return _write


@pytest.fixture
def db(tmp_path):
    """Fresh SQLite DB with Phase 2 schema applied (Migration 0001).

    Yields a connected Db instance; closes on teardown.
    """
    db_path = tmp_path / "test.sqlite3"
    database = Db(db_path)
    database.connect()
    apply_migrations(database)
    yield database
    database.close()
