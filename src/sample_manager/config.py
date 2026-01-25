"""Configuration management for Sample Manager.

Handles loading, validation, normalization, and mutation of config.yaml.
Per docs/02-persistence.md and user requirements.
"""

import os
import json
from pathlib import Path
from dataclasses import dataclass, asdict
from typing import Any

import yaml

from . import exit_codes

# Default locations
DEFAULT_CONFIG_DIR = Path.home() / ".sample_manager"
DEFAULT_CONFIG_PATH = DEFAULT_CONFIG_DIR / "config.yaml"


@dataclass
class ValidationResult:
    """Structured validation result with JSON envelope support."""
    ok: bool
    exit_code: int
    errors: list[str]
    warnings: list[str]
    checked: list[str]
    effective_config: dict
    
    def to_json(self) -> dict:
        """Convert to JSON envelope for --json output."""
        return {
            "ok": self.ok,
            "exit_code": self.exit_code,
            "errors": self.errors,
            "warnings": self.warnings,
            "checked": self.checked,
            "effective_config": self.effective_config
        }


def get_default_config_template() -> dict:
    """Return default config matching config.example.yaml."""
    return {
        "db_path": "~/.sample_manager/sample_manager.sqlite3",
        "library_roots": [],
        "default_library_root": None,
        "defaults": {
            "export_mode": "copy",
            "collision_policy": "suffix",
            "on_violation": "autofix",
            "preview_format": "table",
            "confirmations": True
        }
    }


def get_config_path() -> Path:
    """Get platform-aware config path."""
    return DEFAULT_CONFIG_PATH


def normalize_path(path_str: str) -> Path:
    """Expand ~ and env vars, resolve to absolute path."""
    expanded = os.path.expanduser(os.path.expandvars(path_str))
    return Path(expanded).resolve()


def ensure_config_exists() -> tuple[Path, bool]:
    """
    Create config dir + file if missing (idempotent).
    
    Returns:
        (config_path, created: bool) - Path and whether it was newly created
    """
    config_path = get_config_path()
    
    # Check if already exists
    if config_path.exists():
        return config_path, False
    
    # Create parent directory if needed
    config_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Write default template
    template = get_default_config_template()
    save_config(template, config_path)
    
    return config_path, True


def load_config(config_path: Path | None = None) -> dict:
    """Load and parse YAML config."""
    if config_path is None:
        config_path = get_config_path()
    
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)


def save_config(config: dict, config_path: Path | None = None) -> None:
    """Write config dict to YAML (for explicit mutations)."""
    if config_path is None:
        config_path = get_config_path()
    
    # Ensure parent directory exists
    config_path.parent.mkdir(parents=True, exist_ok=True)
    
    # Write with nice formatting
    with open(config_path, 'w') as f:
        yaml.safe_dump(
            config,
            f,
            default_flow_style=False,
            sort_keys=False,
            allow_unicode=True
        )


def normalize_config(config: dict) -> dict:
    """Expand paths and return normalized copy."""
    normalized = config.copy()
    
    # Normalize db_path
    if "db_path" in normalized:
        normalized["db_path"] = str(normalize_path(normalized["db_path"]))
    
    # Normalize library_roots
    if "library_roots" in normalized:
        normalized["library_roots"] = [
            str(normalize_path(p)) for p in normalized["library_roots"]
        ]
    
    # Normalize default_library_root
    if normalized.get("default_library_root"):
        normalized["default_library_root"] = str(
            normalize_path(normalized["default_library_root"])
        )
    
    # Preserve defaults as-is
    if "defaults" in config:
        normalized["defaults"] = config["defaults"].copy()
    
    return normalized


def validate_config(config: dict, strict: bool = False) -> ValidationResult:
    """
    Validate config paths and settings.
    
    Validation rules per docs/02-persistence.md §2.4:
    - db_path: parent directory should exist (WARN only, don't auto-create)
    - library_roots: each must exist and be a directory (ERROR)
    - default_library_root: must exist, be directory, match normalized root (WARN)
    
    Args:
        config: Config dict to validate
        strict: If True, warnings become errors and exit code != 0
    
    Returns:
        ValidationResult with structured validation info
    """
    normalized = normalize_config(config)
    errors = []
    warnings = []
    checked = []
    
    # 1. Validate db_path parent
    checked.append("db_path")
    if "db_path" in normalized:
        db_path = Path(normalized["db_path"])
        if not db_path.parent.exists():
            warnings.append(
                f"db_path parent directory does not exist: {db_path.parent}"
            )
    
    # 2. Validate library_roots
    checked.append("library_roots")
    valid_roots = []
    for root in normalized.get("library_roots", []):
        root_path = Path(root)
        if not root_path.exists():
            errors.append(f"library_root does not exist: {root}")
        elif not root_path.is_dir():
            errors.append(f"library_root is not a directory: {root}")
        else:
            valid_roots.append(root)
    
    # 3. Validate default_library_root
    checked.append("default_library_root")
    default_root = normalized.get("default_library_root")
    if default_root:
        default_path = Path(default_root)
        if not default_path.exists():
            warnings.append(
                f"default_library_root does not exist: {default_root}"
            )
        elif not default_path.is_dir():
            warnings.append(
                f"default_library_root is not a directory: {default_root}"
            )
        elif default_root not in valid_roots:
            warnings.append(
                f"default_library_root not in library_roots: {default_root}"
            )
    
    # Compute result
    ok = len(errors) == 0 and (not strict or len(warnings) == 0)
    exit_code = 0 if ok else exit_codes.ERROR_CONFIG_VALIDATION
    
    return ValidationResult(
        ok=ok,
        exit_code=exit_code,
        errors=errors,
        warnings=warnings,
        checked=checked,
        effective_config=normalized
    )


