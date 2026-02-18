"""Profile loader for arrangement profiles and export profiles.

Loads profiles from YAML files in a configurable profiles directory.
Per docs/01-data-model.md (ArrangementProfile / ExportProfile),
docs/02-persistence.md (config + profile storage), and
docs/03-cli.md (profile list/show commands).

Phase 6: YAML-only loading. No DB schema changes.
"""

from __future__ import annotations

from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any

import yaml

from . import config as config_module


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class ProfileValidationError(ValueError):
    """Raised when a profile dict fails validation."""


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ARRANGEMENT_PROFILES_FILENAME = "arrangement_profiles.yaml"
EXPORT_PROFILES_FILENAME = "export_profiles.yaml"

VALID_LAYOUT_MODES = {"monolithic", "hierarchical"}
VALID_COLLISION_POLICIES = {"fail", "suffix", "dedupe_hash"}
VALID_CASE_POLICIES = {"preserve", "lower", "upper"}
VALID_PATH_SEP_POLICIES = {"os", "posix"}
VALID_ON_VIOLATION = {"autofix", "fail"}


# ---------------------------------------------------------------------------
# Example / starter content
# ---------------------------------------------------------------------------

EXAMPLE_ARRANGEMENT_PROFILES_YAML = """\
# Arrangement Profiles
# Each entry defines how samples are organized into output folders.
#
# Required fields: name, layout_mode, naming_template, collision_policy
# Optional fields: description, layout_rules, selection_defaults
#
# Example:
# - name: "default-monolithic"
#   description: "Flat bucket layout for hardware samplers"
#   layout_mode: "monolithic"
#   layout_rules:
#     category_map:
#       kick: "KICKS"
#       snare: "SNARES"
#       hat: "HATS"
#       clap: "CLAPS"
#       perc: "PERC"
#       fx: "FX"
#       vocal: "VOCALS"
#       bass: "BASS"
#       synth: "SYNTH"
#       loop: "LOOPS"
#   naming_template: "{category}/{name}"
#   collision_policy: "suffix"
#
# - name: "vendor-hierarchy"
#   description: "Nested by vendor and pack"
#   layout_mode: "hierarchical"
#   layout_rules:
#     folder_template: "{pack}/{category}"
#   naming_template: "{pack}/{category}/{name}"
#   collision_policy: "dedupe_hash"

[]
"""

EXAMPLE_EXPORT_PROFILES_YAML = """\
# Export Profiles
# Each entry defines hardware/filesystem constraints for export targets.
#
# Required fields: name, max_depth, max_filename_len, illegal_chars
# Optional fields: allowed_charset, replace_char, case_policy,
#                  path_sep_policy, on_violation
#
# Example:
# - name: "mpc-live"
#   max_depth: 3
#   max_filename_len: 64
#   illegal_chars: '<>:"/\\\\|?*'
#   replace_char: "_"
#   case_policy: "preserve"
#   path_sep_policy: "posix"
#   on_violation: "autofix"
#
# - name: "sp-404"
#   max_depth: 2
#   max_filename_len: 32
#   illegal_chars: '<>:"/\\\\|?*'
#   replace_char: "_"
#   case_policy: "upper"
#   path_sep_policy: "posix"
#   on_violation: "fail"

[]
"""


# ---------------------------------------------------------------------------
# ArrangementProfile dataclass
# ---------------------------------------------------------------------------

