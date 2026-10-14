---
name: project-test-infrastructure
description: Core facts about sampleman's test framework, isolation strategy, and key gotchas for writing CLI tests
metadata:
  type: project
---

## Test framework and entry points

- **Framework**: pytest 9.x, defined in `pyproject.toml` (`testpaths = ["tests"]`)
- **CLI runner**: `typer.testing.CliRunner` — captures stdout+stderr mixed into `result.output`
- **CLI entry point**: `from sample_manager.cli import app`
- **Tests live in**: `tests/` (flat, no subdirs)
- **Conftest**: `tests/conftest.py` provides `db`, `tmp_home`, `tmp_config_dir`, `cli_runner`, `sample_config_path`, `sample_library_root`

## Isolation strategy — critical gotcha

`DEFAULT_CONFIG_DIR` and `DEFAULT_CONFIG_PATH` in `src/sample_manager/config.py` are **module-level constants evaluated at import time** using `Path.home()`. Patching `HOME` env var afterward has no effect on them.

To fully isolate a test from the real `~/.sample_manager`, three patches are required:

```python
monkeypatch.setenv("HOME", str(tmp_path))                                   # 1
monkeypatch.setattr(config_module, "DEFAULT_CONFIG_DIR", config_dir)        # 2
monkeypatch.setattr(config_module, "DEFAULT_CONFIG_PATH", config_path)      # 3
```

Patch 1 makes `os.path.expanduser("~")` resolve to tmp_path, so the default
config template's `db_path: ~/.sample_manager/...` and `profiles_dir: ~/.sample_manager/...`
expand correctly when loaded and normalized.

Patches 2 & 3 make `get_config_path()` and `load_config()` (no-arg form) point to tmp_path.

**Why:** `test_cli.py` only does patch 3, which means `create_example_profiles()` inside
`init` writes to the *real* `~/.sample_manager/profiles`. That's a pre-existing isolation
leak that doesn't affect test correctness because the files are idempotent, but the e2e
tests fix it by applying all three patches.

## DB creation flow

`_get_db()` in `cli.py`:
1. `get_config_path()` → returns `DEFAULT_CONFIG_PATH`
2. `load_config()` → parses YAML from that path
3. `normalize_config(cfg)` → expands `~` in `db_path`  (uses `os.path.expanduser`)
4. Opens `Db(db_path)` → creates SQLite if absent
5. Calls `apply_migrations(db)` → idempotent; safe to call on every command

**Why:** The DB path is stored as `~/.sample_manager/sample_manager.sqlite3` in the
default config template. With HOME patched, this expands to `tmp_path/.sample_manager/...`.

## Profile loading

`init` creates empty placeholder profile files (`[]`). Tests that need working
arrangement/export profiles must overwrite them after calling `init`:

```python
_write_yaml(profiles_dir / ARRANGEMENT_PROFILES_FILENAME, [...])
_write_yaml(profiles_dir / EXPORT_PROFILES_FILENAME, [...])
```

Minimum valid arrangement profile: `name`, `layout_mode`, `naming_template`, `collision_policy`.
Minimum valid export profile: `name`, `max_depth`, `max_filename_len`, `illegal_chars`.

## audio fixture

`test_lib/Funky_Disco/` contains exactly **one real .wav file**:
`Function_Loops_-_Funky_Disco_repack/loops/FL_FDS_Drum_Loops/FL_FDS_09_Drum_Loop_Full_98.wav`

Scanning `test_lib/Funky_Disco/` should always report `inserted: 1` on first run.
The `src_abs_path` in export plans points to this real file and gets copied during
non-dry-run exports.

## Exit codes

Defined in `exit_codes.py`:
- 0 SUCCESS
- 1 ERROR_GENERAL
- 2 ERROR_INVALID_ARGS
- 3 ERROR_SAFETY_REFUSAL
- 4 ERROR_CONSTRAINT_VIOLATION
- 5 ERROR_PARTIAL_OPERATION
- 6 ERROR_CONFIG_VALIDATION

## JSON output pattern

Commands with `--json` use `print(json.dumps(...))` (not `typer.echo`). Both go to
`result.output` in CliRunner (stdout+stderr mixed). `json.loads(result.output)` works
because `json.loads` tolerates leading/trailing whitespace.

**Why:** Confirmed by reading cli.py and arrangement_commands.py; consistent with how
`test_arrangement_cli.py` tests JSON output.
