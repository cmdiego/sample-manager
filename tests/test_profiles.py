"""Unit tests for the profiles loader module (Phase 6).

Tests cover:
- ArrangementProfile.from_dict validation (valid + invalid cases)
- ExportProfile.from_dict validation (valid + invalid cases)
- YAML file loading (present, missing, empty, malformed)
- Duplicate name detection
- Lookup helpers (get_arrangement_profile, get_export_profile)
- get_profiles_dir resolution (with and without config)
- Example profile creation (create_example_profiles)
"""

import pytest
import yaml
from pathlib import Path

from sample_manager.profiles import (
    ArrangementProfile,
    ExportProfile,
    ProfileValidationError,
    get_profiles_dir,
    load_arrangement_profiles,
    load_export_profiles,
    get_arrangement_profile,
    get_export_profile,
    create_example_profiles,
    ARRANGEMENT_PROFILES_FILENAME,
    EXPORT_PROFILES_FILENAME,
)
from sample_manager import config as config_module


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _valid_arrangement_dict(**overrides) -> dict:
    """Return a minimal valid arrangement profile dict."""
    base = {
        "name": "test-arr",
        "layout_mode": "monolithic",
        "naming_template": "{category}/{name}",
        "collision_policy": "suffix",
    }
    base.update(overrides)
    return base


def _valid_export_dict(**overrides) -> dict:
    """Return a minimal valid export profile dict."""
    base = {
        "name": "test-exp",
        "max_depth": 3,
        "max_filename_len": 64,
        "illegal_chars": '<>:"/\\|?*',
    }
    base.update(overrides)
    return base


@pytest.fixture
def profiles_dir(tmp_path):
    """Create an empty temporary profiles directory."""
    d = tmp_path / "profiles"
    d.mkdir()
    return d


def _write_yaml(filepath: Path, data):
    """Write data as YAML to filepath."""
    with open(filepath, "w") as f:
        yaml.safe_dump(data, f, default_flow_style=False)


# ---------------------------------------------------------------------------
# ArrangementProfile.from_dict — valid
# ---------------------------------------------------------------------------


class TestArrangementProfileValid:
    def test_minimal(self):
        d = _valid_arrangement_dict()
        p = ArrangementProfile.from_dict(d)
        assert p.name == "test-arr"
        assert p.layout_mode == "monolithic"
        assert p.naming_template == "{category}/{name}"
        assert p.collision_policy == "suffix"
        assert p.description is None
        assert p.layout_rules == {}
        assert p.selection_defaults is None

    def test_all_fields(self):
        d = _valid_arrangement_dict(
            description="Test desc",
            layout_rules={"category_map": {"kick": "KICKS"}},
            selection_defaults={"max_samples": 100},
        )
        p = ArrangementProfile.from_dict(d)
        assert p.description == "Test desc"
        assert p.layout_rules == {"category_map": {"kick": "KICKS"}}
        assert p.selection_defaults == {"max_samples": 100}

    def test_hierarchical_mode(self):
        d = _valid_arrangement_dict(layout_mode="hierarchical")
        p = ArrangementProfile.from_dict(d)
        assert p.layout_mode == "hierarchical"

    def test_all_collision_policies(self):
        for policy in ("fail", "suffix", "dedupe_hash"):
            d = _valid_arrangement_dict(collision_policy=policy)
            p = ArrangementProfile.from_dict(d)
            assert p.collision_policy == policy

    def test_to_dict_roundtrip(self):
        d = _valid_arrangement_dict(
            description="x",
            layout_rules={"a": 1},
            selection_defaults={"b": 2},
        )
        p = ArrangementProfile.from_dict(d)
        result = p.to_dict()
        assert result["name"] == "test-arr"
        assert result["layout_mode"] == "monolithic"
        assert result["description"] == "x"
        assert result["layout_rules"] == {"a": 1}
        assert result["selection_defaults"] == {"b": 2}


# ---------------------------------------------------------------------------
# ArrangementProfile.from_dict — invalid
# ---------------------------------------------------------------------------