@dataclass
class ArrangementProfile:
    """An arrangement profile defining output layout and naming rules.

    Per docs/01-data-model.md: ArrangementProfile entity.
    """

    name: str
    layout_mode: str
    naming_template: str
    collision_policy: str
    description: str | None = None
    layout_rules: dict = field(default_factory=dict)
    selection_defaults: dict | None = None

    @classmethod
    def from_dict(cls, data: dict) -> ArrangementProfile:
        """Create an ArrangementProfile from a raw dict, with validation.

        Raises:
            ProfileValidationError: On missing/invalid fields.
        """
        if not isinstance(data, dict):
            raise ProfileValidationError(
                "Arrangement profile entry must be a mapping"
            )

        # Required fields
        name = data.get("name")
        if not name or not isinstance(name, str):
            raise ProfileValidationError(
                "Arrangement profile requires a non-empty 'name' string"
            )

        layout_mode = data.get("layout_mode")
        if not layout_mode or not isinstance(layout_mode, str):
            raise ProfileValidationError(
                f"Arrangement profile '{name}': "
                f"'layout_mode' is required (monolithic | hierarchical)"
            )
        if layout_mode not in VALID_LAYOUT_MODES:
            raise ProfileValidationError(
                f"Arrangement profile '{name}': "
                f"invalid layout_mode '{layout_mode}', "
                f"must be one of {sorted(VALID_LAYOUT_MODES)}"
            )

        naming_template = data.get("naming_template")
        if not naming_template or not isinstance(naming_template, str):
            raise ProfileValidationError(
                f"Arrangement profile '{name}': "
                f"'naming_template' is required"
            )

        collision_policy = data.get("collision_policy")
        if not collision_policy or not isinstance(collision_policy, str):
            raise ProfileValidationError(
                f"Arrangement profile '{name}': "
                f"'collision_policy' is required "
                f"(fail | suffix | dedupe_hash)"
            )
        if collision_policy not in VALID_COLLISION_POLICIES:
            raise ProfileValidationError(
                f"Arrangement profile '{name}': "
                f"invalid collision_policy '{collision_policy}', "
                f"must be one of {sorted(VALID_COLLISION_POLICIES)}"
            )

        # Optional fields
        description = data.get("description")
        if description is not None and not isinstance(description, str):
            raise ProfileValidationError(
                f"Arrangement profile '{name}': "
                f"'description' must be a string"
            )

        layout_rules = data.get("layout_rules", {})
        if not isinstance(layout_rules, dict):
            raise ProfileValidationError(
                f"Arrangement profile '{name}': "
                f"'layout_rules' must be a mapping"
            )

        selection_defaults = data.get("selection_defaults")
        if selection_defaults is not None and not isinstance(
            selection_defaults, dict
        ):
            raise ProfileValidationError(
                f"Arrangement profile '{name}': "
                f"'selection_defaults' must be a mapping"
            )

        return cls(
            name=name,
            layout_mode=layout_mode,
            naming_template=naming_template,
            collision_policy=collision_policy,
            description=description,
            layout_rules=layout_rules,
            selection_defaults=selection_defaults,
        )

    def to_dict(self) -> dict:
        """Serialize to a plain dict (for JSON output)."""
        return asdict(self)


# ---------------------------------------------------------------------------
# ExportProfile dataclass
# ---------------------------------------------------------------------------

