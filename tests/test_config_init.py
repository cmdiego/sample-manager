"""Tests for config initialization and templates."""

import pytest
from pathlib import Path
from sample_manager import config


def test_get_default_template():
    """Test default config template structure."""
    template = config.get_default_config_template()
    
    assert "db_path" in template
    assert "library_roots" in template
    assert "default_library_root" in template
    assert "defaults" in template
    
    defaults = template["defaults"]
    assert defaults["export_mode"] == "copy"
    assert defaults["collision_policy"] == "suffix"
    assert defaults["on_violation"] == "autofix"
    assert defaults["preview_format"] == "table"
    assert defaults["confirmations"] is True


def test_ensure_config_creates_directory(tmp_home, monkeypatch):
    """Test that ensure_config_exists creates directory."""
    # Mock get_config_path to return tmp location
    config_path = tmp_home / ".sample_manager" / "config.yaml"
    monkeypatch.setattr(config, "DEFAULT_CONFIG_PATH", config_path)
    
    assert not config_path.exists()
    
    result_path, created = config.ensure_config_exists()
    
    assert created is True
    assert result_path.exists()
    assert result_path.parent.is_dir()


def test_ensure_config_creates_yaml_with_template(tmp_home, monkeypatch):
    """Test that config.yaml is created with expected keys."""
    config_path = tmp_home / ".sample_manager" / "config.yaml"
    monkeypatch.setattr(config, "DEFAULT_CONFIG_PATH", config_path)
    
    config.ensure_config_exists()
    
    loaded = config.load_config(config_path)
    
    assert "db_path" in loaded
    assert "library_roots" in loaded
    assert isinstance(loaded["library_roots"], list)
    assert "defaults" in loaded


def test_ensure_config_idempotent(tmp_home, monkeypatch):
    """Test that running ensure_config_exists twice doesn't overwrite."""
    config_path = tmp_home / ".sample_manager" / "config.yaml"
    monkeypatch.setattr(config, "DEFAULT_CONFIG_PATH", config_path)
    
    # First call
    _, created1 = config.ensure_config_exists()
    assert created1 is True
    
    # Modify config
    cfg = config.load_config(config_path)
    cfg["library_roots"] = ["/custom/path"]
    config.save_config(cfg, config_path)
    
    # Second call
    _, created2 = config.ensure_config_exists()
    assert created2 is False
    
    # Verify custom value preserved
    cfg2 = config.load_config(config_path)
    assert cfg2["library_roots"] == ["/custom/path"]


def test_load_and_save_roundtrip(tmp_path):
    """Test loading and saving preserves structure."""
    config_path = tmp_path / "config.yaml"
    
    original = config.get_default_config_template()
    original["library_roots"] = ["/path/one", "/path/two"]
    
    config.save_config(original, config_path)
    loaded = config.load_config(config_path)
    
    assert loaded == original