class TestArrangementProfileInvalid:
    def test_not_a_dict(self):
        with pytest.raises(ProfileValidationError, match="must be a mapping"):
            ArrangementProfile.from_dict("not a dict")

    def test_missing_name(self):
        d = _valid_arrangement_dict()
        del d["name"]
        with pytest.raises(ProfileValidationError, match="'name'"):
            ArrangementProfile.from_dict(d)

    def test_empty_name(self):
        d = _valid_arrangement_dict(name="")
        with pytest.raises(ProfileValidationError, match="'name'"):
            ArrangementProfile.from_dict(d)

    def test_missing_layout_mode(self):
        d = _valid_arrangement_dict()
        del d["layout_mode"]
        with pytest.raises(ProfileValidationError, match="layout_mode"):
            ArrangementProfile.from_dict(d)

    def test_invalid_layout_mode(self):
        d = _valid_arrangement_dict(layout_mode="flat")
        with pytest.raises(ProfileValidationError, match="invalid layout_mode"):
            ArrangementProfile.from_dict(d)

    def test_missing_naming_template(self):
        d = _valid_arrangement_dict()
        del d["naming_template"]
        with pytest.raises(ProfileValidationError, match="naming_template"):
            ArrangementProfile.from_dict(d)

    def test_missing_collision_policy(self):
        d = _valid_arrangement_dict()
        del d["collision_policy"]
        with pytest.raises(ProfileValidationError, match="collision_policy"):
            ArrangementProfile.from_dict(d)

    def test_invalid_collision_policy(self):
        d = _valid_arrangement_dict(collision_policy="overwrite")
        with pytest.raises(
            ProfileValidationError, match="invalid collision_policy"
        ):
            ArrangementProfile.from_dict(d)

    def test_description_not_string(self):
        d = _valid_arrangement_dict(description=123)
        with pytest.raises(ProfileValidationError, match="description"):
            ArrangementProfile.from_dict(d)

    def test_layout_rules_not_dict(self):
        d = _valid_arrangement_dict(layout_rules="bad")
        with pytest.raises(ProfileValidationError, match="layout_rules"):
            ArrangementProfile.from_dict(d)

    def test_selection_defaults_not_dict(self):
        d = _valid_arrangement_dict(selection_defaults=[1, 2])
        with pytest.raises(ProfileValidationError, match="selection_defaults"):
            ArrangementProfile.from_dict(d)


# ---------------------------------------------------------------------------
# ExportProfile.from_dict — valid
# ---------------------------------------------------------------------------


class TestExportProfileValid:
    def test_minimal(self):
        d = _valid_export_dict()
        p = ExportProfile.from_dict(d)
        assert p.name == "test-exp"
        assert p.max_depth == 3
        assert p.max_filename_len == 64
        assert p.illegal_chars == '<>:"/\\|?*'
        # Defaults
        assert p.allowed_charset is None
        assert p.replace_char == "_"
        assert p.case_policy == "preserve"
        assert p.path_sep_policy == "os"
        assert p.on_violation == "autofix"

    def test_all_fields(self):
        d = _valid_export_dict(
            allowed_charset="a-zA-Z0-9_-",
            replace_char="-",
            case_policy="lower",
            path_sep_policy="posix",
            on_violation="fail",
        )
        p = ExportProfile.from_dict(d)
        assert p.allowed_charset == "a-zA-Z0-9_-"
        assert p.replace_char == "-"
        assert p.case_policy == "lower"
        assert p.path_sep_policy == "posix"
        assert p.on_violation == "fail"

    def test_all_case_policies(self):
        for cp in ("preserve", "lower", "upper"):
            d = _valid_export_dict(case_policy=cp)
            p = ExportProfile.from_dict(d)
            assert p.case_policy == cp

    def test_to_dict_roundtrip(self):
        d = _valid_export_dict(
            allowed_charset="abc",
            replace_char="~",
            case_policy="upper",
            path_sep_policy="posix",
            on_violation="fail",
        )
        p = ExportProfile.from_dict(d)
        result = p.to_dict()
        assert result["name"] == "test-exp"
        assert result["max_depth"] == 3
        assert result["max_filename_len"] == 64
        assert result["replace_char"] == "~"
        assert result["case_policy"] == "upper"


# ---------------------------------------------------------------------------
# ExportProfile.from_dict — invalid
# ---------------------------------------------------------------------------


