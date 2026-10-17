"""Tests for config validation logic."""

import pytest
from pathlib import Path
from sample_manager import config
from sample_manager.exit_codes import ERROR_CONFIG_VALIDATION


def test_normalize_path_expands_tilde(tmp_home, monkeypatch):
    """Test that normalize_path expands ~."""
    result = config.normalize_path("~/test/path")
    assert "~" not in str(result)
    assert result.is_absolute()


def test_normalize_path_expands_env_vars(monkeypatch, tmp_path):
    """Test that normalize_path expands environment variables."""
    monkeypatch.setenv("TEST_VAR", str(tmp_path / "custom"))
    result = config.normalize_path("$TEST_VAR/subdir")
    assert result == (tmp_path / "custom" / "subdir").resolve()


def test_normalize_config_expands_db_path(tmp_home, monkeypatch):
    """Test that normalize_config expands db_path."""
    cfg = {"db_path": "~/.sample_manager/db.sqlite3"}
    normalized = config.normalize_config(cfg)
    
    assert "~" not in normalized["db_path"]
    assert Path(normalized["db_path"]).is_absolute()


def test_normalize_config_expands_library_roots(tmp_home, monkeypatch):
    """Test that normalize_config expands library_roots."""
    cfg = {"library_roots": ["~/music", "~/samples"]}
    normalized = config.normalize_config(cfg)
    
    for root in normalized["library_roots"]:
        assert "~" not in root
        assert Path(root).is_absolute()


def test_validate_config_missing_library_root():
    """Test validation with non-existent library root."""
    cfg = {
        "db_path": "~/.sample_manager/db.sqlite3",
        "library_roots": ["/does/not/exist"],
        "default_library_root": None
    }
    
    result = config.validate_config(cfg, strict=False)
    
    assert not result.ok
    assert len(result.errors) > 0
    assert any("does not exist" in err for err in result.errors)


def test_validate_config_valid_library_root(sample_library_root):
    """Test validation with valid library root."""
    cfg = {
        "db_path": "~/.sample_manager/db.sqlite3",
        "library_roots": [str(sample_library_root)],
        "default_library_root": None
    }
    
    result = config.validate_config(cfg, strict=False)
    
    # Might have warnings about db_path parent, but should have no errors
    assert len(result.errors) == 0


def test_validate_config_db_path_parent_warning(tmp_path):
    """Test that missing db_path parent produces warning."""
    cfg = {
        "db_path": str(tmp_path / "nonexistent" / "db.sqlite3"),
        "library_roots": [],
        "default_library_root": None
    }
    
    result = config.validate_config(cfg, strict=False)
    
    assert any("parent directory" in warn for warn in result.warnings)


def test_validate_config_default_root_not_in_roots(sample_library_root, tmp_path):
    """Test warning when default_library_root not in library_roots."""
    other_root = tmp_path / "other"
    other_root.mkdir()
    
    cfg = {
        "db_path": "~/.sample_manager/db.sqlite3",
        "library_roots": [str(sample_library_root)],
        "default_library_root": str(other_root)
    }
    
    result = config.validate_config(cfg, strict=False)
    
    assert any("not in library_roots" in warn for warn in result.warnings)


def test_validate_config_strict_mode_exit_code(tmp_path):
    """Test that strict mode returns correct exit code on warnings."""
    cfg = {
        "db_path": str(tmp_path / "nonexistent" / "db.sqlite3"),
        "library_roots": [],
        "default_library_root": None
    }
    
    # Non-strict should succeed despite warnings
    result_normal = config.validate_config(cfg, strict=False)
    assert result_normal.exit_code == 0
    
    # Strict should fail on warnings
    result_strict = config.validate_config(cfg, strict=True)
    assert result_strict.exit_code == ERROR_CONFIG_VALIDATION
    assert not result_strict.ok


def test_validate_config_checked_list():
    """Test that validation result includes checked items."""
    cfg = config.get_default_config_template()
    
    result = config.validate_config(cfg)
    
    assert "db_path" in result.checked
    assert "library_roots" in result.checked
    assert "default_library_root" in result.checked


def test_validate_config_json_envelope(sample_library_root):
    """Test JSON envelope structure."""
    cfg = {
        "db_path": "~/.sample_manager/db.sqlite3",
        "library_roots": [str(sample_library_root)],
        "default_library_root": None
    }
    
    result = config.validate_config(cfg)
    json_output = result.to_json()
    
    assert "ok" in json_output
    assert "exit_code" in json_output
    assert "errors" in json_output
    assert "warnings" in json_output
    assert "checked" in json_output
    assert "effective_config" in json_output
    
    assert isinstance(json_output["ok"], bool)
    assert isinstance(json_output["exit_code"], int)
    assert isinstance(json_output["errors"], list)
    assert isinstance(json_output["warnings"], list)
