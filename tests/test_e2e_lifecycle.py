"""End-to-end lifecycle tests for the sampleman CLI.

Tests the full application lifecycle from ``sampleman init`` through export
and revert, using a valid WAV generated inside each test's temporary library.

Every test runs in a hermetic environment:
  - Isolated HOME   -> ~ expansions resolve inside tmp_path, not real home
  - Patched DEFAULT_CONFIG_DIR / DEFAULT_CONFIG_PATH -> module-level constants
    that are set at import time from Path.home() are redirected to tmp_path
  - Isolated SQLite DB inside tmp_path
  - Isolated export output directory inside tmp_path
  - The real ~/.sample_manager directory is never touched or read

Isolation approach follows the pattern established in test_arrangement_cli.py:
  monkeypatch.setenv("HOME", str(tmp_path))
  monkeypatch.setattr(config_module, "DEFAULT_CONFIG_DIR", ...)
  monkeypatch.setattr(config_module, "DEFAULT_CONFIG_PATH", ...)
"""

import json
import wave
from pathlib import Path

import pytest
import yaml

from sample_manager import config as config_module
from sample_manager.cli import app
from sample_manager.exit_codes import ERROR_INVALID_ARGS, ERROR_SAFETY_REFUSAL
from sample_manager.profiles import (
    ARRANGEMENT_PROFILES_FILENAME,
    EXPORT_PROFILES_FILENAME,
)

# ---------------------------------------------------------------------------
# Audio fixture
# ---------------------------------------------------------------------------