@dataclass
class ExportProfile:
    """An export profile defining filesystem constraints for a target device.

    Per docs/01-data-model.md: ExportProfile entity.
    """

    name: str
    max_depth: int
    max_filename_len: int
    illegal_chars: str
    allowed_charset: str | None = None
    replace_char: str = "_"
    case_policy: str = "preserve"
    path_sep_policy: str = "os"
    on_violation: str = "autofix"

    @classmethod
    def from_dict(cls, data: dict) -> ExportProfile:
        """Create an ExportProfile from a raw dict, with validation.

        Raises:
            ProfileValidationError: On missing/invalid fields.
        """
        if not isinstance(data, dict):
            raise ProfileValidationError(
                "Export profile entry must be a mapping"
            )

        # Required fields
        name = data.get("name")
        if not name or not isinstance(name, str):
            raise ProfileValidationError(
                "Export profile requires a non-empty 'name' string"
            )

        max_depth = data.get("max_depth")
        if max_depth is None:
            raise ProfileValidationError(
                f"Export profile '{name}': 'max_depth' is required"
            )
        if not isinstance(max_depth, int) or isinstance(max_depth, bool):
            raise ProfileValidationError(
                f"Export profile '{name}': 'max_depth' must be an integer"
            )
        if max_depth < 1:
            raise ProfileValidationError(
                f"Export profile '{name}': "
                f"'max_depth' must be >= 1, got {max_depth}"
            )

        max_filename_len = data.get("max_filename_len")
        if max_filename_len is None:
            raise ProfileValidationError(
                f"Export profile '{name}': 'max_filename_len' is required"
            )
        if not isinstance(max_filename_len, int) or isinstance(
            max_filename_len, bool
        ):
            raise ProfileValidationError(
                f"Export profile '{name}': "
                f"'max_filename_len' must be an integer"
            )
        if max_filename_len < 1:
            raise ProfileValidationError(
                f"Export profile '{name}': "
                f"'max_filename_len' must be >= 1, got {max_filename_len}"
            )

        illegal_chars = data.get("illegal_chars")
        if illegal_chars is None:
            raise ProfileValidationError(
                f"Export profile '{name}': 'illegal_chars' is required"
            )
        if not isinstance(illegal_chars, str):
            raise ProfileValidationError(
                f"Export profile '{name}': 'illegal_chars' must be a string"
            )

        # Optional fields with defaults
        allowed_charset = data.get("allowed_charset")
        if allowed_charset is not None and not isinstance(
            allowed_charset, str
        ):
            raise ProfileValidationError(
                f"Export profile '{name}': "
                f"'allowed_charset' must be a string"
            )

        replace_char = data.get("replace_char", "_")
        if not isinstance(replace_char, str):
            raise ProfileValidationError(
                f"Export profile '{name}': 'replace_char' must be a string"
            )

        case_policy = data.get("case_policy", "preserve")
        if case_policy not in VALID_CASE_POLICIES:
            raise ProfileValidationError(
                f"Export profile '{name}': "
                f"invalid case_policy '{case_policy}', "
                f"must be one of {sorted(VALID_CASE_POLICIES)}"
            )

        path_sep_policy = data.get("path_sep_policy", "os")
        if path_sep_policy not in VALID_PATH_SEP_POLICIES:
            raise ProfileValidationError(
                f"Export profile '{name}': "
                f"invalid path_sep_policy '{path_sep_policy}', "
                f"must be one of {sorted(VALID_PATH_SEP_POLICIES)}"
            )

        on_violation = data.get("on_violation", "autofix")
        if on_violation not in VALID_ON_VIOLATION:
            raise ProfileValidationError(
                f"Export profile '{name}': "
                f"invalid on_violation '{on_violation}', "
                f"must be one of {sorted(VALID_ON_VIOLATION)}"
            )

        return cls(
            name=name,
            max_depth=max_depth,
            max_filename_len=max_filename_len,
            illegal_chars=illegal_chars,
            allowed_charset=allowed_charset,
            replace_char=replace_char,
            case_policy=case_policy,
            path_sep_policy=path_sep_policy,
            on_violation=on_violation,
        )

    def to_dict(self) -> dict:
        """Serialize to a plain dict (for JSON output)."""
        return asdict(self)


# ---------------------------------------------------------------------------
# Profiles directory resolution
# ---------------------------------------------------------------------------

def get_profiles_dir(config: dict | None = None) -> Path:
    """Resolve the profiles directory from config or default.

    Looks for ``profiles_dir`` key in the config dict.  Falls back to
    ``~/.sample_manager/profiles`` when absent or when *config* is None.
    """
    default = str(config_module.DEFAULT_CONFIG_DIR / "profiles")

    if config is None:
        return config_module.normalize_path(default)

    raw = config.get("profiles_dir", default)
    return config_module.normalize_path(str(raw))


# ---------------------------------------------------------------------------
# YAML file loaders
# ---------------------------------------------------------------------------