class TestExportProfileInvalid:
    def test_not_a_dict(self):
        with pytest.raises(ProfileValidationError, match="must be a mapping"):
            ExportProfile.from_dict(42)

    def test_missing_name(self):
        d = _valid_export_dict()
        del d["name"]
        with pytest.raises(ProfileValidationError, match="'name'"):
            ExportProfile.from_dict(d)

    def test_missing_max_depth(self):
        d = _valid_export_dict()
        del d["max_depth"]
        with pytest.raises(ProfileValidationError, match="max_depth"):
            ExportProfile.from_dict(d)

    def test_max_depth_zero(self):
        d = _valid_export_dict(max_depth=0)
        with pytest.raises(ProfileValidationError, match="max_depth.*>= 1"):
            ExportProfile.from_dict(d)

    def test_max_depth_negative(self):
        d = _valid_export_dict(max_depth=-1)
        with pytest.raises(ProfileValidationError, match="max_depth.*>= 1"):
            ExportProfile.from_dict(d)

    def test_max_depth_not_int(self):
        d = _valid_export_dict(max_depth="three")
        with pytest.raises(ProfileValidationError, match="max_depth.*integer"):
            ExportProfile.from_dict(d)

    def test_max_depth_bool(self):
        """bool is a subclass of int but should be rejected."""
        d = _valid_export_dict(max_depth=True)
        with pytest.raises(ProfileValidationError, match="max_depth.*integer"):
            ExportProfile.from_dict(d)

    def test_missing_max_filename_len(self):
        d = _valid_export_dict()
        del d["max_filename_len"]
        with pytest.raises(ProfileValidationError, match="max_filename_len"):
            ExportProfile.from_dict(d)

    def test_max_filename_len_zero(self):
        d = _valid_export_dict(max_filename_len=0)
        with pytest.raises(
            ProfileValidationError, match="max_filename_len.*>= 1"
        ):
            ExportProfile.from_dict(d)

    def test_missing_illegal_chars(self):
        d = _valid_export_dict()
        del d["illegal_chars"]
        with pytest.raises(ProfileValidationError, match="illegal_chars"):
            ExportProfile.from_dict(d)

    def test_illegal_chars_not_string(self):
        d = _valid_export_dict(illegal_chars=123)
        with pytest.raises(
            ProfileValidationError, match="illegal_chars.*string"
        ):
            ExportProfile.from_dict(d)

    def test_invalid_case_policy(self):
        d = _valid_export_dict(case_policy="camelCase")
        with pytest.raises(
            ProfileValidationError, match="invalid case_policy"
        ):
            ExportProfile.from_dict(d)

    def test_invalid_path_sep_policy(self):
        d = _valid_export_dict(path_sep_policy="windows")
        with pytest.raises(
            ProfileValidationError, match="invalid path_sep_policy"
        ):
            ExportProfile.from_dict(d)

    def test_invalid_on_violation(self):
        d = _valid_export_dict(on_violation="warn")
        with pytest.raises(
            ProfileValidationError, match="invalid on_violation"
        ):
            ExportProfile.from_dict(d)

    def test_allowed_charset_not_string(self):
        d = _valid_export_dict(allowed_charset=999)
        with pytest.raises(
            ProfileValidationError, match="allowed_charset.*string"
        ):
            ExportProfile.from_dict(d)

    def test_replace_char_not_string(self):
        d = _valid_export_dict(replace_char=0)
        with pytest.raises(
            ProfileValidationError, match="replace_char.*string"
        ):
            ExportProfile.from_dict(d)


# ---------------------------------------------------------------------------
# YAML loading — arrangement profiles
# ---------------------------------------------------------------------------


