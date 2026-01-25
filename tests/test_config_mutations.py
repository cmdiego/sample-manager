"""Tests for config mutation helpers."""

import pytest
from pathlib import Path
from sample_manager import config


def test_parse_config_value_bool():
    """Test parsing boolean values."""
    assert config.parse_config_value("true") is True
    assert config.parse_config_value("false") is False
    assert config.parse_config_value("True") is True
    assert config.parse_config_value("FALSE") is False


def test_parse_config_value_null():
    """Test parsing null."""
    assert config.parse_config_value("null") is None
    assert config.parse_config_value("NULL") is None


def test_parse_config_value_int():
    """Test parsing integers."""
    assert config.parse_config_value("42") == 42
    assert config.parse_config_value("-10") == -10


def test_parse_config_value_float():
    """Test parsing floats."""
    assert config.parse_config_value("3.14") == 3.14
    assert config.parse_config_value("-0.5") == -0.5


def test_parse_config_value_list():
    """Test parsing JSON lists."""
    result = config.parse_config_value('["a", "b", "c"]')
    assert result == ["a", "b", "c"]


def test_parse_config_value_string_fallback():
    """Test that unparseable values become strings."""
    assert config.parse_config_value("just a string") == "just a string"
    assert config.parse_config_value("copy") == "copy"


def test_set_nested_key_top_level():
    """Test setting top-level key."""
    cfg = {}
    config.set_nested_key(cfg, "db_path", "/new/path")
    assert cfg["db_path"] == "/new/path"


def test_set_nested_key_nested():
    """Test setting nested key with dot notation."""
    cfg = {"defaults": {}}
    config.set_nested_key(cfg, "defaults.export_mode", "symlink")
    assert cfg["defaults"]["export_mode"] == "symlink"


def test_set_nested_key_creates_defaults():
    """Test that defaults section is auto-created."""
    cfg = {}
    config.set_nested_key(cfg, "defaults.confirmations", False)
    assert "defaults" in cfg
    assert cfg["defaults"]["confirmations"] is False


def test_set_nested_key_unknown_section():
    """Test that unknown sections raise error."""
    cfg = {}
    with pytest.raises(ValueError, match="Unknown config section"):
        config.set_nested_key(cfg, "unknown.key", "value")


def test_add_library_root_new(sample_library_root):
    """Test adding new library root."""
    cfg = {"library_roots": []}
    
    updated, msg = config.add_library_root(cfg, str(sample_library_root))
    
    # Check if the path is in the roots (might be normalized differently)
    assert len(updated["library_roots"]) == 1
    assert "Added library root" in msg


def test_add_library_root_idempotent(sample_library_root):
    """Test that adding same root twice is idempotent."""
    cfg = {"library_roots": [str(sample_library_root.resolve())]}
    
    updated, msg = config.add_library_root(cfg, str(sample_library_root))
    
    assert "already configured" in msg


def test_add_library_root_with_default(sample_library_root):
    """Test adding root and setting as default."""
    cfg = {"library_roots": [], "default_library_root": None}
    
    updated, msg = config.add_library_root(
        cfg, str(sample_library_root), set_as_default=True
    )
    
    assert updated["default_library_root"] is not None
    assert "default" in msg.lower()


def test_add_library_root_invalid_path():
    """Test that adding non-existent path raises error."""
    cfg = {"library_roots": []}
    
    with pytest.raises(ValueError, match="does not exist"):
        config.add_library_root(cfg, "/does/not/exist")


def test_remove_library_root(sample_library_root):
    """Test removing library root."""
    normalized = str(sample_library_root.resolve())
    cfg = {"library_roots": [normalized], "default_library_root": None}
    
    updated, msg = config.remove_library_root(cfg, str(sample_library_root))
    
    assert len(updated["library_roots"]) == 0
    assert "Removed" in msg


def test_remove_library_root_clears_default(sample_library_root):
    """Test that removing root clears default if matched."""
    normalized = str(sample_library_root.resolve())
    cfg = {
        "library_roots": [normalized],
        "default_library_root": normalized
    }
    
    updated, msg = config.remove_library_root(cfg, str(sample_library_root))
    
    assert updated["default_library_root"] is None
    assert "cleared default" in msg.lower()


def test_set_default_library_root(sample_library_root):
    """Test setting default library root."""
    normalized = str(sample_library_root.resolve())
    cfg = {
        "library_roots": [normalized],
        "default_library_root": None
    }
    
    updated, msg = config.set_default_library_root(cfg, str(sample_library_root))
    
    assert updated["default_library_root"] == normalized


def test_set_default_library_root_not_in_roots():
    """Test that setting default for unconfigured root raises error."""
    cfg = {"library_roots": [], "default_library_root": None}
    
    with pytest.raises(ValueError, match="not in library_roots"):
        config.set_default_library_root(cfg, "/some/path")