def _load_yaml_list(filepath: Path) -> list[dict]:
    """Load a YAML file expected to contain a list of dicts.

    Returns an empty list when the file does not exist or contains
    ``null`` / an empty document.

    Raises:
        ProfileValidationError: If the YAML content is not a list.
    """
    if not filepath.exists():
        return []

    with open(filepath, "r") as f:
        data = yaml.safe_load(f)

    if data is None:
        return []

    if not isinstance(data, list):
        raise ProfileValidationError(
            f"Expected a YAML list in {filepath}, got {type(data).__name__}"
        )

    return data


def _check_unique_names(profiles: list, kind: str) -> None:
    """Raise if any two profiles share the same name."""
    seen: dict[str, int] = {}
    for i, p in enumerate(profiles):
        if p.name in seen:
            raise ProfileValidationError(
                f"Duplicate {kind} profile name '{p.name}' "
                f"(entries {seen[p.name]} and {i})"
            )
        seen[p.name] = i


def load_arrangement_profiles(
    profiles_dir: Path | None = None,
) -> list[ArrangementProfile]:
    """Load arrangement profiles from ``arrangement_profiles.yaml``.

    Args:
        profiles_dir: Directory containing profile YAML files.
            If None, resolved via :func:`get_profiles_dir` (no config).

    Returns:
        List of validated ArrangementProfile instances.
        Empty list if the file does not exist.

    Raises:
        ProfileValidationError: On invalid file content or profile data.
    """
    if profiles_dir is None:
        profiles_dir = get_profiles_dir()

    filepath = profiles_dir / ARRANGEMENT_PROFILES_FILENAME
    raw_list = _load_yaml_list(filepath)

    profiles = [ArrangementProfile.from_dict(entry) for entry in raw_list]
    _check_unique_names(profiles, "arrangement")
    return profiles


def load_export_profiles(
    profiles_dir: Path | None = None,
) -> list[ExportProfile]:
    """Load export profiles from ``export_profiles.yaml``.

    Args:
        profiles_dir: Directory containing profile YAML files.
            If None, resolved via :func:`get_profiles_dir` (no config).

    Returns:
        List of validated ExportProfile instances.
        Empty list if the file does not exist.

    Raises:
        ProfileValidationError: On invalid file content or profile data.
    """
    if profiles_dir is None:
        profiles_dir = get_profiles_dir()

    filepath = profiles_dir / EXPORT_PROFILES_FILENAME
    raw_list = _load_yaml_list(filepath)

    profiles = [ExportProfile.from_dict(entry) for entry in raw_list]
    _check_unique_names(profiles, "export")
    return profiles


# ---------------------------------------------------------------------------
# Lookup helpers
# ---------------------------------------------------------------------------

def get_arrangement_profile(
    name: str,
    profiles_dir: Path | None = None,
) -> ArrangementProfile | None:
    """Look up an arrangement profile by name.

    Returns None if not found.
    """
    for p in load_arrangement_profiles(profiles_dir):
        if p.name == name:
            return p
    return None


def get_export_profile(
    name: str,
    profiles_dir: Path | None = None,
) -> ExportProfile | None:
    """Look up an export profile by name.

    Returns None if not found.
    """
    for p in load_export_profiles(profiles_dir):
        if p.name == name:
            return p
    return None


# ---------------------------------------------------------------------------
# Starter file creation
# ---------------------------------------------------------------------------

def create_example_profiles(profiles_dir: Path) -> tuple[Path, Path]:
    """Create starter profile YAML files in *profiles_dir*.

    Each file is written only if it does not already exist (idempotent).

    Returns:
        (arrangement_path, export_path) — paths of the created files.
    """
    profiles_dir.mkdir(parents=True, exist_ok=True)

    arr_path = profiles_dir / ARRANGEMENT_PROFILES_FILENAME
    if not arr_path.exists():
        arr_path.write_text(EXAMPLE_ARRANGEMENT_PROFILES_YAML)

    exp_path = profiles_dir / EXPORT_PROFILES_FILENAME
    if not exp_path.exists():
        exp_path.write_text(EXAMPLE_EXPORT_PROFILES_YAML)

    return arr_path, exp_path