class TestLoadArrangementProfiles:
    def test_load_valid_file(self, profiles_dir):
        data = [
            _valid_arrangement_dict(name="arr-1"),
            _valid_arrangement_dict(name="arr-2", layout_mode="hierarchical"),
        ]
        _write_yaml(profiles_dir / ARRANGEMENT_PROFILES_FILENAME, data)
        profiles = load_arrangement_profiles(profiles_dir)
        assert len(profiles) == 2
        assert profiles[0].name == "arr-1"
        assert profiles[1].name == "arr-2"
        assert profiles[1].layout_mode == "hierarchical"

    def test_missing_file_returns_empty(self, profiles_dir):
        profiles = load_arrangement_profiles(profiles_dir)
        assert profiles == []

    def test_empty_file_returns_empty(self, profiles_dir):
        (profiles_dir / ARRANGEMENT_PROFILES_FILENAME).write_text("")
        profiles = load_arrangement_profiles(profiles_dir)
        assert profiles == []

    def test_yaml_with_null_returns_empty(self, profiles_dir):
        (profiles_dir / ARRANGEMENT_PROFILES_FILENAME).write_text("null\n")
        profiles = load_arrangement_profiles(profiles_dir)
        assert profiles == []

    def test_yaml_with_empty_list(self, profiles_dir):
        _write_yaml(profiles_dir / ARRANGEMENT_PROFILES_FILENAME, [])
        profiles = load_arrangement_profiles(profiles_dir)
        assert profiles == []

    def test_not_a_list_raises(self, profiles_dir):
        (profiles_dir / ARRANGEMENT_PROFILES_FILENAME).write_text(
            "name: oops\n"
        )
        with pytest.raises(ProfileValidationError, match="Expected a YAML list"):
            load_arrangement_profiles(profiles_dir)

    def test_invalid_entry_raises(self, profiles_dir):
        data = [_valid_arrangement_dict(), {"bad": "entry"}]
        _write_yaml(profiles_dir / ARRANGEMENT_PROFILES_FILENAME, data)
        with pytest.raises(ProfileValidationError):
            load_arrangement_profiles(profiles_dir)

    def test_duplicate_names_raises(self, profiles_dir):
        data = [
            _valid_arrangement_dict(name="dup"),
            _valid_arrangement_dict(name="dup"),
        ]
        _write_yaml(profiles_dir / ARRANGEMENT_PROFILES_FILENAME, data)
        with pytest.raises(ProfileValidationError, match="Duplicate"):
            load_arrangement_profiles(profiles_dir)


# ---------------------------------------------------------------------------
# YAML loading — export profiles
# ---------------------------------------------------------------------------


class TestLoadExportProfiles:
    def test_load_valid_file(self, profiles_dir):
        data = [
            _valid_export_dict(name="exp-1"),
            _valid_export_dict(name="exp-2", max_depth=5),
        ]
        _write_yaml(profiles_dir / EXPORT_PROFILES_FILENAME, data)
        profiles = load_export_profiles(profiles_dir)
        assert len(profiles) == 2
        assert profiles[0].name == "exp-1"
        assert profiles[1].max_depth == 5

    def test_missing_file_returns_empty(self, profiles_dir):
        profiles = load_export_profiles(profiles_dir)
        assert profiles == []

    def test_empty_file_returns_empty(self, profiles_dir):
        (profiles_dir / EXPORT_PROFILES_FILENAME).write_text("")
        profiles = load_export_profiles(profiles_dir)
        assert profiles == []

    def test_not_a_list_raises(self, profiles_dir):
        (profiles_dir / EXPORT_PROFILES_FILENAME).write_text("key: val\n")
        with pytest.raises(ProfileValidationError, match="Expected a YAML list"):
            load_export_profiles(profiles_dir)

    def test_duplicate_names_raises(self, profiles_dir):
        data = [
            _valid_export_dict(name="dup"),
            _valid_export_dict(name="dup"),
        ]
        _write_yaml(profiles_dir / EXPORT_PROFILES_FILENAME, data)
        with pytest.raises(ProfileValidationError, match="Duplicate"):
            load_export_profiles(profiles_dir)


# ---------------------------------------------------------------------------
# Lookup helpers
# ---------------------------------------------------------------------------


