"""Shared pytest fixtures for Sample Manager tests."""

import pytest
from pathlib import Path


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