def _make_audio_fixture(tmp_path: Path) -> Path:
    """Create the one drum-loop WAV used by scan, search, and export tests.

    Generate it in the test directory so a fresh clone needs no ignored sample
    pack and concurrent test runs cannot change each other's source file.
    """
    root = tmp_path / "test_lib" / "Funky_Disco"
    audio_path = (
        root
        / "Function_Loops_-_Funky_Disco_repack"
        / "loops"
        / "FL_FDS_Drum_Loops"
        / "FL_FDS_09_Drum_Loop_Full_98.wav"
    )
    audio_path.parent.mkdir(parents=True)
    with wave.open(str(audio_path), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(8000)
        audio.writeframes(b"\x00\x00" * 800)
    return root


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _write_yaml(filepath: Path, data) -> None:
    """Write *data* as YAML to *filepath*, creating parents as needed."""
    filepath.parent.mkdir(parents=True, exist_ok=True)
    with open(filepath, "w") as f:
        yaml.safe_dump(data, f, default_flow_style=False)


def _write_profiles(profiles_dir: Path) -> None:
    """Populate *profiles_dir* with minimal valid arrangement and export profiles.

    ``sampleman init`` creates empty placeholder profile YAML files (``[]``).
    This helper overwrites them with profiles that the arrangement and export
    commands can actually use.
    """
    _write_yaml(
        profiles_dir / ARRANGEMENT_PROFILES_FILENAME,
        [
            {
                "name": "default-monolithic",
                "layout_mode": "monolithic",
                "naming_template": "{name}",
                "collision_policy": "suffix",
                "description": "Flat layout for E2E tests",
            }
        ],
    )
    _write_yaml(
        profiles_dir / EXPORT_PROFILES_FILENAME,
        [
            {
                "name": "default-export",
                "max_depth": 5,
                "max_filename_len": 128,
                "illegal_chars": '<>:"/\\|?*',
                "replace_char": "_",
                "case_policy": "preserve",
                "path_sep_policy": "posix",
                "on_violation": "autofix",
            }
        ],
    )


# ---------------------------------------------------------------------------
# E2E fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def e2e_env(tmp_path, monkeypatch):
    """Hermetic end-to-end environment for full-lifecycle tests.

    Sets up:
    - HOME env var redirected to tmp_path (so ~ expands here, not real home)
    - config_module.DEFAULT_CONFIG_DIR patched to tmp_path/.sample_manager
    - config_module.DEFAULT_CONFIG_PATH patched to the config.yaml inside it
    - One valid drum-loop WAV below tmp_path/test_lib/Funky_Disco
    - A CliRunner ready to invoke the sampleman app
    - Convenience paths for the config dir, profiles dir, and export output

    Why patch both HOME and the module constants?
    - ``DEFAULT_CONFIG_DIR`` and ``DEFAULT_CONFIG_PATH`` are evaluated once at
      module import time using ``Path.home()``.  Changing HOME afterward has
      no effect on them — the module attribute must be patched directly.
    - ``HOME`` must also be patched so that ``os.path.expanduser("~")`` inside
      ``normalize_path()`` resolves to tmp_path when the default config template
      (which stores ``db_path`` and ``profiles_dir`` as ``~/...`` strings) is
      subsequently loaded and normalized.
    """
    from typer.testing import CliRunner

    monkeypatch.setenv("HOME", str(tmp_path))

    config_dir = tmp_path / ".sample_manager"
    config_path = config_dir / "config.yaml"
    monkeypatch.setattr(config_module, "DEFAULT_CONFIG_DIR", config_dir)
    monkeypatch.setattr(config_module, "DEFAULT_CONFIG_PATH", config_path)
    funky_disco = _make_audio_fixture(tmp_path)

    return {
        "runner": CliRunner(),
        "tmp_path": tmp_path,
        "config_dir": config_dir,
        "config_path": config_path,
        "profiles_dir": config_dir / "profiles",
        "funky_disco": funky_disco,
        "export_dir": tmp_path / "exports",
    }


# ---------------------------------------------------------------------------
# Happy path: complete lifecycle in a single sequential test
# ---------------------------------------------------------------------------


class TestE2EHappyPath:
    """Full lifecycle exercised in one sequential test.

    Each assertion targets an observable output: files on disk, stdout text,
    or parsed JSON payload fields. Internal implementation details are not
    checked directly.
    """

    def test_full_lifecycle_from_init_to_revert(self, e2e_env):  # noqa: C901
        runner = e2e_env["runner"]
        config_path = e2e_env["config_path"]
        profiles_dir = e2e_env["profiles_dir"]
        funky_disco = e2e_env["funky_disco"]
        export_dir = e2e_env["export_dir"]

        # ------------------------------------------------------------------
        # Phase 1 — sampleman init
        # Creates config.yaml and the profiles directory with placeholder
        # profile YAML files.
        # ------------------------------------------------------------------
        result = runner.invoke(app, ["init"])
        assert result.exit_code == 0, f"init failed:\n{result.output}"
        assert config_path.exists(), "init did not create config.yaml"
        assert profiles_dir.exists(), "init did not create profiles/ directory"
        assert (profiles_dir / ARRANGEMENT_PROFILES_FILENAME).exists()
        assert (profiles_dir / EXPORT_PROFILES_FILENAME).exists()
        assert "Created config" in result.output

        # Replace init's empty placeholder files with valid profiles
        _write_profiles(profiles_dir)

        # ------------------------------------------------------------------
        # Phase 2 — sampleman config add-root
        # Registers the generated Funky_Disco fixture as a library root.
        # ------------------------------------------------------------------
        result = runner.invoke(app, ["config", "add-root", str(funky_disco)])
        assert result.exit_code == 0, f"config add-root failed:\n{result.output}"
        assert "Added" in result.output

        # Verify the root was persisted to config.yaml
        with open(config_path) as f:
            cfg_on_disk = yaml.safe_load(f)
        funky_disco_abs = str(funky_disco.resolve())
        assert any(
            funky_disco_abs in root
            for root in cfg_on_disk.get("library_roots", [])
        ), "Library root not saved to config.yaml"

        # ------------------------------------------------------------------
        # Phase 3 — sampleman scan
        # Walks Funky_Disco and inserts the single .wav into SQLite.
        # ------------------------------------------------------------------
        result = runner.invoke(app, ["scan", str(funky_disco)])
        assert result.exit_code == 0, f"scan failed:\n{result.output}"
        # The fixture contains exactly one .wav file
        assert "(inserted: 1," in result.output

        # Retrieve the sample via a JSON search (no filter = all samples)
        result = runner.invoke(app, ["search", "--json"])
        assert result.exit_code == 0
        browse = json.loads(result.output)
        assert browse["total"] == 1, "Expected exactly 1 sample after scan"
        sample = browse["items"][0]
        sample_id = sample["id"]
        assert sample["filename"].endswith(".wav")

        # ------------------------------------------------------------------
        # Phase 4 — sampleman tag add
        # Attaches the tag "drums" to the scanned sample.
        # ------------------------------------------------------------------
        result = runner.invoke(app, ["tag", "add", str(sample_id), "drums"])
        assert result.exit_code == 0, f"tag add failed:\n{result.output}"
        assert "drums" in result.output

        # ------------------------------------------------------------------
        # Phase 5 — sampleman search --tag
        # Confirms the tag filter returns the expected sample.
        # ------------------------------------------------------------------
        result = runner.invoke(app, ["search", "--tag", "drums", "--json"])
        assert result.exit_code == 0
        tag_result = json.loads(result.output)
        assert tag_result["total"] == 1
        assert tag_result["items"][0]["id"] == sample_id

        # ------------------------------------------------------------------
        # Phase 6 — sampleman selection add --from-search
        # Adds samples matching "drum" to the persistent selection buffer.
        # ------------------------------------------------------------------
        result = runner.invoke(app, ["selection", "add", "--from-search", "drum"])
        assert result.exit_code == 0, f"selection add failed:\n{result.output}"
        assert "added 1" in result.output

        # ------------------------------------------------------------------
        # Phase 7 — sampleman arrangement create --from-selection
        # Creates an arrangement from the current selection buffer.
        # ------------------------------------------------------------------
        result = runner.invoke(
            app,
            [
                "arrangement",
                "create",
                "Funky Set",
                "--profile",
                "default-monolithic",
                "--from-selection",
                "--json",
            ],
        )
        assert result.exit_code == 0, f"arrangement create failed:\n{result.output}"
        arr = json.loads(result.output)
        assert arr["name"] == "Funky Set"
        assert arr["profile_name"] == "default-monolithic"
        assert arr["samples_attached"] == 1

        # ------------------------------------------------------------------
        # Phase 8 — sampleman arrangement preview
        # Produces a deterministic export plan without writing any files.
        # ------------------------------------------------------------------
        result = runner.invoke(
            app,
            [
                "arrangement",
                "preview",
                "Funky Set",
                "--export-profile",
                "default-export",
                "--format",
                "json",
            ],
        )
        assert result.exit_code == 0, f"arrangement preview failed:\n{result.output}"
        plan = json.loads(result.output)
        assert plan["arrangement_name"] == "Funky Set"
        assert plan["export_profile_name"] == "default-export"
        assert plan["stats"]["operations"] == 1
        assert not plan["errors"], f"Plan has unexpected errors: {plan['errors']}"
        # Source path must point at the generated WAV inside this test's root.
        assert plan["operations"][0]["src_abs_path"].endswith(".wav")
        assert str(funky_disco.resolve()) in plan["operations"][0]["src_abs_path"]

        # ------------------------------------------------------------------
        # Phase 9 — sampleman export (real file copy)
        # Copies the .wav to export_dir and records the export run in the DB.
        # ------------------------------------------------------------------
        result = runner.invoke(
            app,
            [
                "export",
                "Funky Set",
                "--to",
                str(export_dir),
                "--export-profile",
                "default-export",
                "--confirm",
                "--json",
            ],
        )
        assert result.exit_code == 0, f"export failed:\n{result.output}"
        exp = json.loads(result.output)
        export_id = exp["export_id"]
        assert exp["operations"] == 1
        assert exp["failed"] == 0
        assert exp["dry_run"] is False

        # The .wav file must exist on disk inside export_dir
        exported_wavs = list(export_dir.rglob("*.wav"))
        assert len(exported_wavs) == 1, (
            f"Expected 1 exported .wav, got {len(exported_wavs)}: {exported_wavs}"
        )

        # ------------------------------------------------------------------
        # Phase 10 — sampleman revert
        # Removes the exported file and marks the export run as "reverted".
        # ------------------------------------------------------------------
        result = runner.invoke(
            app,
            [
                "revert",
                "--export-id",
                str(export_id),
                "--confirm",
                "--json",
            ],
        )
        assert result.exit_code == 0, f"revert failed:\n{result.output}"
        rev = json.loads(result.output)
        assert rev["result"]["export_id"] == export_id
        assert rev["result"]["reverted"] == 1
        assert rev["result"]["status"] == "reverted"
        assert rev["errors"] == []

        # The exported .wav must be gone from disk after revert
        remaining = list(export_dir.rglob("*.wav"))
        assert len(remaining) == 0, (
            f"Expected 0 .wav files after revert, got {len(remaining)}: {remaining}"
        )


# ---------------------------------------------------------------------------
# Edge cases and error paths
# ---------------------------------------------------------------------------


class TestE2EEdgeCases:
    """Targeted tests for error handling and boundary conditions."""

    def _init_with_profiles(self, runner, profiles_dir) -> None:
        """Run ``sampleman init`` and populate profiles — shared setup step."""
        result = runner.invoke(app, ["init"])
        assert result.exit_code == 0, f"init failed in helper: {result.output}"
        _write_profiles(profiles_dir)

    # -----------------------------------------------------------------------
    # Idempotency
    # -----------------------------------------------------------------------

    def test_init_is_idempotent(self, e2e_env):
        """Running sampleman init twice is safe and reports 'already exists'."""
        runner = e2e_env["runner"]

        first = runner.invoke(app, ["init"])
        assert first.exit_code == 0
        assert "Created config" in first.output

        second = runner.invoke(app, ["init"])
        assert second.exit_code == 0
        # Second run must not re-create — it reports the existing path
        assert "already exists" in second.output

    # -----------------------------------------------------------------------
    # Safety guard: export requires --confirm
    # -----------------------------------------------------------------------

    def test_export_without_confirm_is_refused(self, e2e_env):
        """Export without --confirm (and without --dry-run) exits ERROR_SAFETY_REFUSAL.

        No files should be written to the export directory.
        """
        runner = e2e_env["runner"]
        profiles_dir = e2e_env["profiles_dir"]
        funky_disco = e2e_env["funky_disco"]
        export_dir = e2e_env["export_dir"]

        self._init_with_profiles(runner, profiles_dir)

        # Scan so the DB has a sample
        r = runner.invoke(app, ["scan", str(funky_disco)])
        assert r.exit_code == 0, f"scan failed: {r.output}"

        # Retrieve sample id
        r = runner.invoke(app, ["search", "--json"])
        sample_id = json.loads(r.output)["items"][0]["id"]

        # Create an arrangement with that sample
        r = runner.invoke(
            app,
            [
                "arrangement",
                "create",
                "Guard Test",
                "--profile",
                "default-monolithic",
                "--from-ids",
                str(sample_id),
            ],
        )
        assert r.exit_code == 0, f"arrangement create failed: {r.output}"

        # Attempt export without --confirm (safety guard must fire)
        result = runner.invoke(
            app,
            [
                "export",
                "Guard Test",
                "--to",
                str(export_dir),
                "--export-profile",
                "default-export",
                # deliberately omitting --confirm and --dry-run
            ],
        )
        assert result.exit_code == ERROR_SAFETY_REFUSAL

        # No files should have been written
        all_created = list(export_dir.rglob("*")) if export_dir.exists() else []
        assert all_created == [], (
            f"Safety refusal should not write files; found: {all_created}"
        )

    # -----------------------------------------------------------------------
    # Scan: invalid path
    # -----------------------------------------------------------------------

    def test_scan_nonexistent_path_fails(self, e2e_env):
        """Scanning a directory that does not exist exits with ERROR_INVALID_ARGS."""
        runner = e2e_env["runner"]
        profiles_dir = e2e_env["profiles_dir"]

        self._init_with_profiles(runner, profiles_dir)

        result = runner.invoke(app, ["scan", "/no/such/path/e2e_test_fixture"])
        assert result.exit_code == ERROR_INVALID_ARGS
        # Error message must mention the missing path
        combined = (result.output or "") + (result.stderr if hasattr(result, "stderr") else "")
        assert "does not exist" in combined.lower() or "does not exist" in result.output.lower()

    # -----------------------------------------------------------------------
    # Arrangement: missing profile
    # -----------------------------------------------------------------------

    def test_arrangement_create_with_unknown_profile_fails(self, e2e_env):
        """Arrangement create with an unregistered profile name exits ERROR_INVALID_ARGS."""
        runner = e2e_env["runner"]
        profiles_dir = e2e_env["profiles_dir"]
        funky_disco = e2e_env["funky_disco"]

        self._init_with_profiles(runner, profiles_dir)

        # Scan so the DB is initialised (arrangement create needs a live DB)
        r = runner.invoke(app, ["scan", str(funky_disco)])
        assert r.exit_code == 0, f"scan failed: {r.output}"

        result = runner.invoke(
            app,
            [
                "arrangement",
                "create",
                "Bad Profile Set",
                "--profile",
                "profile-that-does-not-exist",
            ],
        )
        assert result.exit_code == ERROR_INVALID_ARGS
        assert "profile not found" in result.output