class TestLookupHelpers:
    def test_get_arrangement_profile_found(self, profiles_dir):
        data = [
            _valid_arrangement_dict(name="alpha"),
            _valid_arrangement_dict(name="beta"),
        ]
        _write_yaml(profiles_dir / ARRANGEMENT_PROFILES_FILENAME, data)
        p = get_arrangement_profile("beta", profiles_dir)
        assert p is not None
        assert p.name == "beta"

    def test_get_arrangement_profile_not_found(self, profiles_dir):
        data = [_valid_arrangement_dict(name="alpha")]
        _write_yaml(profiles_dir / ARRANGEMENT_PROFILES_FILENAME, data)
        assert get_arrangement_profile("nope", profiles_dir) is None

    def test_get_arrangement_profile_missing_file(self, profiles_dir):
        assert get_arrangement_profile("any", profiles_dir) is None

    def test_get_export_profile_found(self, profiles_dir):
        data = [
            _valid_export_dict(name="exp-a"),
            _valid_export_dict(name="exp-b"),
        ]
        _write_yaml(profiles_dir / EXPORT_PROFILES_FILENAME, data)
        p = get_export_profile("exp-b", profiles_dir)
        assert p is not None
        assert p.name == "exp-b"

    def test_get_export_profile_not_found(self, profiles_dir):
        data = [_valid_export_dict(name="exp-a")]
        _write_yaml(profiles_dir / EXPORT_PROFILES_FILENAME, data)
        assert get_export_profile("nope", profiles_dir) is None


# ---------------------------------------------------------------------------
# get_profiles_dir
# ---------------------------------------------------------------------------


class TestGetProfilesDir:
    def test_no_config_uses_default(self, monkeypatch, tmp_path):
        monkeypatch.setattr(
            config_module, "DEFAULT_CONFIG_DIR", tmp_path / ".sample_manager"
        )
        result = get_profiles_dir()
        expected = (tmp_path / ".sample_manager" / "profiles").resolve()
        assert result == expected

    def test_config_with_profiles_dir(self, tmp_path):
        cfg = {"profiles_dir": str(tmp_path / "my_profiles")}
        result = get_profiles_dir(cfg)
        assert result == (tmp_path / "my_profiles").resolve()

    def test_config_without_key_uses_default(self, monkeypatch, tmp_path):
        monkeypatch.setattr(
            config_module, "DEFAULT_CONFIG_DIR", tmp_path / ".sample_manager"
        )
        result = get_profiles_dir({})
        expected = (tmp_path / ".sample_manager" / "profiles").resolve()
        assert result == expected

    def test_config_with_tilde(self, monkeypatch, tmp_path):
        monkeypatch.setenv("HOME", str(tmp_path))
        # Windows expands ~ from USERPROFILE rather than HOME.
        monkeypatch.setenv("USERPROFILE", str(tmp_path))
        cfg = {"profiles_dir": "~/my_profiles"}
        result = get_profiles_dir(cfg)
        assert result == (tmp_path / "my_profiles").resolve()


# ---------------------------------------------------------------------------
# create_example_profiles
# ---------------------------------------------------------------------------


class TestCreateExampleProfiles:
    def test_creates_files(self, tmp_path):
        pdir = tmp_path / "profiles"
        arr_path, exp_path = create_example_profiles(pdir)

        assert pdir.exists()
        assert arr_path.exists()
        assert exp_path.exists()
        assert arr_path.name == ARRANGEMENT_PROFILES_FILENAME
        assert exp_path.name == EXPORT_PROFILES_FILENAME

    def test_files_are_valid_yaml(self, tmp_path):
        pdir = tmp_path / "profiles"
        create_example_profiles(pdir)

        # Both should parse as valid YAML
        arr_data = yaml.safe_load(
            (pdir / ARRANGEMENT_PROFILES_FILENAME).read_text()
        )
        exp_data = yaml.safe_load(
            (pdir / EXPORT_PROFILES_FILENAME).read_text()
        )

        # Default content is an empty list
        assert arr_data == []
        assert exp_data == []

    def test_loadable_after_creation(self, tmp_path):
        pdir = tmp_path / "profiles"
        create_example_profiles(pdir)

        # Should load without errors (empty lists)
        assert load_arrangement_profiles(pdir) == []
        assert load_export_profiles(pdir) == []

    def test_idempotent(self, tmp_path):
        pdir = tmp_path / "profiles"
        create_example_profiles(pdir)

        # Write custom content
        custom = [_valid_arrangement_dict(name="custom")]
        _write_yaml(pdir / ARRANGEMENT_PROFILES_FILENAME, custom)

        # Second call should NOT overwrite existing
        create_example_profiles(pdir)
        profiles = load_arrangement_profiles(pdir)
        assert len(profiles) == 1
        assert profiles[0].name == "custom"

    def test_creates_directory(self, tmp_path):
        pdir = tmp_path / "nested" / "deep" / "profiles"
        create_example_profiles(pdir)
        assert pdir.is_dir()