def parse_config_value(value_str: str) -> Any:
    """
    Smart parse: try bool/int/float/null/JSON list, fallback to string.
    Per user requirement: parse from string with safe fallback.
    """
    # Handle booleans
    if value_str.lower() in ("true", "false"):
        return value_str.lower() == "true"
    
    # Handle null
    if value_str.lower() == "null":
        return None
    
    # Try int
    try:
        return int(value_str)
    except ValueError:
        pass
    
    # Try float
    try:
        return float(value_str)
    except ValueError:
        pass
    
    # Try JSON (for lists/objects)
    try:
        return json.loads(value_str)
    except (json.JSONDecodeError, ValueError):
        pass
    
    # Fallback: string
    return value_str


def set_nested_key(config: dict, key_path: str, value: Any) -> None:
    """
    Set value at dot-separated key path (e.g., "defaults.export_mode").
    Creates intermediate dicts for known top-level keys like "defaults".
    Modifies config in-place.
    """
    parts = key_path.split(".")
    
    # Navigate to parent
    current = config
    for part in parts[:-1]:
        if part not in current:
            # Only create known top-level keys
            if current is config and part in ("defaults",):
                current[part] = {}
            else:
                raise ValueError(f"Unknown config section: {part}")
        current = current[part]
    
    # Set final value
    current[parts[-1]] = value


def get_nested_key(config: dict, key_path: str) -> Any:
    """Get value at dot-separated key path."""
    parts = key_path.split(".")
    current = config
    for part in parts:
        current = current[part]
    return current


def add_library_root(
    config: dict,
    root_path: str,
    set_as_default: bool = False
) -> tuple[dict, str]:
    """
    Add library root to config (validates immediately).
    
    Returns:
        (updated_config, status_message)
    
    Raises:
        ValueError: If path invalid
    """
    # Normalize path
    normalized_path = str(normalize_path(root_path))
    root_pathobj = Path(normalized_path)
    
    # Validate exists and is directory
    if not root_pathobj.exists():
        raise ValueError(f"Path does not exist: {root_path}")
    if not root_pathobj.is_dir():
        raise ValueError(f"Path is not a directory: {root_path}")
    
    # Check if already present (idempotent)
    if normalized_path in config.get("library_roots", []):
        msg = f"Library root already configured: {normalized_path}"
        if set_as_default:
            config["default_library_root"] = normalized_path
            msg += " (set as default)"
        return config, msg
    
    # Add to library_roots
    if "library_roots" not in config:
        config["library_roots"] = []
    config["library_roots"].append(normalized_path)
    
    # Set as default if requested
    if set_as_default:
        config["default_library_root"] = normalized_path
        msg = f"Added and set as default: {normalized_path}"
    else:
        msg = f"Added library root: {normalized_path}"
    
    return config, msg


def remove_library_root(config: dict, root_path: str) -> tuple[dict, str]:
    """
    Remove library root from config (by normalized match).
    
    Returns:
        (updated_config, status_message)
    """
    normalized_path = str(normalize_path(root_path))
    
    if normalized_path not in config.get("library_roots", []):
        raise ValueError(f"Library root not found: {normalized_path}")
    
    config["library_roots"].remove(normalized_path)
    
    # Clear default if it matched
    if config.get("default_library_root") == normalized_path:
        config["default_library_root"] = None
        msg = f"Removed library root and cleared default: {normalized_path}"
    else:
        msg = f"Removed library root: {normalized_path}"
    
    return config, msg


def set_default_library_root(config: dict, root_path: str) -> tuple[dict, str]:
    """
    Set default library root (must exist in library_roots).
    
    Returns:
        (updated_config, status_message)
    """
    normalized_path = str(normalize_path(root_path))
    
    if normalized_path not in config.get("library_roots", []):
        raise ValueError(
            f"Path not in library_roots: {normalized_path}. "
            f"Add it first with 'sample config add-root {root_path}'"
        )
    
    config["default_library_root"] = normalized_path
    return config, f"Set default library root: {normalized_path}"
